import json
import math
import re
import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def load_figma_json(filepath: str) -> dict:
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Figma file not found: {filepath}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_node_by_id(root: Dict[str, Any], node_id: str) -> Optional[Dict[str, Any]]:
    if not isinstance(root, dict):
        return None
    if root.get("id") == node_id:
        return root
    for child in root.get("children", []):
        found = find_node_by_id(child, node_id)
        if found:
            return found
    return None


def _px(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _box_area(box: Optional[Dict[str, Any]]) -> float:
    if not box:
        return 0.0
    w = _px(box.get("width")) or 0
    h = _px(box.get("height")) or 0
    return max(w * h, 0.0)


def _boxes_overlap(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    ax = _px(a.get("x")) or 0
    ay = _px(a.get("y")) or 0
    aw = _px(a.get("width")) or 0
    ah = _px(a.get("height")) or 0
    bx = _px(b.get("x")) or 0
    by = _px(b.get("y")) or 0
    bw = _px(b.get("width")) or 0
    bh = _px(b.get("height")) or 0
    return not (ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay)


@dataclass
class CheckResult:
    check_id: str
    passed: bool
    severity: str
    summary: str
    details: List[Dict[str, Any]] = field(default_factory=list)
    suggestion: str = ""


class PreciseModeAuditor:
    TARGET_VIEWPORT_DEFAULTS = {"desktop": (1440, 900), "mobile": (375, 812)}

    def __init__(self, root: Dict[str, Any], target_viewport: Optional[Tuple[int, int]] = None):
        self.root = root
        self.target_viewport = target_viewport or self.TARGET_VIEWPORT_DEFAULTS["desktop"]
        self.checks: List[CheckResult] = []
        self._all_nodes: List[Dict[str, Any]] = []
        self._collect_nodes(root)

    def _collect_nodes(self, node: Dict[str, Any]) -> None:
        if not isinstance(node, dict):
            return
        self._all_nodes.append(node)
        for child in node.get("children", []):
            self._collect_nodes(child)

    def audit(self) -> Dict[str, Any]:
        self.checks = [
            self._check_auto_layout(),
            self._check_exported_images(),
            self._check_snug_text(),
            self._check_overlaps(),
            self._check_alpha(),
            self._check_viewport(),
            self._check_semantic_naming(),
            self._check_component_sets(),
        ]
        score = self._compute_score()
        critical_count = sum(1 for c in self.checks if not c.passed and c.severity == "critical")
        status = "ready"
        hint = "continue"
        if score < 0.80 or critical_count > 0:
            status = "not_ready"
            hint = "halt_for_cleanup"
        elif score < 0.90:
            status = "needs_cleanup"
            hint = "warn_and_continue"

        auto_fixable = []
        requires_designer = []
        for c in self.checks:
            bucket = auto_fixable if c.check_id in {
                "alpha_transparency", "exported_images", "snug_text", "viewport_realism"
            } else requires_designer
            if not c.passed:
                bucket.append({
                    "check_id": c.check_id,
                    "summary": c.summary,
                    "suggestion": c.suggestion,
                })

        warning_count = sum(1 for c in self.checks if not c.passed and c.severity == "warning")

        return {
            "score": round(score, 3),
            "status": status,
            "target_viewport": self.target_viewport,
            "checks": [self._check_to_dict(c) for c in self.checks],
            "auto_fixable": auto_fixable,
            "requires_designer": requires_designer,
            "next_phase_hint": hint,
            "metrics": {
                "raw_score": score,
                "threshold_ready": 0.90,
                "threshold_cleanup": 0.80,
                "critical_count": critical_count,
                "warning_count": warning_count,
                "passed_checks": sum(1 for c in self.checks if c.passed),
                "total_checks": len(self.checks),
            },
        }

    def _check_to_dict(self, c: CheckResult) -> Dict[str, Any]:
        return {
            "check_id": c.check_id,
            "passed": c.passed,
            "severity": c.severity,
            "summary": c.summary,
            "details": c.details[:20],
            "suggestion": c.suggestion,
        }

    def _compute_score(self) -> float:
        weights = {
            "auto_layout_coverage": 0.25,
            "exported_images": 0.15,
            "snug_text": 0.15,
            "overlap_intersection": 0.15,
            "alpha_transparency": 0.10,
            "viewport_realism": 0.10,
            "semantic_naming": 0.05,
            "component_sets": 0.05,
        }
        score = 0.0
        for c in self.checks:
            weight = weights.get(c.check_id, 0.0)
            if c.passed:
                score += weight
            elif c.severity == "warning":
                score += weight * 0.5
        return min(max(score, 0.0), 1.0)

    def _visible_frame_like_nodes(self) -> List[Dict[str, Any]]:
        return [
            n for n in self._all_nodes
            if n.get("visible", True) and n.get("type") in ("FRAME", "COMPONENT", "COMPONENT_SET", "INSTANCE", "GROUP")
        ]

    def _check_auto_layout(self) -> CheckResult:
        containers = [n for n in self._visible_frame_like_nodes() if n.get("children")]
        if not containers:
            return CheckResult(
                check_id="auto_layout_coverage",
                passed=True,
                severity="info",
                summary="No containers to check for Auto Layout",
                suggestion="Add Auto Layout to frames/components that contain children.",
            )
        laid_out = sum(1 for n in containers if n.get("layoutMode") in ("HORIZONTAL", "VERTICAL"))
        ratio = laid_out / len(containers)
        details = [
            {"id": n.get("id"), "name": n.get("name"), "layoutMode": n.get("layoutMode")}
            for n in containers if n.get("layoutMode") not in ("HORIZONTAL", "VERTICAL")
        ]
        passed = ratio >= 0.90
        severity = "critical" if ratio < 0.75 else ("warning" if ratio < 1.0 else "info")
        return CheckResult(
            check_id="auto_layout_coverage",
            passed=passed,
            severity=severity,
            summary=f"Auto Layout coverage: {laid_out}/{len(containers)} ({round(ratio * 100)}%)",
            details=details[:20],
            suggestion="Apply Auto Layout (HORIZONTAL/VERTICAL) to all frames, components, and groups with children. Use Figma's 'Suggest Auto Layout' feature.",
        )

    def _check_exported_images(self) -> CheckResult:
        image_like = [
            n for n in self._all_nodes
            if n.get("visible", True) and (
                n.get("type") == "IMAGE"
                or (n.get("type") == "VECTOR" and any(f.get("type") == "IMAGE" for f in (n.get("fills") or [])))
                or (n.get("type") in ("RECTANGLE", "ELLIPSE") and any(f.get("type") == "IMAGE" for f in (n.get("fills") or [])))
            )
        ]
        if not image_like:
            return CheckResult(
                check_id="exported_images",
                passed=True,
                severity="info",
                summary="No image-like nodes found",
                suggestion="Explicitly export raster/vector images via Figma's Export panel when present.",
            )
        missing = [n for n in image_like if not (n.get("imageRef") or (n.get("exportSettings")) or n.get("isAsset"))]
        passed = len(missing) == 0
        severity = "critical" if len(missing) > len(image_like) * 0.25 else ("warning" if missing else "info")
        details = [{"id": n.get("id"), "name": n.get("name"), "type": n.get("type")} for n in missing[:20]]
        return CheckResult(
            check_id="exported_images",
            passed=passed,
            severity=severity,
            summary=f"Exported images: {len(image_like) - len(missing)}/{len(image_like)}",
            details=details,
            suggestion="Select each image/vector layer and add an Export setting in Figma so the asset has an explicit imageRef.",
        )

    def _check_snug_text(self) -> CheckResult:
        texts = [n for n in self._all_nodes if n.get("visible", True) and n.get("type") == "TEXT"]
        if not texts:
            return CheckResult(
                check_id="snug_text",
                passed=True,
                severity="info",
                summary="No text nodes to check",
                suggestion="Keep text bounding boxes snug to content to avoid extra whitespace and line breaks.",
            )
        loose = []
        for n in texts:
            chars = n.get("characters", "")
            if not chars:
                continue
            auto_resize = n.get("textAutoResize")
            if auto_resize in ("WIDTH_AND_HEIGHT", "HEIGHT_AND_WIDTH"):
                # Figma is auto-sizing this text; treat as snug.
                continue
            box = n.get("box") or n.get("absoluteBoundingBox")
            if not box:
                continue
            bw = _px(box.get("width")) or 0
            bh = _px(box.get("height")) or 0
            # Figma sometimes exposes a tighter text content box; use it when available.
            content_box = n.get("boundingBox")
            if content_box:
                cw = _px(content_box.get("width"))
                ch = _px(content_box.get("height"))
                if cw and ch and (bw > cw + 4 or bh > ch + 4):
                    loose.append({
                        "id": n.get("id"),
                        "name": n.get("name"),
                        "box_width": bw,
                        "box_height": bh,
                        "content_width": round(cw, 1),
                        "content_height": round(ch, 1),
                        "reason": "bounding-box-exceeds-content-box",
                    })
                    continue
                if cw and ch:
                    # Content box is available and fits; no need for heuristic.
                    continue
            style = n.get("style") or {}
            font_size = _px(n.get("fontSize")) or _px(style.get("fontSize")) or 16
            weight = _px(style.get("fontWeight")) or 400
            lines = chars.split("\n") or [chars]
            max_line_len = max(len(line) for line in lines)
            # Per-character width adjusted by weight; 0.6 is a conservative average for UI fonts.
            char_width = 0.65 if weight >= 700 else 0.6
            est_width = max_line_len * font_size * char_width
            est_height = font_size * len(lines) * 1.2
            tolerance_w = max(16, font_size * 1.5)
            tolerance_h = max(8, font_size * 0.75)
            if bw > est_width + tolerance_w or bh > est_height + tolerance_h:
                loose.append({
                    "id": n.get("id"),
                    "name": n.get("name"),
                    "box_width": bw,
                    "box_height": bh,
                    "estimated_text_width": round(est_width, 1),
                    "estimated_text_height": round(est_height, 1),
                    "reason": "heuristic-bounding-box",
                })
        ratio = (len(texts) - len(loose)) / len(texts)
        passed = ratio >= 0.90
        severity = "critical" if ratio < 0.75 else ("warning" if ratio < 0.90 else "info")
        return CheckResult(
            check_id="snug_text",
            passed=passed,
            severity=severity,
            summary=f"Snug text boxes: {len(texts) - len(loose)}/{len(texts)} ({round(ratio * 100)}%)",
            details=loose[:20],
            suggestion="Resize text bounding boxes to tightly fit their content. Use Figma's 'Auto Width/Height' text resizing or match the bounding box to the text content box.",
        )

    def _check_overlaps(self) -> CheckResult:
        visible = [
            n for n in self._all_nodes
            if n.get("visible", True) and n.get("box") and n.get("type") not in ("PAGE", "DOCUMENT")
        ]
        overlaps = []
        # Group by parent for sibling overlap detection
        by_parent: Dict[Optional[str], List[Dict[str, Any]]] = {}
        for n in visible:
            parent_id = n.get("parent", {}).get("id") if isinstance(n.get("parent"), dict) else None
            by_parent.setdefault(parent_id, []).append(n)
        for siblings in by_parent.values():
            for i in range(len(siblings)):
                for j in range(i + 1, len(siblings)):
                    a, b = siblings[i], siblings[j]
                    if _boxes_overlap(a.get("box", {}), b.get("box", {})):
                        # Skip if one contains the other (nesting)
                        if a.get("id") in [c.get("id") for c in b.get("children", [])]:
                            continue
                        if b.get("id") in [c.get("id") for c in a.get("children", [])]:
                            continue
                        overlaps.append({
                            "a_id": a.get("id"),
                            "a_name": a.get("name"),
                            "b_id": b.get("id"),
                            "b_name": b.get("name"),
                        })
        passed = len(overlaps) == 0
        severity = "critical" if len(overlaps) > 10 else ("warning" if overlaps else "info")
        return CheckResult(
            check_id="overlap_intersection",
            passed=passed,
            severity=severity,
            summary=f"Sibling overlaps detected: {len(overlaps)}",
            details=overlaps[:20],
            suggestion="Align selection boxes so sibling layers do not overlap or touch unless intentional. Group background elements together.",
        )

    def _check_alpha(self) -> CheckResult:
        alpha_nodes = []
        for n in self._all_nodes:
            if not n.get("visible", True):
                continue
            opacity = _px(n.get("opacity"))
            if opacity is not None and opacity < 1.0:
                alpha_nodes.append({"id": n.get("id"), "name": n.get("name"), "reason": "node opacity < 1.0", "value": opacity})
                continue
            for fill in n.get("fills", []):
                if fill.get("type") == "SOLID":
                    color = fill.get("color") or {}
                    if isinstance(color, dict) and _px(color.get("a")) is not None and color.get("a") < 1.0:
                        alpha_nodes.append({"id": n.get("id"), "name": n.get("name"), "reason": "fill alpha < 1.0"})
                        break
                if fill.get("type") == "GRADIENT_LINEAR":
                    stops = fill.get("gradientStops") or fill.get("stops") or []
                    if any((s.get("color") or {}).get("a", 1.0) < 1.0 for s in stops):
                        alpha_nodes.append({"id": n.get("id"), "name": n.get("name"), "reason": "gradient transparency"})
                        break
            for effect in n.get("effects", []):
                if effect.get("type") == "BACKGROUND_BLUR":
                    alpha_nodes.append({"id": n.get("id"), "name": n.get("name"), "reason": "background blur"})
                    break
        passed = len(alpha_nodes) == 0
        severity = "warning" if alpha_nodes else "info"
        return CheckResult(
            check_id="alpha_transparency",
            passed=passed,
            severity=severity,
            summary=f"Nodes with transparency/blur: {len(alpha_nodes)}",
            details=alpha_nodes[:20],
            suggestion="Avoid opacity, translucent fills, and background blur for predictable code output. The generator will fall back to rgba/backdrop-filter where needed.",
        )

    def _check_viewport(self) -> CheckResult:
        frame = self.root
        if frame.get("type") != "FRAME" and frame.get("children"):
            frame = next((c for c in frame.get("children", []) if c.get("type") == "FRAME"), frame)
        box = frame.get("box") or frame.get("absoluteBoundingBox")
        if not box:
            return CheckResult(
                check_id="viewport_realism",
                passed=False,
                severity="warning",
                summary="Could not determine design viewport size",
                suggestion="Ensure the top-level frame has explicit width/height matching the target device.",
            )
        fw = _px(box.get("width")) or 0
        fh = _px(box.get("height")) or 0
        tw, th = self.target_viewport
        scale_x = fw / tw if tw else 1.0
        scale_y = fh / th if th else 1.0
        passed = 0.5 <= scale_x <= 1.5 and 0.5 <= scale_y <= 1.5
        details = [{"design_width": fw, "design_height": fh, "target_width": tw, "target_height": th, "scale_x": round(scale_x, 2), "scale_y": round(scale_y, 2)}]
        return CheckResult(
            check_id="viewport_realism",
            passed=passed,
            severity="warning" if not passed else "info",
            summary=f"Design size {int(fw)}×{int(fh)} vs target {tw}×{th}",
            details=details,
            suggestion="Design at the intended output size. Extreme scaling requires manual size adjustments after generation.",
        )

    def _check_semantic_naming(self) -> CheckResult:
        generic = re.compile(r"^(frame|group|rectangle|vector|ellipse|component)\s*\d*$", re.IGNORECASE)
        bad = []
        for n in self._all_nodes:
            name = str(n.get("name", ""))
            if not name:
                continue
            is_generic = bool(generic.match(name))
            has_emoji = bool(re.search(r"[\U00010000-\U0010ffff]", name))
            has_special = bool(re.search(r"[^\w\s\-/]", name))
            if is_generic or has_emoji or has_special:
                bad.append({
                    "id": n.get("id"),
                    "name": name,
                    "depth": self._depth(n),
                    "issues": [i for i, flag in [("generic", is_generic), ("emoji", has_emoji), ("special_chars", has_special)] if flag],
                })
        # Critical only if a top-level frame has a bad name
        top_bad = [b for b in bad if b["depth"] == 1]
        passed = len(bad) == 0
        severity = "critical" if top_bad else ("warning" if bad else "info")
        return CheckResult(
            check_id="semantic_naming",
            passed=passed,
            severity=severity,
            summary=f"Nodes with non-semantic names: {len(bad)}",
            details=bad[:20],
            suggestion="Use semantic names (Hero, PricingCard, Button) and avoid emoji/special characters. Match component names between Figma and code.",
        )

    def _depth(self, target: Dict[str, Any]) -> int:
        def walk(n: Dict[str, Any], depth: int) -> int:
            if n.get("id") == target.get("id"):
                return depth
            for child in n.get("children", []):
                d = walk(child, depth + 1)
                if d >= 0:
                    return d
            return -1
        return walk(self.root, 0)

    def _check_component_sets(self) -> CheckResult:
        sets = [n for n in self._all_nodes if n.get("type") == "COMPONENT_SET"]
        comps = [n for n in self._all_nodes if n.get("type") == "COMPONENT" and not n.get("componentSetId")]
        instances = [n for n in self._all_nodes if n.get("type") == "INSTANCE"]
        passed = len(sets) > 0 or len(comps) > 0
        details = [{"component_sets": len(sets), "standalone_components": len(comps), "instances": len(instances)}]
        return CheckResult(
            check_id="component_sets",
            passed=passed,
            severity="warning" if not passed else "info",
            summary=f"Component Sets: {len(sets)}, Standalone Components: {len(comps)}, Instances: {len(instances)}",
            details=details,
            suggestion="Convert reusable UI elements (buttons, inputs, cards) into Figma Components/Variants. This enables prop mapping and design system consistency.",
        )


def run_audit(
    figma_file: str,
    node_id: Optional[str] = None,
    target_viewport: Optional[Tuple[int, int]] = None,
    output_path: Optional[str] = "precise_mode_report.json",
) -> Dict[str, Any]:
    data = load_figma_json(figma_file)
    root = data
    if node_id:
        target = find_node_by_id(data, node_id)
        if target:
            root = target
    auditor = PreciseModeAuditor(root, target_viewport=target_viewport)
    report = auditor.audit()
    if output_path:
        Path(output_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description="Precise Mode Auditor: Figma JSON readiness check")
    parser.add_argument("--file", default="figma_node.json", help="Path to Figma node JSON")
    parser.add_argument("--node-id", default=None, help="Optional node id to scope audit")
    parser.add_argument("--target-viewport", default=None, help="Target viewport as WIDTHxHEIGHT")
    parser.add_argument("--output", default="precise_mode_report.json", help="Report output path")
    args = parser.parse_args()

    target_viewport = None
    if args.target_viewport:
        match = re.match(r"(\d+)x(\d+)", args.target_viewport)
        if match:
            target_viewport = (int(match.group(1)), int(match.group(2)))

    try:
        report = run_audit(args.file, args.node_id, target_viewport, args.output)
        print(f"[PRECISE MODE] score={report['score']} status={report['status']} hint={report['next_phase_hint']}")
        for c in report["checks"]:
            icon = "[PASS]" if c["passed"] else "[FAIL]"
            print(f"  {icon} [{c['severity']}] {c['check_id']}: {c['summary']}")
        print(f"[PRECISE MODE] report written to {args.output}")
    except Exception as e:
        print(f"[PRECISE MODE] audit failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
