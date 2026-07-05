#!/usr/bin/env python3
"""
FTS Index — SQLite FTS5 full-text index for memory entries.

Indexes title, body, tags, and type for fast keyword / BM25 retrieval.
"""

from __future__ import annotations

import sqlite3
import time
from threading import Lock
from typing import Any


class FTSIndex:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._lock = Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        # FTS5 virtual table (contentful so we can DELETE/UPDATE by rowid)
        self._conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                title,
                body,
                tags,
                memory_type
            )
        """)
        # Auxiliary mapping table to preserve memory_id → rowid
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_fts_map (
                memory_id TEXT PRIMARY KEY,
                rowid INTEGER NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        self._conn.commit()

    def index(self, memory_id: str, title: str, body: str, tags: list[str], memory_type: str) -> None:
        """Insert or replace a document in the FTS index."""
        tags_str = ", ".join(tags)
        with self._lock:
            # Delete old mapping if any
            old = self._conn.execute(
                "SELECT rowid FROM memory_fts_map WHERE memory_id=?", (memory_id,)
            ).fetchone()
            if old:
                self._conn.execute("DELETE FROM memory_fts WHERE rowid=?", (old[0],))
                self._conn.execute("DELETE FROM memory_fts_map WHERE memory_id=?", (memory_id,))

            cur = self._conn.execute(
                "INSERT INTO memory_fts (title, body, tags, memory_type) VALUES (?, ?, ?, ?)",
                (title, body, tags_str, memory_type),
            )
            rowid = cur.lastrowid
            self._conn.execute(
                "INSERT INTO memory_fts_map (memory_id, rowid, updated_at) VALUES (?, ?, ?)",
                (memory_id, rowid, time.time()),
            )
            self._conn.commit()

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """BM25-ranked keyword search."""
        # Escape quotes in query
        safe_query = query.replace('"', '""')
        rows = self._conn.execute(
            """SELECT m.memory_id, rank
               FROM memory_fts f
               JOIN memory_fts_map m ON m.rowid = f.rowid
               WHERE memory_fts MATCH ?
               ORDER BY rank
               LIMIT ?""",
            (safe_query, limit),
        ).fetchall()
        return [
            {"memory_id": mid, "rank": idx + 1, "bm25_score": round(rank, 4)}
            for idx, (mid, rank) in enumerate(rows)
        ]

    def delete(self, memory_id: str) -> None:
        with self._lock:
            old = self._conn.execute(
                "SELECT rowid FROM memory_fts_map WHERE memory_id=?", (memory_id,)
            ).fetchone()
            if old:
                self._conn.execute("DELETE FROM memory_fts WHERE rowid=?", (old[0],))
                self._conn.execute("DELETE FROM memory_fts_map WHERE memory_id=?", (memory_id,))
                self._conn.commit()

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM memory_fts").fetchone()
        return row[0] if row else 0

    def close(self) -> None:
        self._conn.close()
