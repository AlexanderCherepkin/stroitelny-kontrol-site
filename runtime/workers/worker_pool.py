from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .context_isolator import ContextIsolator, ContextBudget


class WorkerStatus(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class WorkerJob:
    """A job dispatched to an isolated worker."""
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    agent_path: str = ""
    agent_spec: dict[str, Any] = field(default_factory=dict)
    inputs: dict[str, Any] = field(default_factory=dict)
    task_category: str = "read"
    complexity: str = "normal"
    max_tokens: int = 4096
    timeout_ms: int = 60_000
    priority: int = 5  # lower number = higher priority (1..10)

    def __lt__(self, other: WorkerJob) -> bool:
        return self.priority < other.priority


@dataclass
class WorkerResult:
    """Summary returned by worker — parent sees ONLY this, not raw data."""
    job_id: str = ""
    worker_id: str = ""
    status: str = "ok"
    summary: str = ""
    parsed_output: dict[str, Any] = field(default_factory=dict)
    tokens_used: int = 0
    latency_ms: float = 0
    model: str = ""
    error: str = ""

    @property
    def is_success(self) -> bool:
        return self.status == "ok" and not self.error

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "worker_id": self.worker_id,
            "status": self.status,
            "summary": self.summary,
            "parsed_output": self.parsed_output,
            "tokens_used": self.tokens_used,
            "latency_ms": self.latency_ms,
            "model": self.model,
        }


class WorkerPool:
    """Pool of isolated worker processes for agent execution.

    Each worker runs in a separate subprocess. Raw tool output stays
    inside the worker. Only a JSON summary returns to the parent process,
    keeping the main context window clean.

    Architecture:
      Parent (PipelineRunner)
        |-> WorkerPool.dispatch(job)
              |-> asyncio.subprocess (isolated)
                    |-> worker.py reads agent spec + inputs
                    |-> worker.py calls LLM or executes locally
                    |-> worker.py returns ONLY JSON summary
              |<- WorkerResult (compact summary)
      Parent continues with clean context
    """

    DEFAULT_WORKER_SCRIPT = Path(__file__).resolve().parent / "worker.py"

    def __init__(self, max_workers: int = 4, worker_script: str | Path | None = None,
                 isolator: ContextIsolator | None = None, max_queue_size: int = 100):
        self.max_workers = max_workers
        self.max_queue_size = max_queue_size
        self.worker_script = Path(worker_script) if worker_script else self.DEFAULT_WORKER_SCRIPT
        self.isolator = isolator or ContextIsolator()

        self._workers: dict[str, dict[str, Any]] = {}  # worker_id -> {process, status, job}
        self._queue: asyncio.PriorityQueue[WorkerJob] = asyncio.PriorityQueue()
        self._results: dict[str, WorkerResult] = {}
        self._running = False
        self._dispatch_task: asyncio.Task[Any] | None = None

        # Stats
        self.total_jobs = 0
        self.rejected_jobs = 0
        self.total_tokens_saved = 0  # Tokens NOT loaded into parent context

    async def start(self):
        self._running = True
        self._dispatch_task = asyncio.create_task(self._dispatcher_loop())

    async def stop(self):
        self._running = False
        if self._dispatch_task:
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass
        # Cancel all running workers
        for worker_id, info in list(self._workers.items()):
            proc = info.get("process")
            if proc and proc.returncode is None:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
        self._workers.clear()

    async def dispatch(self, job: WorkerJob) -> WorkerResult:
        """Dispatch a job to a worker. Returns summary when done.

        Backpressure: if queue is at max capacity, job is rejected immediately.
        """
        if self._queue.qsize() >= self.max_queue_size:
            self.rejected_jobs += 1
            return WorkerResult(
                job_id=job.job_id,
                status="rejected",
                error=f"Queue full ({self.max_queue_size}) — job rejected",
            )
        self.total_jobs += 1
        await self._queue.put(job)

        # Wait for result (with timeout)
        deadline = time.time() + job.timeout_ms / 1000
        while time.time() < deadline:
            if job.job_id in self._results:
                result = self._results.pop(job.job_id)
                self.total_tokens_saved += self._estimate_saved_tokens(result)
                return result
            await asyncio.sleep(0.05)

        # Timeout
        return WorkerResult(
            job_id=job.job_id,
            status="timeout",
            error=f"Job timed out after {job.timeout_ms}ms",
        )

    async def _dispatcher_loop(self):
        """Main loop: pick jobs from queue, assign to free workers or spawn new ones."""
        while self._running:
            try:
                job = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            # Find free worker or create new one
            worker_id = self._find_free_worker()
            if not worker_id and len(self._workers) < self.max_workers:
                worker_id = await self._spawn_worker()

            if not worker_id:
                # All workers busy — requeue and wait
                await self._queue.put(job)
                await asyncio.sleep(0.1)
                continue

            # Execute job in worker
            asyncio.create_task(self._execute_in_worker(worker_id, job))

    async def _execute_in_worker(self, worker_id: str, job: WorkerJob):
        """Run a job in a specific worker process."""
        info = self._workers.get(worker_id)
        if not info:
            return

        info["status"] = WorkerStatus.BUSY
        info["job"] = job

        # Create isolated context for this invocation
        self.isolator.create_context(worker_id, job.task_category, job.complexity)
        model = self.isolator.get_model_for_task(job.task_category)
        budget = self.isolator.get_budget_for_complexity(job.complexity)

        # Serialize job to JSON for the worker process
        job_payload = {
            "worker_id": worker_id,
            "agent_spec": job.agent_spec,
            "inputs": job.inputs,
            "max_tokens": budget.max_output_tokens if budget else job.max_tokens,
            "model": model,
        }

        try:
            # Sanitized environment: only pass through safe variables.
            # API keys are NOT passed in the job payload; the worker reads
            # them from its own environment if needed. We strip everything
            # except PATH, Python path, and locale to minimize leakage.
            safe_env = {
                k: v for k, v in os.environ.items()
                if k in ('PATH', 'PYTHONPATH', 'PYTHONHOME', 'SYSTEMROOT',
                         'TEMP', 'TMP', 'LANG', 'LC_ALL', 'HOME', 'USERPROFILE',
                         'PATHEXT', 'COMPUTERNAME', 'NUMBER_OF_PROCESSORS')
                or k.startswith('PYTHON')
            }

            proc = await asyncio.create_subprocess_exec(
                sys.executable, str(self.worker_script),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=safe_env,
            )

            info["process"] = proc

            # Send job to worker via stdin
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(input=json.dumps(job_payload, ensure_ascii=False).encode("utf-8")),
                    timeout=job.timeout_ms / 1000,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                self._store_result(job.job_id, WorkerResult(
                    job_id=job.job_id, worker_id=worker_id, status="timeout",
                    error="Worker process timed out",
                ))
                info["status"] = WorkerStatus.TIMEOUT
                return

            # Parse worker's JSON summary — this is ALL the parent sees
            stdout_text = stdout.decode("utf-8", errors="replace").strip() if stdout else ""
            stderr_text = stderr.decode("utf-8", errors="replace").strip() if stderr else ""

            if proc.returncode != 0 or not stdout_text:
                self._store_result(job.job_id, WorkerResult(
                    job_id=job.job_id, worker_id=worker_id, status="error",
                    error=stderr_text or f"Worker exited with code {proc.returncode}",
                ))
                info["status"] = WorkerStatus.ERROR
                return

            try:
                worker_output = json.loads(stdout_text)
            except json.JSONDecodeError:
                worker_output = {"status": "error", "error": f"Invalid JSON from worker: {stdout_text[:200]}"}

            result = WorkerResult(
                job_id=job.job_id,
                worker_id=worker_id,
                status=worker_output.get("status", "error"),
                summary=worker_output.get("summary", ""),
                parsed_output=worker_output.get("parsed_output", worker_output.get("parsed", {})),
                tokens_used=worker_output.get("tokens_used", 0),
                latency_ms=worker_output.get("latency_ms", 0),
                model=worker_output.get("model", model),
                error=worker_output.get("error", ""),
            )

            self._store_result(job.job_id, result)

        except Exception as e:
            self._store_result(job.job_id, WorkerResult(
                job_id=job.job_id, worker_id=worker_id, status="error", error=str(e),
            ))
            info["status"] = WorkerStatus.ERROR
        finally:
            info["status"] = WorkerStatus.IDLE
            info["job"] = None
            self.isolator.destroy_context(worker_id)

    async def _spawn_worker(self) -> str:
        """Spawn a new worker slot."""
        worker_id = f"worker_{uuid.uuid4().hex[:8]}"
        self._workers[worker_id] = {
            "id": worker_id,
            "status": WorkerStatus.IDLE,
            "process": None,
            "job": None,
            "created_at": time.time(),
        }
        return worker_id

    def _find_free_worker(self) -> str | None:
        for worker_id, info in self._workers.items():
            if info["status"] == WorkerStatus.IDLE:
                return worker_id
        return None

    def _store_result(self, job_id: str, result: WorkerResult):
        self._results[job_id] = result

    def _estimate_saved_tokens(self, result: WorkerResult) -> int:
        """Estimate how many tokens were kept OUT of the parent context."""
        # A full agent response could be 4000+ tokens. The summary is ~200 tokens.
        # We saved roughly: 4000 - len(summary) tokens
        summary_tokens = len(result.summary) // 4
        return max(0, 4000 - summary_tokens)

    @property
    def busy_workers(self) -> int:
        return sum(1 for w in self._workers.values() if w["status"] == WorkerStatus.BUSY)

    @property
    def idle_workers(self) -> int:
        return sum(1 for w in self._workers.values() if w["status"] == WorkerStatus.IDLE)

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "total_jobs": self.total_jobs,
            "rejected_jobs": self.rejected_jobs,
            "active_workers": len(self._workers),
            "busy": self.busy_workers,
            "idle": self.idle_workers,
            "tokens_saved": self.total_tokens_saved,
            "queue_depth": self._queue.qsize(),
            "queue_limit": self.max_queue_size,
        }
