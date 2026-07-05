import json
import re
import time
import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except Exception:
    sync_playwright = None  # type: ignore
    PLAYWRIGHT_AVAILABLE = False


try:
    from PIL import Image

    PIL_AVAILABLE = True
except Exception:
    Image = None  # type: ignore
    PIL_AVAILABLE = False


DEFAULT_VIEWPORT = {"width": 1280, "height": 720}
DEFAULT_OUTPUT_DIR = ".tmp/browser/visual_qa"
DEFAULT_BBOX_TOLERANCE_PX = 8

FREEZE_CSS = """
*, *::before, *::after {
  animation-duration: 0s !important;
  animation-delay: 0s !important;
  transition-duration: 0s !important;
  transition-delay: 0s !important;
  scroll-behavior: auto !important;
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0s !important;
    transition-duration: 0s !important;
  }
}
"""


def _rgba_to_hex(r: float, g: float, b: float, a: float = 1.0) -> str:
    """Convert 0..1 Figma RGBA floats to an 8-digit or 6-digit hex string."""
    rh = int(round(r * 255))
    gh = int(round(g * 255))
    bh = int(round(b * 255))
    if a is not None and a < 1.0:
        ah = int(round(a * 255))
        return f"#{rh:02x}{gh:02x}{bh:02x}{ah:02x}"
    return f"#{rh:02x}{gh:02x}{bh:02x}"


def _parse_css_color(value: Optional[str]) -> Optional[str]:
    """Normalize a CSS color string (rgb/rgba/hex) to 6-digit hex, ignoring alpha."""
    if not value:
        return None
    value = value.strip().lower()
    # hex
    if value.startswith("#"):
        v = value[1:]
        if len(v) == 3:
            v = "".join(c + c for c in v)
        if len(v) in (6, 8):
            try:
                return f"#{v[:6]}"
            except Exception:
                return None
        return None
    # rgb(a)
    m = re.match(r"rgba?\s*\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)(?:\s*,\s*([0-9.]+))?\s*\)", value)
    if m:
        try:
            r = int(float(m.group(1)))
            g = int(float(m.group(2)))
            b = int(float(m.group(3)))
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return None
    return None


def _figma_color_to_hex(color: Optional[Dict[str, Any]]) -> Optional[str]:
    """Convert a Figma color dict to 6-digit hex."""
    if not color or not isinstance(color, dict):
        return None
    try:
        return _rgba_to_hex(float(color["r"]), float(color["g"]), float(color["b"]), float(color.get("a", 1.0)))
    except Exception:
        return None


def _extract_figma_fill_color(node: Dict[str, Any]) -> Optional[str]:
    """Extract the first visible SOLID fill color from a Figma node."""
    fills = node.get("fills") or []
    for fill in fills:
        if fill.get("visible", True) and fill.get("type") == "SOLID":
            return _figma_color_to_hex(fill.get("color"))
    return None


def _extract_figma_stroke_color(node: Dict[str, Any]) -> Optional[str]:
    """Extract the first visible SOLID stroke color from a Figma node."""
    strokes = node.get("strokes") or []
    for stroke in strokes:
        if stroke.get("visible", True) and stroke.get("type") == "SOLID":
            return _figma_color_to_hex(stroke.get("color"))
    return None


def _sanitize_output_dir(output_dir: str, root_dir: Optional[str] = None) -> Path:
    target = Path(output_dir).resolve()
    root = Path(root_dir).resolve() if root_dir else Path.cwd().resolve()
    if not str(target).startswith(str(root)):
        raise ValueError(f"Output directory outside workspace: {output_dir}")
    target.mkdir(parents=True, exist_ok=True)
    return target


def _is_allowed_url(url: str, allowed_domains: Optional[List[str]] = None) -> bool:
    if url.startswith("http://localhost:") or url.startswith("http://127.0.0.1:"):
        return True
    if url.startswith("file://"):
        path = Path(url.replace("file://", "").replace("/", "\\") if "win" in __import__("sys").platform else url.replace("file://", ""))
        return str(path.resolve()).startswith(str(Path.cwd().resolve()))
    if allowed_domains:
        for domain in allowed_domains:
            host = __import__("urllib.parse").urlparse(url).hostname or ""
            if domain == host or domain in url:
                return True
    return False


def _parse_viewport(viewport: Optional[str]) -> Optional[Dict[str, int]]:
    if not viewport:
        return None
    match = re.match(r"(\d+)x(\d+)", viewport)
    if match:
        return {"width": int(match.group(1)), "height": int(match.group(2))}
    return None


@dataclass
class DomAssertion:
    selector: str
    expected_count: Optional[int] = None
    expected_text: Optional[str] = None
    exact_text: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selector": self.selector,
            "expected_count": self.expected_count,
            "expected_text": self.expected_text,
            "exact_text": self.exact_text,
        }


@dataclass
class VisualQaReport:
    status: str
    screenshot_path: Optional[str] = None
    reference_screenshot_path: Optional[str] = None
    diff_score: Optional[float] = None
    dom_assertions: List[Dict[str, Any]] = field(default_factory=list)
    layout_checks: List[Dict[str, Any]] = field(default_factory=list)
    bbox_comparison: Dict[str, Any] = field(default_factory=dict)
    font_metrics: Dict[str, Any] = field(default_factory=dict)
    image_metrics: Dict[str, Any] = field(default_factory=dict)
    pixel_metrics: Dict[str, Any] = field(default_factory=dict)
    snug_text_checks: List[Dict[str, Any]] = field(default_factory=list)
    color_metrics: Dict[str, Any] = field(default_factory=dict)
    discrepancies: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "screenshot_path": self.screenshot_path,
            "reference_screenshot_path": self.reference_screenshot_path,
            "diff_score": self.diff_score,
            "dom_assertions": self.dom_assertions,
            "layout_checks": self.layout_checks,
            "bbox_comparison": self.bbox_comparison,
            "font_metrics": self.font_metrics,
            "image_metrics": self.image_metrics,
            "pixel_metrics": self.pixel_metrics,
            "snug_text_checks": self.snug_text_checks,
            "color_metrics": self.color_metrics,
            "discrepancies": self.discrepancies,
            "metrics": self.metrics,
        }


class VisualQAEngine:
    def __init__(
        self,
        viewport: Optional[Dict[str, int]] = None,
        allowed_domains: Optional[List[str]] = None,
        output_dir: str = DEFAULT_OUTPUT_DIR,
        root_dir: Optional[str] = None,
        bbox_tolerance_px: int = DEFAULT_BBOX_TOLERANCE_PX,
    ):
        self.viewport = viewport or DEFAULT_VIEWPORT.copy()
        self.allowed_domains = allowed_domains or []
        self.output_dir = _sanitize_output_dir(output_dir, root_dir=root_dir)
        self.bbox_tolerance_px = bbox_tolerance_px
        self.report = VisualQaReport(status="blocked")

    def run(
        self,
        page_url: str,
        reference_path: Optional[str] = None,
        expected_nodes: Optional[List[Dict[str, Any]]] = None,
        figma_frame: Optional[Dict[str, Any]] = None,
        figma_bboxes: Optional[List[Dict[str, Any]]] = None,
        figma_color_nodes: Optional[List[Dict[str, Any]]] = None,
    ) -> VisualQaReport:
        if not PLAYWRIGHT_AVAILABLE:
            return self._blocked("Playwright is not installed. Install with: pip install playwright && playwright install")

        if not _is_allowed_url(page_url, self.allowed_domains):
            return self._blocked(f"URL not allowed by network guard: {page_url}")

        screenshot_path = self.output_dir / f"page_{int(time.time())}.png"
        reference_screenshot_path = None
        if reference_path:
            reference_screenshot_path = str(Path(reference_path).resolve())

        viewport = self.viewport.copy()
        if figma_frame:
            viewport["width"] = int(figma_frame.get("width", viewport["width"]))
            viewport["height"] = int(figma_frame.get("height", viewport["height"]))

        start_time = time.time()
        metrics: Dict[str, Any] = {
            "viewport_width": viewport["width"],
            "viewport_height": viewport["height"],
        }

        discrepancies: List[str] = []
        dom_assertions: List[Dict[str, Any]] = []
        layout_checks: List[Dict[str, Any]] = []
        bbox_comparison: Dict[str, Any] = {}
        font_metrics: Dict[str, Any] = {}
        image_metrics: Dict[str, Any] = {}
        color_metrics: Dict[str, Any] = {}
        diff_score: Optional[float] = None

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
                context = browser.new_context(viewport=viewport)
                page = context.new_page()

                try:
                    page.goto(page_url, wait_until="networkidle", timeout=30000)
                except Exception as e:
                    discrepancies.append(f"Navigation warning: {e}")

                self._inject_freeze_css(page)
                self._wait_for_stable_state(page)

                page.screenshot(path=str(screenshot_path), full_page=True)

                screenshot_size = Image.open(screenshot_path).size if PIL_AVAILABLE else (0, 0)
                metrics["screenshot_width"] = screenshot_size[0]
                metrics["screenshot_height"] = screenshot_size[1]
                metrics["load_time_ms"] = int(round((time.time() - start_time) * 1000))

                dom_assertions = self._run_dom_assertions(page, expected_nodes or [])
                layout_checks = self._run_layout_checks(page, figma_bboxes=figma_bboxes, figma_text_nodes=expected_nodes)
                bbox_comparison = self._build_bbox_comparison(layout_checks)
                pixel_metrics = self._build_pixel_metrics(layout_checks)
                snug_text_checks = [c for c in layout_checks if c.get("type") == "snug_text"]
                font_metrics = self._collect_font_metrics(page, figma_text_nodes=expected_nodes)
                image_metrics = self._collect_image_metrics(page)
                color_metrics = self._collect_color_metrics(page, figma_color_nodes=figma_color_nodes or [])

                if reference_screenshot_path and Path(reference_screenshot_path).exists():
                    diff_score = self._compute_diff(str(screenshot_path), reference_screenshot_path, discrepancies)

                browser.close()
        except Exception as e:
            return self._blocked(f"Browser session failed: {e}")

        failed_assertions = [a for a in dom_assertions if not a.get("passed", False)]
        failed_layout = [c for c in layout_checks if not c.get("passed", False)]
        failed_color = color_metrics.get("failed", 0) if isinstance(color_metrics, dict) else 0
        status = "passed"
        if failed_assertions or failed_layout or discrepancies or failed_color:
            status = "failed"

        self.report = VisualQaReport(
            status=status,
            screenshot_path=str(screenshot_path.resolve()),
            reference_screenshot_path=reference_screenshot_path,
            diff_score=diff_score,
            dom_assertions=dom_assertions,
            layout_checks=layout_checks,
            bbox_comparison=bbox_comparison,
            font_metrics=font_metrics,
            image_metrics=image_metrics,
            pixel_metrics=pixel_metrics,
            snug_text_checks=snug_text_checks,
            color_metrics=color_metrics,
            discrepancies=discrepancies,
            metrics=metrics,
        )
        self._write_report()
        return self.report

    def _blocked(self, reason: str) -> VisualQaReport:
        self.report = VisualQaReport(status="blocked", discrepancies=[reason])
        self._write_report()
        return self.report

    def _inject_freeze_css(self, page: Any) -> None:
        try:
            style = page.locator("style#qa-freeze").first
            if style.count() == 0:
                page.add_style_tag(content=FREEZE_CSS)
        except Exception:
            pass

    def _wait_for_stable_state(self, page: Any) -> None:
        try:
            page.evaluate("document.fonts.ready")
        except Exception:
            pass

        try:
            page.wait_for_function(
                """
                () => {
                    const images = Array.from(document.querySelectorAll('img, svg image'));
                    return images.every(img => img.complete && ((img.naturalWidth || 0) > 0 || img.tagName === 'image'));
                }
                """,
                timeout=10000,
            )
        except Exception:
            pass

        try:
            page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
        except Exception:
            pass

    def _run_dom_assertions(self, page: Any, expected_nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for entry in expected_nodes:
            selector = entry.get("selector", "")
            if not selector:
                continue

            expected_count = entry.get("expected_count")
            expected_text = entry.get("expected_text")
            exact_text = entry.get("exact_text")

            passed = True
            actual: Dict[str, Any] = {}
            entry_discrepancies: List[str] = []

            try:
                elements = page.query_selector_all(selector)
                actual["count"] = len(elements)

                if expected_count is not None and len(elements) != expected_count:
                    passed = False
                    entry_discrepancies.append(f"expected {expected_count} elements, found {len(elements)}")

                if expected_text or exact_text:
                    texts = [el.inner_text().strip() for el in elements if el.inner_text()]
                    actual["texts"] = texts
                    target = exact_text or expected_text
                    if target and target not in texts:
                        passed = False
                        if exact_text:
                            entry_discrepancies.append(f"no element has exact text '{exact_text}'")
                        else:
                            entry_discrepancies.append(f"no element contains text '{expected_text}'")
            except Exception as e:
                passed = False
                actual["error"] = str(e)
                entry_discrepancies.append(f"selector query failed: {e}")

            results.append({
                "selector": selector,
                "expected": entry,
                "actual": actual,
                "passed": passed,
                "discrepancies": entry_discrepancies,
            })
        return results

    def _run_layout_checks(
        self,
        page: Any,
        figma_bboxes: Optional[List[Dict[str, Any]]] = None,
        figma_text_nodes: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        checks: List[Dict[str, Any]] = []
        checks.extend(self._detect_overflow(page) or [])
        checks.extend(self._detect_clipped_text(page) or [])
        checks.extend(self._detect_overlaps(page) or [])
        if figma_bboxes:
            checks.extend(self._compare_bboxes(page, figma_bboxes) or [])
        if figma_text_nodes:
            checks.extend(self._collect_font_metrics_checks(page, figma_text_nodes) or [])
            checks.extend(self._detect_snug_text(page, figma_text_nodes) or [])
        return checks

    def _detect_overflow(self, page: Any) -> List[Dict[str, Any]]:
        return page.evaluate(
            """
            (tolerance) => {
                const results = [];
                const candidates = document.querySelectorAll('section, header, main, footer, article, div');
                for (const el of candidates) {
                    const style = window.getComputedStyle(el);
                    const isVisible = style.display !== 'none' && style.visibility !== 'hidden';
                    if (!isVisible) continue;
                    const overflowX = el.scrollWidth > el.clientWidth + tolerance;
                    const overflowY = el.scrollHeight > el.clientHeight + tolerance;
                    if (overflowX || overflowY) {
                        const rect = el.getBoundingClientRect();
                        results.push({
                            type: 'overflow',
                            selector: el.tagName.toLowerCase() + (el.id ? '#' + el.id : ''),
                            figma_id: el.dataset ? el.dataset.figmaId : null,
                            overflow_x: overflowX,
                            overflow_y: overflowY,
                            scroll_width: el.scrollWidth,
                            client_width: el.clientWidth,
                            scroll_height: el.scrollHeight,
                            client_height: el.clientHeight,
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height),
                        });
                    }
                }
                return results;
            }
            """,
            self.bbox_tolerance_px,
        )

    def _detect_clipped_text(self, page: Any) -> List[Dict[str, Any]]:
        return page.evaluate(
            """
            () => {
                const results = [];
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                let node;
                while ((node = walker.nextNode())) {
                    const el = node.parentElement;
                    if (!el) continue;
                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden') continue;
                    const range = document.createRange();
                    range.selectNode(node);
                    const rect = range.getBoundingClientRect();
                    const parent = el.getBoundingClientRect();
                    const clippedY = rect.bottom > parent.bottom + 2 || rect.top < parent.top - 2;
                    const clippedX = rect.right > parent.right + 2 || rect.left < parent.left - 2;
                    if ((clippedY || clippedX) && el.scrollHeight > el.clientHeight + 2) {
                        results.push({
                            type: 'clipped_text',
                            selector: el.tagName.toLowerCase() + (el.id ? '#' + el.id : ''),
                            text_preview: node.textContent.trim().slice(0, 60),
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height),
                        });
                    }
                }
                return results;
            }
            """
        )

    def _detect_overlaps(self, page: Any) -> List[Dict[str, Any]]:
        return page.evaluate(
            """
            () => {
                const results = [];
                const candidates = Array.from(document.querySelectorAll('section, header, main, footer, article, div, button, a, p, h1, h2, h3, h4, h5, h6, li'));
                for (let i = 0; i < candidates.length; i++) {
                    const a = candidates[i];
                    const styleA = window.getComputedStyle(a);
                    if (styleA.display === 'none' || styleA.visibility === 'hidden') continue;
                    if (styleA.position === 'absolute' || styleA.position === 'fixed') continue;
                    const rectA = a.getBoundingClientRect();
                    if (rectA.width === 0 || rectA.height === 0) continue;
                    for (let j = i + 1; j < candidates.length; j++) {
                        const b = candidates[j];
                        const styleB = window.getComputedStyle(b);
                        if (styleB.display === 'none' || styleB.visibility === 'hidden') continue;
                        if (styleB.position === 'absolute' || styleB.position === 'fixed') continue;
                        const rectB = b.getBoundingClientRect();
                        if (rectB.width === 0 || rectB.height === 0) continue;
                        const overlap = !(rectA.right < rectB.left || rectA.left > rectB.right || rectA.bottom < rectB.top || rectA.top > rectB.bottom);
                        if (overlap) {
                            const aContainsB = a !== b && a.contains(b);
                            const bContainsA = b !== a && b.contains(a);
                            if (!aContainsB && !bContainsA) {
                                results.push({
                                    type: 'overlap',
                                    selector_a: a.tagName.toLowerCase() + (a.id ? '#' + a.id : ''),
                                    selector_b: b.tagName.toLowerCase() + (b.id ? '#' + b.id : ''),
                                    x: Math.round(Math.max(rectA.left, rectB.left)),
                                    y: Math.round(Math.max(rectA.top, rectB.top)),
                                    width: Math.round(Math.min(rectA.right, rectB.right) - Math.max(rectA.left, rectB.left)),
                                    height: Math.round(Math.min(rectA.bottom, rectB.bottom) - Math.max(rectA.top, rectB.top)),
                                });
                            }
                        }
                    }
                }
                return results.slice(0, 20);
            }
            """
        )

    def _collect_page_bboxes(self, page: Any) -> List[Dict[str, Any]]:
        """Collect all visible DOM bboxes, preferring elements with data-figma-id."""
        return page.evaluate(
            """
            () => {
                const all = document.querySelectorAll('[data-figma-id]');
                if (all.length > 0) {
                    return Array.from(all).map(el => {
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return {
                            tag: el.tagName.toLowerCase(),
                            id: el.id || null,
                            figma_id: el.dataset.figmaId || null,
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height),
                        };
                    }).filter(b => b.width > 0 && b.height > 0);
                }
                const structural = ['section', 'header', 'main', 'footer', 'article', 'div'];
                const results = [];
                for (const tag of structural) {
                    for (const el of document.querySelectorAll(tag)) {
                        const style = window.getComputedStyle(el);
                        if (style.display === 'none' || style.visibility === 'hidden') continue;
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {
                            results.push({
                                tag: tag,
                                id: el.id || null,
                                figma_id: el.dataset ? el.dataset.figmaId : null,
                                x: Math.round(rect.x),
                                y: Math.round(rect.y),
                                width: Math.round(rect.width),
                                height: Math.round(rect.height),
                            });
                        }
                    }
                }
                return results;
            }
            """
        ) or []

    def _compare_bboxes(
        self,
        page: Any,
        figma_bboxes: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        page_bboxes = self._collect_page_bboxes(page)
        if not isinstance(page_bboxes, list):
            page_bboxes = []

        checks: List[Dict[str, Any]] = []
        tolerance = self.bbox_tolerance_px
        for figma_box in figma_bboxes:
            fid = figma_box.get("id")
            candidates = [b for b in page_bboxes if b.get("figma_id") == fid] if fid else []
            if not candidates:
                candidates = [
                    b for b in page_bboxes
                    if b.get("tag") == (figma_box.get("tag") or b.get("tag"))
                    and abs(b.get("x", 0) - figma_box.get("x", 0)) <= tolerance
                    and abs(b.get("y", 0) - figma_box.get("y", 0)) <= tolerance
                ]
            if not candidates:
                checks.append({
                    "type": "bbox_missing",
                    "passed": False,
                    "figma": figma_box,
                    "page": None,
                    "discrepancy": f"No matching DOM element for Figma node {fid or figma_box.get('name')}",
                })
                continue

            page_box = candidates[0]
            dw = page_box["width"] - figma_box.get("width", 0)
            dh = page_box["height"] - figma_box.get("height", 0)
            dx = page_box["x"] - figma_box.get("x", 0)
            dy = page_box["y"] - figma_box.get("y", 0)
            width_ok = abs(dw) <= tolerance
            height_ok = abs(dh) <= tolerance
            position_ok = abs(dx) <= tolerance and abs(dy) <= tolerance
            passed = width_ok and height_ok and position_ok
            check: Dict[str, Any] = {
                "type": "bbox_mismatch",
                "passed": passed,
                "figma": figma_box,
                "page": page_box,
                "delta_x": dx,
                "delta_y": dy,
                "delta_width": dw,
                "delta_height": dh,
            }
            if not passed:
                check["discrepancy"] = (
                    f"Size/position mismatch: Figma {figma_box.get('x')},{figma_box.get('y')} "
                    f"{figma_box.get('width')}x{figma_box.get('height')} "
                    f"vs page {page_box['x']},{page_box['y']} {page_box['width']}x{page_box['height']}"
                )
            checks.append(check)
        return checks

    def _build_bbox_comparison(self, layout_checks: List[Dict[str, Any]]) -> Dict[str, Any]:
        bbox_checks = [c for c in layout_checks if c.get("type") in ("bbox_mismatch", "bbox_missing")]
        return {
            "total": len(bbox_checks),
            "passed": sum(1 for c in bbox_checks if c.get("passed", False)),
            "failed": sum(1 for c in bbox_checks if not c.get("passed", False)),
            "checks": bbox_checks,
        }

    def _build_pixel_metrics(self, layout_checks: List[Dict[str, Any]]) -> Dict[str, Any]:
        bbox_checks = [c for c in layout_checks if c.get("type") == "bbox_mismatch" and not c.get("passed", False)]
        if not bbox_checks:
            return {"total_drift_px": 0.0, "max_drift_px": 0.0, "mean_drift_px": 0.0, "failed_nodes": 0}
        drift_per_node = [
            abs(c.get("delta_x", 0))
            + abs(c.get("delta_y", 0))
            + abs(c.get("delta_width", 0))
            + abs(c.get("delta_height", 0))
            for c in bbox_checks
        ]
        return {
            "total_drift_px": round(sum(drift_per_node), 2),
            "max_drift_px": round(max(drift_per_node), 2),
            "mean_drift_px": round(sum(drift_per_node) / len(drift_per_node), 2),
            "failed_nodes": len(bbox_checks),
        }

    def _collect_font_metrics_checks(
        self,
        page: Any,
        figma_text_nodes: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        figma_text_nodes = figma_text_nodes or []
        by_id = {n.get("id"): n for n in figma_text_nodes if n.get("id")}

        def parse_px(value: Optional[str]) -> Optional[float]:
            if not value:
                return None
            try:
                match = re.search(r"[0-9.]+(?:px)?", value)
                if not match:
                    return None
                num = float(match.group().replace("px", ""))
                if "rem" in value:
                    num *= 16
                return num
            except Exception:
                return None

        def parse_weight(value: Optional[str]) -> Optional[int]:
            if not value:
                return None
            try:
                return int(float(value))
            except Exception:
                return None

        try:
            page_metrics = page.evaluate(
                """
                () => {
                    const results = [];
                    for (const el of document.querySelectorAll('[data-figma-id]')) {
                        const style = window.getComputedStyle(el);
                        results.push({
                            figma_id: el.dataset.figmaId,
                            font_family: style.fontFamily.split(',')[0].trim().replace(/["']/g, ''),
                            font_size: style.fontSize,
                            line_height: style.lineHeight,
                            letter_spacing: style.letterSpacing,
                            font_weight: style.fontWeight,
                            x: Math.round(el.getBoundingClientRect().x),
                            y: Math.round(el.getBoundingClientRect().y),
                            width: Math.round(el.getBoundingClientRect().width),
                            height: Math.round(el.getBoundingClientRect().height),
                        });
                    }
                    return results;
                }
                """
            )
            if not isinstance(page_metrics, list):
                return []
            checks: List[Dict[str, Any]] = []
            for page_metric in page_metrics:
                fid = page_metric.get("figma_id")
                figma_node = by_id.get(fid)
                if not figma_node or not figma_node.get("is_text"):
                    continue
                style = figma_node.get("style", {})
                figma_family = style.get("fontFamily")
                figma_size = style.get("fontSize")
                figma_line = style.get("lineHeightPx")
                figma_ls = style.get("letterSpacing")
                figma_weight = style.get("fontWeight")

                mismatches: List[str] = []
                if figma_family and page_metric.get("font_family") and figma_family.lower() not in page_metric["font_family"].lower():
                    mismatches.append("family")
                page_size = parse_px(page_metric.get("font_size"))
                if figma_size is not None and page_size is not None and abs(page_size - float(figma_size)) > 1:
                    mismatches.append("size")
                page_weight = parse_weight(page_metric.get("font_weight"))
                if figma_weight is not None and page_weight is not None and page_weight != int(figma_weight):
                    mismatches.append("weight")
                page_lh = parse_px(page_metric.get("line_height"))
                if figma_line is not None and page_lh is not None and figma_size:
                    figma_lh_ratio = round(float(figma_line) / float(figma_size), 3)
                    page_lh_ratio = round(page_lh / page_size, 3) if page_size else 0
                    if abs(page_lh_ratio - figma_lh_ratio) > 0.05:
                        mismatches.append("line_height")
                page_ls = parse_px(page_metric.get("letter_spacing"))
                if figma_ls is not None and page_ls is not None and abs(page_ls - float(figma_ls)) > 0.5:
                    mismatches.append("letter_spacing")

                if mismatches:
                    checks.append({
                        "type": "font_mismatch",
                        "passed": False,
                        "figma_id": fid,
                        "mismatches": mismatches,
                        "page": page_metric,
                        "figma": {
                            "font_family": figma_family,
                            "font_size": figma_size,
                            "line_height_px": figma_line,
                            "letter_spacing": figma_ls,
                            "font_weight": figma_weight,
                        },
                    })
            return checks
        except Exception as e:
            return [{"type": "font_mismatch", "passed": False, "error": str(e)}]

    def _collect_font_metrics(
        self,
        page: Any,
        figma_text_nodes: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        figma_text_nodes = figma_text_nodes or []
        by_id = {n.get("id"): n for n in figma_text_nodes if n.get("id")}

        def parse_px(value: Optional[str]) -> Optional[float]:
            if not value:
                return None
            try:
                # handles '16px' or computed string values
                match = re.search(r"[0-9.]+(?:px)?", value)
                if not match:
                    return None
                num = float(match.group().replace("px", ""))
                if "rem" in value:
                    # assume root 16px; best-effort
                    num *= 16
                return num
            except Exception:
                return None

        def parse_weight(value: Optional[str]) -> Optional[int]:
            if not value:
                return None
            try:
                return int(float(value))
            except Exception:
                return None

        try:
            summary = page.evaluate(
                """
                () => {
                    const families = new Set();
                    for (const el of document.querySelectorAll('body, body *')) {
                        const style = window.getComputedStyle(el);
                        if (style.fontFamily) families.add(style.fontFamily.split(',')[0].trim().replace(/["']/g, ''));
                    }
                    const body = document.body;
                    const style = window.getComputedStyle(body);
                    return {
                        font_families: Array.from(families),
                        body_font_size: style.fontSize,
                        body_line_height: style.lineHeight,
                    };
                }
                """
            )
            if not isinstance(summary, dict):
                return {"error": "font_metrics summary unavailable"}
            per_node: List[Dict[str, Any]] = []
            page_metrics = page.evaluate(
                """
                () => {
                    const results = [];
                    for (const el of document.querySelectorAll('[data-figma-id]')) {
                        const style = window.getComputedStyle(el);
                        results.push({
                            figma_id: el.dataset.figmaId,
                            font_family: style.fontFamily.split(',')[0].trim().replace(/["']/g, ''),
                            font_size: style.fontSize,
                            line_height: style.lineHeight,
                            letter_spacing: style.letterSpacing,
                            font_weight: style.fontWeight,
                            x: Math.round(el.getBoundingClientRect().x),
                            y: Math.round(el.getBoundingClientRect().y),
                            width: Math.round(el.getBoundingClientRect().width),
                            height: Math.round(el.getBoundingClientRect().height),
                        });
                    }
                    return results;
                }
                """
            )
            if not isinstance(page_metrics, list):
                summary["per_node"] = []
                return summary
            for page_metric in page_metrics:
                fid = page_metric.get("figma_id")
                figma_node = by_id.get(fid)
                if not figma_node or not figma_node.get("is_text"):
                    continue
                style = figma_node.get("style", {})
                figma_family = style.get("fontFamily")
                figma_size = style.get("fontSize")
                figma_line = style.get("lineHeightPx")
                figma_ls = style.get("letterSpacing")
                figma_weight = style.get("fontWeight")

                mismatches: List[str] = []
                if figma_family and page_metric.get("font_family") and figma_family.lower() not in page_metric["font_family"].lower():
                    mismatches.append("family")
                page_size = parse_px(page_metric.get("font_size"))
                if figma_size is not None and page_size is not None and abs(page_size - float(figma_size)) > 1:
                    mismatches.append("size")
                page_weight = parse_weight(page_metric.get("font_weight"))
                if figma_weight is not None and page_weight is not None and page_weight != int(figma_weight):
                    mismatches.append("weight")
                page_lh = parse_px(page_metric.get("line_height"))
                if figma_line is not None and page_lh is not None and figma_size:
                    figma_lh_ratio = round(float(figma_line) / float(figma_size), 3)
                    page_lh_ratio = round(page_lh / page_size, 3) if page_size else 0
                    if abs(page_lh_ratio - figma_lh_ratio) > 0.05:
                        mismatches.append("line_height")
                page_ls = parse_px(page_metric.get("letter_spacing"))
                if figma_ls is not None and page_ls is not None and abs(page_ls - float(figma_ls)) > 0.5:
                    mismatches.append("letter_spacing")

                if mismatches:
                    per_node.append({
                        "figma_id": fid,
                        "mismatches": mismatches,
                        "page": page_metric,
                        "figma": {
                            "font_family": figma_family,
                            "font_size": figma_size,
                            "line_height_px": figma_line,
                            "letter_spacing": figma_ls,
                            "font_weight": figma_weight,
                        },
                    })
            summary["per_node"] = per_node
            return summary
        except Exception as e:
            return {"error": str(e)}

    def _detect_snug_text(
        self,
        page: Any,
        figma_text_nodes: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not figma_text_nodes:
            return []
        by_id = {n.get("id"): n for n in figma_text_nodes if n.get("id")}
        try:
            page_bboxes = self._collect_page_bboxes(page)
        except Exception:
            return []
        if not isinstance(page_bboxes, list):
            return []

        checks: List[Dict[str, Any]] = []
        for page_box in page_bboxes:
            fid = page_box.get("figma_id")
            figma_node = by_id.get(fid) if fid else None
            if not figma_node or not figma_node.get("is_text"):
                continue
            figma_box = figma_node.get("box") or figma_node.get("absoluteBoundingBox") or {}
            fw = figma_box.get("width", 0)
            pw = page_box.get("width", 0)
            if fw and pw and (pw - fw) > 4:
                checks.append({
                    "type": "snug_text",
                    "passed": False,
                    "figma_id": fid,
                    "figma_width": fw,
                    "page_width": pw,
                    "delta_width": pw - fw,
                    "discrepancy": f"Rendered text width ({pw}px) exceeds Figma text bbox ({fw}px) by {pw - fw}px",
                })
        return checks


    def _collect_image_metrics(self, page: Any) -> Dict[str, Any]:
        try:
            result = page.evaluate(
                """
                () => {
                    const images = Array.from(document.querySelectorAll('img'));
                    return {
                        total_images: images.length,
                        loaded_images: images.filter(img => img.complete && img.naturalWidth > 0).length,
                        broken_images: images.filter(img => img.complete && img.naturalWidth === 0).length,
                    };
                }
                """
            )
            return result if isinstance(result, dict) else {"error": "image metrics unavailable"}
        except Exception as e:
            return {"error": str(e)}

    def _collect_color_metrics(
        self,
        page: Any,
        figma_color_nodes: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not figma_color_nodes:
            return {"total": 0, "passed": 0, "failed": 0, "checks": []}

        figma_by_id = {n.get("id"): n for n in figma_color_nodes if n.get("id")}
        try:
            page_colors = page.evaluate(
                """
                () => {
                    const results = [];
                    for (const el of document.querySelectorAll('[data-figma-id]')) {
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        results.push({
                            figma_id: el.dataset.figmaId,
                            background_color: style.backgroundColor,
                            color: style.color,
                            border_color: style.borderColor,
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height),
                        });
                    }
                    return results;
                }
                """
            )
            if not isinstance(page_colors, list):
                return {"error": "color metrics unavailable"}

            checks: List[Dict[str, Any]] = []
            for page_color in page_colors:
                fid = page_color.get("figma_id")
                figma_node = figma_by_id.get(fid)
                if not figma_node:
                    continue

                expected_fill = _extract_figma_fill_color(figma_node)
                expected_stroke = _extract_figma_stroke_color(figma_node)
                page_bg = _parse_css_color(page_color.get("background_color"))
                page_fg = _parse_css_color(page_color.get("color"))
                page_border = _parse_css_color(page_color.get("border_color"))

                mismatches: List[str] = []
                if expected_fill and page_bg and expected_fill.lower() != page_bg.lower():
                    mismatches.append("background")
                if expected_stroke and page_border and expected_stroke.lower() != page_border.lower():
                    mismatches.append("border")

                if mismatches:
                    checks.append({
                        "type": "color_mismatch",
                        "passed": False,
                        "figma_id": fid,
                        "mismatches": mismatches,
                        "page": {
                            "background_color": page_bg,
                            "color": page_fg,
                            "border_color": page_border,
                        },
                        "figma": {
                            "fill": expected_fill,
                            "stroke": expected_stroke,
                        },
                    })

            failed = len(checks)
            return {
                "total": len(page_colors),
                "passed": len(page_colors) - failed,
                "failed": failed,
                "checks": checks,
            }
        except Exception as e:
            return {"error": str(e)}

    def _compute_diff(
        self,
        screenshot_path: str,
        reference_path: str,
        discrepancies: List[str],
    ) -> Optional[float]:
        if not PIL_AVAILABLE:
            discrepancies.append("PIL not installed; skipping image diff.")
            return None

        try:
            img = Image.open(screenshot_path).convert("RGB")
            ref = Image.open(reference_path).convert("RGB")

            if img.size != ref.size:
                discrepancies.append(
                    f"Screenshot size {img.size} differs from reference {ref.size}; normalizing before diff."
                )
                ref = ref.resize(img.size, Image.Resampling.LANCZOS)

            diff = 0.0
            pixels = img.size[0] * img.size[1]
            if pixels == 0:
                return 0.0

            img_data = list(img.getdata())
            ref_data = list(ref.getdata())
            for (r1, g1, b1), (r2, g2, b2) in zip(img_data, ref_data):
                diff += abs(r1 - r2) + abs(g1 - g2) + abs(b1 - b2)

            max_diff = pixels * 3 * 255
            return round(diff / max_diff, 4)
        except Exception as e:
            discrepancies.append(f"Image diff failed: {e}")
            return None

    def _write_report(self) -> None:
        report_path = self.output_dir / "report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(self.report.to_dict(), f, ensure_ascii=False, indent=2)


def _expected_nodes_from_ast(ast: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Извлекает минимальные DOM-assertions из Tailwind AST."""
    nodes: List[Dict[str, Any]] = []

    def walk(node: Dict[str, Any]) -> None:
        tag = node.get("tag")
        text = node.get("text")
        if tag == "img" and node.get("src"):
            nodes.append({"selector": f'img[src="{node["src"]}"]', "expected_count": 1})
        if text and tag in ("h1", "h2", "h3"):
            nodes.append({"selector": tag, "expected_text": text})
        for child in node.get("children", []):
            walk(child)

    root = ast.get("root", ast)
    walk(root)
    return nodes


def run_visual_qa(
    page_url: str,
    ast_path: Optional[str] = None,
    reference_path: Optional[str] = None,
    expected_nodes: Optional[List[Dict[str, Any]]] = None,
    viewport: Optional[Dict[str, int]] = None,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    allowed_domains: Optional[List[str]] = None,
    root_dir: Optional[str] = None,
    figma_frame: Optional[Dict[str, Any]] = None,
    figma_bboxes: Optional[List[Dict[str, Any]]] = None,
    figma_color_nodes: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    merged_expected = list(expected_nodes or [])
    if ast_path:
        path = Path(ast_path)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                ast = json.load(f)
            merged_expected.extend(_expected_nodes_from_ast(ast))

    engine = VisualQAEngine(
        viewport=viewport,
        allowed_domains=allowed_domains,
        output_dir=output_dir,
        root_dir=root_dir,
    )
    report = engine.run(
        page_url,
        reference_path=reference_path,
        expected_nodes=merged_expected,
        figma_frame=figma_frame,
        figma_bboxes=figma_bboxes,
        figma_color_nodes=figma_color_nodes,
    )
    return report.to_dict()


def main():
    parser = argparse.ArgumentParser(description="Visual QA: screenshot + DOM assertions for generated landing page")
    parser.add_argument("--url", required=True, help="URL of the generated landing page")
    parser.add_argument("--ast", default=None, help="Path to Tailwind AST (layout_ast.json) for auto assertions")
    parser.add_argument("--reference", default=None, help="Path to Figma reference screenshot")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Directory for screenshots and report")
    parser.add_argument(
        "--viewport",
        default=None,
        help="Viewport as WIDTHxHEIGHT, e.g. 1280x720",
    )
    parser.add_argument(
        "--expected",
        default=None,
        help='JSON string with DOM assertions, e.g. [{"selector":"h1","expected_text":"Hero"}]',
    )
    parser.add_argument(
        "--allowed-domains",
        default=None,
        help="Comma-separated list of allowed external domains for URL guard.",
    )
    parser.add_argument(
        "--figma-frame",
        default=None,
        help='JSON string with Figma frame dimensions, e.g. {"width":1280,"height":720}',
    )
    parser.add_argument(
        "--figma-bboxes",
        default=None,
        help='JSON string with Figma structural bounding boxes for comparison.',
    )
    parser.add_argument(
        "--figma-color-nodes",
        default=None,
        help='JSON string with Figma nodes containing fill/stroke colors for comparison.',
    )
    args = parser.parse_args()

    viewport = None
    if args.viewport:
        match = re.match(r"(\d+)x(\d+)", args.viewport)
        if match:
            viewport = {"width": int(match.group(1)), "height": int(match.group(2))}

    expected_nodes = None
    if args.expected:
        expected_nodes = json.loads(args.expected)

    allowed_domains = None
    if args.allowed_domains:
        allowed_domains = [d.strip() for d in args.allowed_domains.split(",") if d.strip()]

    figma_frame = None
    if args.figma_frame:
        figma_frame = json.loads(args.figma_frame)

    figma_bboxes = None
    if args.figma_bboxes:
        figma_bboxes = json.loads(args.figma_bboxes)

    figma_color_nodes = None
    if args.figma_color_nodes:
        figma_color_nodes = json.loads(args.figma_color_nodes)

    result = run_visual_qa(
        page_url=args.url,
        ast_path=args.ast,
        reference_path=args.reference,
        expected_nodes=expected_nodes,
        viewport=viewport,
        output_dir=args.output_dir,
        allowed_domains=allowed_domains,
        figma_frame=figma_frame,
        figma_bboxes=figma_bboxes,
        figma_color_nodes=figma_color_nodes,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
