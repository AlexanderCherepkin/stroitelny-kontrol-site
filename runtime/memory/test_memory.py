#!/usr/bin/env python3
"""Unit tests for runtime/memory components."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np

from runtime.memory.embedding_agent import EmbeddingAgent
from runtime.memory.vector_store import VectorStore
from runtime.memory.fts_index import FTSIndex
from runtime.memory.enrichment import MemoryEnrichment
from runtime.memory.memory_manager import MemoryManager


class TestEmbeddingAgent(unittest.TestCase):
    def setUp(self):
        self._old_key = os.environ.pop("OPENAI_API_KEY", None)

    def tearDown(self):
        if self._old_key is not None:
            os.environ["OPENAI_API_KEY"] = self._old_key
        elif "OPENAI_API_KEY" in os.environ:
            del os.environ["OPENAI_API_KEY"]

    def test_fallback_backend_exists(self):
        agent = EmbeddingAgent()
        self.assertIn(agent.backend, ("local", "openai", "simple"))
        self.assertGreater(agent.dimensions, 0)

    def test_embed_normalized(self):
        agent = EmbeddingAgent()
        vec = agent.embed("hello world")
        self.assertEqual(vec.shape, (agent.dimensions,))
        norm = np.linalg.norm(vec)
        self.assertAlmostEqual(norm, 1.0, places=5)

    def test_batch_embed(self):
        agent = EmbeddingAgent()
        batch = agent.batch_embed(["first text", "second text"])
        self.assertEqual(batch.shape, (2, agent.dimensions))
        for vec in batch:
            self.assertAlmostEqual(np.linalg.norm(vec), 1.0, places=5)

    def test_similarity_range(self):
        agent = EmbeddingAgent()
        a = agent.embed("dog")
        b = agent.embed("cat")
        sim = agent.similarity(a, b)
        self.assertGreaterEqual(sim, -1.0)
        self.assertLessEqual(sim, 1.0)


class TestVectorStore(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "vectors.db")
        self.store = VectorStore(db_path=self.db_path, dimensions=8)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_insert_and_search(self):
        v1 = np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
        v1 /= np.linalg.norm(v1)
        v2 = np.array([0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
        v2 /= np.linalg.norm(v2)
        self.store.insert("id_1", v1)
        self.store.insert("id_2", v2)

        q = np.array([0.9, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
        q /= np.linalg.norm(q)
        results = self.store.search(q, top_k=2, threshold=0.5)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["memory_id"], "id_1")

    def test_count(self):
        self.assertEqual(self.store.count(), 0)
        v = np.ones(8, dtype=np.float32)
        v /= np.linalg.norm(v)
        self.store.insert("x", v)
        self.assertEqual(self.store.count(), 1)


class TestFTSIndex(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "fts.db")
        self.fts = FTSIndex(db_path=self.db_path)

    def tearDown(self):
        self.fts.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_index_and_search(self):
        self.fts.index("m1", "Project Alpha", "Build the auth module using JWT.", ["auth", "jwt"], "project")
        self.fts.index("m2", "User Preference", "Prefer dark mode UI.", ["ui", "preference"], "user")
        results = self.fts.search("auth module")
        self.assertGreaterEqual(len(results), 1)
        ids = {r["memory_id"] for r in results}
        self.assertIn("m1", ids)

    def test_delete(self):
        self.fts.index("m1", "Title", "Body text", [], "reference")
        self.assertEqual(self.fts.count(), 1)
        self.fts.delete("m1")
        self.assertEqual(self.fts.count(), 0)


class TestMemoryEnrichment(unittest.TestCase):
    def test_extract_basic_facts(self):
        enrich = MemoryEnrichment()
        facts = enrich.extract({
            "user_input": "Refactor the login flow",
            "final_response": "Done. Extracted auth service.",
            "trace": [],
            "metrics": {"tools_used": ["replace", "search"]},
            "termination_status": "success",
        })
        types = {f["type"] for f in facts}
        self.assertIn("user", types)
        self.assertIn("project", types)
        self.assertIn("reference", types)

    def test_extract_failure_feedback(self):
        enrich = MemoryEnrichment()
        facts = enrich.extract({
            "user_input": "Deploy now",
            "final_response": "Error: no credentials",
            "trace": [],
            "metrics": {},
            "termination_status": "failure",
        })
        types = {f["type"] for f in facts}
        self.assertIn("feedback", types)


class TestMemoryManager(unittest.TestCase):
    def setUp(self):
        self._old_key = os.environ.pop("OPENAI_API_KEY", None)
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "memory.db")
        self.mm = MemoryManager(db_path=self.db_path)

    def tearDown(self):
        self.mm.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        if self._old_key is not None:
            os.environ["OPENAI_API_KEY"] = self._old_key
        elif "OPENAI_API_KEY" in os.environ:
            del os.environ["OPENAI_API_KEY"]

    def test_store_and_recall(self):
        entry = {
            "id": "e1",
            "type": "project",
            "title": "Add OAuth2",
            "body": "Implemented OAuth2 login with PKCE.",
            "tags": ["auth", "oauth"],
            "priority": 8,
            "source": "test",
        }
        self.mm.store(entry)
        results = self.mm.recall("OAuth login", top_k=5)
        ids = [r["id"] for r in results]
        self.assertIn("e1", ids)

    def test_stats(self):
        stats = self.mm.stats()
        self.assertIn("total_entries", stats)
        self.assertIn("vector_count", stats)
        self.assertIn("fts_count", stats)
        self.assertEqual(stats["total_entries"], 0)

    def test_enrich_session(self):
        stored = self.mm.enrich_session({
            "user_input": "Create a memory layer",
            "final_response": "Memory layer created.",
            "trace": [{"phase": "execution", "agent_path": "test", "outputs": {}}],
            "metrics": {"tools_used": ["write"]},
            "termination_status": "success",
        })
        self.assertGreaterEqual(len(stored), 1)
        stats = self.mm.stats()
        self.assertGreaterEqual(stats["total_entries"], 1)


if __name__ == "__main__":
    unittest.main()
