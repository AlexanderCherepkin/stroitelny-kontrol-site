from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from .base import MCPServer


class TerminalMCPServer(MCPServer):
    """MCP server for tools_terminal — terminal I/O pipeline (session-stateful)."""

    def __init__(self, workspace_root: str = "."):
        super().__init__(name="tools_terminal", version="1.0.0")
        self.workspace = Path(workspace_root).resolve()
        self._sessions: dict[str, dict[str, Any]] = {}

        self.register("create_session", "Create a new terminal session",
                       self._s({"session_id?": "string", "cwd?": "string"}),
                       self.create_session)
        self.register("get_state", "Get current terminal session state",
                       self._s({"session_id": "string"}), self.get_state)
        self.register("add_to_history", "Add command to session history",
                       self._s({"session_id": "string", "command": "string", "output?": "string"}),
                       self.add_to_history)
        self.register("parse_ansi", "Parse ANSI escape codes from terminal output",
                       self._s({"text": "string"}), self.parse_ansi)
        self.register("filter_output", "Filter terminal output by pattern or level",
                       self._s({"text": "string", "pattern?": "string", "filter_type?": "string"}),
                       self.filter_output)
        self.register("detect_error", "Detect errors in terminal output",
                       self._s({"text": "string"}), self.detect_error)
        self.register("get_session_history", "Get command history for a session",
                       self._s({"session_id": "string", "limit?": "int"}), self.get_session_history)
        self.register("list_sessions", "List all active terminal sessions",
                       self._s({}), self.list_sessions)
        self.register("close_session", "Close and clean up a terminal session",
                       self._s({"session_id": "string"}), self.close_session)

    async def create_session(self, session_id: str = "", cwd: str = "") -> dict[str, Any]:
        sid = session_id or f"term_{int(time.time() * 1000)}"
        self._sessions[sid] = {
            "id": sid, "created_at": time.time(), "cwd": cwd or str(self.workspace),
            "history": [], "state": "active", "exit_code": None,
        }
        return {"session_id": sid, **self._sessions[sid]}

    async def get_state(self, session_id: str) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if not session:
            return {"error": f"Session not found: {session_id}"}
        return {"session_id": session_id, **session}

    async def add_to_history(self, session_id: str, command: str, output: str = "") -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if not session:
            return {"error": f"Session not found: {session_id}"}
        entry = {"command": command, "output": output[:5000], "timestamp": time.time()}
        session["history"].append(entry)
        return {"session_id": session_id, "entry_added": True, "history_size": len(session["history"])}

    async def parse_ansi(self, text: str) -> dict[str, Any]:
        ansi_pattern = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
        codes: list[str] = []
        clean = text
        for match in ansi_pattern.finditer(text):
            codes.append(match.group())
            clean = clean.replace(match.group(), "", 1)

        colors_found = []
        for code in codes:
            if "31" in code or "91" in code:
                colors_found.append("red")
            elif "32" in code or "92" in code:
                colors_found.append("green")
            elif "33" in code or "93" in code:
                colors_found.append("yellow")
            elif "34" in code or "94" in code:
                colors_found.append("blue")
            elif "1" in code and "3" not in code.replace("1", ""):
                colors_found.append("bold")

        return {"original_length": len(text), "clean_length": len(clean),
                "ansi_codes": codes[:50], "code_count": len(codes),
                "clean_text": clean, "colors_detected": list(set(colors_found))}

    async def filter_output(self, text: str, pattern: str = "", filter_type: str = "grep") -> dict[str, Any]:
        lines = text.split("\n")
        if filter_type == "grep" and pattern:
            try:
                regex = re.compile(pattern)
                filtered = [l for l in lines if regex.search(l)]
            except re.error:
                filtered = [l for l in lines if pattern.lower() in l.lower()]
        elif filter_type == "errors":
            error_patterns = [r"error", r"fail", r"exception", r"traceback", r"fatal", r"invalid"]
            filtered = [l for l in lines if any(re.search(p, l, re.IGNORECASE) for p in error_patterns)]
        elif filter_type == "head":
            filtered = lines[:20]
        elif filter_type == "tail":
            filtered = lines[-20:]
        else:
            filtered = lines
        return {"original_lines": len(lines), "filtered_lines": len(filtered),
                "filter_type": filter_type, "output": "\n".join(filtered)}

    async def detect_error(self, text: str) -> dict[str, Any]:
        errors: list[dict[str, Any]] = []
        error_patterns = [
            (r"(?i)error[: ]", "generic_error"),
            (r"(?i)exception[: ]", "exception"),
            (r"(?i)Traceback \(most recent call last\)", "python_traceback"),
            (r"(?i)fatal[: ]", "fatal_error"),
            (r"(?i)command not found", "command_not_found"),
            (r"(?i)permission denied", "permission_denied"),
            (r"(?i)out of memory", "oom"),
            (r"(?i)segmentation fault", "segfault"),
            (r"(?i)connection refused", "connection_refused"),
            (r"(?i)timeout", "timeout"),
        ]
        for line in text.split("\n"):
            for pattern, err_type in error_patterns:
                if re.search(pattern, line):
                    errors.append({"line": line.strip()[:200], "type": err_type})
                    break
        return {"error_count": len(errors), "errors": errors[:20],
                "has_errors": len(errors) > 0}

    async def get_session_history(self, session_id: str, limit: int = 50) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if not session:
            return {"error": f"Session not found: {session_id}"}
        history = session["history"][-limit:]
        return {"session_id": session_id, "commands": history, "total": len(session["history"])}

    async def list_sessions(self) -> dict[str, Any]:
        sessions = [{"id": sid, "state": s["state"], "history_size": len(s["history"]),
                      "cwd": s["cwd"], "created_at": s["created_at"]}
                    for sid, s in self._sessions.items()]
        return {"sessions": sessions, "count": len(sessions)}

    async def close_session(self, session_id: str) -> dict[str, Any]:
        session = self._sessions.pop(session_id, None)
        if not session:
            return {"error": f"Session not found: {session_id}"}
        return {"session_id": session_id, "closed": True, "commands_executed": len(session["history"])}

    @staticmethod
    def _s(props: dict[str, str]) -> dict[str, Any]:
        required = [k for k in props if not k.endswith("?")]
        properties = {}
        for k, v in props.items():
            name = k.rstrip("?")
            type_map = {"string": "string", "int": "integer", "bool": "boolean", "float": "number", "array": "array", "object": "object"}
            properties[name] = {"type": type_map.get(v, "string"), "description": f"The {name} parameter"}
        return {"type": "object", "properties": properties, "required": required}
