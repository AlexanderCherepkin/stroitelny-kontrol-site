import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


DEFAULT_MAX_ITERATIONS = 3
DEFAULT_DIFF_SCORE_THRESHOLD = 0.05


@dataclass
class RefinementReport:
    status: str
    iterations: int
    final_visual_qa: Optional[Dict[str, Any]] = None
    adjustments: List[Dict[str, Any]] = field(default_factory=list)
    escalation_reason: Optional[str] = None
    max_iterations: int = DEFAULT_MAX_ITERATIONS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "iterations": self.iterations,
            "max_iterations": self.max_iterations,
            "final_visual_qa": self.final_visual_qa,
            "adjustments": self.adjustments,
            "escalation_reason": self.escalation_reason,
        }


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _visual_qa_needs_refinement(report: Dict[str, Any], diff_threshold: float) -> bool:
    status = report.get("status")
    if status == "blocked":
        return True
    if status != "passed":
        return True
    diff_score = report.get("diff_score")
    if diff_score is not None and diff_score > diff_threshold:
        return True
    for assertion in report.get("dom_assertions", []):
        if not assertion.get("passed", True):
            return True
    for check in report.get("layout_checks", []):
        if not check.get("passed", True):
            return True
    bbox_comparison = report.get("bbox_comparison", {})
    if bbox_comparison.get("failed", 0) > 0:
        return True
    if report.get("discrepancies"):
        return True
    return False


def _qa_score(report: Dict[str, Any]) -> Optional[float]:
    """Возвращает нормализованный score: diff_score, или drift px, или число failed checks."""
    diff_score = report.get("diff_score")
    if diff_score is not None:
        return float(diff_score)
    pixel_metrics = report.get("pixel_metrics", {})
    drift = pixel_metrics.get("total_drift_px")
    if drift is not None:
        return float(drift)
    failed_checks = sum(1 for c in report.get("layout_checks", []) if not c.get("passed", True))
    failed_assertions = sum(1 for a in report.get("dom_assertions", []) if not a.get("passed", True))
    return float(failed_checks + failed_assertions) if (failed_checks or failed_assertions) else None


def _apply_layout_adjustments(
    ast: Dict[str, Any],
    report: Dict[str, Any],
) -> List[Dict[str, Any]]:
    adjustments: List[Dict[str, Any]] = []
    root = ast.get("root", ast)

    for assertion in report.get("dom_assertions", []):
        if assertion.get("passed", True):
            continue
        selector = assertion.get("expected", {}).get("selector", "")
        expected_count = assertion.get("expected", {}).get("expected_count")
        actual_count = assertion.get("actual", {}).get("count")
        if expected_count is not None and actual_count is not None and actual_count < expected_count:
            adjustments.append({
                "type": "add_node",
                "selector": selector,
                "reason": f"expected {expected_count}, found {actual_count}",
            })

    for discrepancy in report.get("discrepancies", []):
        text = str(discrepancy).lower()
        if "size" in text or "screenshot" in text or "normalize" in text:
            adjustments.append({
                "type": "size_adjustment",
                "reason": discrepancy,
            })
        if "navigation" in text or "load" in text:
            adjustments.append({
                "type": "fallback",
                "reason": discrepancy,
            })
        if "padding" in text or "gap" in text or "spacing" in text:
            root_classes = root.get("classes", [])
            if not any(c.startswith("p-") for c in root_classes):
                root_classes.append("p-4")
                adjustments.append({
                    "type": "padding",
                    "reason": discrepancy,
                })
        if "font" in text or "text" in text:
            root_classes = root.get("classes", [])
            if "text-base" not in root_classes:
                root_classes.append("text-base")
                adjustments.append({
                    "type": "typography",
                    "reason": discrepancy,
                })

    diff_score = report.get("diff_score")
    if diff_score is not None and diff_score > DEFAULT_DIFF_SCORE_THRESHOLD:
        root_classes = root.get("classes", [])
        if "bg-white" not in root_classes:
            root_classes.append("bg-white")
        adjustments.append({
            "type": "background",
            "reason": f"diff score {diff_score} above threshold",
        })

    for check in report.get("layout_checks", []):
        if check.get("passed", True):
            continue
        check_type = check.get("type")
        figma_id = _extract_figma_id(check)
        node = _find_node_by_figma_id(root, figma_id) if figma_id else root
        classes = node.setdefault("classes", [])

        if check_type == "overflow":
            if check.get("overflow_y") and "overflow-y-hidden" not in classes and "overflow-hidden" not in classes:
                classes.append("overflow-hidden")
            if check.get("overflow_x") and "overflow-x-hidden" not in classes and "overflow-hidden" not in classes:
                classes.append("overflow-hidden")
            if "h-full" in classes:
                classes.remove("h-full")
                classes.append("h-auto")
            adjustments.append({
                "type": "overflow_fix",
                "figma_id": figma_id,
                "reason": _check_reason(check),
            })
        elif check_type == "clipped_text":
            for cls in ("whitespace-normal", "break-words"):
                if cls not in classes:
                    classes.append(cls)
            if "line-clamp-3" not in classes:
                classes.append("line-clamp-3")
            adjustments.append({
                "type": "clipped_text_fix",
                "figma_id": figma_id,
                "reason": _check_reason(check),
            })
        elif check_type == "overlap":
            if "flex-col" not in classes and "flex" not in classes:
                classes.append("flex")
                classes.append("flex-col")
            if not any(c.startswith("gap-") for c in classes):
                classes.append("gap-4")
            adjustments.append({
                "type": "overlap_fix",
                "figma_id": figma_id,
                "reason": _check_reason(check),
            })
        elif check_type == "bbox_mismatch":
            page = check.get("page") or {}
            figma = check.get("figma") or {}
            page_w = page.get("width", 0)
            figma_w = figma.get("width", 0)
            page_h = page.get("height", 0)
            figma_h = figma.get("height", 0)
            exact_adjusted = False
            if figma_w and abs(page_w - figma_w) > 2:
                _replace_size_class(classes, "w", figma_w)
                exact_adjusted = True
            if figma_h and abs(page_h - figma_h) > 2:
                _replace_size_class(classes, "h", figma_h)
                exact_adjusted = True
            if not exact_adjusted and figma_w and page_w > figma_w + 8 and "w-full" in classes:
                classes.remove("w-full")
                classes.append(f"w-[{figma_w}px]")
            if "p-4" not in classes and not any(c.startswith("p-") for c in classes):
                classes.append("p-4")
            adjustments.append({
                "type": "bbox_fix",
                "figma_id": figma_id,
                "reason": _check_reason(check),
                "exact_size": exact_adjusted,
            })
        elif check_type == "bbox_missing":
            adjustments.append({
                "type": "bbox_missing",
                "figma_id": figma_id,
                "reason": _check_reason(check),
            })
        elif check_type == "font_mismatch":
            page = check.get("page") or {}
            mismatches = check.get("mismatches", [])
            figma = check.get("figma") or {}
            for m in mismatches:
                if m == "size":
                    size = figma.get("font_size")
                    if size:
                        _replace_size_class(classes, "text", int(round(float(size))))
                elif m == "weight":
                    weight = figma.get("font_weight")
                    if weight:
                        _replace_size_class(classes, "font", int(weight), unit="")
                elif m == "line_height":
                    lh = figma.get("line_height_px")
                    size = figma.get("font_size")
                    if lh and size:
                        ratio = round(float(lh) / float(size), 3)
                        _replace_size_class(classes, "leading", ratio, unit="")
                elif m == "letter_spacing":
                    ls = figma.get("letter_spacing")
                    if ls is not None:
                        _replace_size_class(classes, "tracking", int(round(float(ls))))
            adjustments.append({
                "type": "font_fix",
                "figma_id": figma_id,
                "reason": _check_reason(check),
                "mismatches": mismatches,
            })
        elif check_type == "snug_text":
            figma_width = check.get("figma_width")
            if figma_width:
                has_fixed_width = any(c.startswith("w-") for c in classes)
                has_whitespace_nowrap = "whitespace-nowrap" in classes
                single_line_label = has_whitespace_nowrap or (
                    "\n" not in (check.get("text") or "") and ("flex" in classes or "flex-row" in " ".join(classes))
                )
                if single_line_label:
                    if "whitespace-nowrap" not in classes:
                        classes.append("whitespace-nowrap")
                    if "min-w-0" not in classes:
                        classes.append("min-w-0")
                elif has_fixed_width:
                    _replace_size_class(classes, "w", int(round(figma_width)))
                else:
                    _replace_size_class(classes, "max-w", int(round(figma_width)))
            adjustments.append({
                "type": "snug_text_fix",
                "figma_id": figma_id,
                "reason": _check_reason(check),
            })

    return adjustments


def _check_reason(check: Dict[str, Any]) -> str:
    return check.get("discrepancy") or check.get("reason") or json.dumps(check, ensure_ascii=False)


def _extract_figma_id(check: Dict[str, Any]) -> Optional[str]:
    page = check.get("page") or {}
    return page.get("figma_id") or check.get("figma_id")


def _find_node_by_figma_id(node: Dict[str, Any], figma_id: str) -> Optional[Dict[str, Any]]:
    if node.get("figma_id") == figma_id:
        return node
    for child in node.get("children", []):
        found = _find_node_by_figma_id(child, figma_id)
        if found:
            return found
    return None


def _replace_size_class(classes: List[str], prefix: str, value: Any, unit: str = "px") -> None:
    """Удаляет существующие классы размера prefix и добавляет exact arbitrary class."""
    keep = [c for c in classes if not (c.startswith(prefix + "-") or c.startswith(prefix + "["))]
    keep.append(f"{prefix}-[{value}{unit}]")
    classes[:] = keep


def _run_compose(
    compose_module: Any,
    ast_path: Path,
    output_path: Path,
    title: Optional[str] = None,
) -> bool:
    try:
        ast = _load_json(ast_path)
        if not ast:
            return False
        page = compose_module.compose_page(ast, title=title)
        compose_module.write_page(page, str(output_path))
        return True
    except Exception as e:
        print(f"Refinement compose failed: {e}", file=sys.stderr)
        return False


def _run_visual_qa(
    visual_qa_module: Any,
    page_url: str,
    ast_path: Path,
    reference_path: Optional[str],
    output_dir: Path,
    viewport: Optional[Dict[str, int]] = None,
    allowed_domains: Optional[List[str]] = None,
) -> Dict[str, Any]:
    report = visual_qa_module.run_visual_qa(
        page_url=page_url,
        ast_path=str(ast_path),
        reference_path=reference_path,
        output_dir=str(output_dir),
        viewport=viewport,
        allowed_domains=allowed_domains,
        root_dir=str(Path.cwd()),
    )
    return report


def run_refinement_loop(
    page_url: str,
    ast_path: str = "layout_ast.json",
    compose_output: str = "src/app/page.tsx",
    reference_path: Optional[str] = None,
    visual_qa_output_dir: str = ".tmp/browser/visual_qa",
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    diff_threshold: float = DEFAULT_DIFF_SCORE_THRESHOLD,
    viewport: Optional[Dict[str, int]] = None,
    allowed_domains: Optional[List[str]] = None,
    compose_title: Optional[str] = None,
    report_output: str = "refinement_report.json",
    on_visual_qa: Optional[Callable[[int, str, Path, Path, Optional[str], Path], Dict[str, Any]]] = None,
    on_compose: Optional[Callable[[Any, Path, Path, Optional[str]], bool]] = None,
    on_adjust: Optional[Callable[[Dict[str, Any], Dict[str, Any]], List[Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    ast_file = Path(ast_path).resolve()
    page_file = Path(compose_output).resolve()
    qa_dir = Path(visual_qa_output_dir).resolve()

    if not ast_file.exists():
        report = RefinementReport(
            status="blocked",
            iterations=0,
            escalation_reason=f"AST file not found: {ast_path}",
            max_iterations=max_iterations,
        )
        _save_json(Path(report_output), report.to_dict())
        return report.to_dict()

    compose_module = _load_module("page_composer.py", "figma_page_composer")
    visual_qa_module = _load_module("visual_qa.py", "figma_visual_qa")

    final_qa_report: Optional[Dict[str, Any]] = None
    all_adjustments: List[Dict[str, Any]] = []
    previous_score: Optional[float] = None
    stagnant_iterations = 0

    for iteration in range(1, max_iterations + 1):
        if on_compose:
            compose_ok = on_compose(compose_module, ast_file, page_file, compose_title)
        else:
            compose_ok = _run_compose(compose_module, ast_file, page_file, compose_title)
        if not compose_ok:
            report = RefinementReport(
                status="failed",
                iterations=iteration,
                final_visual_qa=final_qa_report,
                adjustments=all_adjustments,
                escalation_reason="Compose step failed during refinement",
                max_iterations=max_iterations,
            )
            _save_json(Path(report_output), report.to_dict())
            return report.to_dict()

        if on_visual_qa:
            qa_report = on_visual_qa(iteration, page_url, ast_file, page_file, reference_path, qa_dir)
        else:
            qa_report = _run_visual_qa(
                visual_qa_module,
                page_url,
                ast_file,
                reference_path,
                qa_dir,
                viewport,
                allowed_domains,
            )
        final_qa_report = qa_report

        if not _visual_qa_needs_refinement(qa_report, diff_threshold):
            report = RefinementReport(
                status="passed",
                iterations=iteration,
                final_visual_qa=final_qa_report,
                adjustments=all_adjustments,
                max_iterations=max_iterations,
            )
            _save_json(Path(report_output), report.to_dict())
            return report.to_dict()

        if on_adjust:
            ast = _load_json(ast_file)
            adjustments = on_adjust(ast, qa_report)
        else:
            ast = _load_json(ast_file)
            adjustments = _apply_layout_adjustments(ast, qa_report)
            if adjustments:
                _save_json(ast_file, ast)
        all_adjustments.extend(adjustments)

        current_score = _qa_score(qa_report)
        if previous_score is not None and current_score is not None and current_score >= previous_score and adjustments:
            stagnant_iterations += 1
        else:
            stagnant_iterations = 0
        if stagnant_iterations >= 2:
            report = RefinementReport(
                status="needs_human",
                iterations=iteration,
                final_visual_qa=final_qa_report,
                adjustments=all_adjustments,
                escalation_reason="Visual QA score did not improve after adjustments; manual review required",
                max_iterations=max_iterations,
            )
            _save_json(Path(report_output), report.to_dict())
            return report.to_dict()
        previous_score = current_score

    report = RefinementReport(
        status="needs_human",
        iterations=max_iterations,
        final_visual_qa=final_qa_report,
        adjustments=all_adjustments,
        escalation_reason="Visual QA discrepancies remain after max iterations",
        max_iterations=max_iterations,
    )
    _save_json(Path(report_output), report.to_dict())
    return report.to_dict()


def _load_module(file_name: str, module_name: str) -> Any:
    from importlib import util as importlib_util
    module_dir = Path(__file__).resolve().parent
    file_path = module_dir / file_name
    spec = importlib_util.spec_from_file_location(module_name, str(file_path))
    if not spec or not spec.loader:
        raise ImportError(f"Cannot load module {file_name}")
    if module_name in sys.modules:
        existing = sys.modules[module_name]
        spec.loader.exec_module(existing)
        return existing
    module = importlib_util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _run_command(command: List[str], timeout: int = 120) -> bool:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0
    except Exception as e:
        print(f"Command failed: {' '.join(command)}: {e}", file=sys.stderr)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Refinement loop: re-run compose + visual QA until passing or max iterations")
    parser.add_argument("--url", required=True, help="URL of generated landing page")
    parser.add_argument("--ast", default="layout_ast.json", help="Path to Tailwind AST")
    parser.add_argument("--compose-output", default="src/app/page.tsx", help="Path to generated page")
    parser.add_argument("--reference", default=None, help="Path to reference screenshot")
    parser.add_argument("--visual-qa-output-dir", default=".tmp/browser/visual_qa", help="Visual QA output directory")
    parser.add_argument("--max-iterations", type=int, default=DEFAULT_MAX_ITERATIONS, help="Maximum refinement iterations")
    parser.add_argument("--diff-threshold", type=float, default=DEFAULT_DIFF_SCORE_THRESHOLD, help="Image diff score threshold")
    parser.add_argument("--viewport", default=None, help="Viewport as WIDTHxHEIGHT")
    parser.add_argument("--allowed-domains", default=None, help="Comma-separated allowed domains for URL guard")
    parser.add_argument("--compose-title", default=None, help="Page title for compose")
    parser.add_argument("--report-output", default="refinement_report.json", help="Path to refinement report")
    args = parser.parse_args()

    viewport = None
    if args.viewport:
        match = re.match(r"(\d+)x(\d+)", args.viewport)
        if match:
            viewport = {"width": int(match.group(1)), "height": int(match.group(2))}

    allowed_domains = None
    if args.allowed_domains:
        allowed_domains = [d.strip() for d in args.allowed_domains.split(",") if d.strip()]

    result = run_refinement_loop(
        page_url=args.url,
        ast_path=args.ast,
        compose_output=args.compose_output,
        reference_path=args.reference,
        visual_qa_output_dir=args.visual_qa_output_dir,
        max_iterations=args.max_iterations,
        diff_threshold=args.diff_threshold,
        viewport=viewport,
        allowed_domains=allowed_domains,
        compose_title=args.compose_title,
        report_output=args.report_output,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
