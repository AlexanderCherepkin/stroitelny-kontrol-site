import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple


DEFAULT_PLACEHOLDER_PATTERNS = [
    "lorem ipsum",
    "lorem",
    "ipsum",
    "todo",
    "fixme",
    "placeholder",
    "coming soon",
    "sample text",
    "example text",
    "your text here",
    "insert text",
    "content here",
]


DANGEROUS_PATTERNS = [
    (r"\beval\s*\(", "eval() call detected"),
    (r"\bFunction\s*\(\s*['\"]", "Function constructor detected"),
    (r"\.innerHTML\s*\=", "innerHTML assignment detected"),
    (r"\.outerHTML\s*\=", "outerHTML assignment detected"),
    (r"document\.write\s*\(", "document.write() detected"),
    (r"dangerouslySetInnerHTML", "dangerouslySetInnerHTML detected"),
]


SECRET_PATTERNS = [
    (r"(?:password|passwd|pwd)\s*[:=]\s*['\"][^'\"]{4,}['\"]", "hardcoded password-like value"),
    (r"(?:api[_-]?key|apikey)\s*[:=]\s*['\"][^'\"]{8,}['\"]", "hardcoded API key"),
    (r"(?:secret|token)\s*[:=]\s*['\"][^'\"]{8,}['\"]", "hardcoded secret/token"),
    (r"sk-[a-zA-Z0-9]{20,}", "OpenAI-style secret key"),
    (r"ghp_[a-zA-Z0-9]{36}", "GitHub personal access token"),
]


PATH_TRAVERSAL_PATTERNS = [
    (r"\.\./", "relative path traversal in import or string"),
    (r"\.\./\.\.", "deep path traversal in import or string"),
]


@dataclass
class Violation:
    rule: str
    severity: str
    file: str
    line: int
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "file": self.file,
            "line": self.line,
            "message": self.message,
        }


@dataclass
class PlaceholderFinding:
    file: str
    line: int
    match: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "match": self.match,
        }


@dataclass
class ComplianceReport:
    passed: bool
    violations: List[Violation] = field(default_factory=list)
    placeholders: List[PlaceholderFinding] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "violations": [v.to_dict() for v in self.violations],
            "placeholders": [p.to_dict() for p in self.placeholders],
            "summary": self.summary,
        }


def _load_project_rules(path: Path) -> str:
    if not path.exists():
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _is_inside_workspace(file_path: Path, workspace_root: Path) -> bool:
    try:
        file_path.resolve().relative_to(workspace_root.resolve())
        return True
    except ValueError:
        return False


def _extract_text_literals(line: str) -> Iterator[str]:
    for match in re.finditer(r'["\']([^"\']+)["\']', line):
        yield match.group(1)


def _check_placeholders(
    file_path: Path,
    lines: List[str],
    patterns: List[str],
) -> List[PlaceholderFinding]:
    findings: List[PlaceholderFinding] = []
    compiled = [re.compile(re.escape(p), re.IGNORECASE) for p in patterns]
    for line_no, line in enumerate(lines, start=1):
        matched_on_line: List[str] = []
        for text in _extract_text_literals(line):
            for pattern in compiled:
                if pattern.search(text):
                    matched_on_line.append(text)
                    break
        lower = line.lower()
        for raw in DEFAULT_PLACEHOLDER_PATTERNS:
            if raw in lower:
                # Skip raw matches that are already covered by a longer text-literal match.
                if not any(raw in m.lower() for m in matched_on_line):
                    matched_on_line.append(raw)
        # Deduplicate overlapping matches on the same line while preserving case of first hit.
        seen: set = set()
        for match in matched_on_line:
            key = match.lower()
            if key not in seen:
                seen.add(key)
                findings.append(PlaceholderFinding(
                    file=str(file_path),
                    line=line_no,
                    match=match,
                ))
    return findings


def _check_patterns(
    file_path: Path,
    lines: List[str],
    patterns: List[Tuple[str, str]],
    rule: str,
    severity: str,
) -> List[Violation]:
    violations: List[Violation] = []
    for line_no, line in enumerate(lines, start=1):
        for regex, message in patterns:
            if re.search(regex, line):
                violations.append(Violation(
                    rule=rule,
                    severity=severity,
                    file=str(file_path),
                    line=line_no,
                    message=message,
                ))
    return violations


def _check_import_path_safety(file_path: Path, lines: List[str]) -> List[Violation]:
    violations: List[Violation] = []
    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped.startswith("import") and not stripped.startswith("from"):
            continue
        if "../" in stripped:
            violations.append(Violation(
                rule="project_rules.md / filesystem safety",
                severity="critical",
                file=str(file_path),
                line=line_no,
                message="import uses relative path traversal outside the package",
            ))
    return violations


def _check_project_rules(file_path: Path, lines: List[str], rules_text: str) -> List[Violation]:
    violations: List[Violation] = []

    if "No comments" in rules_text and "unless the WHY is non-obvious" in rules_text:
        for line_no, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("//") and not _is_non_obvious_comment(stripped):
                violations.append(Violation(
                    rule="project_rules.md / no comments unless WHY is non-obvious",
                    severity="low",
                    file=str(file_path),
                    line=line_no,
                    message="comment may not explain WHY; consider removing",
                ))

    if "Filenames" in rules_text and "snake_case" in rules_text:
        if not re.match(r"^[a-z0-9_]+\.(tsx?|jsx?|css|scss)$", file_path.name):
            violations.append(Violation(
                rule="project_rules.md / snake_case filenames",
                severity="low",
                file=str(file_path),
                line=0,
                message=f"generated filename '{file_path.name}' does not follow snake_case convention",
            ))

    return violations


def _is_non_obvious_comment(comment: str) -> bool:
    stripped = comment.lstrip("/").strip()
    explainers = ("because", "since", "why", "without this", "needed for", "handles", "avoids", "required")
    return any(stripped.lower().startswith(word) for word in explainers)


def check_file(
    file_path: Path,
    workspace_root: Path,
    rules_text: str,
    placeholder_patterns: Optional[List[str]] = None,
) -> Tuple[List[Violation], List[PlaceholderFinding]]:
    if not _is_inside_workspace(file_path, workspace_root):
        raise ValueError(f"Path outside workspace: {file_path}")

    if not file_path.exists():
        return [], []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except UnicodeDecodeError:
        return [], []

    violations: List[Violation] = []
    placeholders: List[PlaceholderFinding] = []

    patterns = placeholder_patterns or DEFAULT_PLACEHOLDER_PATTERNS
    placeholders.extend(_check_placeholders(file_path, lines, patterns))

    violations.extend(_check_patterns(file_path, lines, DANGEROUS_PATTERNS, "project_rules.md / safety defaults", "critical"))
    violations.extend(_check_patterns(file_path, lines, SECRET_PATTERNS, "project_rules.md / safety defaults", "critical"))
    violations.extend(_check_patterns(file_path, lines, PATH_TRAVERSAL_PATTERNS, "project_rules.md / filesystem safety", "critical"))
    violations.extend(_check_import_path_safety(file_path, lines))
    violations.extend(_check_project_rules(file_path, lines, rules_text))

    return violations, placeholders


def run_compliance_check(
    code_paths: List[str],
    rules_path: str = "project_rules.md",
    workspace_root: Optional[str] = None,
    placeholder_patterns: Optional[List[str]] = None,
    severity_threshold: str = "low",
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    workspace = Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()
    rules_file = Path(rules_path).resolve()
    rules_text = _load_project_rules(rules_file)

    severity_rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    threshold = severity_rank.get(severity_threshold, 0)

    all_violations: List[Violation] = []
    all_placeholders: List[PlaceholderFinding] = []
    scanned_files: List[str] = []
    skipped_files: List[str] = []

    for path_str in code_paths:
        path = Path(path_str).resolve()
        try:
            if not _is_inside_workspace(path, workspace):
                all_violations.append(Violation(
                    rule="workspace boundary",
                    severity="critical",
                    file=path_str,
                    line=0,
                    message="file path outside workspace root",
                ))
                skipped_files.append(str(path))
                continue
            violations, placeholders = check_file(
                path,
                workspace,
                rules_text,
                placeholder_patterns,
            )
            all_violations.extend(violations)
            all_placeholders.extend(placeholders)
            scanned_files.append(str(path))
        except ValueError:
            skipped_files.append(str(path))
            all_violations.append(Violation(
                rule="workspace boundary",
                severity="critical",
                file=path_str,
                line=0,
                message="file path outside workspace root",
            ))

    critical_count = sum(1 for v in all_violations if v.severity == "critical")
    high_count = sum(1 for v in all_violations if v.severity == "high")
    medium_count = sum(1 for v in all_violations if v.severity == "medium")
    low_count = sum(1 for v in all_violations if v.severity == "low")

    blocking = any(
        severity_rank.get(v.severity, 0) >= threshold
        for v in all_violations
    )
    passed = not blocking and not all_placeholders

    report = ComplianceReport(
        passed=passed,
        violations=all_violations,
        placeholders=all_placeholders,
        summary={
            "scanned_files": scanned_files,
            "skipped_files": skipped_files,
            "violations_by_severity": {
                "critical": critical_count,
                "high": high_count,
                "medium": medium_count,
                "low": low_count,
            },
            "total_violations": len(all_violations),
            "total_placeholders": len(all_placeholders),
        },
    )

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)

    return report.to_dict()


def main() -> None:
    parser = argparse.ArgumentParser(description="Project Rules Compliance Checker for generated code")
    parser.add_argument("--files", nargs="+", required=True, help="Generated files to check")
    parser.add_argument("--rules", default="project_rules.md", help="Path to project_rules.md")
    parser.add_argument("--workspace-root", default=None, help="Workspace root for path traversal guard")
    parser.add_argument("--severity-threshold", default="low", choices=["low", "medium", "high", "critical"], help="Minimum severity that blocks compliance")
    parser.add_argument("--output", default="compliance_report.json", help="Path to write JSON report")
    parser.add_argument(
        "--placeholder-patterns",
        default=None,
        help="Comma-separated list of additional placeholder patterns",
    )
    args = parser.parse_args()

    extra_patterns = None
    if args.placeholder_patterns:
        extra_patterns = [p.strip().lower() for p in args.placeholder_patterns.split(",") if p.strip()]

    result = run_compliance_check(
        code_paths=args.files,
        rules_path=args.rules,
        workspace_root=args.workspace_root,
        placeholder_patterns=extra_patterns,
        severity_threshold=args.severity_threshold,
        output_path=args.output,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
