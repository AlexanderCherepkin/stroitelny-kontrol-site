from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class AuditEventType(str, Enum):
    AGENT_INVOKED = "agent_invoked"
    AGENT_COMPLETED = "agent_completed"
    AGENT_FAILED = "agent_failed"
    SAFETY_CHECK = "safety_check"
    SAFETY_BLOCKED = "safety_blocked"
    PIPELINE_START = "pipeline_start"
    PIPELINE_END = "pipeline_end"
    STATE_CHANGE = "state_change"
    MESSAGE_SENT = "message_sent"
    ERROR = "error"
    HUMAN_OVERSIGHT = "human_oversight"


@dataclass
class AuditEvent:
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    event_type: AuditEventType = AuditEventType.AGENT_INVOKED
    timestamp: float = field(default_factory=time.time)
    agent_path: str = ""
    session_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    result: str = ""


class AuditLogger:
    def __init__(self, log_dir: str | Path = "./logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._buffer: list[AuditEvent] = []
        self._max_buffer = 100

    def log(self, event: AuditEvent):
        self._buffer.append(event)
        if len(self._buffer) >= self._max_buffer:
            self.flush()

    def log_agent_invoked(self, agent_path: str, session_id: str, inputs: dict[str, Any]):
        self.log(AuditEvent(
            event_type=AuditEventType.AGENT_INVOKED,
            agent_path=agent_path,
            session_id=session_id,
            payload={"inputs": self._sanitize(inputs)},
        ))

    def log_agent_completed(self, agent_path: str, session_id: str, outputs: dict[str, Any] | None, latency_ms: float):
        self.log(AuditEvent(
            event_type=AuditEventType.AGENT_COMPLETED,
            agent_path=agent_path,
            session_id=session_id,
            payload={"outputs": self._sanitize(outputs), "latency_ms": latency_ms},
        ))

    def log_agent_failed(self, agent_path: str, session_id: str, error: str):
        self.log(AuditEvent(
            event_type=AuditEventType.AGENT_FAILED,
            agent_path=agent_path,
            session_id=session_id,
            payload={"error": error},
        ))

    def log_safety_blocked(self, agent_path: str, session_id: str, reason: str):
        self.log(AuditEvent(
            event_type=AuditEventType.SAFETY_BLOCKED,
            agent_path=agent_path,
            session_id=session_id,
            payload={"reason": reason},
        ))

    def log_pipeline_start(self, session_id: str, user_input: str):
        self.log(AuditEvent(
            event_type=AuditEventType.PIPELINE_START,
            session_id=session_id,
            payload={"user_input": user_input[:200]},
        ))

    def log_pipeline_end(self, session_id: str, status: str, metrics: dict[str, Any]):
        self.log(AuditEvent(
            event_type=AuditEventType.PIPELINE_END,
            session_id=session_id,
            payload={"status": status, "metrics": metrics},
        ))

    def flush(self):
        if not self._buffer:
            return
        today = time.strftime("%Y-%m-%d")
        log_file = self.log_dir / f"audit_{today}.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            for event in self._buffer:
                f.write(json.dumps({
                    "event_id": event.event_id,
                    "type": event.event_type.value,
                    "timestamp": event.timestamp,
                    "agent": event.agent_path,
                    "session": event.session_id,
                    "payload": event.payload,
                    "result": event.result,
                }, ensure_ascii=False) + "\n")
        self._buffer.clear()

    def _sanitize(self, data: dict[str, Any] | None) -> dict[str, Any]:
        if data is None:
            return {}
        sanitized: dict[str, Any] = {}
        for k, v in data.items():
            if isinstance(v, str) and len(v) > 1000:
                sanitized[k] = v[:1000] + "..."
            else:
                sanitized[k] = v
        return sanitized
