#!/usr/bin/env python3
"""
Embedding Agent — generates dense vector embeddings for memory entries.

Tiers (best-available):
  1. Local sentence-transformers (all-MiniLM-L6-v2, 384d)
  2. OpenAI API (text-embedding-3-small, 1536d)
  3. SimpleBagOfWords fallback (dynamic vocab, ~500–5000d)

Caches embeddings keyed by SHA256(text) to avoid redundant API calls.
"""

from __future__ import annotations

import hashlib
import math
import os
import time
from typing import Any

import numpy as np


class _SimpleEmbedding:
    """Lightweight TF-like fallback when no model or API is available."""

    def __init__(self, max_vocab: int = 5000):
        self.max_vocab = max_vocab
        self._word_to_idx: dict[str, int] = {}
        self._next_idx = 0

    def _tokenize(self, text: str) -> list[str]:
        return text.lower().replace(",", " ").replace(".", " ").split()

    def _get_or_add(self, word: str) -> int:
        if word not in self._word_to_idx:
            if self._next_idx < self.max_vocab:
                self._word_to_idx[word] = self._next_idx
                self._next_idx += 1
            else:
                # Hash collision bucket
                return hash(word) % self.max_vocab
        return self._word_to_idx.get(word, hash(word) % self.max_vocab)

    def encode(self, texts: list[str]) -> np.ndarray:
        if isinstance(texts, str):
            texts = [texts]
        dim = self.max_vocab
        vectors = np.zeros((len(texts), dim), dtype=np.float32)
        for i, text in enumerate(texts):
            tokens = self._tokenize(text)
            if not tokens:
                continue
            counts: dict[int, int] = {}
            for w in tokens:
                idx = self._get_or_add(w)
                counts[idx] = counts.get(idx, 0) + 1
            for idx, cnt in counts.items():
                vectors[i, idx] = cnt / len(tokens)
            norm = np.linalg.norm(vectors[i])
            if norm > 0:
                vectors[i] /= norm
        return vectors


class EmbeddingAgent:
    """Produces normalized embedding vectors with tiered fallback."""

    def __init__(self, model: str | None = None, dimensions: int | None = None):
        self._preferred = model
        self._fixed_dim = dimensions
        self._cache: dict[str, np.ndarray] = {}
        self._backend: str | None = None
        self._model_name: str = ""
        self._dim: int = 0
        self._local_model: Any = None
        self._simple: _SimpleEmbedding | None = None
        self._init_backend()

    def _init_backend(self) -> None:
        # Tier 1: sentence-transformers local
        try:
            from sentence_transformers import SentenceTransformer

            name = self._preferred or "all-MiniLM-L6-v2"
            self._local_model = SentenceTransformer(name)
            self._backend = "local"
            self._model_name = name
            self._dim = self._fixed_dim or self._local_model.get_sentence_embedding_dimension()
            return
        except Exception:
            pass

        # Tier 2: OpenAI API
        if os.getenv("OPENAI_API_KEY"):
            self._backend = "openai"
            self._model_name = self._preferred or "text-embedding-3-small"
            self._dim = self._fixed_dim or (3072 if "large" in self._model_name else 1536)
            return

        # Tier 3: simple fallback (also used as emergency fallback for API failures)
        self._backend = "simple"
        self._model_name = "simple-bow"
        self._dim = self._fixed_dim or 5000
        self._simple = _SimpleEmbedding(max_vocab=self._dim)

    def _fallback_vec(self, texts: list[str]) -> np.ndarray:
        """Return simple embeddings, initializing lazily if needed."""
        if self._simple is None:
            dim = self._fixed_dim or 5000
            self._simple = _SimpleEmbedding(max_vocab=dim)
        return self._simple.encode(texts)

    @property
    def backend(self) -> str:
        return self._backend or "none"

    @property
    def dimensions(self) -> int:
        return self._dim

    @property
    def model_name(self) -> str:
        return self._model_name

    def _hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def embed(self, text: str) -> np.ndarray:
        """Return a single normalized embedding vector (float32)."""
        key = self._hash(text)
        if key in self._cache:
            return self._cache[key]

        if self._backend == "local":
            vec = self._local_model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
        elif self._backend == "openai":
            try:
                vec = self._embed_openai([text])[0]
            except Exception:
                vec = self._fallback_vec([text])[0]
        else:
            vec = self._simple.encode([text])[0]

        vec = np.asarray(vec, dtype=np.float32)
        if vec.shape != (self._dim,):
            # Pad or trim to fixed dim
            out = np.zeros(self._dim, dtype=np.float32)
            length = min(self._dim, vec.shape[0])
            out[:length] = vec[:length]
            vec = out
            # re-normalize after resize
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec /= norm

        self._cache[key] = vec
        return vec

    def batch_embed(self, texts: list[str]) -> np.ndarray:
        """Return N×D matrix of normalized embeddings."""
        results: list[np.ndarray] = []
        uncached_texts: list[str] = []
        uncached_indices: list[int] = []
        for i, text in enumerate(texts):
            key = self._hash(text)
            if key in self._cache:
                results.append(self._cache[key])
            else:
                results.append(np.zeros(self._dim, dtype=np.float32))  # placeholder
                uncached_texts.append(text)
                uncached_indices.append(i)

        if uncached_texts:
            if self._backend == "local":
                batch = self._local_model.encode(uncached_texts, convert_to_numpy=True, normalize_embeddings=True)
                batch = np.asarray(batch, dtype=np.float32)
            elif self._backend == "openai":
                try:
                    batch = self._embed_openai(uncached_texts)
                except Exception:
                    batch = self._fallback_vec(uncached_texts)
            else:
                batch = self._simple.encode(uncached_texts)

            for idx, text, vec in zip(uncached_indices, uncached_texts, batch):
                vec = np.asarray(vec, dtype=np.float32)
                if vec.shape != (self._dim,):
                    out = np.zeros(self._dim, dtype=np.float32)
                    length = min(self._dim, vec.shape[0])
                    out[:length] = vec[:length]
                    vec = out
                    norm = np.linalg.norm(vec)
                    if norm > 0:
                        vec /= norm
                key = self._hash(text)
                self._cache[key] = vec
                results[idx] = vec

        return np.stack(results)

    def _embed_openai(self, texts: list[str]) -> np.ndarray:
        import openai

        client = openai.OpenAI()
        resp = client.embeddings.create(model=self._model_name, input=texts)
        vectors = [np.array(d.embedding, dtype=np.float32) for d in resp.data]
        # normalize
        for v in vectors:
            n = np.linalg.norm(v)
            if n > 0:
                v /= n
        return np.stack(vectors)

    def similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity of two normalized vectors."""
        return float(np.clip(np.dot(a, b), -1.0, 1.0))
