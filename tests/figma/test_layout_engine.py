"""Unit tests for figma-agent-core/layout_engine.py.

Loads the module via importlib because the directory name contains a hyphen.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
LAYOUT_ENGINE_PATH = ROOT / "figma-agent-core" / "layout_engine.py"


def _load_layout_engine() -> Any:
    spec = importlib.util.spec_from_file_location("figma_layout_engine", str(LAYOUT_ENGINE_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_layout_engine"] = module
    spec.loader.exec_module(module)
    return module


layout_engine = _load_layout_engine()


def _find_class(node: Dict[str, Any], class_name: str) -> bool:
    return class_name in node.get("classes", [])


def test_load_module() -> None:
    assert hasattr(layout_engine, "FigmaLayoutEngine")
    assert hasattr(layout_engine, "convert_figma_node")


def test_empty_node_returns_section() -> None:
    result = layout_engine.convert_figma_node({
        "id": "0:1",
        "name": "Canvas",
        "type": "FRAME",
        "visible": True,
    })
    root = result.root
    assert root.tag == "section"
    assert root.figma_id == "0:1"


def test_autolayout_vertical_with_gap_and_padding() -> None:
    node = {
        "id": "10:1",
        "name": "Features",
        "type": "FRAME",
        "visible": True,
        "layoutMode": "VERTICAL",
        "itemSpacing": 24,
        "paddingTop": 64,
        "paddingRight": 32,
        "paddingBottom": 64,
        "paddingLeft": 32,
        "primaryAxisAlignItems": "CENTER",
        "counterAxisAlignItems": "CENTER",
        "box": {"x": 0, "y": 0, "width": 1200, "height": 600},
        "children": [],
    }
    result = layout_engine.convert_figma_node(node)
    classes = result.root.classes
    assert "flex" in classes
    assert "flex-col" in classes
    assert "gap-[24px]" in classes
    assert "py-[64px]" in classes
    assert "px-[32px]" in classes
    assert "justify-center" in classes
    assert "items-center" in classes
    assert "w-[1200px]" in classes
    assert "h-[600px]" in classes


def test_autolayout_horizontal_space_between() -> None:
    node = {
        "id": "20:1",
        "name": "Header",
        "type": "FRAME",
        "visible": True,
        "layoutMode": "HORIZONTAL",
        "itemSpacing": 0,
        "paddingTop": 16,
        "paddingRight": 24,
        "paddingBottom": 16,
        "paddingLeft": 24,
        "primaryAxisAlignItems": "SPACE_BETWEEN",
        "counterAxisAlignItems": "CENTER",
        "children": [],
    }
    result = layout_engine.convert_figma_node(node)
    classes = result.root.classes
    assert "flex-row" in classes
    assert "justify-between" in classes
    assert "items-center" in classes
    assert "p-[16px]" not in classes
    assert "py-[16px]" in classes
    assert "px-[24px]" in classes


def test_text_node_typography() -> None:
    node = {
        "id": "30:1",
        "name": "Headline",
        "type": "TEXT",
        "visible": True,
        "characters": "Build fast",
        "box": {"x": 100, "y": 200, "width": 400, "height": 48},
        "style": {
            "fontFamily": "Inter",
            "fontSize": 40,
            "fontWeight": 700,
            "lineHeightPx": 48,
            "letterSpacing": -1,
            "textAlignHorizontal": "CENTER",
            "fills": [{"type": "SOLID", "hex": "#111827"}],
        },
    }
    result = layout_engine.convert_figma_node(node)
    root = result.root
    assert root.tag == "h1"
    assert root.text == "Build fast"
    assert "text-[40px]" in root.classes
    assert "font-[700]" in root.classes
    assert "font-[Inter]" in root.classes
    assert "text-center" in root.classes
    assert "text-[#111827]" in root.classes
    assert result.text_node_count == 1


def test_text_tag_fallback_to_paragraph() -> None:
    node = {
        "id": "31:1",
        "name": "Description",
        "type": "TEXT",
        "visible": True,
        "characters": "Some body text",
        "style": {"fontSize": 16, "fontWeight": 400},
    }
    result = layout_engine.convert_figma_node(node)
    assert result.root.tag == "p"


def test_rich_text_bold_span_keeps_base_text() -> None:
    node = {
        "id": "32:1",
        "name": "Mixed",
        "type": "TEXT",
        "visible": True,
        "characters": "Hello world",
        "style": {"fontSize": 16, "fontWeight": 400},
        "characterStyleOverrides": ["", "", "", "", "", "", "bold", "bold", "bold", "bold", "bold"],
        "styleOverrideTable": {
            "bold": {"fontWeight": 700},
        },
    }
    result = layout_engine.convert_figma_node(node)
    root = result.root
    assert root.text == "Hello world"
    assert root.rich_text
    assert len(root.rich_text) == 2
    assert root.rich_text[1]["text"] == "world"
    assert "font-[700]" in root.rich_text[1]["classes"]


def test_rich_text_italic_and_color_span() -> None:
    node = {
        "id": "32:2",
        "name": "Styled",
        "type": "TEXT",
        "visible": True,
        "characters": "Start middle end",
        "style": {"fontSize": 16, "fontWeight": 400},
        "characterStyleOverrides": ["", "", "", "", "", "", "em", "em", "em", "em", "em", "em", "", "", ""],
        "styleOverrideTable": {
            "em": {"italic": True, "fills": [{"type": "SOLID", "hex": "#ef4444"}]},
        },
    }
    result = layout_engine.convert_figma_node(node)
    root = result.root
    spans = root.rich_text or []
    middle = [s for s in spans if s["text"] == "middle"]
    assert middle
    assert "italic" in middle[0]["classes"]
    assert any("text-red-500" in c for c in middle[0]["classes"])


def test_rich_text_link_span() -> None:
    node = {
        "id": "32:3",
        "name": "Link",
        "type": "TEXT",
        "visible": True,
        "characters": "Click here",
        "style": {"fontSize": 16, "fontWeight": 400},
        "characterStyleOverrides": ["", "", "", "", "", "", "link", "link", "link", "link"],
        "styleOverrideTable": {
            "link": {"hyperlink": {"type": "URL", "url": "https://example.com"}, "fontWeight": 700},
        },
    }
    result = layout_engine.convert_figma_node(node)
    spans = result.root.rich_text or []
    link_span = [s for s in spans if s.get("tag") == "a"]
    assert link_span
    assert link_span[0]["href"] == "https://example.com"
    assert link_span[0]["text"] == "here"


def test_rich_text_newlines_emit_br_markers() -> None:
    node = {
        "id": "32:4",
        "name": "Multiline",
        "type": "TEXT",
        "visible": True,
        "characters": "Line1\nLine2",
        "style": {"fontSize": 16, "fontWeight": 400},
        "characterStyleOverrides": ["", "", "", "", "", "", "bold", "bold", "bold", "bold", "bold"],
        "styleOverrideTable": {
            "bold": {"fontWeight": 700},
        },
    }
    result = layout_engine.convert_figma_node(node)
    spans = result.root.rich_text or []
    assert len(spans) == 3
    assert spans[1]["text"] == ""
    assert spans[1]["newline_before"] is True
    assert spans[2]["text"] == "Line2"
    assert "font-[700]" in spans[2]["classes"]


def test_text_node_italic_base_style() -> None:
    node = {
        "id": "32:5",
        "name": "Italic",
        "type": "TEXT",
        "visible": True,
        "characters": "Italic text",
        "style": {"fontSize": 16, "fontWeight": 400, "italic": True},
    }
    result = layout_engine.convert_figma_node(node)
    assert "italic" in result.root.classes


def test_asset_node_becomes_image() -> None:
    node = {
        "id": "40:1",
        "name": "Hero image",
        "type": "IMAGE",
        "visible": True,
        "isAsset": True,
        "publicPath": "/images/hero_40_1.png",
        "box": {"x": 0, "y": 0, "width": 600, "height": 400},
    }
    result = layout_engine.convert_figma_node(node)
    root = result.root
    assert root.tag == "img"
    assert root.src == "/images/hero_40_1.png"
    assert "w-[600px]" in root.classes
    assert "h-[400px]" in root.classes
    assert result.asset_count == 1


def test_asset_registry_resolves_image_ref() -> None:
    node = {
        "id": "40:2",
        "name": "Hero image",
        "type": "IMAGE",
        "visible": True,
        "box": {"x": 0, "y": 0, "width": 360, "height": 160},
    }
    assets = {
        "assets": {
            "40:2": {
                "publicPath": "/assets/figma/hero_40_2.png",
                "type": "raster",
                "width": 360,
                "height": 160,
            }
        }
    }
    result = layout_engine.convert_figma_node(node, config={"assets": assets})
    root = result.root
    assert root.tag == "img"
    assert root.src == "/assets/figma/hero_40_2.png"
    assert root.asset_type == "raster"
    assert root.asset_width == 360
    assert root.asset_height == 160


def test_image_fill_resolved_from_registry() -> None:
    node = {
        "id": "50:1",
        "name": "Card bg",
        "type": "RECTANGLE",
        "visible": True,
        "box": {"x": 0, "y": 0, "width": 300, "height": 200},
        "fills": [{"type": "IMAGE", "imageRef": "bg-ref-1"}],
    }
    assets = {
        "assets": {
            "bg-ref-1": {
                "publicPath": "/assets/figma/card_bg.png",
                "type": "raster",
                "width": 300,
                "height": 200,
            }
        }
    }
    result = layout_engine.convert_figma_node(node, config={"assets": assets})
    root = result.root
    assert "background-image" in root.inline_styles
    assert "/assets/figma/card_bg.png" in root.inline_styles["background-image"]


def test_shape_with_fill_and_radius() -> None:
    node = {
        "id": "50:1",
        "name": "Card bg",
        "type": "RECTANGLE",
        "visible": True,
        "box": {"x": 0, "y": 0, "width": 300, "height": 200},
        "fills": [{"type": "SOLID", "hex": "#ffffff"}],
        "cornerRadius": 16,
    }
    result = layout_engine.convert_figma_node(node)
    root = result.root
    assert root.tag == "div"
    assert "bg-white" in root.classes
    assert "rounded-2xl" in root.classes
    assert "w-[300px]" in root.classes
    assert "h-[200px]" in root.classes


def test_nested_autolayout_children_preserve_structure() -> None:
    child = {
        "id": "60:2",
        "name": "Row",
        "type": "FRAME",
        "visible": True,
        "layoutMode": "HORIZONTAL",
        "itemSpacing": 12,
        "children": [
            {
                "id": "60:3",
                "name": "Label",
                "type": "TEXT",
                "visible": True,
                "characters": "Label",
                "style": {"fontSize": 14, "fontWeight": 500},
            }
        ],
    }
    parent = {
        "id": "60:1",
        "name": "Wrapper",
        "type": "FRAME",
        "visible": True,
        "layoutMode": "VERTICAL",
        "itemSpacing": 8,
        "children": [child],
    }
    result = layout_engine.convert_figma_node(parent)
    assert result.root.tag == "section"
    assert result.root.children[0].tag == "div"
    assert "flex-row" in result.root.children[0].classes
    assert "gap-[12px]" in result.root.children[0].classes
    assert result.root.children[0].children[0].tag == "p"


def test_absolute_positioning_for_non_autolayout() -> None:
    parent = {
        "id": "70:1",
        "name": "Canvas",
        "type": "FRAME",
        "visible": True,
        "box": {"x": 0, "y": 0, "width": 800, "height": 600},
        "children": [
            {
                "id": "70:2",
                "name": "Badge",
                "type": "FRAME",
                "visible": True,
                "box": {"x": 720, "y": 20, "width": 60, "height": 24},
                "fills": [{"type": "SOLID", "hex": "#22c55e"}],
            }
        ],
    }
    result = layout_engine.convert_figma_node(parent)
    badge = result.root.children[0]
    assert "absolute" in badge.classes
    assert badge.inline_styles.get("left") == "720px"
    assert badge.inline_styles.get("top") == "20px"


def test_invisible_nodes_are_skipped() -> None:
    parent = {
        "id": "80:1",
        "name": "Wrapper",
        "type": "FRAME",
        "visible": True,
        "children": [
            {"id": "80:2", "name": "Hidden", "type": "TEXT", "visible": False},
            {"id": "80:3", "name": "Visible", "type": "TEXT", "visible": True, "characters": "OK"},
        ],
    }
    result = layout_engine.convert_figma_node(parent)
    assert len(result.root.children) == 1
    assert result.root.children[0].text == "OK"


def test_shadow_effect_maps_to_inline_style() -> None:
    node = {
        "id": "90:1",
        "name": "Shadow box",
        "type": "RECTANGLE",
        "visible": True,
        "box": {"width": 200, "height": 100},
        "effects": [
            {
                "type": "DROP_SHADOW",
                "hex": "rgba(0, 0, 0, 0.15)",
                "offset": {"x": 0, "y": 4},
                "radius": 16,
            }
        ],
    }
    result = layout_engine.convert_figma_node(node)
    assert result.root.inline_styles.get("box-shadow") == "0px 4px 16px 0px rgba(0, 0, 0, 0.15)"


def test_stats_counters() -> None:
    node = {
        "id": "100:1",
        "name": "Section",
        "type": "FRAME",
        "visible": True,
        "children": [
            {"id": "100:2", "name": "T", "type": "TEXT", "visible": True, "characters": "A"},
            {"id": "100:3", "name": "I", "type": "IMAGE", "visible": True, "isAsset": True, "publicPath": "/images/i.png"},
            {"id": "100:4", "name": "D", "type": "FRAME", "visible": True},
        ],
    }
    result = layout_engine.convert_figma_node(node)
    assert result.node_count == 4
    assert result.text_node_count == 1
    assert result.asset_count == 1


def _load_fixture(name: str) -> Dict[str, Any]:
    path = Path(__file__).resolve().parent / "fixtures" / name
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_raw_color_computed_when_hex_missing() -> None:
    node = {
        "id": "110:1",
        "name": "Button",
        "type": "FRAME",
        "visible": True,
        "layoutMode": "HORIZONTAL",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 120, "height": 40},
        "fills": [{"type": "SOLID", "color": {"r": 0.23, "g": 0.51, "b": 0.96, "a": 1}}],
    }
    result = layout_engine.convert_figma_node(node)
    assert "bg-[#3b82f5]" in result.root.classes


def test_gradient_stops_from_raw_figma() -> None:
    node = {
        "id": "120:1",
        "name": "Hero Section",
        "type": "FRAME",
        "visible": True,
        "layoutMode": "VERTICAL",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 600},
        "fills": [
            {
                "type": "GRADIENT_LINEAR",
                "gradientStops": [
                    {"position": 0, "color": {"r": 1, "g": 1, "b": 1, "a": 1}},
                    {"position": 1, "color": {"r": 0, "g": 0, "b": 0, "a": 1}},
                ],
            }
        ],
    }
    result = layout_engine.convert_figma_node(node)
    assert result.root.inline_styles.get("background") == "linear-gradient(180deg, #ffffff 0%, #000000 100%)"


def test_vector_without_image_fill_becomes_shape() -> None:
    node = {
        "id": "130:1",
        "name": "Icon",
        "type": "VECTOR",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 48, "height": 48},
        "fills": [{"type": "SOLID", "color": {"r": 0.23, "g": 0.51, "b": 0.96, "a": 1}}],
    }
    result = layout_engine.convert_figma_node(node)
    assert result.root.tag == "div"
    assert result.root.src is None
    assert "bg-[#3b82f5]" in result.root.classes


def test_counter_axis_stretch_maps_to_items_stretch() -> None:
    node = {
        "id": "140:1",
        "name": "Row",
        "type": "FRAME",
        "visible": True,
        "layoutMode": "HORIZONTAL",
        "counterAxisAlignItems": "STRETCH",
        "children": [],
    }
    result = layout_engine.convert_figma_node(node)
    assert "items-stretch" in result.root.classes


def test_semantic_tags_on_saas_landing_fixture() -> None:
    data = _load_fixture("saas_landing.json")
    result = layout_engine.convert_figma_node(data)
    root = result.root

    navbar = root.children[0]
    assert navbar.tag == "header"
    assert "w-[1440px]" in navbar.classes
    assert "h-[72px]" in navbar.classes

    hero = root.children[1]
    assert hero.tag == "section"
    assert hero.inline_styles.get("background", "").startswith("linear-gradient")

    hero_buttons = hero.children[2]
    assert hero_buttons.tag == "div"

    features = root.children[2]
    cards_row = features.children[1]
    assert "items-stretch" in cards_row.classes

    card = cards_row.children[0]
    assert card.tag == "article"
    assert "bg-[#f7faff]" in card.classes
    assert card.inline_styles.get("box-shadow", "").startswith("0px 4px 24px")

    card_title = card.children[1]
    assert card_title.tag == "h3"

    footer = root.children[3]
    assert footer.tag == "footer"
    assert "bg-[#0d0d14]" in footer.classes


def test_absolute_bounding_box_fallback_for_size() -> None:
    node = {
        "id": "150:1",
        "name": "Box",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 100, "height": 200},
    }
    result = layout_engine.convert_figma_node(node)
    assert "w-[100px]" in result.root.classes
    assert "h-[200px]" in result.root.classes


def test_complex_layout_absolute_badge() -> None:
    data = _load_fixture("complex_layout.json")
    result = layout_engine.convert_figma_node(data)
    card_stack = result.root.children[0].children[1]
    card = card_stack.children[0]
    assert "relative" in card.classes
    badge = card.children[0]
    assert badge.figma_name == "Badge"
    assert "absolute" in badge.classes
    assert badge.inline_styles.get("left") == "312px"
    assert badge.inline_styles.get("top") == "-16px"


def test_complex_layout_auto_sized_card_skips_fixed_size() -> None:
    data = _load_fixture("complex_layout.json")
    result = layout_engine.convert_figma_node(data)
    card_stack = result.root.children[0].children[1]
    auto_card = card_stack.children[2]
    assert auto_card.figma_name == "Auto_Card"
    assert "w-[352px]" not in auto_card.classes
    assert "h-[244px]" not in auto_card.classes
    assert "flex" in auto_card.classes
    assert "flex-col" in auto_card.classes


def test_complex_layout_mask_card_has_overflow_hidden() -> None:
    data = _load_fixture("complex_layout.json")
    result = layout_engine.convert_figma_node(data)
    card_stack = result.root.children[0].children[1]
    mask_card = card_stack.children[1]
    assert mask_card.figma_name == "Mask_Card"
    assert "overflow-hidden" in mask_card.classes
    assert "rounded-2xl" in mask_card.classes


def test_complex_layout_nested_autolayout_rows() -> None:
    data = _load_fixture("complex_layout.json")
    result = layout_engine.convert_figma_node(data)
    grid = result.root.children[1]
    nested = grid.children[1]
    assert nested.figma_name == "Nested_Auto_Layout"
    assert "flex-col" in nested.classes
    assert "gap-[16px]" in nested.classes
    assert len(nested.children) == 2
    row_a, row_b = nested.children
    assert "flex-row" in row_a.classes
    assert "gap-[16px]" in row_a.classes
    assert "items-center" in row_a.classes
    text_stack = row_a.children[1]
    assert "flex-col" in text_stack.classes
    assert "gap-[4px]" in text_stack.classes


def test_complex_layout_overlay_alpha_renders_rgba_inline() -> None:
    data = _load_fixture("complex_layout.json")
    result = layout_engine.convert_figma_node(data)
    overlay = result.root.children[2]
    assert overlay.figma_name == "Modal_Overlay"
    assert "bg-[#1a1a1f99]" not in overlay.classes
    assert overlay.inline_styles.get("backgroundColor") == "rgba(26, 26, 31, 0.60)"
    assert overlay.inline_styles.get("opacity") == "0.6"


def _build_token_registry() -> Dict[str, Any]:
    return {
        "color_by_hex": {
            "1a1a1f": "foreground",
            "ffffff": "background",
            "3b82f5": "primary",
            "334c66": "secondary",
            "66666e": "muted",
            "f04242": "destructive",
            "38a687": "accent",
        },
        "fonts": {"Inter": "sans"},
        "font_sizes": {"12": "xs", "14": "sm", "16": "base", "18": "lg", "22": "xl", "24": "2xl", "56": "5xl"},
        "font_weights": {"400": "normal", "500": "medium", "600": "semibold", "700": "bold"},
        "line_heights": {"1.5": "normal"},
    }


def test_token_registry_maps_background_and_text_colors() -> None:
    node = {
        "id": "200:1",
        "name": "Card",
        "type": "FRAME",
        "visible": True,
        "fills": [{"type": "SOLID", "color": {"r": 1, "g": 1, "b": 1, "a": 1}}],
        "children": [
            {
                "id": "200:2",
                "name": "Title",
                "type": "TEXT",
                "visible": True,
                "characters": "Title",
                "style": {
                    "fontFamily": "Inter",
                    "fontSize": 24,
                    "fontWeight": 700,
                    "fills": [{"type": "SOLID", "color": {"r": 0.1, "g": 0.1, "b": 0.12, "a": 1}}],
                },
            }
        ],
    }
    result = layout_engine.convert_figma_node(node, config={"tokens": _build_token_registry()})
    assert "bg-background" in result.root.classes
    title = result.root.children[0]
    assert "text-foreground" in title.classes


def test_exact_variable_tokens_emit_dashed_classes() -> None:
    tokens = {
        "variable_token_map": {"v-primary": "colors.primary.500"},
        "color_by_hex": {},
    }
    node = {
        "id": "200:1",
        "name": "Card",
        "type": "FRAME",
        "visible": True,
        "fills": [{"type": "SOLID", "color": {"r": 0.23, "g": 0.51, "b": 0.96, "a": 1}}],
        "boundVariables": {"fill": "v-primary"},
    }
    result = layout_engine.convert_figma_node(node, config={"tokens": tokens})
    assert "bg-colors-primary-500" in result.root.classes


def test_exact_style_tokens_emit_dashed_classes() -> None:
    tokens = {
        "style_token_map": {"s-border": "colors.border.subtle"},
        "color_by_hex": {},
    }
    node = {
        "id": "200:2",
        "name": "Divider",
        "type": "FRAME",
        "visible": True,
        "fills": [{"type": "SOLID", "color": {"r": 0.9, "g": 0.92, "b": 0.95, "a": 1}}],
        "styles": {"fill": "s-border"},
    }
    result = layout_engine.convert_figma_node(node, config={"tokens": tokens})
    assert "bg-colors-border-subtle" in result.root.classes


def test_token_registry_maps_font_tokens() -> None:
    node = {
        "id": "210:1",
        "name": "Headline",
        "type": "TEXT",
        "visible": True,
        "characters": "Hero",
        "style": {
            "fontFamily": "Inter",
            "fontSize": 56,
            "fontWeight": 700,
            "lineHeightPx": 84,
        },
    }
    result = layout_engine.convert_figma_node(node, config={"tokens": _build_token_registry()})
    text = result.root
    assert "font-sans" in text.classes
    assert "text-5xl" in text.classes
    assert "font-bold" in text.classes
    assert "leading-normal" in text.classes


def test_no_semantic_token_fallback_in_layout_engine() -> None:
    """A bound style/variable ID must only be resolved through exact maps, never the semantic map."""
    tokens = {
        "style_token_map": {},
        "variable_token_map": {},
        "semantic_token_map": {"v-orphan": "primary", "s-orphan": "primary"},
        "color_by_hex": {},
    }
    engine = layout_engine.FigmaLayoutEngine(config={"tokens": tokens})
    fill_node = {"boundVariables": {"fill": "v-orphan"}}
    stroke_node = {"styles": {"stroke": "s-orphan"}}
    assert engine._token_for_style_or_variable(fill_node, "fill") is None
    assert engine._token_for_style_or_variable(stroke_node, "stroke") is None


def test_complex_layout_with_tokens_emits_semantic_classes() -> None:
    data = _load_fixture("complex_layout.json")
    result = layout_engine.convert_figma_node(data, config={"tokens": _build_token_registry()})
    card_stack = result.root.children[0].children[1]
    card = card_stack.children[0]
    assert "bg-background" in card.classes
    badge = card.children[0]
    assert "bg-destructive" in badge.classes


def test_layout_node_records_bbox() -> None:
    node = {
        "id": "200:1",
        "name": "Card",
        "type": "FRAME",
        "visible": True,
        "box": {"x": 10, "y": 20, "width": 300, "height": 150},
    }
    result = layout_engine.convert_figma_node(node)
    assert result.root.bbox == {"x": 10, "y": 20, "width": 300, "height": 150}
    assert result.root.to_dict()["bbox"] == {"x": 10, "y": 20, "width": 300, "height": 150}


def test_text_node_snug_fit_horizontal_parent() -> None:
    node = {
        "id": "100:1",
        "name": "Row",
        "type": "FRAME",
        "visible": True,
        "layoutMode": "HORIZONTAL",
        "box": {"x": 0, "y": 0, "width": 300, "height": 40},
        "children": [
            {
                "id": "200:1",
                "name": "Label",
                "type": "TEXT",
                "visible": True,
                "characters": "Label",
                "box": {"x": 0, "y": 0, "width": 120, "height": 24},
                "style": {"fontFamily": "Inter", "fontSize": 16, "fontWeight": 400},
            }
        ],
    }
    result = layout_engine.convert_figma_node(node)
    assert "whitespace-nowrap" in result.root.children[0].classes


def test_text_node_snug_fit_vertical_parent() -> None:
    node = {
        "id": "100:2",
        "name": "Column",
        "type": "FRAME",
        "visible": True,
        "layoutMode": "VERTICAL",
        "box": {"x": 0, "y": 0, "width": 300, "height": 200},
        "children": [
            {
                "id": "200:2",
                "name": "Paragraph",
                "type": "TEXT",
                "visible": True,
                "characters": "Paragraph",
                "box": {"x": 0, "y": 0, "width": 200, "height": 48},
                "style": {"fontFamily": "Inter", "fontSize": 16, "fontWeight": 400},
            }
        ],
    }
    result = layout_engine.convert_figma_node(node)
    assert "max-w-[200px]" in result.root.children[0].classes


def test_text_node_horizontal_parent_gets_min_w_0() -> None:
    node = {
        "id": "100:1",
        "name": "Row",
        "type": "FRAME",
        "visible": True,
        "layoutMode": "HORIZONTAL",
        "box": {"x": 0, "y": 0, "width": 300, "height": 40},
        "children": [
            {
                "id": "200:1",
                "name": "Label",
                "type": "TEXT",
                "visible": True,
                "characters": "Label",
                "box": {"x": 0, "y": 0, "width": 120, "height": 24},
                "style": {"fontFamily": "Inter", "fontSize": 16, "fontWeight": 400},
            }
        ],
    }
    result = layout_engine.convert_figma_node(node)
    classes = result.root.children[0].classes
    assert "whitespace-nowrap" in classes
    assert "min-w-0" in classes


def test_text_node_auto_resize_width_skips_max_w() -> None:
    node = {
        "id": "100:3",
        "name": "Auto",
        "type": "FRAME",
        "visible": True,
        "layoutMode": "VERTICAL",
        "box": {"x": 0, "y": 0, "width": 300, "height": 200},
        "children": [
            {
                "id": "200:3",
                "name": "Label",
                "type": "TEXT",
                "visible": True,
                "characters": "Auto label",
                "textAutoResize": "WIDTH_AND_HEIGHT",
                "box": {"x": 0, "y": 0, "width": 200, "height": 48},
                "style": {"fontFamily": "Inter", "fontSize": 16, "fontWeight": 400},
            }
        ],
    }
    result = layout_engine.convert_figma_node(node)
    classes = result.root.children[0].classes
    assert "w-auto" in classes
    assert "h-auto" in classes
    assert "max-w-[200px]" not in classes


def test_text_node_height_auto_resize_keeps_fixed_width() -> None:
    node = {
        "id": "100:4",
        "name": "AutoHeight",
        "type": "FRAME",
        "visible": True,
        "layoutMode": "VERTICAL",
        "box": {"x": 0, "y": 0, "width": 300, "height": 200},
        "children": [
            {
                "id": "200:4",
                "name": "Label",
                "type": "TEXT",
                "visible": True,
                "characters": "Fixed width auto height",
                "textAutoResize": "HEIGHT",
                "box": {"x": 0, "y": 0, "width": 200, "height": 48},
                "style": {"fontFamily": "Inter", "fontSize": 16, "fontWeight": 400},
            }
        ],
    }
    result = layout_engine.convert_figma_node(node)
    classes = result.root.children[0].classes
    assert "w-[200px]" in classes
    assert "h-auto" in classes
    assert "max-w-[200px]" not in classes


def test_layout_sizing_fill_emits_w_full() -> None:
    node = {
        "id": "300:1",
        "name": "Fill row",
        "type": "FRAME",
        "visible": True,
        "layoutSizingHorizontal": "FILL",
        "box": {"x": 0, "y": 0, "width": 400, "height": 100},
    }
    result = layout_engine.convert_figma_node(node)
    assert "w-full" in result.root.classes
    assert "w-[400px]" not in result.root.classes


def test_layout_sizing_hug_emits_w_auto_and_drops_fixed_width() -> None:
    node = {
        "id": "301:1",
        "name": "Hug card",
        "type": "FRAME",
        "visible": True,
        "layoutSizingHorizontal": "HUG",
        "layoutSizingVertical": "HUG",
        "box": {"x": 0, "y": 0, "width": 200, "height": 120},
    }
    result = layout_engine.convert_figma_node(node)
    assert "w-auto" in result.root.classes
    assert "h-auto" in result.root.classes
    assert "w-[200px]" not in result.root.classes
    assert "h-[120px]" not in result.root.classes


def test_layout_grow_maps_to_flex_1() -> None:
    node = {
        "id": "302:1",
        "name": "Grow item",
        "type": "FRAME",
        "visible": True,
        "layoutGrow": 1,
        "box": {"x": 0, "y": 0, "width": 100, "height": 40},
    }
    result = layout_engine.convert_figma_node(node)
    assert "flex-1" in result.root.classes


def test_layout_align_stretch_maps_to_self_stretch() -> None:
    node = {
        "id": "303:1",
        "name": "Stretch child",
        "type": "FRAME",
        "visible": True,
        "layoutAlign": "STRETCH",
        "box": {"x": 0, "y": 0, "width": 100, "height": 40},
    }
    result = layout_engine.convert_figma_node(node)
    assert "self-stretch" in result.root.classes


def test_constraint_stretch_horizontal_maps_to_w_full() -> None:
    node = {
        "id": "304:1",
        "name": "Stretch width",
        "type": "FRAME",
        "visible": True,
        "constraints": {"horizontal": "STRETCH", "vertical": "TOP"},
        "box": {"x": 0, "y": 0, "width": 300, "height": 50},
    }
    result = layout_engine.convert_figma_node(node)
    assert "w-full" in result.root.classes


def test_min_max_width_height_emits_arbitrary_classes() -> None:
    node = {
        "id": "305:1",
        "name": "Bounded box",
        "type": "FRAME",
        "visible": True,
        "minWidth": 120,
        "maxWidth": 600,
        "minHeight": 40,
        "maxHeight": 300,
        "box": {"x": 0, "y": 0, "width": 300, "height": 100},
    }
    result = layout_engine.convert_figma_node(node)
    assert "min-w-[120px]" in result.root.classes
    assert "max-w-[600px]" in result.root.classes
    assert "min-h-[40px]" in result.root.classes
    assert "max-h-[300px]" in result.root.classes


def test_drop_shadow_with_spread_maps_to_box_shadow() -> None:
    node = {
        "id": "400:1",
        "name": "Shadow card",
        "type": "FRAME",
        "visible": True,
        "box": {"x": 0, "y": 0, "width": 200, "height": 100},
        "effects": [
            {
                "type": "DROP_SHADOW",
                "hex": "rgba(0, 0, 0, 0.15)",
                "offset": {"x": 0, "y": 4},
                "radius": 16,
                "spread": 0,
            }
        ],
    }
    result = layout_engine.convert_figma_node(node)
    assert result.root.inline_styles.get("box-shadow") == "0px 4px 16px 0px rgba(0, 0, 0, 0.15)"


def test_inner_shadow_adds_isolate() -> None:
    node = {
        "id": "401:1",
        "name": "Inner shadow card",
        "type": "FRAME",
        "visible": True,
        "box": {"x": 0, "y": 0, "width": 200, "height": 100},
        "effects": [
            {
                "type": "INNER_SHADOW",
                "hex": "rgba(0, 0, 0, 0.20)",
                "offset": {"x": 0, "y": 2},
                "radius": 8,
                "spread": 1,
            }
        ],
    }
    result = layout_engine.convert_figma_node(node)
    assert "isolate" in result.root.classes
    assert "inset" in result.root.inline_styles.get("box-shadow", "")


def test_layer_blur_maps_to_filter() -> None:
    node = {
        "id": "402:1",
        "name": "Blur layer",
        "type": "FRAME",
        "visible": True,
        "box": {"x": 0, "y": 0, "width": 200, "height": 100},
        "effects": [{"type": "LAYER_BLUR", "radius": 12}],
    }
    result = layout_engine.convert_figma_node(node)
    assert result.root.inline_styles.get("filter") == "blur(12px)"


def test_background_blur_maps_to_backdrop_filter() -> None:
    node = {
        "id": "403:1",
        "name": "Backdrop blur",
        "type": "FRAME",
        "visible": True,
        "box": {"x": 0, "y": 0, "width": 200, "height": 100},
        "effects": [{"type": "BACKGROUND_BLUR", "radius": 20}],
    }
    result = layout_engine.convert_figma_node(node)
    assert result.root.inline_styles.get("backdrop-filter") == "blur(20px)"


def test_node_opacity_maps_to_inline_opacity() -> None:
    node = {
        "id": "404:1",
        "name": "Semi transparent",
        "type": "FRAME",
        "visible": True,
        "opacity": 0.5,
        "box": {"x": 0, "y": 0, "width": 100, "height": 100},
    }
    result = layout_engine.convert_figma_node(node)
    assert result.root.inline_styles.get("opacity") == "0.5"


def test_blend_mode_maps_to_mix_blend_mode() -> None:
    node = {
        "id": "405:1",
        "name": "Blend",
        "type": "FRAME",
        "visible": True,
        "blendMode": "MULTIPLY",
        "box": {"x": 0, "y": 0, "width": 100, "height": 100},
    }
    result = layout_engine.convert_figma_node(node)
    assert result.root.inline_styles.get("mix-blend-mode") == "multiply"


def test_mask_adds_overflow_hidden_and_mask_image() -> None:
    node = {
        "id": "406:1",
        "name": "Mask group",
        "type": "FRAME",
        "visible": True,
        "isMask": True,
        "maskType": "ALPHA",
        "box": {"x": 0, "y": 0, "width": 100, "height": 100},
    }
    result = layout_engine.convert_figma_node(node)
    assert "overflow-hidden" in result.root.classes
    assert result.root.inline_styles.get("mask-image") == "linear-gradient(#000 0 0)"


def test_vector_mask_adds_clip_path() -> None:
    node = {
        "id": "407:1",
        "name": "Vector mask",
        "type": "FRAME",
        "visible": True,
        "isMask": True,
        "maskType": "VECTOR",
        "box": {"x": 0, "y": 0, "width": 100, "height": 100},
    }
    result = layout_engine.convert_figma_node(node)
    assert result.root.inline_styles.get("clip-path") == "inset(0 0 0 0)"


def test_boolean_operation_adds_clip_rule() -> None:
    node = {
        "id": "408:1",
        "name": "Boolean group",
        "type": "BOOLEAN",
        "visible": True,
        "booleanOperation": "SUBTRACT",
        "box": {"x": 0, "y": 0, "width": 100, "height": 100},
    }
    result = layout_engine.convert_figma_node(node)
    assert result.root.inline_styles.get("clip-rule") == "subtract"


def test_padding_per_side_all_different() -> None:
    node = {
        "id": "306:1",
        "name": "Card",
        "type": "FRAME",
        "visible": True,
        "layoutMode": "VERTICAL",
        "paddingTop": 8,
        "paddingRight": 16,
        "paddingBottom": 24,
        "paddingLeft": 32,
        "children": [],
    }
    result = layout_engine.convert_figma_node(node)
    classes = result.root.classes
    assert "pt-[8px]" in classes
    assert "pr-[16px]" in classes
    assert "pb-[24px]" in classes
    assert "pl-[32px]" in classes
    assert "p-[8px]" not in classes
    assert "py-[8px]" not in classes
    assert "px-[16px]" not in classes


def test_counter_axis_space_between_emits_content_between_and_flex_wrap() -> None:
    node = {
        "id": "307:1",
        "name": "Wrapped grid",
        "type": "FRAME",
        "visible": True,
        "layoutMode": "HORIZONTAL",
        "layoutWrap": "WRAP",
        "counterAxisAlignItems": "SPACE_BETWEEN",
        "children": [],
    }
    result = layout_engine.convert_figma_node(node)
    classes = result.root.classes
    assert "flex-wrap" in classes
    assert "content-between" in classes
    assert "items-between" not in classes
    assert "items-start" not in classes


def test_counter_axis_space_between_without_wrap_forces_flex_wrap() -> None:
    node = {
        "id": "307:2",
        "name": "Stack",
        "type": "FRAME",
        "visible": True,
        "layoutMode": "VERTICAL",
        "counterAxisAlignItems": "SPACE_BETWEEN",
        "children": [],
    }
    result = layout_engine.convert_figma_node(node)
    classes = result.root.classes
    assert "flex-wrap" in classes
    assert "content-between" in classes


def test_layout_wrap_adds_flex_wrap_and_keeps_counter_items() -> None:
    node = {
        "id": "308:1",
        "name": "Tags",
        "type": "FRAME",
        "visible": True,
        "layoutMode": "HORIZONTAL",
        "layoutWrap": "WRAP",
        "counterAxisAlignItems": "CENTER",
        "itemSpacing": 12,
        "children": [],
    }
    result = layout_engine.convert_figma_node(node)
    classes = result.root.classes
    assert "flex-wrap" in classes
    assert "items-center" in classes
    assert "gap-[12px]" in classes


def test_spacing_mode_packed_uses_gap() -> None:
    node = {
        "id": "309:1",
        "name": "List",
        "type": "FRAME",
        "visible": True,
        "layoutMode": "VERTICAL",
        "spacingMode": "PACKED",
        "itemSpacing": 16,
        "primaryAxisAlignItems": "MIN",
        "children": [],
    }
    result = layout_engine.convert_figma_node(node)
    classes = result.root.classes
    assert "gap-[16px]" in classes
    assert "justify-start" in classes


def test_spacing_mode_space_between_ignores_item_spacing_gap() -> None:
    node = {
        "id": "309:2",
        "name": "Distributed",
        "type": "FRAME",
        "visible": True,
        "layoutMode": "HORIZONTAL",
        "spacingMode": "SPACE_BETWEEN",
        "itemSpacing": 32,
        "primaryAxisAlignItems": "CENTER",
        "children": [],
    }
    result = layout_engine.convert_figma_node(node)
    classes = result.root.classes
    assert "justify-between" in classes
    assert "gap-[32px]" not in classes
    assert "justify-center" not in classes


def _find_node_by_figma_id(root, node_id: str):
    if root.figma_id == node_id:
        return root
    for child in root.children:
        found = _find_node_by_figma_id(child, node_id)
        if found:
            return found
    return None


def test_data_models_annotate_binding() -> None:
    data_models = {
        "version": "1",
        "models": [
            {
                "name": "Card",
                "occurrence_ids": ["card-1"],
                "field_map": {"title": "title", "imageUrl": "imageUrl"},
                "sample_data": [{"title": "Card A"}],
            }
        ],
    }
    root = {
        "id": "page",
        "name": "Page",
        "type": "FRAME",
        "visible": True,
        "children": [
            {
                "id": "card-1",
                "name": "Card 1",
                "type": "FRAME",
                "visible": True,
                "children": [
                    {"id": "t1", "name": "Title", "type": "TEXT", "visible": True, "characters": "Card A"},
                    {"id": "i1", "name": "Cover", "type": "IMAGE", "visible": True},
                ],
            },
        ],
    }
    engine = layout_engine.FigmaLayoutEngine(config={"data_models": data_models})
    result = engine.convert(root)
    card = _find_node_by_figma_id(result.root, "card-1")
    assert card is not None
    assert card.data_model is not None
    assert card.data_model["model"] == "Card"

    title_node = card.children[0]
    assert title_node.data_binding == {"model": "Card", "field": "title", "item": True}
    assert title_node.text is None

    image_node = card.children[1]
    assert image_node.data_binding == {"model": "Card", "field": "imageUrl", "item": True}
    assert image_node.src is None


def test_data_model_image_alt_binding() -> None:
    data_models = {
        "version": "1",
        "models": [
            {
                "name": "Card",
                "occurrence_ids": ["card-1"],
                "field_map": {"title": "title", "imageUrl": "imageUrl", "imageAlt": "imageAlt"},
                "sample_data": [{"title": "Card A", "imageUrl": "", "imageAlt": ""}],
            }
        ],
    }
    root = {
        "id": "page",
        "name": "Page",
        "type": "FRAME",
        "visible": True,
        "children": [
            {
                "id": "card-1",
                "name": "Card 1",
                "type": "FRAME",
                "visible": True,
                "children": [
                    {"id": "t1", "name": "Title", "type": "TEXT", "visible": True, "characters": "Card A"},
                    {"id": "i1", "name": "Cover", "type": "IMAGE", "visible": True},
                ],
            },
        ],
    }
    engine = layout_engine.FigmaLayoutEngine(config={"data_models": data_models})
    result = engine.convert(root)
    card = _find_node_by_figma_id(result.root, "card-1")
    image_node = card.children[1]
    assert image_node.alt_binding == {"model": "Card", "field": "imageAlt", "item": True}
