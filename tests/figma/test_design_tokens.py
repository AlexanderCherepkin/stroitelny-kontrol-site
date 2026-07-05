"""Unit tests for figma-agent-core/design_tokens.py.

Loads the module via importlib because the directory name contains a hyphen.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
DESIGN_TOKENS_PATH = ROOT / "figma-agent-core" / "design_tokens.py"
FIXTURES = ROOT / "tests" / "figma" / "fixtures"


def _load_design_tokens() -> Any:
    spec = importlib.util.spec_from_file_location("figma_design_tokens", str(DESIGN_TOKENS_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_design_tokens"] = module
    spec.loader.exec_module(module)
    return module


design_tokens = _load_design_tokens()


def load_complex_fixture() -> dict:
    return json.loads((FIXTURES / "complex_layout.json").read_text(encoding="utf-8"))


def test_module_loads() -> None:
    assert hasattr(design_tokens, "FigmaTokenExtractor")
    assert hasattr(design_tokens, "generate_artifacts")


def test_extracts_expected_color_tokens() -> None:
    fixture = load_complex_fixture()
    registry = design_tokens.FigmaTokenExtractor(fixture).extract()

    assert "foreground" in registry.colors
    assert "background" in registry.colors
    assert "primary" in registry.colors
    assert "secondary" in registry.colors
    assert "muted" in registry.colors
    assert "destructive" in registry.colors
    assert "border" in registry.colors

    # Verify heuristic assignments against the known fixture palette.
    assert registry.colors["foreground"].hex == "#1a1a1f"
    assert registry.colors["background"].hex == "#ffffff"
    assert registry.colors["primary"].hex == "#3b82f5"
    assert registry.colors["secondary"].hex == "#334c66"
    assert registry.colors["muted"].hex == "#66666e"
    assert registry.colors["destructive"].hex == "#f04242"


def test_extracts_typography_tokens() -> None:
    fixture = load_complex_fixture()
    registry = design_tokens.FigmaTokenExtractor(fixture).extract()

    assert registry.fonts == {"Inter": "sans"}
    assert set(registry.font_sizes.keys()) == {12, 14, 16, 18, 22, 24, 56}
    assert set(registry.font_weights.keys()) == {400, 500, 600, 700}


def test_explicit_styles_override_heuristics() -> None:
    fixture = json.loads((FIXTURES / "tokens_explicit.json").read_text(encoding="utf-8"))
    registry = design_tokens.FigmaTokenExtractor(fixture).extract()

    assert registry.colors["colors.background"].hex == "#ffffff"
    assert registry.colors["colors.foreground"].hex == "#1a1a1f"
    assert registry.colors["colors.primary"].hex == "#3b82f5"
    assert registry.colors["colors.secondary"].hex == "#334c66"
    assert registry.colors["colors.muted"].hex == "#66666e"
    assert registry.colors["colors.destructive"].hex == "#f04242"
    assert registry.colors["colors.border"].hex == "#e6ebf2"
    assert registry.style_token_map["s-background"] == "colors.background"
    assert registry.style_token_map["s-foreground"] == "colors.foreground"


def test_generates_tailwind_config_with_css_variables() -> None:
    fixture = load_complex_fixture()
    registry = design_tokens.FigmaTokenExtractor(fixture).extract()
    config = design_tokens.generate_tailwind_config(registry)

    assert 'import type { Config } from "tailwindcss";' in config
    assert '"primary": {' in config
    assert '"DEFAULT": "var(--primary)"' in config
    assert '"foreground": "var(--primary-foreground)"' in config
    assert '"background": "var(--background)"' in config
    assert '"fontFamily": {' in config


def test_generates_globals_css_with_root_variables() -> None:
    fixture = load_complex_fixture()
    registry = design_tokens.FigmaTokenExtractor(fixture).extract()
    css = design_tokens.generate_globals_css(registry)

    assert "@tailwind base;" in css
    assert ":root {" in css
    assert "--background: #ffffff;" in css
    assert "--foreground: #1a1a1f;" in css
    assert "--primary: #3b82f5;" in css
    assert "--font-sans: 'Inter'" in css
    assert "body {" in css
    assert "@apply bg-background text-foreground;" in css


def test_extract_exact_variable_color_tokens() -> None:
    fixture = {
        "id": "0:1",
        "name": "Variable Fixture",
        "type": "FRAME",
        "variables": {
            "v-primary": {"name": "colors/primary/500"},
            "v-surface": {"name": "colors/background", "collection": "theme"},
        },
        "children": [
            {
                "id": "1:1",
                "name": "Card",
                "type": "FRAME",
                "fills": [{"type": "SOLID", "color": {"r": 0.23, "g": 0.51, "b": 0.96, "a": 1}}],
                "boundVariables": {"fill": "v-primary"},
                "children": [
                    {
                        "id": "1:2",
                        "name": "Title",
                        "type": "TEXT",
                        "characters": "Title",
                        "style": {
                            "fontFamily": "Inter",
                            "fontSize": 16,
                            "fills": [{"type": "SOLID", "color": {"r": 1, "g": 1, "b": 1, "a": 1}}],
                        },
                        "boundVariables": {"text": "v-surface"},
                    }
                ],
            }
        ],
    }
    registry = design_tokens.FigmaTokenExtractor(fixture).extract()

    assert "colors.primary.500" in registry.colors
    assert registry.colors["colors.primary.500"].hex == "#3b82f5"
    assert registry.colors["colors.primary.500"].css_var == "--colors-primary-500"
    assert registry.variable_token_map["v-primary"] == "colors.primary.500"

    assert "theme.colors.background" in registry.colors
    assert registry.colors["theme.colors.background"].hex == "#ffffff"
    assert registry.colors["theme.colors.background"].css_var == "--theme-colors-background"
    assert registry.variable_token_map["v-surface"] == "theme.colors.background"


def test_extract_exact_style_color_tokens() -> None:
    fixture = {
        "id": "0:1",
        "name": "Style Fixture",
        "type": "FRAME",
        "styles": {"s-border": {"name": "colors/border/subtle"}},
        "children": [
            {
                "id": "1:1",
                "name": "Divider",
                "type": "FRAME",
                "fills": [{"type": "SOLID", "color": {"r": 0.9, "g": 0.92, "b": 0.95, "a": 1}}],
                "styles": {"fill": "s-border"},
            }
        ],
    }
    registry = design_tokens.FigmaTokenExtractor(fixture).extract()
    assert "colors.border.subtle" in registry.colors
    assert registry.colors["colors.border.subtle"].hex == "#e6ebf2"
    assert registry.colors["colors.border.subtle"].css_var == "--colors-border-subtle"
    assert registry.style_token_map["s-border"] == "colors.border.subtle"


def test_exact_tokens_generate_nested_tailwind_config() -> None:
    fixture = {
        "id": "0:1",
        "name": "Nested Token Fixture",
        "type": "FRAME",
        "variables": {"v-primary": {"name": "colors/primary/500"}},
        "children": [
            {
                "id": "1:1",
                "name": "Box",
                "type": "FRAME",
                "fills": [{"type": "SOLID", "color": {"r": 0.23, "g": 0.51, "b": 0.96, "a": 1}}],
                "boundVariables": {"fill": "v-primary"},
            }
        ],
    }
    registry = design_tokens.FigmaTokenExtractor(fixture).extract()
    config = design_tokens.generate_tailwind_config(registry)
    assert '"colors": {' in config
    assert '"primary": {' in config
    assert '"500": "var(--colors-primary-500)"' in config


def test_exact_variable_token_map_written_to_registry() -> None:
    fixture = {
        "id": "0:1",
        "name": "Registry Fixture",
        "type": "FRAME",
        "variables": {"v-primary": {"name": "colors/primary/500"}},
        "children": [
            {
                "id": "1:1",
                "name": "Box",
                "type": "FRAME",
                "fills": [{"type": "SOLID", "color": {"r": 0.23, "g": 0.51, "b": 0.96, "a": 1}}],
                "boundVariables": {"fill": "v-primary"},
            }
        ],
    }
    registry = design_tokens.FigmaTokenExtractor(fixture).extract()
    assert registry.exact_token_paths == ["colors.primary.500"]
    with tempfile.TemporaryDirectory() as tmp:
        design_tokens.save_registry(registry, str(Path(tmp) / "design_tokens.json"))
        saved = json.loads((Path(tmp) / "design_tokens.json").read_text(encoding="utf-8"))
        assert saved["variable_token_map"] == {"v-primary": "colors.primary.500"}
        assert saved["exact_token_paths"] == ["colors.primary.500"]


def test_exact_variable_id_takes_precedence_over_hex_fallback() -> None:
    """A bound variable's resolved value wins over a differently-colored raw fill."""
    fixture = {
        "id": "0:1",
        "name": "Precedence Fixture",
        "type": "FRAME",
        "variables": {
            "v-primary": {
                "name": "colors/primary/500",
                "resolvedValue": {"color": {"r": 0.23, "g": 0.51, "b": 0.96, "a": 1}},
            }
        },
        "children": [
            {
                "id": "1:1",
                "name": "Box",
                "type": "FRAME",
                # raw fill is red, but bound variable resolves to blue
                "fills": [{"type": "SOLID", "color": {"r": 0.94, "g": 0.26, "b": 0.26, "a": 1}}],
                "boundVariables": {"fill": "v-primary"},
            }
        ],
    }
    registry = design_tokens.FigmaTokenExtractor(fixture).extract()
    assert registry.variable_token_map["v-primary"] == "colors.primary.500"
    assert registry.colors["colors.primary.500"].hex == "#3b82f5"
    # The raw red color should NOT have been used for the primary token.
    assert registry.colors["colors.primary.500"].hex != "#f04242"


def test_style_id_takes_precedence_over_semantic_fallback() -> None:
    """A bound style ID must be recorded before semantic/heuristic matching runs."""
    fixture = {
        "id": "0:1",
        "name": "Style Precedence Fixture",
        "type": "FRAME",
        "styles": {"s-custom": {"name": "colors/custom/brand"}},
        "children": [
            {
                "id": "1:1",
                "name": "Box",
                "type": "FRAME",
                "fills": [{"type": "SOLID", "color": {"r": 0.23, "g": 0.51, "b": 0.96, "a": 1}}],
                "styles": {"fill": "s-custom"},
            }
        ],
    }
    registry = design_tokens.FigmaTokenExtractor(fixture).extract()
    assert registry.style_token_map["s-custom"] == "colors.custom.brand"
    assert "colors.custom.brand" in registry.colors


def test_generate_artifacts_writes_files() -> None:
    fixture = load_complex_fixture()
    with tempfile.TemporaryDirectory() as tmp:
        artifacts = design_tokens.generate_artifacts(
            fixture,
            output_dir=tmp,
            registry_file="design_tokens.json",
            tailwind_config="tailwind.config.ts",
            globals_css="app/globals.css",
        )
        assert Path(artifacts["registry"]).exists()
        assert Path(artifacts["tailwind_config"]).exists()
        assert Path(artifacts["globals_css"]).exists()

        saved = json.loads(Path(artifacts["registry"]).read_text(encoding="utf-8"))
        assert "colors" in saved
        assert "fonts" in saved
        # Strict token matching: no semantic fallback maps are persisted.
        assert "semantic_token_map" not in saved
        assert "semantic_match_scores" not in saved


def test_style_name_does_not_alias_to_heuristic_semantic_token() -> None:
    """A style name containing a semantic keyword must map to its exact path, not alias to a heuristic token."""
    fixture = {
        "id": "0:1",
        "name": "No Semantic Alias",
        "type": "FRAME",
        "styles": {"s-primary-blue": {"name": "colors/primary/blue"}},
        "children": [
            {
                "id": "1:1",
                "name": "Primary Button",
                "type": "FRAME",
                "fills": [{"type": "SOLID", "color": {"r": 0.23, "g": 0.51, "b": 0.96, "a": 1}}],
                "styles": {"fill": "s-primary-blue"},
            },
            {
                "id": "1:2",
                "name": "Surface",
                "type": "FRAME",
                "fills": [{"type": "SOLID", "color": {"r": 1, "g": 1, "b": 1, "a": 1}}],
            },
        ],
    }
    registry = design_tokens.FigmaTokenExtractor(fixture).extract()
    # Heuristic extraction still creates a "primary" token from the saturated blue.
    assert "primary" in registry.colors
    # But the style ID must map to its exact path, not silently alias to "primary".
    assert registry.style_token_map["s-primary-blue"] == "colors.primary.blue"
    assert not hasattr(registry, "semantic_token_map")


def test_variable_name_does_not_alias_to_heuristic_semantic_token() -> None:
    """A variable name containing a semantic keyword must map to its exact path, not alias to a heuristic token."""
    fixture = {
        "id": "0:1",
        "name": "No Semantic Alias",
        "type": "FRAME",
        "variables": {"v-primary": {"name": "colors/primary/500", "collection": "theme"}},
        "children": [
            {
                "id": "1:1",
                "name": "Primary Button",
                "type": "FRAME",
                "fills": [{"type": "SOLID", "color": {"r": 0.23, "g": 0.51, "b": 0.96, "a": 1}}],
                "boundVariables": {"fill": "v-primary"},
            },
            {
                "id": "1:2",
                "name": "Surface",
                "type": "FRAME",
                "fills": [{"type": "SOLID", "color": {"r": 1, "g": 1, "b": 1, "a": 1}}],
            },
        ],
    }
    registry = design_tokens.FigmaTokenExtractor(fixture).extract()
    assert "primary" in registry.colors
    assert registry.variable_token_map["v-primary"] == "theme.colors.primary.500"
    assert not hasattr(registry, "semantic_token_map")


def test_exact_style_and_variable_names_take_precedence_over_heuristics() -> None:
    """If a style or variable name resolves to an exact path, it must not be overridden by a semantic guess."""
    fixture = {
        "id": "0:1",
        "name": "Exact Precedence",
        "type": "FRAME",
        "styles": {"s-primary": {"name": "colors/semantic/brand"}},
        "variables": {"v-primary": {"name": "colors/primary/500", "collection": "theme"}},
        "children": [
            {
                "id": "1:1",
                "name": "Brand Box",
                "type": "FRAME",
                "fills": [{"type": "SOLID", "color": {"r": 0.23, "g": 0.51, "b": 0.96, "a": 1}}],
                "styles": {"fill": "s-primary"},
                "boundVariables": {"fill": "v-primary"},
            }
        ],
    }
    registry = design_tokens.FigmaTokenExtractor(fixture).extract()
    assert registry.style_token_map["s-primary"] == "colors.semantic.brand"
    assert registry.variable_token_map["v-primary"] == "theme.colors.primary.500"
    assert "colors.semantic.brand" in registry.colors
    assert "theme.colors.primary.500" in registry.colors
