from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class MemoryType(str, Enum):
    USER = "user"
    FEEDBACK = "feedback"
    PROJECT = "project"
    REFERENCE = "reference"


class StateScope(str, Enum):
    SESSION = "session"
    AGENT = "agent"
    PIPELINE = "pipeline"
    SYSTEM = "system"
    USER_PROFILE = "user_profile"


class ExecutionMode(str, Enum):
    SYNC = "sync"
    ASYNC = "async"
    FIRE_AND_FORGET = "fire_and_forget"
    BATCH = "batch"


@dataclass
class Parameter:
    name: str
    type_hint: str
    description: str = ""


@dataclass
class ContractSpec:
    receives: list[Parameter] = field(default_factory=list)
    returns: list[Parameter] = field(default_factory=list)
    side_effects: list[str] = field(default_factory=list)


@dataclass
class DecisionStep:
    number: int
    title: str
    description: str


@dataclass
class FailureMode:
    condition: str
    response: str


@dataclass
class AgentSpec:
    name: str
    role: str
    contract: ContractSpec = field(default_factory=ContractSpec)
    decision_flow: list[DecisionStep] = field(default_factory=list)
    failure_modes: list[FailureMode] = field(default_factory=list)
    source_path: Path | None = None

    def to_system_prompt(self) -> str:
        parts: list[str] = []

        if self.name:
            parts.append(f"You are the **{self.name}** agent.")
        if self.role:
            parts.append(f"\n## Your Role\n{self.role}")

        if self.contract.receives:
            parts.append("\n## Input Contract\nYou will receive:")
            for p in self.contract.receives:
                parts.append(f"- `{p.name}`: {p.type_hint} — {p.description}")

        if self.contract.returns:
            parts.append("\n## Output Contract\nYou must return:")
            for p in self.contract.returns:
                parts.append(f"- `{p.name}`: {p.type_hint} — {p.description}")

        if self.contract.side_effects:
            parts.append("\n## Allowed Side Effects")
            for s in self.contract.side_effects:
                parts.append(f"- {s}")

        if self.decision_flow:
            parts.append("\n## Decision Flow\nFollow these steps in order:")
            for step in self.decision_flow:
                parts.append(f"{step.number}. **{step.title}** — {step.description}")

        if self.failure_modes:
            parts.append("\n## Failure Modes\nIf something goes wrong, respond according to this table:")
            for fm in self.failure_modes:
                parts.append(f"- When `{fm.condition}` → {fm.response}")

        parts.append("\n## Output Format\nReturn a JSON object matching the Output Contract above. No extra text outside the JSON.")
        return "\n".join(parts)

    def to_input_message(self, inputs: dict[str, Any]) -> str:
        lines = ["Execute your Decision Flow with the following inputs:"]
        for key, value in inputs.items():
            lines.append(f"\n**{key}**: {value}")
        return "\n".join(lines)
