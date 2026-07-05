"""Unit tests for figma-agent-core/page_composer.py.

Loads the module via importlib because the directory name contains a hyphen.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
PAGE_COMPOSER_PATH = ROOT / "figma-agent-core" / "page_composer.py"


def _load_page_composer() -> Any:
    spec = importlib.util.spec_from_file_location("figma_page_composer", str(PAGE_COMPOSER_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_page_composer"] = module
    spec.loader.exec_module(module)
    return module


page_composer = _load_page_composer()


def _minimal_ast(root_children: list) -> dict:
    return {"root": {"tag": "div", "children": root_children}}


def test_load_module() -> None:
    assert hasattr(page_composer, "compose_page")
    assert hasattr(page_composer, "write_page")


def test_compose_emits_data_figma_id() -> None:
    ast = _minimal_ast([
        {"tag": "section", "figma_id": "1:1", "classes": ["bg-white"], "children": []},
    ])
    code = page_composer.compose_page(ast)
    assert 'data-figma-id="1:1"' in code


def test_compose_nested_nodes_emits_data_figma_id() -> None:
    ast = _minimal_ast([
        {
            "tag": "section",
            "figma_id": "1:1",
            "classes": ["flex"],
            "children": [
                {"tag": "h1", "figma_id": "1:2", "text": "Title", "classes": ["text-2xl"]},
                {"tag": "p", "figma_id": "1:3", "text": "Body", "classes": ["text-base"]},
            ],
        }
    ])
    code = page_composer.compose_page(ast)
    assert 'data-figma-id="1:1"' in code
    assert 'data-figma-id="1:2"' in code
    assert 'data-figma-id="1:3"' in code


def test_compose_empty_page() -> None:
    code = page_composer.compose_page({"root": {"tag": "div", "children": []}})
    assert "export default function Page()" in code
    assert "</div>" in code


def test_compose_single_section_with_text() -> None:
    ast = _minimal_ast([
        {
            "tag": "section",
            "classes": ["flex", "flex-col", "items-center"],
            "children": [
                {"tag": "h1", "text": "Hero Title", "classes": ["text-[40px]", "font-[700]"]},
                {"tag": "p", "text": "Subtitle", "classes": ["text-[18px]"]},
            ],
        }
    ])
    code = page_composer.compose_page(ast)
    assert "<section className=\"flex flex-col items-center\">" in code
    assert "<h1 className=\"text-[40px] font-[700]\">\n        Hero Title\n      </h1>" in code
    assert "<p className=\"text-[18px]\">Subtitle</p>" in code


def test_compose_image_asset() -> None:
    ast = _minimal_ast([
        {"tag": "img", "classes": ["w-[600px]", "h-[400px]"], "src": "/images/hero.png", "alt": "Hero"},
    ])
    code = page_composer.compose_page(ast)
    assert 'src="/images/hero.png"' in code
    assert 'alt="Hero"' in code
    assert "<img className=\"w-[600px] h-[400px]\" src=\"/images/hero.png\" alt=\"Hero\" />" in code


def test_compose_raster_asset_uses_next_image() -> None:
    ast = _minimal_ast([
        {
            "tag": "img",
            "classes": ["w-[360px]", "h-[160px]"],
            "src": "/assets/figma/hero.png",
            "alt": "Hero",
            "asset_type": "raster",
            "asset_width": 360,
            "asset_height": 160,
        },
    ])
    code = page_composer.compose_page(ast)
    assert 'import Image from "next/image"' in code
    assert "<Image" in code
    assert 'src="/assets/figma/hero.png"' in code
    assert "width={360}" in code
    assert "height={160}" in code


def test_compose_inline_svg() -> None:
    ast = _minimal_ast([
        {
            "tag": "img",
            "classes": ["w-[48px]", "h-[48px]"],
            "src": "/assets/figma/logo.svg",
            "alt": "Logo",
            "asset_type": "svg",
            "inline_svg": '<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48"><circle r="20"/></svg>',
        },
    ])
    code = page_composer.compose_page(ast)
    assert "<svg xmlns=\"http://www.w3.org/2000/svg\"" in code


def test_compose_layout_with_google_font() -> None:
    ast = _minimal_ast([
        {"tag": "h1", "text": "Title", "classes": ["font-sans"], "inline_styles": {"fontFamily": "'Inter'"}},
    ])
    layout = page_composer.compose_layout("Test", fonts=page_composer._collect_fonts(ast))
    assert 'import { Inter } from "next/font/google"' in layout
    assert "const inter = Inter({ subsets: [\"latin\"], variable: \"--font-inter\" })" in layout
    assert "className={`${inter.variable} antialiased`}" in layout


def test_compose_inline_styles() -> None:
    ast = _minimal_ast([
        {
            "tag": "div",
            "classes": ["absolute"],
            "inline_styles": {"left": "120px", "top": "40px"},
            "children": [],
        }
    ])
    code = page_composer.compose_page(ast)
    assert 'style={{left: "120px", top: "40px"}}' in code
    assert '<div className="absolute" style={{left: "120px", top: "40px"}} />' in code


def test_compose_nested_children() -> None:
    ast = _minimal_ast([
        {
            "tag": "header",
            "classes": ["flex", "justify-between"],
            "children": [
                {"tag": "span", "text": "Logo", "classes": ["font-bold"]},
                {
                    "tag": "nav",
                    "classes": ["flex", "gap-[16px]"],
                    "children": [
                        {"tag": "a", "text": "Home", "classes": ["text-[14px]"]},
                        {"tag": "a", "text": "About", "classes": ["text-[14px]"]},
                    ],
                },
            ],
        }
    ])
    code = page_composer.compose_page(ast)
    assert "<header className=\"flex justify-between\">" in code
    assert "<nav className=\"flex gap-[16px]\">" in code
    assert "<a className=\"text-[14px]\">Home</a>" in code
    assert "</header>" in code


def test_title_inference_from_h1() -> None:
    ast = _minimal_ast([
        {"tag": "section", "children": [
            {"tag": "h1", "text": "Build Fast", "classes": ["text-[40px]"]},
        ]},
    ])
    code = page_composer.compose_page(ast)
    assert 'title: "Build Fast"' in code


def test_title_override() -> None:
    ast = _minimal_ast([
        {"tag": "h1", "text": "Old", "classes": []},
    ])
    code = page_composer.compose_page(ast, title="Custom Title")
    assert 'title: "Custom Title"' in code


def test_font_import_detection() -> None:
    ast = _minimal_ast([
        {"tag": "p", "text": "Hello", "classes": ["font-[Inter]"]},
    ])
    code = page_composer.compose_page(ast)
    assert 'import { Inter } from "next/font/google"' in code or 'import { Inter } from \'next/font/google\'' in code


def test_write_page_creates_file(tmp_path: Path) -> None:
    output = tmp_path / "src" / "app" / "page.tsx"
    code = "export default function Page() { return <div />; }"
    result = page_composer.write_page(code, str(output), root_dir=str(tmp_path))
    assert result == str(output.resolve())
    assert output.exists()
    assert output.read_text(encoding="utf-8") == code


def test_write_page_blocks_path_traversal() -> None:
    with pytest.raises(ValueError):
        page_composer.write_page("code", "../outside/page.tsx")


def test_compose_from_ast_file(tmp_path: Path) -> None:
    ast_path = tmp_path / "layout_ast.json"
    ast = _minimal_ast([{"tag": "section", "children": [{"tag": "h1", "text": "From file"}]}])
    ast_path.write_text(json.dumps(ast), encoding="utf-8")
    code = page_composer.compose_page_from_ast_file(str(ast_path))
    assert "From file" in code
    assert 'title: "From file"' in code


def test_self_closing_for_empty_non_text() -> None:
    ast = _minimal_ast([{"tag": "div", "classes": ["bg-white"], "children": []}])
    code = page_composer.compose_page(ast)
    assert "<div className=\"bg-white\" />" in code


def test_compose_component_reference() -> None:
    ast = _minimal_ast([
        {
            "tag": "HeroSection",
            "component": True,
            "component_name": "HeroSection",
            "component_path": "@/app/components/HeroSection",
            "props": {},
            "children": [],
        }
    ])
    code = page_composer.compose_page(ast)
    assert 'import HeroSection from "@/app/components/HeroSection"' in code
    assert "<HeroSection />" in code


def test_compose_component_with_props() -> None:
    ast = _minimal_ast([
        {
            "tag": "CTAButton",
            "component": True,
            "component_name": "CTAButton",
            "component_path": "@/app/components/CTAButton",
            "props": {"label": "Get started"},
            "children": [],
        }
    ])
    code = page_composer.compose_page(ast)
    assert 'import CTAButton from "@/app/components/CTAButton"' in code
    assert 'label="Get started"' in code


def test_compose_mixed_nodes_and_components() -> None:
    ast = _minimal_ast([
        {"tag": "h1", "text": "Title", "classes": ["text-[40px]"]},
        {
            "tag": "FeatureCard",
            "component": True,
            "component_name": "FeatureCard",
            "component_path": "@/app/components/FeatureCard",
            "props": {},
            "children": [],
        },
    ])
    code = page_composer.compose_page(ast)
    assert 'import FeatureCard from "@/app/components/FeatureCard"' in code
    assert "<h1 className=\"text-[40px]\">\n      Title\n    </h1>" in code
    assert "<FeatureCard />" in code


def test_compose_navigation_adds_client_directive_and_router() -> None:
    ast = _minimal_ast([
        {
            "tag": "button",
            "text": "Go to pricing",
            "classes": ["bg-blue-500"],
            "figma_id": "1:2",
            "interactive": {
                "state_key": "pricingButtonState",
                "component_name": "PricingButton",
                "needs_client": True,
                "triggers": [
                    {"event": "on_click", "type": "navigate", "route": "/pricing"}
                ],
            },
        }
    ])
    code = page_composer.compose_page(ast)
    assert '"use client"' in code
    assert 'import { useRouter } from "next/navigation"' in code
    assert 'import { useState } from "react"' in code
    assert "const router = useRouter();" in code
    assert "const [pricingButtonState, setPricingButtonState] = useState(false);" in code
    assert "onClick={() => router.push(\"/pricing\")}" in code
    assert "export const metadata" not in code


def test_compose_overlay_conditional_rendering() -> None:
    ast = _minimal_ast([
        {
            "tag": "button",
            "text": "Open modal",
            "classes": ["bg-black", "text-white"],
            "figma_id": "1:2",
            "interactive": {
                "state_key": "modalButtonState",
                "component_name": "ModalButton",
                "needs_client": True,
                "triggers": [
                    {"event": "on_click", "type": "overlay", "destination_id": "5:6"}
                ],
            },
        },
        {
            "tag": "div",
            "classes": ["fixed", "inset-0"],
            "figma_id": "5:6",
            "children": [{"tag": "p", "text": "Modal content"}],
        },
    ])
    code = page_composer.compose_page(ast)
    assert "const [modalButtonState, setModalButtonState] = useState(false);" in code
    assert "onClick={() => setModalButtonState(true)}" in code
    assert "{modalButtonState} && (" in code
    assert "<div className=\"fixed inset-0\"" in code


def test_compose_external_url_opens_window() -> None:
    ast = _minimal_ast([
        {
            "tag": "a",
            "text": "External",
            "classes": ["text-blue-500"],
            "figma_id": "1:2",
            "interactive": {
                "state_key": "externalLinkState",
                "component_name": "ExternalLink",
                "needs_client": True,
                "triggers": [
                    {"event": "on_click", "type": "url", "url": "https://example.com", "external": True}
                ],
            },
        }
    ])
    code = page_composer.compose_page(ast)
    assert "onClick={() => window.open(\"https://example.com\", '_blank')}" in code


def test_compose_hover_event() -> None:
    ast = _minimal_ast([
        {
            "tag": "div",
            "text": "Hover me",
            "classes": ["p-4"],
            "figma_id": "1:2",
            "interactive": {
                "state_key": "hoverState",
                "component_name": "HoverBox",
                "needs_client": True,
                "triggers": [
                    {"event": "on_hover", "type": "url", "url": "/hover-target"}
                ],
            },
        }
    ])
    code = page_composer.compose_page(ast)
    assert "onMouseEnter={() => router.push(\"/hover-target\")}" in code


def test_compose_rich_text_spans() -> None:
    ast = _minimal_ast([
        {
            "tag": "p",
            "rich_text": [
                {"text": "Plain "},
                {"text": "bold", "classes": ["font-[700]"]},
                {"text": " text"},
            ],
        }
    ])
    code = page_composer.compose_page(ast)
    assert "<p>" in code
    assert "<span>Plain </span>" in code
    assert 'className="font-[700]"' in code
    assert "<span className=\"font-[700]\">bold</span>" in code


def test_compose_rich_text_link() -> None:
    ast = _minimal_ast([
        {
            "tag": "p",
            "rich_text": [
                {"text": "Visit "},
                {"text": "site", "tag": "a", "href": "https://example.com", "classes": ["font-[700]"]},
            ],
        }
    ])
    code = page_composer.compose_page(ast)
    assert 'href="https://example.com"' in code
    assert "<a className=\"font-[700]\" href=\"https://example.com\">site</a>" in code


def test_compose_rich_text_newline_br() -> None:
    ast = _minimal_ast([
        {
            "tag": "p",
            "rich_text": [
                {"text": "Line1"},
                {"text": "Line2", "newline_before": True},
            ],
        }
    ])
    code = page_composer.compose_page(ast)
    assert "<br />" in code
    assert "<span>Line2</span>" in code


def test_compose_escapes_jsx_special_chars() -> None:
    ast = _minimal_ast([
        {"tag": "p", "text": "Use {config} <script>"},
    ])
    code = page_composer.compose_page(ast)
    assert "{'{'" in code
    assert "{'}'}" in code
    assert "&lt;script&gt;" in code


def test_compose_backdrop_filter_inline_style() -> None:
    ast = _minimal_ast([
        {
            "tag": "div",
            "classes": ["fixed", "inset-0"],
            "inline_styles": {"backdrop-filter": "blur(20px)"},
        }
    ])
    code = page_composer.compose_page(ast)
    assert 'style={{backdropFilter: "blur(20px)"}}' in code


def test_compose_mix_blend_mode_inline_style() -> None:
    ast = _minimal_ast([
        {
            "tag": "div",
            "classes": ["absolute"],
            "inline_styles": {"mix-blend-mode": "multiply"},
        }
    ])
    code = page_composer.compose_page(ast)
    assert 'style={{mixBlendMode: "multiply"}}' in code


def test_compose_opacity_inline_style() -> None:
    ast = _minimal_ast([
        {
            "tag": "div",
            "classes": ["bg-white"],
            "inline_styles": {"opacity": "0.5"},
        }
    ])
    code = page_composer.compose_page(ast)
    assert 'style={{opacity: "0.5"}}' in code


def test_compose_data_binding_renders_item_map() -> None:
    ast = _minimal_ast([
        {
            "tag": "div",
            "classes": ["grid", "gap-4"],
            "data_model": {
                "model": "Card",
                "field_map": {"title": "title"},
                "sample_data": [{"title": "Card A"}, {"title": "Card B"}],
            },
            "children": [
                {"tag": "h3", "classes": ["text-lg"], "text": "ignored", "data_binding": {"field": "title"}},
            ],
        }
    ])
    code = page_composer.compose_page(ast)
    assert "const cardData =" in code
    assert "Card A" in code
    assert "Card B" in code
    assert "{cardData.map((item) => (" in code
    assert "{item.title}" in code
    assert "ignored" not in code
