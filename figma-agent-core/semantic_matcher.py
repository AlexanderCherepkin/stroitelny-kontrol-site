from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _normalize_text(text: Optional[str]) -> str:
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"[^\w\s]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _tokenize(text: str) -> List[str]:
    return [t for t in _normalize_text(text).split() if t]


def _ngram_set(tokens: List[str], n: int = 2) -> set:
    return set(" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1))


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _levenshtein_ratio(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    m, n = len(a), len(b)
    prev = list(range(n + 1))
    curr = [0] * (n + 1)
    for i in range(1, m + 1):
        curr[0] = i
        for j in range(1, n + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev, curr = curr, prev
    distance = prev[n]
    return 1.0 - distance / max(m, n)


def _field_weight(field: str) -> float:
    weights = {
        "name": 1.0,
        "export_name": 1.0,
        "file_path": 0.3,
        "description": 0.8,
        "contexts": 0.7,
        "props": 0.6,
        "tags": 0.9,
        "doc": 0.7,
    }
    return weights.get(field, 0.4)


def _semantic_score(figma_features: Dict[str, str], candidate_features: Dict[str, str]) -> Tuple[float, Dict[str, float]]:
    """Compute weighted semantic similarity between two feature dictionaries."""
    per_field: Dict[str, float] = {}
    total_weight = 0.0
    score = 0.0
    all_fields = set(figma_features.keys()) | set(candidate_features.keys())
    for field in all_fields:
        figma_text = figma_features.get(field, "")
        cand_text = candidate_features.get(field, "")
        if not figma_text or not cand_text:
            continue
        weight = _field_weight(field)
        figma_tokens = _tokenize(figma_text)
        cand_tokens = _tokenize(cand_text)
        if not figma_tokens or not cand_tokens:
            continue
        # Combine token-overlap, bigram Jaccard, and normalized edit distance.
        token_sim = len(set(figma_tokens) & set(cand_tokens)) / max(len(figma_tokens), len(cand_tokens))
        ngram_sim = _jaccard(_ngram_set(figma_tokens), _ngram_set(cand_tokens))
        edit_sim = _levenshtein_ratio(" ".join(figma_tokens), " ".join(cand_tokens))
        field_score = max(token_sim, ngram_sim, edit_sim)
        per_field[field] = field_score
        score += field_score * weight
        total_weight += weight
    if total_weight == 0.0:
        return 0.0, per_field
    return round(score / total_weight, 4), per_field


class SemanticIndex:
    """Index existing design-system artifacts for semantic matching."""

    def __init__(self, components: Optional[List[Dict[str, Any]]] = None, tokens: Optional[List[Dict[str, Any]]] = None):
        self.components: List[Dict[str, Any]] = components or []
        self.tokens: List[Dict[str, Any]] = tokens or []

    @classmethod
    def from_component_registry(cls, registry: Dict[str, Any]) -> "SemanticIndex":
        components: List[Dict[str, Any]] = []
        for eid, entry in registry.get("local_components", {}).items():
            description = entry.get("description") or entry.get("doc", "")
            tags = " ".join(entry.get("tags", []))
            features = {
                "export_name": entry.get("export_name", ""),
                "name": entry.get("export_name", ""),
                "file_path": entry.get("file_path", ""),
                "description": description,
                "doc": description,
                "tags": tags,
                "props": " ".join(entry.get("props", {}).keys()),
            }
            components.append({"key": eid, "features": features, "entry": entry})
        return cls(components=components)

    @classmethod
    def from_token_registry(cls, registry: Dict[str, Any]) -> "SemanticIndex":
        tokens: List[Dict[str, Any]] = []
        for name, token in registry.get("colors", {}).items():
            features = {
                "name": name,
                "description": token.get("description", ""),
                "contexts": " ".join(token.get("contexts", [])),
            }
            tokens.append({"key": name, "features": features, "entry": token})
        return cls(tokens=tokens)

    @classmethod
    def load(cls, path: Path | str) -> "SemanticIndex":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            components=data.get("components", []),
            tokens=data.get("tokens", []),
        )

    def save(self, path: Path | str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(
            json.dumps(
                {"components": self.components, "tokens": self.tokens},
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def match_component(
        self,
        figma_entry: Dict[str, Any],
        threshold: float = 0.5,
    ) -> Tuple[Optional[Dict[str, Any]], float, str]:
        """Return best matching existing component, score, and reason."""
        figma_features = self._figma_component_features(figma_entry)
        best: Optional[Dict[str, Any]] = None
        best_score = 0.0
        best_reason = ""
        for candidate in self.components:
            score, per_field = _semantic_score(figma_features, candidate.get("features", {}))
            if score > best_score:
                best_score = score
                best = candidate
                matched = sorted(
                    [f"{k}({v:.2f})" for k, v in per_field.items() if v >= 0.5],
                    key=lambda s: float(s.split("(")[1].rstrip(")")),
                    reverse=True,
                )
                best_reason = f"Semantic match via {', '.join(matched)}" if matched else "Weak semantic match"
        if best_score < threshold:
            return None, best_score, best_reason
        return best, best_score, best_reason

    def match_token(
        self,
        figma_features: Dict[str, str],
        threshold: float = 0.5,
    ) -> Tuple[Optional[str], float, str]:
        best_key: Optional[str] = None
        best_score = 0.0
        best_reason = ""
        for candidate in self.tokens:
            score, per_field = _semantic_score(figma_features, candidate.get("features", {}))
            if score > best_score:
                best_score = score
                best_key = candidate.get("key")
                matched = sorted(
                    [f"{k}({v:.2f})" for k, v in per_field.items() if v >= 0.5],
                    key=lambda s: float(s.split("(")[1].rstrip(")")),
                    reverse=True,
                )
                best_reason = f"Semantic token match via {', '.join(matched)}" if matched else "Weak token match"
        if best_score < threshold:
            return None, best_score, best_reason
        return best_key, best_score, best_reason

    @staticmethod
    def _figma_component_features(entry: Dict[str, Any]) -> Dict[str, str]:
        props = entry.get("variant_properties", {})
        return {
            "name": entry.get("name", ""),
            "export_name": entry.get("pascal_name", ""),
            "description": entry.get("description", ""),
            "props": " ".join(props.keys()),
        }


class SemanticMatcher:
    """High-level matcher used by registry/token builders."""

    def __init__(self, index: SemanticIndex, threshold: float = 0.5):
        self.index = index
        self.threshold = threshold

    def find_local_component(
        self,
        figma_entry: Dict[str, Any],
    ) -> Tuple[Optional[Dict[str, Any]], float, str]:
        return self.index.match_component(figma_entry, threshold=self.threshold)

    def find_token(
        self,
        figma_name: str,
        description: str = "",
        contexts: str = "",
    ) -> Tuple[Optional[str], float, str]:
        features = {
            "name": figma_name,
            "description": description,
            "contexts": contexts,
        }
        return self.index.match_token(features, threshold=self.threshold)
