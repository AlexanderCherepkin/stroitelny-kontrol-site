from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ModelTier(str, Enum):
    """Model tiers for different task complexity levels."""
    HAWAII = "claude-haiku-4-5"        # Fast, cheap — simple I/O, formatting
    SONNET = "claude-sonnet-4-6"       # Balanced — analysis, planning
    OPUS = "claude-opus-4-7"           # Powerful — complex reasoning, architecture


@dataclass
class ContextBudget:
    """Token budget for an isolated worker context window."""
    max_input_tokens: int = 8000
    max_output_tokens: int = 4096
    max_summary_tokens: int = 1000
    input_tokens_used: int = 0
    output_tokens_used: int = 0
    summary_tokens_used: int = 0

    @property
    def remaining_input(self) -> int:
        return max(0, self.max_input_tokens - self.input_tokens_used)

    @property
    def remaining_output(self) -> int:
        return max(0, self.max_output_tokens - self.output_tokens_used)

    @property
    def is_exhausted(self) -> bool:
        return self.remaining_input <= 0 or self.remaining_output <= 0

    def consume_input(self, tokens: int):
        self.input_tokens_used += tokens

    def consume_output(self, tokens: int):
        self.output_tokens_used += tokens

    def reset(self):
        self.input_tokens_used = 0
        self.output_tokens_used = 0


@dataclass
class IsolatedContext:
    """An isolated context window for a single agent invocation."""
    worker_id: str
    budget: ContextBudget = field(default_factory=ContextBudget)
    model: str = ModelTier.HAWAII.value
    data_retained: dict[str, Any] = field(default_factory=dict)

    def can_accept(self, tokens_needed: int) -> bool:
        return self.budget.remaining_input >= tokens_needed


class ContextIsolator:
    """Manages isolated context windows for worker processes.

    Each worker gets its own ContextBudget. Raw data from tool execution
    stays inside the worker's process. Only the summary returns to the parent.

    This prevents context pollution — the main orchestrator never sees
    the 50 files a search agent read or the 10,000 rows a DB agent queried.
    """

    # Model assignment by task category
    TASK_MODEL_MAP = {
        "read": ModelTier.HAWAII,       # Simple I/O — fast model
        "search": ModelTier.HAWAII,     # Pattern matching — fast model
        "replace": ModelTier.HAWAII,    # Text editing — fast model
        "runcom": ModelTier.HAWAII,     # Command execution — fast model
        "runtest": ModelTier.SONNET,    # Test analysis — needs reasoning
        "terminal": ModelTier.HAWAII,   # Terminal I/O — fast model
        "manangr": ModelTier.SONNET,    # Project analysis — needs reasoning
        "database": ModelTier.SONNET,   # Query analysis — needs reasoning
        "web": ModelTier.HAWAII,         # HTTP requests — fast model
        "memory": ModelTier.SONNET,     # Memory operations — needs reasoning
        "planning": ModelTier.SONNET,   # Planning — balanced
        "execution": ModelTier.SONNET,  # Execution coordination — balanced
        "safety": ModelTier.HAWAII,     # Safety checks — fast
        "validation": ModelTier.HAWAII, # Validation — fast
        "self_correction": ModelTier.OPUS,  # Self-correction — complex reasoning
    }

    # Token budgets by task complexity
    BUDGET_PRESETS = {
        "light": ContextBudget(max_input_tokens=4000, max_output_tokens=2048, max_summary_tokens=500),
        "normal": ContextBudget(max_input_tokens=8000, max_output_tokens=4096, max_summary_tokens=1000),
        "heavy": ContextBudget(max_input_tokens=16000, max_output_tokens=8192, max_summary_tokens=2000),
    }

    def __init__(self):
        self._active_contexts: dict[str, IsolatedContext] = {}
        self._global_budget = 200_000  # Total token budget across all workers
        self._global_used = 0

    def create_context(self, worker_id: str, task_category: str = "read",
                       complexity: str = "normal") -> IsolatedContext:
        model = self.TASK_MODEL_MAP.get(task_category, ModelTier.HAWAII)
        budget_template = self.BUDGET_PRESETS.get(complexity, self.BUDGET_PRESETS["normal"])
        budget = ContextBudget(
            max_input_tokens=budget_template.max_input_tokens,
            max_output_tokens=budget_template.max_output_tokens,
            max_summary_tokens=budget_template.max_summary_tokens,
        )

        ctx = IsolatedContext(worker_id=worker_id, budget=budget, model=model.value)
        self._active_contexts[worker_id] = ctx
        return ctx

    def destroy_context(self, worker_id: str):
        ctx = self._active_contexts.pop(worker_id, None)
        if ctx:
            self._global_used += ctx.budget.input_tokens_used + ctx.budget.output_tokens_used

    def get_model_for_task(self, task_category: str) -> str:
        tier = self.TASK_MODEL_MAP.get(task_category, ModelTier.HAWAII)
        return tier.value

    def get_budget_for_complexity(self, complexity: str) -> ContextBudget:
        preset = self.BUDGET_PRESETS.get(complexity, self.BUDGET_PRESETS["normal"])
        return ContextBudget(
            max_input_tokens=preset.max_input_tokens,
            max_output_tokens=preset.max_output_tokens,
            max_summary_tokens=preset.max_summary_tokens,
        )

    def estimate_tokens(self, text: str) -> int:
        """Rough token estimation: ~4 chars per token for English text."""
        return max(1, len(text) // 4)

    def is_within_global_budget(self, tokens_needed: int) -> bool:
        return (self._global_used + tokens_needed) <= self._global_budget

    @property
    def active_workers(self) -> int:
        return len(self._active_contexts)

    @property
    def global_usage_pct(self) -> float:
        return (self._global_used / self._global_budget * 100) if self._global_budget > 0 else 0.0
