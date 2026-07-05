#!/usr/bin/env python3
"""
Memory Manager — coordinates VectorStore, FTSIndex, EmbeddingAgent, and Enrichment.

Provides the single runtime API for cross-session memory:
  - store(entry)   → write to FTS + vector indexes
  - recall(query)  → hybrid semantic + keyword search (RRF)
  - enrich_session(session_result) → extract facts, store them
  - get_relevant_memories(user_input) → load context for a new session
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from threading import Lock
from typing import Any

from .embedding_agent import EmbeddingAgent
from .vector_store import VectorStore
from .fts_index import FTSIndex
from .enrichment import MemoryEnrichment


class MemoryManager:
    """Cross-session memory coordinator."""

    def __init__(
        self,
        db_path: str | None = None,
        llm_engine: Any | None = None,
        embedding_model: str | None = None,
        embedding_dim: int | None = None,
    ):
        root = Path(__file__).resolve().parent.parent.parent
        self.db_path = db_path or str(root / "data" / "memory.db")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = Lock()
        self._init_meta_table()

        self.embedder = EmbeddingAgent(model=embedding_model, dimensions=embedding_dim)
        self.dimensions = self.embedder.dimensions

        self.vector = VectorStore(db_path=self.db_path, dimensions=self.dimensions)
        self.fts = FTSIndex(db_path=self.db_path)
        self.enrichment = MemoryEnrichment(llm_engine=llm_engine)

    def _init_meta_table(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_entries (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                priority INTEGER NOT NULL DEFAULT 5,
                source TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_mem_type ON memory_entries(type)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_mem_priority ON memory_entries(priority DESC)
        """)
        self._conn.commit()

    # ── Public API ────────────────────────────────────────────────────────────

    def store(self, entry: dict[str, Any]) -> dict[str, Any]:
        """
        Store a single memory entry.
        Entry keys: id, type, title, body, tags, priority, source
        """
        entry_id = entry.get("id") or f"mem_{int(time.time()*1000)}"
        mem_type = entry.get("type", "reference")
        title = entry.get("title", "")
        body = entry.get("body", "")
        tags = entry.get("tags", [])
        priority = entry.get("priority", 5)
        source = entry.get("source", "")

        # 1. Write canonical record
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO memory_entries
                   (id, type, title, body, tags, priority, source, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry_id,
                    mem_type,
                    title,
                    body,
                    json.dumps(tags),
                    priority,
                    source,
                    time.time(),
                    time.time(),
                ),
            )
            self._conn.commit()

        # 2. Update FTS
        self.fts.index(entry_id, title, body, tags, mem_type)

        # 3. Update vector index
        text_to_embed = f"[{mem_type}] {title}\n{body}\nTags: {', '.join(tags)}"
        embedding = self.embedder.embed(text_to_embed)
        self.vector.insert(entry_id, embedding, model=self.embedder.model_name)

        return {"id": entry_id, "status": "stored", "type": mem_type}

    def store_batch(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Store multiple entries efficiently."""
        results = []
        for e in entries:
            results.append(self.store(e))
        return results

    def recall(self, query: str, top_k: int = 5, type_filter: str | None = None) -> list[dict[str, Any]]:
        """
        Hybrid retrieval: semantic + keyword via Reciprocal Rank Fusion (RRF).
        Returns enriched memory entries sorted by fused score.
        """
        # Semantic search
        q_emb = self.embedder.embed(query)
        vec_results = self.vector.search(q_emb, top_k=top_k * 3, threshold=0.5)

        # Keyword search
        fts_results = self.fts.search(query, limit=top_k * 3)

        # RRF fusion
        fused: dict[str, float] = {}
        k_rrf = 60
        for rank, r in enumerate(vec_results, start=1):
            mid = r["memory_id"]
            fused[mid] = fused.get(mid, 0.0) + 1.0 / (k_rrf + rank)
        for rank, r in enumerate(fts_results, start=1):
            mid = r["memory_id"]
            fused[mid] = fused.get(mid, 0.0) + 1.0 / (k_rrf + rank)

        sorted_ids = sorted(fused.keys(), key=lambda m: fused[m], reverse=True)[:top_k]

        # Enrich with canonical data
        results: list[dict[str, Any]] = []
        for mid in sorted_ids:
            row = self._conn.execute(
                "SELECT id, type, title, body, tags, priority, source, created_at FROM memory_entries WHERE id=?",
                (mid,),
            ).fetchone()
            if not row:
                continue
            if type_filter and row[1] != type_filter:
                continue
            results.append({
                "id": row[0],
                "type": row[1],
                "title": row[2],
                "body": row[3],
                "tags": json.loads(row[4]) if row[4] else [],
                "priority": row[5],
                "source": row[6],
                "created_at": row[7],
                "rrf_score": round(fused[mid], 4),
            })

        return results

    def get_relevant_memories(self, user_input: str, limit: int = 5) -> list[dict[str, Any]]:
        """Load relevant memories before a new session starts."""
        return self.recall(user_input, top_k=limit)

    def enrich_session(self, session_result: Any) -> list[dict[str, Any]]:
        """
        Extract facts from a completed session and persist them.
        Accepts either a PipelineResult dataclass or a plain dict.
        """
        if hasattr(session_result, "__dataclass_fields__"):
            data = {
                "user_input": getattr(session_result, "final_response", ""),
                "final_response": getattr(session_result, "final_response", ""),
                "trace": [
                    t.__dict__ if hasattr(t, "__dataclass_fields__") else t
                    for t in getattr(session_result, "trace", [])
                ],
                "metrics": getattr(session_result, "session_metrics", {}),
                "termination_status": getattr(session_result, "termination_status", ""),
            }
        else:
            data = dict(session_result)

        facts = self.enrichment.extract(data)
        stored = self.store_batch(facts)
        return stored

    def delete(self, memory_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM memory_entries WHERE id=?", (memory_id,))
            self._conn.commit()
        self.vector.delete(memory_id)
        self.fts.delete(memory_id)

    def stats(self) -> dict[str, Any]:
        row = self._conn.execute("SELECT COUNT(*) FROM memory_entries").fetchone()
        total = row[0] if row else 0
        return {
            "total_entries": total,
            "vector_count": self.vector.count(),
            "fts_count": self.fts.count(),
            "embedding_backend": self.embedder.backend,
            "embedding_model": self.embedder.model_name,
            "embedding_dimensions": self.embedder.dimensions,
        }

    def close(self) -> None:
        self.vector.close()
        self.fts.close()
        self._conn.close()


