#!/usr/bin/env python3
"""
Vector Store — SQLite-backed dense vector storage with brute-force cosine search.

Stores normalized vectors as BLOBs. Search computes dot product over all rows
(lazy ANN; fast enough for <100k entries and small dims).
"""

from __future__ import annotations

import sqlite3
import time
from threading import Lock
from typing import Any

import numpy as np


class VectorStore:
    def __init__(self, db_path: str = ":memory:", dimensions: int = 384):
        self.db_path = db_path
        self.dimensions = dimensions
        self._lock = Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_vectors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_id TEXT NOT NULL UNIQUE,
                embedding BLOB NOT NULL,
                model TEXT,
                dimensions INTEGER,
                created_at REAL NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_vec_memory_id ON memory_vectors(memory_id)
        """)
        self._conn.commit()

    def insert(self, memory_id: str, embedding: np.ndarray, model: str = "") -> None:
        """Store a single normalized vector."""
        if embedding.shape != (self.dimensions,):
            raise ValueError(f"Expected dim {self.dimensions}, got {embedding.shape}")
        blob = embedding.tobytes()
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO memory_vectors
                   (memory_id, embedding, model, dimensions, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (memory_id, blob, model, self.dimensions, time.time()),
            )
            self._conn.commit()

    def insert_batch(self, items: list[tuple[str, np.ndarray]], model: str = "") -> None:
        with self._lock:
            for memory_id, emb in items:
                blob = emb.tobytes()
                self._conn.execute(
                    """INSERT OR REPLACE INTO memory_vectors
                       (memory_id, embedding, model, dimensions, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (memory_id, blob, model, self.dimensions, time.time()),
                )
            self._conn.commit()

    def delete(self, memory_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM memory_vectors WHERE memory_id=?", (memory_id,))
            self._conn.commit()

    def search(self, query_embedding: np.ndarray, top_k: int = 5, threshold: float = 0.7) -> list[dict[str, Any]]:
        """Brute-force cosine similarity search. Returns sorted results."""
        if query_embedding.shape != (self.dimensions,):
            raise ValueError(f"Query dim mismatch: expected {self.dimensions}, got {query_embedding.shape}")

        rows = self._conn.execute(
            "SELECT memory_id, embedding FROM memory_vectors"
        ).fetchall()

        scores: list[tuple[str, float]] = []
        q = query_embedding.astype(np.float32)
        for memory_id, blob in rows:
            vec = np.frombuffer(blob, dtype=np.float32)
            if vec.shape[0] != self.dimensions:
                continue
            sim = float(np.dot(q, vec))
            if sim >= threshold:
                scores.append((memory_id, sim))

        scores.sort(key=lambda x: x[1], reverse=True)
        return [
            {"memory_id": mid, "score": round(s, 4), "rank": i + 1}
            for i, (mid, s) in enumerate(scores[:top_k])
        ]

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM memory_vectors").fetchone()
        return row[0] if row else 0

    def close(self) -> None:
        self._conn.close()
