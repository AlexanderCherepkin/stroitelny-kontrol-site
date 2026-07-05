# Community 45

> 18 nodes

## Key Concepts

- **worker.py** (11 connections) — `runtime/workers/worker.py`
- **Any** (9 connections) — `runtime/workers/worker.py`
- **execute_agent()** (9 connections) — `runtime/workers/worker.py`
- **call_llm_api()** (6 connections) — `runtime/workers/worker.py`
- **run_worker()** (6 connections) — `runtime/workers/worker.py`
- **build_result_summary()** (4 connections) — `runtime/workers/worker.py`
- **execute_locally()** (4 connections) — `runtime/workers/worker.py`
- **build_system_prompt()** (3 connections) — `runtime/workers/worker.py`
- **build_user_message()** (3 connections) — `runtime/workers/worker.py`
- **extract_json()** (3 connections) — `runtime/workers/worker.py`
- **write_error()** (3 connections) — `runtime/workers/worker.py`
- **write_summary()** (3 connections) — `runtime/workers/worker.py`
- **_get_api_key()** (2 connections) — `runtime/workers/worker.py`
- **Call LLM API and extract summary from response.** (1 connections) — `runtime/workers/worker.py`
- **Build a compact summary — this is ALL the parent process sees.** (1 connections) — `runtime/workers/worker.py`
- **Main entry point for worker process. Reads job, executes, writes summary.** (1 connections) — `runtime/workers/worker.py`
- **Execute agent spec via LLM API. Returns summary only — raw data stays in process** (1 connections) — `runtime/workers/worker.py`
- **Execute decision flow locally without LLM — extract structured result.** (1 connections) — `runtime/workers/worker.py`

## Relationships

- [[Community 24]] (1 shared connections)

## Source Files

- `runtime/workers/worker.py`

## Audit Trail

- EXTRACTED: 70 (99%)
- INFERRED: 1 (1%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*