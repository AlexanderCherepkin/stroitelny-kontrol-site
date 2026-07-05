from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any


class OperationStatus(str, Enum):
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    TIMEOUT = "timeout"
    CORRUPTED = "corrupted"


class ConsistencyLevel(str, Enum):
    EVENTUAL = "eventual"
    SESSION_STRONG = "session_strong"
    IMMEDIATE = "immediate"


@dataclass
class StateRecord:
    key: str
    value: dict[str, Any]
    scope: str
    version: int = 1
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    tombstone: bool = False


@dataclass
class StateResult:
    status: OperationStatus
    value: dict[str, Any] | None = None
    version: int = 0
    message: str = ""


class StateManager:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._lock = Lock()
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self):
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS state_store (
                key TEXT NOT NULL,
                scope TEXT NOT NULL DEFAULT 'session',
                value TEXT NOT NULL DEFAULT '{}',
                version INTEGER NOT NULL DEFAULT 1,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                tombstone INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (key, scope)
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS checkpoints (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                state_snapshot TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        self._conn.commit()

    def create(self, key: str, value: dict[str, Any], scope: str = "session") -> StateResult:
        with self._lock:
            now = time.time()
            try:
                self._conn.execute(
                    "INSERT INTO state_store (key, scope, value, version, created_at, updated_at) VALUES (?, ?, ?, 1, ?, ?)",
                    (key, scope, json.dumps(value), now, now),
                )
                self._conn.commit()
                return StateResult(status=OperationStatus.SUCCESS, value=value, version=1)
            except sqlite3.IntegrityError:
                return StateResult(status=OperationStatus.CONFLICT, message=f"Key '{key}' already exists in scope '{scope}'")

    def read(self, key: str, scope: str = "session") -> StateResult:
        row = self._conn.execute(
            "SELECT value, version FROM state_store WHERE key=? AND scope=? AND tombstone=0",
            (key, scope),
        ).fetchone()
        if not row:
            return StateResult(status=OperationStatus.NOT_FOUND, message=f"Key '{key}' not found in scope '{scope}'")
        try:
            value = json.loads(row[0])
        except json.JSONDecodeError:
            return StateResult(status=OperationStatus.CORRUPTED, message=f"Corrupted value for key '{key}'")
        return StateResult(status=OperationStatus.SUCCESS, value=value, version=row[1])

    def update(self, key: str, value: dict[str, Any], expected_version: int | None = None, scope: str = "session") -> StateResult:
        with self._lock:
            current = self.read(key, scope)
            if current.status == OperationStatus.NOT_FOUND:
                return self.create(key, value, scope)
            if current.status != OperationStatus.SUCCESS:
                return current
            if expected_version is not None and current.version != expected_version:
                return StateResult(status=OperationStatus.CONFLICT, value=current.value, version=current.version,
                                   message=f"Version conflict: expected {expected_version}, current {current.version}")

            new_version = current.version + 1
            now = time.time()
            self._conn.execute(
                "UPDATE state_store SET value=?, version=?, updated_at=? WHERE key=? AND scope=?",
                (json.dumps(value), new_version, now, key, scope),
            )
            self._conn.commit()
            return StateResult(status=OperationStatus.SUCCESS, value=value, version=new_version)

    def delete(self, key: str, scope: str = "session", hard: bool = False) -> StateResult:
        with self._lock:
            if hard:
                self._conn.execute("DELETE FROM state_store WHERE key=? AND scope=?", (key, scope))
            else:
                self._conn.execute(
                    "UPDATE state_store SET tombstone=1, updated_at=? WHERE key=? AND scope=?",
                    (time.time(), key, scope),
                )
            self._conn.commit()
            return StateResult(status=OperationStatus.SUCCESS, message=f"Deleted '{key}'")

    def checkpoint(self, session_id: str) -> str:
        rows = self._conn.execute(
            "SELECT key, scope, value, version FROM state_store WHERE tombstone=0"
        ).fetchall()
        snapshot = {f"{r[1]}:{r[0]}": {"value": json.loads(r[2]), "version": r[3]} for r in rows}
        checkpoint_id = uuid.uuid4().hex
        self._conn.execute(
            "INSERT INTO checkpoints (id, session_id, state_snapshot, created_at) VALUES (?, ?, ?, ?)",
            (checkpoint_id, session_id, json.dumps(snapshot), time.time()),
        )
        self._conn.commit()
        return checkpoint_id

    def restore(self, checkpoint_id: str | None = None, session_id: str | None = None) -> StateResult:
        if checkpoint_id:
            row = self._conn.execute("SELECT state_snapshot FROM checkpoints WHERE id=?", (checkpoint_id,)).fetchone()
        elif session_id:
            row = self._conn.execute(
                "SELECT state_snapshot FROM checkpoints WHERE session_id=? ORDER BY created_at DESC LIMIT 1",
                (session_id,),
            ).fetchone()
        else:
            row = self._conn.execute("SELECT state_snapshot FROM checkpoints ORDER BY created_at DESC LIMIT 1").fetchone()

        if not row:
            return StateResult(status=OperationStatus.NOT_FOUND, message="No checkpoint found")

        try:
            snapshot = json.loads(row[0])
        except json.JSONDecodeError:
            return StateResult(status=OperationStatus.CORRUPTED, message="Checkpoint corrupted")

        with self._lock:
            self._conn.execute("DELETE FROM state_store WHERE tombstone=0")
            now = time.time()
            for composite_key, data in snapshot.items():
                scope, key = composite_key.split(":", 1)
                self._conn.execute(
                    "INSERT OR REPLACE INTO state_store (key, scope, value, version, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (key, scope, json.dumps(data["value"]), data["version"], now, now),
                )
            self._conn.commit()
        return StateResult(status=OperationStatus.SUCCESS, value=snapshot)

    def list_keys(self, scope: str = "session") -> list[str]:
        rows = self._conn.execute(
            "SELECT key FROM state_store WHERE scope=? AND tombstone=0", (scope,)
        ).fetchall()
        return [r[0] for r in rows]

    def close(self):
        if self._conn:
            self._conn.close()
