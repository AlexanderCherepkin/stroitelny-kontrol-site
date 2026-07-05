from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SafetyLevel(str, Enum):
    CLEAR = "clear"
    WARNING = "warning"
    PAUSED = "paused"
    ABORTED = "aborted"


class SafetyVerdict(str, Enum):
    PROCEED = "proceed"
    RESUME_WITH_LIMITS = "resume_with_limits"
    ABORT_AND_REPORT = "abort_and_report"
    ESCALATE_TO_HUMAN = "escalate_to_human"


@dataclass
class GuardrailRule:
    name: str
    description: str
    severity: SafetyLevel
    evaluate: Any  # callable that returns bool when rule is triggered


@dataclass
class TriggeredRule:
    rule: GuardrailRule
    evidence: str
    severity: SafetyLevel


@dataclass
class SafetyResult:
    level: SafetyLevel
    verdict: SafetyVerdict
    triggered_rules: list[TriggeredRule] = field(default_factory=list)
    mitigations: list[str] = field(default_factory=list)


class SafetyChain:
    FORBIDDEN_PATTERNS = [
        (r"rm\s+-rf\s+/", SafetyLevel.ABORTED, "Recursive root deletion attempt"),
        (r"DROP\s+(TABLE|DATABASE)", SafetyLevel.PAUSED, "Database destruction command"),
        (r"curl.*\|\s*(ba)?sh", SafetyLevel.ABORTED, "Pipe-to-shell pattern"),
        (r"eval\s+", SafetyLevel.WARNING, "Dynamic code evaluation"),
        (r"sudo\s+", SafetyLevel.PAUSED, "Privilege escalation attempt"),
        (r"/etc/(passwd|shadow)", SafetyLevel.ABORTED, "Access to system auth files"),
        (r"\.env", SafetyLevel.WARNING, "Access to environment secrets"),
    ]

    FORBIDDEN_PATHS = [
        "/etc/", "/proc/", "/sys/", "C:\\Windows\\System32\\",
    ]

    def __init__(self, live_risk_threshold: float = 0.6):
        self.live_risk_threshold = live_risk_threshold
        self._rules = self._build_rules()

    def _build_rules(self) -> list[GuardrailRule]:
        rules: list[GuardrailRule] = []
        for pattern, severity, desc in self.FORBIDDEN_PATTERNS:
            rules.append(GuardrailRule(
                name=f"forbidden_pattern:{desc}",
                description=desc,
                severity=severity,
                evaluate=lambda text, p=pattern: bool(re.search(p, str(text), re.IGNORECASE)),
            ))
        return rules

    def pre_check(self, user_input: str) -> SafetyResult:
        triggered: list[TriggeredRule] = []

        for rule in self._rules:
            try:
                if rule.evaluate(user_input):
                    triggered.append(TriggeredRule(rule=rule, evidence=f"Matched pattern in input", severity=rule.severity))
            except Exception:
                continue

        for path in self.FORBIDDEN_PATHS:
            if path.lower() in str(user_input).lower():
                triggered.append(TriggeredRule(
                    rule=GuardrailRule(name="forbidden_path", description=f"Access to {path}", severity=SafetyLevel.ABORTED,
                                       evaluate=lambda x: True),
                    evidence=f"Path reference: {path}",
                    severity=SafetyLevel.ABORTED,
                ))

        return self._compute_result(triggered)

    def post_check(self, output: str) -> SafetyResult:
        triggered: list[TriggeredRule] = []

        sensitive_patterns = [
            (r"api[_-]?key[:=]\s*\S+", "API key in output"),
            (r"token[:=]\s*\S+", "Token in output"),
            (r"password[:=]\s*\S+", "Password in output"),
            (r"secret[:=]\s*\S+", "Secret in output"),
        ]
        for pattern, desc in sensitive_patterns:
            if re.search(pattern, str(output), re.IGNORECASE):
                triggered.append(TriggeredRule(
                    rule=GuardrailRule(name="sensitive_data_leak", description=desc, severity=SafetyLevel.ABORTED,
                                       evaluate=lambda x: True),
                    evidence=f"Pattern: {pattern}",
                    severity=SafetyLevel.ABORTED,
                ))

        return self._compute_result(triggered)

    def check_content(self, content: str) -> SafetyResult:
        triggered: list[TriggeredRule] = []

        suspicious = [
            (r"<script[^>]*>", "XSS attempt"),
            (r"javascript\s*:\s*", "JS injection"),
            (r"onerror\s*=", "Event handler injection"),
        ]
        for pattern, desc in suspicious:
            if re.search(pattern, str(content), re.IGNORECASE):
                triggered.append(TriggeredRule(
                    rule=GuardrailRule(name="xss", description=desc, severity=SafetyLevel.ABORTED,
                                       evaluate=lambda x: True),
                    evidence=f"Pattern: {pattern}",
                    severity=SafetyLevel.ABORTED,
                ))

        return self._compute_result(triggered)

    def _compute_result(self, triggered: list[TriggeredRule]) -> SafetyResult:
        if not triggered:
            return SafetyResult(level=SafetyLevel.CLEAR, verdict=SafetyVerdict.PROCEED)

        severities = {r.severity for r in triggered}
        mitigations: list[str] = []

        if SafetyLevel.ABORTED in severities:
            return SafetyResult(
                level=SafetyLevel.ABORTED,
                verdict=SafetyVerdict.ABORT_AND_REPORT,
                triggered_rules=triggered,
                mitigations=["Operation aborted", "Preserved state before abort"],
            )

        if SafetyLevel.PAUSED in severities:
            return SafetyResult(
                level=SafetyLevel.PAUSED,
                verdict=SafetyVerdict.RESUME_WITH_LIMITS,
                triggered_rules=triggered,
                mitigations=["Execution paused", "Requesting plan adjustment"],
            )

        return SafetyResult(
            level=SafetyLevel.WARNING,
            verdict=SafetyVerdict.PROCEED,
            triggered_rules=triggered,
            mitigations=["Warnings logged for review"],
        )
