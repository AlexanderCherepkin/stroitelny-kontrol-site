"""Unit tests for figma-agent-core/visual_qa.py.

Loads the module via importlib because the directory name contains a hyphen.
All Playwright and PIL interactions are mocked.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
VISUAL_QA_PATH = ROOT / "figma-agent-core" / "visual_qa.py"


def _load_visual_qa() -> Any:
    spec = importlib.util.spec_from_file_location("figma_visual_qa", str(VISUAL_QA_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_visual_qa"] = module
    spec.loader.exec_module(module)
    return module


visual_qa = _load_visual_qa()


def test_module_loads() -> None:
    assert hasattr(visual_qa, "VisualQAEngine")
    assert hasattr(visual_qa, "run_visual_qa")


def test_allowed_url_localhost() -> None:
    assert visual_qa._is_allowed_url("http://localhost:3000") is True
    assert visual_qa._is_allowed_url("http://127.0.0.1:3000") is True


def test_disallowed_file_outside_workspace(tmp_path: Path) -> None:
    outside = "file:///C:/outside/page.html"
    assert visual_qa._is_allowed_url(outside) is False


def test_visual_qa_blocked_without_playwright() -> None:
    with patch.object(visual_qa, "PLAYWRIGHT_AVAILABLE", False):
        result = visual_qa.run_visual_qa("http://localhost:3000")
        assert result["status"] == "blocked"
        assert "Playwright is not installed" in result["discrepancies"][0]


def test_visual_qa_blocked_for_disallowed_url(tmp_path: Path) -> None:
    with patch.object(visual_qa, "PLAYWRIGHT_AVAILABLE", True):
        with patch("figma_visual_qa.sync_playwright"):
            result = visual_qa.run_visual_qa(
                "http://evil.example.com",
                output_dir=str(tmp_path / "qa"),
                root_dir=str(tmp_path),
            )
            assert result["status"] == "blocked"
            assert "not allowed" in result["discrepancies"][0].lower()


def _build_mock_page() -> MagicMock:
    page = MagicMock()
    page.query_selector_all.return_value = []
    page.evaluate.return_value = None
    page.wait_for_function.return_value = None
    page.locator.return_value.first.count.return_value = 0
    return page


def _build_mock_playwright(tmp_path: Path) -> Any:
    page = _build_mock_page()
    context = MagicMock()
    context.new_page.return_value = page
    browser = MagicMock()
    browser.new_context.return_value = context
    browser.close = MagicMock()
    playwright_obj = MagicMock()
    playwright_obj.chromium.launch.return_value = browser

    class SyncPlaywrightContext:
        def __enter__(self):
            return playwright_obj
        def __exit__(self, *args):
            pass

    sync_p = SyncPlaywrightContext()
    return sync_p, page, browser


def test_visual_qa_captures_screenshot_and_passes(tmp_path: Path) -> None:
    output_dir = tmp_path / "qa"
    sync_p, page, browser = _build_mock_playwright(tmp_path)

    fake_image = tmp_path / "fake.png"
    fake_image.write_bytes(b"png")

    with patch.object(visual_qa, "PLAYWRIGHT_AVAILABLE", True):
        with patch.object(visual_qa, "PIL_AVAILABLE", False):
            with patch("figma_visual_qa.sync_playwright", return_value=sync_p):
                engine = visual_qa.VisualQAEngine(output_dir=str(output_dir), root_dir=str(tmp_path))
                report = engine.run("http://localhost:3000")

    assert report.status == "passed"
    assert report.screenshot_path is not None
    assert Path(report.screenshot_path).parent == output_dir.resolve()
    assert (output_dir / "report.json").exists()
    page.screenshot.assert_called_once()
    page.goto.assert_called_once_with("http://localhost:3000", wait_until="networkidle", timeout=30000)


def test_visual_qa_dom_assertion_failure(tmp_path: Path) -> None:
    output_dir = tmp_path / "qa"
    sync_p, page, browser = _build_mock_playwright(tmp_path)
    fake_image = tmp_path / "fake.png"
    fake_image.write_bytes(b"png")

    el = MagicMock()
    el.inner_text.return_value = "Wrong"
    page.query_selector_all.return_value = [el]

    expected = [{"selector": "h1", "exact_text": "Hero Title", "expected_count": 1}]

    with patch.object(visual_qa, "PLAYWRIGHT_AVAILABLE", True):
        with patch.object(visual_qa, "PIL_AVAILABLE", False):
            with patch("figma_visual_qa.sync_playwright", return_value=sync_p):
                result = visual_qa.run_visual_qa(
                    "http://localhost:3000",
                    expected_nodes=expected,
                    output_dir=str(output_dir),
                    root_dir=str(tmp_path),
                )

    assert result["status"] == "failed"
    assertions = result["dom_assertions"]
    assert len(assertions) == 1
    assert assertions[0]["passed"] is False
    assert "exact text" in " ".join(assertions[0]["discrepancies"]).lower()


def test_expected_nodes_from_ast_extracts_headings_and_images() -> None:
    ast = {
        "root": {
            "tag": "section",
            "children": [
                {"tag": "h1", "text": "Build fast"},
                {"tag": "img", "src": "/images/hero.png"},
                {"tag": "p", "text": "Body"},
            ],
        }
    }
    nodes = visual_qa._expected_nodes_from_ast(ast)
    selectors = {n["selector"] for n in nodes}
    assert "h1" in selectors
    assert 'img[src="/images/hero.png"]' in selectors


def test_visual_qa_with_ast_file(tmp_path: Path) -> None:
    ast_path = tmp_path / "ast.json"
    ast = {"root": {"tag": "section", "children": [{"tag": "h1", "text": "Hello"}]}}
    ast_path.write_text(json.dumps(ast), encoding="utf-8")

    output_dir = tmp_path / "qa"
    sync_p, page, browser = _build_mock_playwright(tmp_path)
    fake_image = tmp_path / "fake.png"
    fake_image.write_bytes(b"png")

    el = MagicMock()
    el.inner_text.return_value = "Hello"
    page.query_selector_all.return_value = [el]

    with patch.object(visual_qa, "PLAYWRIGHT_AVAILABLE", True):
        with patch.object(visual_qa, "PIL_AVAILABLE", False):
            with patch("figma_visual_qa.sync_playwright", return_value=sync_p):
                result = visual_qa.run_visual_qa(
                    "http://localhost:3000",
                    ast_path=str(ast_path),
                    output_dir=str(output_dir),
                    root_dir=str(tmp_path),
                )

    assert result["status"] == "passed"
    assert any(a["selector"] == "h1" for a in result["dom_assertions"])


def test_visual_qa_navigation_warning_still_reports(tmp_path: Path) -> None:
    output_dir = tmp_path / "qa"
    sync_p, page, browser = _build_mock_playwright(tmp_path)
    fake_image = tmp_path / "fake.png"
    fake_image.write_bytes(b"png")
    page.goto.side_effect = Exception("timeout")

    with patch.object(visual_qa, "PLAYWRIGHT_AVAILABLE", True):
        with patch.object(visual_qa, "PIL_AVAILABLE", False):
            with patch("figma_visual_qa.sync_playwright", return_value=sync_p):
                result = visual_qa.run_visual_qa(
                    "http://localhost:3000",
                    output_dir=str(output_dir),
                    root_dir=str(tmp_path),
                )

    assert result["status"] == "failed"
    assert any("Navigation warning" in d for d in result["discrepancies"])


def test_visual_qa_uses_figma_frame_viewport(tmp_path: Path) -> None:
    output_dir = tmp_path / "qa"
    sync_p, page, browser = _build_mock_playwright(tmp_path)
    fake_image = tmp_path / "fake.png"
    fake_image.write_bytes(b"png")

    with patch.object(visual_qa, "PLAYWRIGHT_AVAILABLE", True):
        with patch.object(visual_qa, "PIL_AVAILABLE", False):
            with patch("figma_visual_qa.sync_playwright", return_value=sync_p):
                engine = visual_qa.VisualQAEngine(
                    viewport={"width": 1280, "height": 720},
                    output_dir=str(output_dir),
                    root_dir=str(tmp_path),
                )
                engine.run(
                    "http://localhost:3000",
                    figma_frame={"width": 1440, "height": 900},
                )

    context = browser.new_context
    assert context.call_args
    assert context.call_args.kwargs["viewport"]["width"] == 1440
    assert context.call_args.kwargs["viewport"]["height"] == 900


def test_visual_qa_injects_freeze_css(tmp_path: Path) -> None:
    output_dir = tmp_path / "qa"
    sync_p, page, browser = _build_mock_playwright(tmp_path)
    fake_image = tmp_path / "fake.png"
    fake_image.write_bytes(b"png")

    with patch.object(visual_qa, "PLAYWRIGHT_AVAILABLE", True):
        with patch.object(visual_qa, "PIL_AVAILABLE", False):
            with patch("figma_visual_qa.sync_playwright", return_value=sync_p):
                engine = visual_qa.VisualQAEngine(output_dir=str(output_dir), root_dir=str(tmp_path))
                engine.run("http://localhost:3000")

    page.add_style_tag.assert_called_once()
    content = page.add_style_tag.call_args.kwargs.get("content", "")
    assert "animation-duration: 0s" in content


def test_visual_qa_waits_for_fonts_and_images(tmp_path: Path) -> None:
    output_dir = tmp_path / "qa"
    sync_p, page, browser = _build_mock_playwright(tmp_path)
    fake_image = tmp_path / "fake.png"
    fake_image.write_bytes(b"png")

    with patch.object(visual_qa, "PLAYWRIGHT_AVAILABLE", True):
        with patch.object(visual_qa, "PIL_AVAILABLE", False):
            with patch("figma_visual_qa.sync_playwright", return_value=sync_p):
                engine = visual_qa.VisualQAEngine(output_dir=str(output_dir), root_dir=str(tmp_path))
                engine.run("http://localhost:3000")

    page.evaluate.assert_any_call("document.fonts.ready")
    page.wait_for_function.assert_called_once()
    wait_script = page.wait_for_function.call_args.args[0]
    assert "document.querySelectorAll('img, svg image')" in wait_script


def test_visual_qa_detects_overflow(tmp_path: Path) -> None:
    output_dir = tmp_path / "qa"
    sync_p, page, browser = _build_mock_playwright(tmp_path)
    fake_image = tmp_path / "fake.png"
    fake_image.write_bytes(b"png")

    page.evaluate.return_value = None
    page.wait_for_function.return_value = None
    page.evaluate.side_effect = [
        None,
        None,
        [{"type": "overflow", "selector": "div", "overflow_y": True, "overflow_x": False}],
        [],
        [],
        {"font_families": ["Inter"], "body_font_size": "16px", "body_line_height": "1.5"},
        {"total_images": 0, "loaded_images": 0, "broken_images": 0},
    ]

    with patch.object(visual_qa, "PLAYWRIGHT_AVAILABLE", True):
        with patch.object(visual_qa, "PIL_AVAILABLE", False):
            with patch("figma_visual_qa.sync_playwright", return_value=sync_p):
                engine = visual_qa.VisualQAEngine(output_dir=str(output_dir), root_dir=str(tmp_path))
                report = engine.run("http://localhost:3000")

    assert report.status == "failed"
    assert any(c.get("type") == "overflow" for c in report.layout_checks)


def test_visual_qa_bbox_comparison_passes_within_tolerance(tmp_path: Path) -> None:
    output_dir = tmp_path / "qa"
    sync_p, page, browser = _build_mock_playwright(tmp_path)
    fake_image = tmp_path / "fake.png"
    fake_image.write_bytes(b"png")

    page.evaluate.return_value = None
    page.wait_for_function.return_value = None
    page_bboxes = [{"tag": "section", "figma_id": "1:1", "x": 0, "y": 0, "width": 100, "height": 200}]
    page.evaluate.side_effect = [
        None,
        None,
        [],
        [],
        [],
        page_bboxes,
        {"font_families": ["Inter"], "body_font_size": "16px", "body_line_height": "1.5"},
        {"total_images": 0, "loaded_images": 0, "broken_images": 0},
    ]

    figma_bboxes = [{"id": "1:1", "width": 104, "height": 208}]

    with patch.object(visual_qa, "PLAYWRIGHT_AVAILABLE", True):
        with patch.object(visual_qa, "PIL_AVAILABLE", False):
            with patch("figma_visual_qa.sync_playwright", return_value=sync_p):
                engine = visual_qa.VisualQAEngine(
                    output_dir=str(output_dir),
                    root_dir=str(tmp_path),
                    bbox_tolerance_px=8,
                )
                report = engine.run(
                    "http://localhost:3000",
                    figma_bboxes=figma_bboxes,
                )

    assert report.status == "passed"
    assert report.bbox_comparison["passed"] == 1


def test_visual_qa_bbox_comparison_fails_outside_tolerance(tmp_path: Path) -> None:
    output_dir = tmp_path / "qa"
    sync_p, page, browser = _build_mock_playwright(tmp_path)
    fake_image = tmp_path / "fake.png"
    fake_image.write_bytes(b"png")

    page.evaluate.return_value = None
    page.wait_for_function.return_value = None
    page_bboxes = [{"tag": "section", "figma_id": "1:1", "x": 0, "y": 0, "width": 100, "height": 200}]
    page.evaluate.side_effect = [
        None,
        None,
        [],
        [],
        [],
        page_bboxes,
        {"font_families": ["Inter"], "body_font_size": "16px", "body_line_height": "1.5"},
        {"total_images": 0, "loaded_images": 0, "broken_images": 0},
    ]

    figma_bboxes = [{"id": "1:1", "width": 130, "height": 200}]

    with patch.object(visual_qa, "PLAYWRIGHT_AVAILABLE", True):
        with patch.object(visual_qa, "PIL_AVAILABLE", False):
            with patch("figma_visual_qa.sync_playwright", return_value=sync_p):
                engine = visual_qa.VisualQAEngine(
                    output_dir=str(output_dir),
                    root_dir=str(tmp_path),
                    bbox_tolerance_px=8,
                )
                report = engine.run(
                    "http://localhost:3000",
                    figma_bboxes=figma_bboxes,
                )

    assert report.status == "failed"
    assert report.bbox_comparison["failed"] == 1


def test_visual_qa_pixel_metrics_report_deltas(tmp_path: Path) -> None:
    output_dir = tmp_path / "qa"
    sync_p, page, browser = _build_mock_playwright(tmp_path)
    fake_image = tmp_path / "fake.png"
    fake_image.write_bytes(b"png")

    page.evaluate.return_value = None
    page.wait_for_function.return_value = None
    page_bboxes = [{"tag": "section", "figma_id": "1:1", "x": 4, "y": 2, "width": 100, "height": 200}]
    page.evaluate.side_effect = [
        None,
        None,
        [],
        [],
        [],
        page_bboxes,
        {"font_families": ["Inter"], "body_font_size": "16px", "body_line_height": "1.5"},
        {"total_images": 0, "loaded_images": 0, "broken_images": 0},
    ]

    figma_bboxes = [{"id": "1:1", "x": 0, "y": 0, "width": 130, "height": 230}]

    with patch.object(visual_qa, "PLAYWRIGHT_AVAILABLE", True):
        with patch.object(visual_qa, "PIL_AVAILABLE", False):
            with patch("figma_visual_qa.sync_playwright", return_value=sync_p):
                engine = visual_qa.VisualQAEngine(
                    output_dir=str(output_dir),
                    root_dir=str(tmp_path),
                    bbox_tolerance_px=8,
                )
                report = engine.run(
                    "http://localhost:3000",
                    figma_bboxes=figma_bboxes,
                )

    assert report.status == "failed"
    assert report.pixel_metrics["failed_nodes"] == 1
    assert report.pixel_metrics["total_drift_px"] == 4 + 2 + 30 + 30
    check = report.bbox_comparison["checks"][0]
    assert check["delta_x"] == 4
    assert check["delta_y"] == 2
    assert check["delta_width"] == -30
    assert check["delta_height"] == -30


def test_visual_qa_font_mismatch_check(tmp_path: Path) -> None:
    output_dir = tmp_path / "qa"
    sync_p, page, browser = _build_mock_playwright(tmp_path)
    fake_image = tmp_path / "fake.png"
    fake_image.write_bytes(b"png")

    el = MagicMock()
    el.inner_text.return_value = "Hello"
    page.query_selector_all.return_value = [el]

    page.evaluate.return_value = None
    page.wait_for_function.return_value = None
    page.evaluate.side_effect = [
        None,
        None,
        [],
        [],
        [],
        [
            {
                "figma_id": "10:1",
                "font_family": "Arial",
                "font_size": "14px",
                "line_height": "14px",
                "letter_spacing": "0px",
                "font_weight": "400",
                "x": 0,
                "y": 0,
                "width": 100,
                "height": 20,
            }
        ],
        [],
        {"font_families": ["Arial"], "body_font_size": "16px", "body_line_height": "1.5"},
        {"total_images": 0, "loaded_images": 0, "broken_images": 0},
    ]

    expected = [
        {
            "id": "10:1",
            "selector": "h1",
            "expected_count": 1,
            "exact_text": "Hello",
            "is_text": True,
            "style": {
                "fontFamily": "Inter",
                "fontSize": 18,
                "lineHeightPx": 27,
                "letterSpacing": 1,
                "fontWeight": 700,
            },
        }
    ]

    with patch.object(visual_qa, "PLAYWRIGHT_AVAILABLE", True):
        with patch.object(visual_qa, "PIL_AVAILABLE", False):
            with patch("figma_visual_qa.sync_playwright", return_value=sync_p):
                result = visual_qa.run_visual_qa(
                    "http://localhost:3000",
                    expected_nodes=expected,
                    output_dir=str(output_dir),
                    root_dir=str(tmp_path),
                )

    assert result["status"] == "failed"
    font_checks = [c for c in result["layout_checks"] if c.get("type") == "font_mismatch"]
    assert len(font_checks) == 1
    assert set(font_checks[0]["mismatches"]) == {"family", "size", "weight", "line_height", "letter_spacing"}


def test_visual_qa_snug_text_check(tmp_path: Path) -> None:
    output_dir = tmp_path / "qa"
    sync_p, page, browser = _build_mock_playwright(tmp_path)
    fake_image = tmp_path / "fake.png"
    fake_image.write_bytes(b"png")

    el = MagicMock()
    el.inner_text.return_value = "Hello"
    page.query_selector_all.return_value = [el]

    page.evaluate.return_value = None
    page.wait_for_function.return_value = None
    page.evaluate.side_effect = [
        None,
        None,
        [],
        [],
        [],
        [],
        [
            {
                "tag": "span",
                "figma_id": "20:1",
                "x": 0,
                "y": 0,
                "width": 180,
                "height": 20,
            }
        ],
        {"font_families": ["Inter"], "body_font_size": "16px", "body_line_height": "1.5"},
        {"total_images": 0, "loaded_images": 0, "broken_images": 0},
    ]

    expected = [
        {
            "id": "20:1",
            "selector": "span",
            "expected_count": 1,
            "exact_text": "Hello",
            "is_text": True,
            "box": {"width": 142, "height": 20},
        }
    ]

    with patch.object(visual_qa, "PLAYWRIGHT_AVAILABLE", True):
        with patch.object(visual_qa, "PIL_AVAILABLE", False):
            with patch("figma_visual_qa.sync_playwright", return_value=sync_p):
                result = visual_qa.run_visual_qa(
                    "http://localhost:3000",
                    expected_nodes=expected,
                    output_dir=str(output_dir),
                    root_dir=str(tmp_path),
                )

    assert result["status"] == "failed"
    snug_checks = [c for c in result["layout_checks"] if c.get("type") == "snug_text"]
    assert len(snug_checks) == 1
    assert snug_checks[0]["delta_width"] == 38


def test_rgba_to_hex() -> None:
    assert visual_qa._rgba_to_hex(1, 1, 1) == "#ffffff"
    assert visual_qa._rgba_to_hex(0, 0, 0, 1) == "#000000"
    assert visual_qa._rgba_to_hex(0.23, 0.51, 0.96, 1.0) == "#3b82f5"
    assert visual_qa._rgba_to_hex(1, 0, 0, 0.5) == "#ff000080"


def test_parse_css_color() -> None:
    assert visual_qa._parse_css_color("rgb(59, 130, 245)") == "#3b82f5"
    assert visual_qa._parse_css_color("rgba(59, 130, 245, 0.8)") == "#3b82f5"
    assert visual_qa._parse_css_color("#3b82f5") == "#3b82f5"
    assert visual_qa._parse_css_color("#f00") == "#ff0000"
    assert visual_qa._parse_css_color("transparent") is None


def test_extract_figma_fill_color() -> None:
    node = {
        "fills": [
            {"type": "SOLID", "visible": True, "color": {"r": 0.23, "g": 0.51, "b": 0.96, "a": 1}},
        ]
    }
    assert visual_qa._extract_figma_fill_color(node) == "#3b82f5"


def test_extract_figma_stroke_color() -> None:
    node = {
        "strokes": [
            {"type": "SOLID", "visible": True, "color": {"r": 1, "g": 0, "b": 0, "a": 1}},
        ]
    }
    assert visual_qa._extract_figma_stroke_color(node) == "#ff0000"


def test_visual_qa_color_mismatch_detected(tmp_path: Path) -> None:
    output_dir = tmp_path / "qa"
    sync_p, page, browser = _build_mock_playwright(tmp_path)
    fake_image = tmp_path / "fake.png"
    fake_image.write_bytes(b"png")

    page.evaluate.return_value = None
    page.wait_for_function.return_value = None
    page.evaluate.side_effect = [
        None,
        None,
        [],
        [],
        [],
        {"font_families": ["Inter"], "body_font_size": "16px", "body_line_height": "1.5"},
        [],
        {"total_images": 0, "loaded_images": 0, "broken_images": 0},
        [
            {
                "figma_id": "30:1",
                "background_color": "rgb(255, 0, 0)",
                "color": "rgb(0, 0, 0)",
                "border_color": "rgb(0, 0, 255)",
                "x": 0,
                "y": 0,
                "width": 100,
                "height": 100,
            }
        ],
    ]

    figma_color_nodes = [
        {
            "id": "30:1",
            "fills": [{"type": "SOLID", "visible": True, "color": {"r": 0, "g": 1, "b": 0, "a": 1}}],
            "strokes": [{"type": "SOLID", "visible": True, "color": {"r": 0, "g": 0, "b": 0, "a": 1}}],
        }
    ]

    with patch.object(visual_qa, "PLAYWRIGHT_AVAILABLE", True):
        with patch.object(visual_qa, "PIL_AVAILABLE", False):
            with patch("figma_visual_qa.sync_playwright", return_value=sync_p):
                engine = visual_qa.VisualQAEngine(output_dir=str(output_dir), root_dir=str(tmp_path))
                report = engine.run(
                    "http://localhost:3000",
                    figma_color_nodes=figma_color_nodes,
                )

    assert report.status == "failed"
    assert report.color_metrics["total"] == 1
    assert report.color_metrics["failed"] == 1
    checks = report.color_metrics["checks"]
    assert any("background" in c["mismatches"] for c in checks)
    assert any("border" in c["mismatches"] for c in checks)


def test_visual_qa_color_match_passes(tmp_path: Path) -> None:
    output_dir = tmp_path / "qa"
    sync_p, page, browser = _build_mock_playwright(tmp_path)
    fake_image = tmp_path / "fake.png"
    fake_image.write_bytes(b"png")

    page.evaluate.return_value = None
    page.wait_for_function.return_value = None
    page.evaluate.side_effect = [
        None,
        None,
        [],
        [],
        [],
        {"font_families": ["Inter"], "body_font_size": "16px", "body_line_height": "1.5"},
        [],
        {"total_images": 0, "loaded_images": 0, "broken_images": 0},
        [
            {
                "figma_id": "31:1",
                "background_color": "rgb(59, 130, 245)",
                "color": "rgb(0, 0, 0)",
                "border_color": "rgb(255, 255, 255)",
                "x": 0,
                "y": 0,
                "width": 100,
                "height": 100,
            }
        ],
    ]

    figma_color_nodes = [
        {
            "id": "31:1",
            "fills": [{"type": "SOLID", "visible": True, "color": {"r": 0.23, "g": 0.51, "b": 0.96, "a": 1}}],
        }
    ]

    with patch.object(visual_qa, "PLAYWRIGHT_AVAILABLE", True):
        with patch.object(visual_qa, "PIL_AVAILABLE", False):
            with patch("figma_visual_qa.sync_playwright", return_value=sync_p):
                engine = visual_qa.VisualQAEngine(output_dir=str(output_dir), root_dir=str(tmp_path))
                report = engine.run(
                    "http://localhost:3000",
                    figma_color_nodes=figma_color_nodes,
                )

    assert report.status == "passed"
    assert report.color_metrics["total"] == 1
    assert report.color_metrics["passed"] == 1
    assert report.color_metrics["failed"] == 0
