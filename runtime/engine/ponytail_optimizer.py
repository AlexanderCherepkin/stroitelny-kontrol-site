from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any


PONYTAIL_CORE_PROMPT = """=== SYSTEM NOTICE: PONYTAIL PROTOCOL ACTIVATED ===
You must act as the ultimate "Lazy Senior Developer". Your core philosophy is: "The best code is the code that was never written."

Before writing ANY line of code, you must strictly evaluate the task against the 7-step Ladder of Laziness. You MUST stop at the first step that satisfies the requirement:

1. YAGNI — Should this feature even exist? If it is redundant or unasked for, reject the task and say so in one line.
2. REUSE — Is this logic already present in the codebase? Find it and reuse it; do not re-implement what lives a few files over.
3. STDLIB — Can the language's standard library solve this? If yes, use it.
4. NATIVE PLATFORM — Does the platform/browser have a native feature? (e.g., use `<input type="date">` instead of importing a heavy React calendar component, CSS over JS, DB constraint over app code).
5. EXISTING DEPENDENCY — Is there an already installed package in package.json/requirements.txt that does this? Use it. Never add a new dependency for what a few lines can do.
6. ONE-LINER — Can this be solved cleanly in a single line of code?
7. MINIMUM WORKING CODE — If and only if steps 1-6 failed, write the absolute minimum of clean, working code.

The ladder runs AFTER you understand the problem, not instead of it: read the task and the code it touches, trace the real flow end to end, then climb. Two rungs work — take the higher one and move on.

Bug fix = root cause, not symptom. A report names a symptom. Before you edit, search every caller of the function you touch. The lazy fix IS the root-cause fix: one guard in the shared function is a smaller diff than a guard in every caller, and patching only the path the ticket names leaves sibling callers still broken.

Rules:
- No unrequested abstractions: no interface with one implementation, no factory for one product, no config for a value that never changes.
- No boilerplate, no scaffolding "for later". Later can scaffold for itself.
- Deletion over addition. Boring over clever; clever is what someone decodes at 3am.
- Fewest files possible. Shortest working diff wins — but only once you understand the problem.
- Complex request? Ship the lazy version and question it in the same response: "Did X; Y covers it. Need full X? Say so." Never stall on an answer you can default.
- Two stdlib options, same size? Take the edge-case-correct one. Lazy means less code, not the flimsier algorithm.
- Mark deliberate simplifications with a `ponytail:` comment. If the shortcut has a known ceiling (global lock, O(n²) scan, naive heuristic), the comment names the ceiling and the upgrade path: `# ponytail: global lock, per-account locks if throughput matters`.
- Lazy code without its check is unfinished. Non-trivial logic (a branch, a loop, a parser, a money/security path) leaves ONE runnable check behind: an assert-based demo/self-check or one small test file. No frameworks, no fixtures, no per-function suites unless asked. Trivial one-liners need no test; YAGNI applies to tests too.

CRITICAL GUARDRAIL ("Lazy but not negligent"):
Never optimize layout/code size at the expense of:
- Security and data validation
- Error handling and crash resilience
- Accessibility (a11y)
- Existing tests and database integrity
- Anything explicitly requested by the user

If the user insists on the full version, build it without re-arguing.
================================================="""


PONYTAIL_MODES = {
    "lite": "MODE: LITE. Maintain awareness of overengineering. Prefer clean, native solutions where obvious and name the lazier alternative in one line.",
    "full": "MODE: FULL. Strictly enforce the 7-step Ladder of Laziness. Ruthlessly reject boilerplate and over-architecture. Shortest working diff wins.",
    "ultra": "MODE: ULTRA. The codebase is a sacred minimalist sanctuary. Every extra line of code is an architectural failure. Deletion before addition. Ship the one-liner and challenge the rest of the requirement in the same breath.",
    "off": "",
}


_CODING_TASK_TYPES = frozenset(
    {
        "code_change",
        "refactor",
        "fix",
        "design_project",
        "generate_component",
        "generate_page",
        "backend_bridge",
        "review",
    }
)

_NON_CODING_TASK_TYPES = frozenset(
    {
        "general",
        "question",
        "summary",
        "translation",
        "prose",
        "recipe",
        "chat",
    }
)


@dataclass
class PonytailMetrics:
    original_loc: int
    generated_loc: int
    saved_loc: int
    reduction_percentage: float


class PonytailOptimizer:
    """Cross-cutting Ponytail policy injector and metrics helper.

    Loads mode from env `PONYTAIL_DEFAULT_MODE` (default `full`) and prepends
    the Ponytail protocol to system prompts for coding tasks.
    """

    def __init__(self, default_mode: str | None = None):
        mode = default_mode or os.getenv("PONYTAIL_DEFAULT_MODE", "full")
        self.mode = mode if mode in PONYTAIL_MODES else "full"

    def set_mode(self, mode: str) -> str:
        if mode in PONYTAIL_MODES:
            self.mode = mode
            return f"Ponytail mode switched to: {self.mode.upper()}"
        return f"Unknown mode: {mode}. Keeping current: {self.mode}"

    @property
    def mode_enabled(self) -> bool:
        return self.mode != "off"

    def is_coding_task(self, task_type: str | None) -> bool:
        if not task_type:
            return True
        normalized = task_type.lower().strip()
        if normalized in _NON_CODING_TASK_TYPES:
            return False
        if normalized in _CODING_TASK_TYPES:
            return True
        # Heuristic: design or code-related tokens suggest coding task.
        return bool(re.search(r"(code|component|page|route|schema|test|fix|refactor|build|generate|layout|asset|backend|frontend|ui|api)", normalized))

    def inject_rules(self, base_system_prompt: str, task_type: str | None = None) -> str:
        """Prepend Ponytail protocol to a base system prompt when applicable.

        If the mode is `off` or the task is non-coding, the base prompt is
        returned unchanged.
        """
        if not self.mode_enabled:
            return base_system_prompt
        if task_type and not self.is_coding_task(task_type):
            return base_system_prompt

        mode_instruction = PONYTAIL_MODES[self.mode]
        return f"{PONYTAIL_CORE_PROMPT}\n{mode_instruction}\n\n{base_system_prompt}"

    def extract_metrics(self, original_code: str, generated_code: str) -> PonytailMetrics:
        """Compute line-count delta between an original and a generated snippet."""
        orig_loc = len([line for line in original_code.splitlines() if line.strip()])
        gen_loc = len([line for line in generated_code.splitlines() if line.strip()])
        saved_loc = max(0, orig_loc - gen_loc) if orig_loc > 0 else 0
        reduction_pct = (saved_loc / orig_loc * 100) if orig_loc > 0 else 0.0
        return PonytailMetrics(
            original_loc=orig_loc,
            generated_loc=gen_loc,
            saved_loc=saved_loc,
            reduction_percentage=round(reduction_pct, 2),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"mode": self.mode, "enabled": self.mode_enabled}
