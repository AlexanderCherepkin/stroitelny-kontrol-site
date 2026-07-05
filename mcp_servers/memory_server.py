from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from .base import MCPServer


class MemoryMCPServer(MCPServer):
    """MCP server for tools_memory — memory store pipeline (store-lifecycle)."""

    def __init__(self, workspace_root: str = "."):
        super().__init__(name="tools_memory", version="1.0.0")
        self.workspace = Path(workspace_root).resolve()
        self._memory_store: dict[str, dict[str, Any]] = {}
        self._index: dict[str, list[str]] = {}
        self._access_count: dict[str, int] = {}
        self._load_memory_files()

    def _load_memory_files(self):
        mem_dir = Path(os.environ.get(
            "MEMORY_DIR",
            os.path.expandvars(r"%USERPROFILE%\.claude\projects\D--My-head-folders-My-desktop----------Agentic-Loop\memory")
        ))
        if mem_dir.exists():
            for md_file in mem_dir.glob("*.md"):
                if md_file.name == "MEMORY.md":
                    continue
                try:
                    content = md_file.read_text(encoding="utf-8")
                    self._memory_store[md_file.name] = {
                        "name": md_file.stem,
                        "content": content,
                        "size": len(content),
                        "modified": md_file.stat().st_mtime,
                    }
                except Exception:
                    pass

    def _resolve_path(self, path: str) -> Path:
        base = Path(os.environ.get(
            "MEMORY_DIR",
            os.path.expandvars(r"%USERPROFILE%\.claude\projects\D--My-head-folders-My-desktop----------Agentic-Loop\memory")
        ))
        return base / path

    def register_all(self):
        self.register("read_memory", "Read a memory entry by key",
                       self._s({"key": "string"}), self.read_memory)
        self.register("write_memory", "Write a new memory entry or update existing",
                       self._s({"key": "string", "content": "string", "type?": "string",
                                "tags?": "array"}), self.write_memory)
        self.register("list_entries", "List all memory entries with optional filter",
                       self._s({"type?": "string", "tag?": "string", "limit?": "int"}),
                       self.list_entries)
        self.register("index_entry", "Add entry to search index with keywords",
                       self._s({"key": "string", "keywords": "array"}), self.index_entry)
        self.register("search_index", "Search memory index by keywords",
                       self._s({"query": "string", "limit?": "int"}), self.search_index)
        self.register("generate_embedding", "Generate a simple text embedding for semantic search",
                       self._s({"text": "string"}), self.generate_embedding)
        self.register("compress_content", "Compress memory content by removing redundancy",
                       self._s({"content": "string", "level?": "string"}), self.compress_content)
        self.register("summarize_entry", "Generate summary of memory entry",
                       self._s({"content": "string", "max_length?": "int"}), self.summarize_entry)
        self.register("evict_entry", "Evict entry based on policy (LRU, oldest, by tag)",
                       self._s({"policy?": "string", "tag?": "string"}), self.evict_entry)
        self.register("check_consistency", "Check memory store consistency",
                       self._s({}), self.check_consistency)
        self.register("optimize_store", "Optimize memory store — deduplicate, compact, reindex",
                       self._s({}), self.optimize_store)

    async def read_memory(self, key: str) -> dict[str, Any]:
        entry = self._memory_store.get(key)
        if not entry:
            mem_file = self._resolve_path(key) if not key.endswith(".md") else self._resolve_path(key)
            if mem_file.exists():
                content = mem_file.read_text(encoding="utf-8")
                entry = {"name": mem_file.stem, "content": content, "size": len(content)}
                self._memory_store[key] = entry
            else:
                return {"error": f"Memory not found: {key}"}
        self._access_count[key] = self._access_count.get(key, 0) + 1
        return {"key": key, **entry}

    async def write_memory(self, key: str, content: str, type: str = "project",
                           tags: list[str] | None = None) -> dict[str, Any]:
        mem_file = self._resolve_path(key) if key.endswith(".md") else self._resolve_path(f"{key}.md")

        frontmatter = f"""---
name: {key.replace('.md', '')}
description: Memory entry of type {type}
metadata:
  type: {type}
---
"""
        full_content = frontmatter + "\n" + content
        mem_file.parent.mkdir(parents=True, exist_ok=True)
        mem_file.write_text(full_content, encoding="utf-8")

        self._memory_store[key] = {"name": key.replace(".md", ""),
                                    "content": content, "size": len(content),
                                    "modified": time.time(), "type": type,
                                    "tags": tags or []}
        if tags:
            await self.index_entry(key, tags)
        return {"key": key, "written": True, "size": len(content), "path": str(mem_file)}

    async def list_entries(self, type: str = "", tag: str = "", limit: int = 50) -> dict[str, Any]:
        entries = []
        for key, entry in self._memory_store.items():
            if type and entry.get("type") != type:
                continue
            if tag and tag not in entry.get("tags", []):
                continue
            entries.append({"key": key, "name": entry["name"],
                            "size": entry["size"],
                            "modified": entry.get("modified", 0),
                            "type": entry.get("type", ""),
                            "tags": entry.get("tags", [])})
        entries.sort(key=lambda e: e.get("modified", 0), reverse=True)
        return {"entries": entries[:limit], "total": len(entries), "filtered": len(entries) < len(self._memory_store)}

    async def index_entry(self, key: str, keywords: list[str]) -> dict[str, Any]:
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower not in self._index:
                self._index[kw_lower] = []
            if key not in self._index[kw_lower]:
                self._index[kw_lower].append(key)
        return {"key": key, "keywords_added": len(keywords), "index_size": len(self._index)}

    async def search_index(self, query: str, limit: int = 10) -> dict[str, Any]:
        query_terms = set(query.lower().split())
        scores: dict[str, float] = {}
        for term in query_terms:
            for indexed_term, keys in self._index.items():
                if term in indexed_term or indexed_term in term:
                    for key in keys:
                        scores[key] = scores.get(key, 0) + 1

        for key, entry in self._memory_store.items():
            content_lower = entry.get("content", "").lower()
            for term in query_terms:
                if term in content_lower:
                    scores[key] = scores.get(key, 0) + 0.5

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:limit]
        results = [{"key": k, "score": s, "preview": self._memory_store.get(k, {}).get("content", "")[:200]}
                   for k, s in ranked]
        return {"query": query, "results": results, "total_matches": len(scores)}

    async def generate_embedding(self, text: str) -> dict[str, Any]:
        words = re.findall(r"\w+", text.lower())
        word_freq: dict[str, int] = {}
        for w in words:
            word_freq[w] = word_freq.get(w, 0) + 1

        hash_vec = []
        for i in range(64):
            seed = f"{i}:{sorted(word_freq.items())}"
            hash_vec.append(float(int(hashlib.md5(seed.encode()).hexdigest()[:4], 16)) / 65535)
        norm = sum(v**2 for v in hash_vec) ** 0.5
        if norm > 0:
            hash_vec = [v / norm for v in hash_vec]

        return {"dimensions": len(hash_vec), "embedding": hash_vec[:16],
                "model": "hash-embedding-v1", "note": "Lightweight hash-based embedding. Use OpenAI API for production."}

    async def compress_content(self, content: str, level: str = "medium") -> dict[str, Any]:
        original_size = len(content)
        compressed = content
        if level in ("high", "medium"):
            compressed = re.sub(r"\n{3,}", "\n\n", compressed)
            compressed = re.sub(r" {2,}", " ", compressed)
        if level == "high":
            lines = compressed.split("\n")
            compressed = "\n".join(l for l in lines if l.strip())
        return {"original_size": original_size, "compressed_size": len(compressed),
                "ratio": f"{len(compressed)/original_size*100:.1f}%" if original_size else "0%",
                "level": level, "compressed": compressed[:5000]}

    async def summarize_entry(self, content: str, max_length: int = 200) -> dict[str, Any]:
        sentences = re.split(r"(?<=[.!?])\s+", content)
        if not sentences:
            return {"summary": content[:max_length], "confidence": 0.5}

        summary = sentences[0][:max_length]
        if len(sentences) > 1 and len(summary) + len(sentences[1]) < max_length:
            summary += " " + sentences[1]
        summary = summary[:max_length]

        keywords = []
        words = re.findall(r"\b[a-zA-Z]{4,}\b", content.lower())
        stopwords = {"this", "that", "with", "from", "they", "have", "been", "were", "about", "when", "what"}
        for w in words:
            if w not in stopwords:
                keywords.append(w)
        from collections import Counter
        top_keywords = [k for k, _ in Counter(keywords).most_common(10)]

        return {"summary": summary.strip(), "original_length": len(content),
                "compression_ratio": f"{len(summary)/len(content)*100:.1f}%" if content else "0%",
                "keywords": top_keywords, "confidence": 0.7}

    async def evict_entry(self, policy: str = "lru", tag: str = "") -> dict[str, Any]:
        if not self._memory_store:
            return {"evicted": None, "reason": "Store is empty"}

        target = None
        if policy == "lru":
            if self._access_count:
                target = min(self._access_count, key=self._access_count.get)
            else:
                target = list(self._memory_store.keys())[0]
        elif policy == "oldest":
            target = min(self._memory_store.items(), key=lambda e: e[1].get("modified", 0))[0]
        elif policy == "by_tag" and tag:
            for key, entry in self._memory_store.items():
                if tag in entry.get("tags", []):
                    target = key
                    break

        if target and target in self._memory_store:
            entry = self._memory_store.pop(target)
            return {"evicted": target, "size_freed": entry.get("size", 0), "policy": policy}
        return {"evicted": None, "reason": "No matching entry"}

    async def check_consistency(self) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        for key, entry in self._memory_store.items():
            if not entry.get("content"):
                issues.append({"key": key, "issue": "empty_content", "severity": "high"})
            if not entry.get("name"):
                issues.append({"key": key, "issue": "missing_name", "severity": "medium"})

        stale_count = sum(1 for e in self._memory_store.values()
                          if time.time() - e.get("modified", 0) > 90 * 86400)
        health = 100 - len(issues) * 10 - stale_count
        return {"total_entries": len(self._memory_store), "issues": issues, "issue_count": len(issues),
                "stale_entries": stale_count, "health_score": max(0, health)}

    async def optimize_store(self) -> dict[str, Any]:
        # Deduplicate
        seen_hashes: dict[str, str] = {}
        duplicates: list[str] = []
        for key, entry in list(self._memory_store.items()):
            h = hashlib.md5(entry.get("content", "").encode()).hexdigest()
            if h in seen_hashes:
                duplicates.append(key)
            else:
                seen_hashes[h] = key

        for dup in duplicates:
            self._memory_store.pop(dup, None)

        # Reindex
        old_index_size = len(self._index)
        self._index.clear()
        for key, entry in self._memory_store.items():
            tags = entry.get("tags", [])
            if tags:
                for tag in tags:
                    self._index.setdefault(tag.lower(), []).append(key)

        return {"before_entries": len(self._memory_store) + len(duplicates),
                "after_entries": len(self._memory_store),
                "duplicates_removed": len(duplicates),
                "index_size_before": old_index_size,
                "index_size_after": len(self._index)}

    @staticmethod
    def _s(props: dict[str, str]) -> dict[str, Any]:
        required = [k for k in props if not k.endswith("?")]
        properties = {}
        for k, v in props.items():
            name = k.rstrip("?")
            type_map = {"string": "string", "int": "integer", "bool": "boolean", "float": "number", "array": "array", "object": "object"}
            properties[name] = {"type": type_map.get(v, "string"), "description": f"The {name} parameter"}
        return {"type": "object", "properties": properties, "required": required}
