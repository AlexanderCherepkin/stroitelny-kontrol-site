import json
import re
import argparse
import colorsys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set


DEFAULT_OUTPUT_DIR = "src"
DEFAULT_REGISTRY_FILE = "design_tokens.json"
DEFAULT_TAILWIND_CONFIG = "tailwind.config.ts"
DEFAULT_GLOBALS_CSS = "app/globals.css"


def _rgba_to_hex(color: Optional[Dict[str, float]]) -> Optional[str]:
    if not color:
        return None
    try:
        r = int(round(color.get("r", 0) * 255))
        g = int(round(color.get("g", 0) * 255))
        b = int(round(color.get("b", 0) * 255))
        a = color.get("a", 1.0)
        if a < 1.0:
            a_int = int(round(a * 255))
            return f"#{r:02x}{g:02x}{b:02x}{a_int:02x}"
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return None


def _hex_to_rgb_tuple(hex_color: str) -> Tuple[float, float, float]:
    hex_color = hex_color.strip().lstrip("#").lower()
    if len(hex_color) == 3:
        r = int(hex_color[0] * 2, 16) / 255
        g = int(hex_color[1] * 2, 16) / 255
        b = int(hex_color[2] * 2, 16) / 255
    elif len(hex_color) == 4:
        r = int(hex_color[0] * 2, 16) / 255
        g = int(hex_color[1] * 2, 16) / 255
        b = int(hex_color[2] * 2, 16) / 255
    elif len(hex_color) == 6:
        r = int(hex_color[0:2], 16) / 255
        g = int(hex_color[2:4], 16) / 255
        b = int(hex_color[4:6], 16) / 255
    elif len(hex_color) == 8:
        r = int(hex_color[0:2], 16) / 255
        g = int(hex_color[2:4], 16) / 255
        b = int(hex_color[4:6], 16) / 255
    else:
        return (0.0, 0.0, 0.0)
    return (r, g, b)


def _hex_to_hsv(hex_color: str) -> Tuple[float, float, float]:
    r, g, b = _hex_to_rgb_tuple(hex_color)
    return colorsys.rgb_to_hsv(r, g, b)


def _hex_hue_category(hex_color: str) -> str:
    h, s, v = _hex_to_hsv(hex_color)
    if s < 0.08 or v < 0.12:
        return "gray"
    if 0 <= h < 0.06 or h >= 0.94:
        return "red"
    if 0.06 <= h < 0.15:
        return "orange"
    if 0.15 <= h < 0.20:
        return "yellow"
    if 0.20 <= h < 0.42:
        return "green"
    if 0.42 <= h < 0.50:
        return "cyan"
    if 0.50 <= h < 0.68:
        return "blue"
    if 0.68 <= h < 0.80:
        return "purple"
    return "pink"


def _safe_kebab(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9\-_/\s]+", "", name)
    name = re.sub(r"[\s/]+", "-", name)
    name = re.sub(r"-+", "-", name)
    return name.strip("-")


def _safe_css_var(name: str) -> str:
    return f"--{_safe_kebab(name)}"


def _safe_token_path(name: str) -> str:
    """Convert a Figma variable/style name into a dotted Tailwind token path."""
    name = name.strip().lower()
    # preserve slash as dot, remove everything else except alphanumerics / _ / .
    name = re.sub(r"[^a-z0-9_/.\s]+", "", name)
    name = re.sub(r"[\s/]+", ".", name)
    name = re.sub(r"\.+", ".", name)
    return name.strip(".")


def _css_var_from_path(path: str) -> str:
    """Convert a dotted token path into a dashed CSS variable name."""
    return _safe_css_var(path.replace(".", "-"))


def _path_to_dashed(path: str) -> str:
    return path.replace(".", "-")


def _has_alpha(hex_color: str) -> bool:
    hex_color = hex_color.strip().lstrip("#")
    return len(hex_color) in (4, 8)


def _style_lookup(node: Dict[str, Any], kind: str, styles_map: Dict[str, Any]) -> Optional[str]:
    styles = node.get("styles") or {}
    style_id = styles.get(kind)
    if not style_id or not styles_map:
        return None
    style = styles_map.get(style_id) or {}
    return style.get("name")


def _variable_lookup(node: Dict[str, Any], kind: str, variables_map: Dict[str, Any]) -> Optional[str]:
    bound = node.get("boundVariables") or {}
    var_id = bound.get(kind)
    if not var_id or not variables_map:
        return None
    variable = variables_map.get(var_id) or {}
    return variable.get("name")


SEMANTIC_COLOR_PATTERNS = [
    (r"\bbackground\b|\bbg\b|\bsurface\b|\bcanvas\b", "background"),
    (r"\bforeground\b|\btext\b|\bheading\b|\bbody\b", "foreground"),
    (r"\bprimary\b|\bbrand\b|\bmain\b", "primary"),
    (r"\bsecondary\b|\bsub\b", "secondary"),
    (r"\bmuted\b|\bsecondary-text\b|\bplaceholder\b|\bdisabled\b", "muted"),
    (r"\baccent\b|\bhighlight\b|\bcta\b", "accent"),
    (r"\bdanger\b|\berror\b|\bdestructive\b", "destructive"),
    (r"\bsuccess\b|\bpositive\b", "success"),
    (r"\bwarning\b|\bcaution\b", "warning"),
    (r"\bborder\b|\bdivider\b|\boutline\b", "border"),
    (r"\bcard\b|\bpanel\b", "card"),
    (r"\bpopover\b|\bdropdown\b", "popover"),
]


def _semantic_name_from_style(style_name: Optional[str]) -> Optional[str]:
    if not style_name:
        return None
    lower = style_name.lower()
    for pattern, name in SEMANTIC_COLOR_PATTERNS:
        if re.search(pattern, lower):
            return name
    return None


@dataclass
class ColorToken:
    name: str
    hex: str
    rgb: str
    css_var: str
    contexts: List[str] = field(default_factory=list)
    source: str = "local"
    is_alpha: bool = False


@dataclass
class TypographyToken:
    name: str
    kind: str
    value: Any
    css_var: Optional[str] = None
    contexts: List[str] = field(default_factory=list)


@dataclass
class TokenRegistry:
    colors: Dict[str, ColorToken] = field(default_factory=dict)
    fonts: Dict[str, str] = field(default_factory=dict)
    font_sizes: Dict[int, str] = field(default_factory=dict)
    font_weights: Dict[int, str] = field(default_factory=dict)
    line_heights: Dict[float, str] = field(default_factory=dict)
    color_by_hex: Dict[str, str] = field(default_factory=dict)
    text_color_by_hex: Dict[str, str] = field(default_factory=dict)
    style_token_map: Dict[str, str] = field(default_factory=dict)
    variable_token_map: Dict[str, str] = field(default_factory=dict)
    exact_token_paths: List[str] = field(default_factory=list)

    def to_config_map(self) -> Dict[str, Any]:
        return {
            "colors": {name: token.hex for name, token in self.colors.items()},
            "fonts": dict(self.fonts),
            "font_sizes": {str(px): name for px, name in self.font_sizes.items()},
            "font_weights": {str(w): name for w, name in self.font_weights.items()},
            "line_heights": {str(lh): name for lh, name in self.line_heights.items()},
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "colors": {
                name: {
                    "name": token.name,
                    "hex": token.hex,
                    "rgb": token.rgb,
                    "css_var": token.css_var,
                    "contexts": token.contexts,
                    "source": token.source,
                    "is_alpha": token.is_alpha,
                }
                for name, token in self.colors.items()
            },
            "fonts": dict(self.fonts),
            "font_sizes": {str(px): name for px, name in self.font_sizes.items()},
            "font_weights": {str(w): name for w, name in self.font_weights.items()},
            "line_heights": {str(lh): name for lh, name in self.line_heights.items()},
            "color_by_hex": dict(self.color_by_hex),
            "text_color_by_hex": dict(self.text_color_by_hex),
            "style_token_map": dict(self.style_token_map),
            "variable_token_map": dict(self.variable_token_map),
            "semantic_token_map": dict(self.semantic_token_map),
            "semantic_match_scores": dict(self.semantic_match_scores),
            "exact_token_paths": list(self.exact_token_paths),
        }

    def to_json(self) -> Dict[str, Any]:
        return self.to_dict()


def _walk_nodes(node: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(node, dict):
        return []
    results = [node]
    for child in node.get("children", []):
        results.extend(_walk_nodes(child))
    return results


def _color_value_to_hex(value: Any) -> Optional[str]:
    if not isinstance(value, dict):
        return None
    if "hex" in value:
        return value["hex"]
    if "color" in value:
        return _rgba_to_hex(value["color"])
    if "r" in value and "g" in value and "b" in value:
        return _rgba_to_hex(value)
    return None


def _resolve_id_to_hex(
    nodes: List[Dict[str, Any]],
    styles_map: Dict[str, Any],
    variables_map: Dict[str, Any],
) -> Dict[str, str]:
    """Map each style/variable ID to the first raw hex color observed on a node that uses it."""
    id_to_hex: Dict[str, str] = {}

    # 1. Prefer explicit resolved colors from variable/style metadata when present.
    for vid, meta in variables_map.items():
        hex_color = _color_value_to_hex(meta.get("value")) or _color_value_to_hex(meta.get("resolvedValue"))
        if not hex_color:
            values = meta.get("valuesByMode")
            if isinstance(values, dict):
                for mode_value in values.values():
                    hex_color = _color_value_to_hex(mode_value)
                    if hex_color:
                        break
        if hex_color:
            id_to_hex[vid] = hex_color

    for sid, meta in styles_map.items():
        hex_color = _color_value_to_hex(meta.get("value")) or _color_value_to_hex(meta.get("resolvedValue"))
        if hex_color:
            id_to_hex[sid] = hex_color

    def record_for_node(node: Dict[str, Any], hex_color: str, kind: str):
        style_id = (node.get("styles") or {}).get(kind)
        if style_id and style_id not in id_to_hex:
            id_to_hex.setdefault(style_id, hex_color)
        var_id = (node.get("boundVariables") or {}).get(kind)
        if var_id and var_id not in id_to_hex:
            id_to_hex.setdefault(var_id, hex_color)

    for node in nodes:
        for fill in node.get("fills", []):
            if fill.get("type") != "SOLID":
                continue
            hex_color = fill.get("hex") or _rgba_to_hex(fill.get("color"))
            if not hex_color:
                continue
            record_for_node(node, hex_color, "fill")

        for stroke in node.get("strokes", []):
            if stroke.get("type") != "SOLID":
                continue
            hex_color = stroke.get("hex") or _rgba_to_hex(stroke.get("color"))
            if not hex_color:
                continue
            record_for_node(node, hex_color, "stroke")

        style = node.get("style") or {}
        for fill in style.get("fills", []):
            if fill.get("type") != "SOLID":
                continue
            hex_color = fill.get("hex") or _rgba_to_hex(fill.get("color"))
            if not hex_color:
                continue
            record_for_node(node, hex_color, "text")

    return id_to_hex


def _context_weights(context: str) -> Dict[str, float]:
    lower = context.lower()
    weights = {"surface": 1.0, "body": 1.0, "heading": 1.0, "button": 1.0, "other": 1.0}
    if any(w in lower for w in ["body", "description", "subtitle", "caption", "paragraph"]):
        weights["body"] = 3.0
    if any(w in lower for w in ["headline", "title", "heading", "h1", "h2", "h3", "hero", "head"]):
        weights["heading"] = 2.5
    if any(w in lower for w in ["confirm", "primary", "cta", "main"]):
        weights["button"] = 5.0
    elif any(w in lower for w in ["button", "submit", "save"]):
        weights["button"] = 4.0
    elif any(w in lower for w in ["action", "cancel", "secondary", "close"]):
        weights["button"] = 2.0
    if any(w in lower for w in ["page", "canvas", "background", "navbar", "footer"]):
        weights["surface"] = 2.5
    if any(w in lower for w in ["section", "hero section"]):
        weights["surface"] = 2.0
    if any(w in lower for w in ["card", "panel", "tile", "modal"]):
        weights["surface"] = 1.5
    return weights


def _collect_color_usages(
    nodes: List[Dict[str, Any]],
    styles_map: Dict[str, Any],
    variables_map: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    usages: Dict[str, Dict[str, Any]] = {}

    def record(hex_color: str, context: str, kind: str, style_name: Optional[str] = None):
        hex_norm = hex_color.lower().strip().lstrip("#")
        if not re.match(r"^[0-9a-f]{3,8}$", hex_norm):
            return
        key = hex_norm
        if key not in usages:
            usages[key] = {
                "hex": f"#{hex_norm}",
                "contexts": set(),
                "kinds": set(),
                "style_names": set(),
                "weights": {"surface": 0.0, "body": 0.0, "heading": 0.0, "button": 0.0, "other": 0.0},
            }
        meta = usages[key]
        meta["contexts"].add(context)
        meta["kinds"].add(kind)
        if style_name:
            meta["style_names"].add(style_name)
        w = _context_weights(context)
        for k, v in w.items():
            meta["weights"][k] += v

    for node in nodes:
        context = node.get("name", "unnamed")
        # Node fills
        for fill in node.get("fills", []):
            if fill.get("type") != "SOLID":
                continue
            hex_color = fill.get("hex") or _rgba_to_hex(fill.get("color"))
            if not hex_color:
                continue
            style_name = (
                _style_lookup(node, "fill", styles_map)
                or _variable_lookup(node, "fill", variables_map)
            )
            record(hex_color, context, "fill", style_name)

        # Strokes
        for stroke in node.get("strokes", []):
            if stroke.get("type") != "SOLID":
                continue
            hex_color = stroke.get("hex") or _rgba_to_hex(stroke.get("color"))
            if not hex_color:
                continue
            style_name = _style_lookup(node, "stroke", styles_map)
            record(hex_color, context, "stroke", style_name)

        # Text style fills
        style = node.get("style") or {}
        for fill in style.get("fills", []):
            if fill.get("type") != "SOLID":
                continue
            hex_color = fill.get("hex") or _rgba_to_hex(fill.get("color"))
            if not hex_color:
                continue
            style_name = _style_lookup(node, "text", styles_map)
            record(hex_color, context, "text", style_name)

        # Effects shadows
        for effect in node.get("effects", []):
            color = effect.get("color") or effect.get("hex")
            if not color:
                continue
            hex_color = _rgba_to_hex(color) if isinstance(color, dict) else color
            if not hex_color:
                continue
            record(hex_color, context, "effect")

    return usages


def _assign_color_tokens(
    usages: Dict[str, Dict[str, Any]],
    nodes: List[Dict[str, Any]],
) -> Dict[str, ColorToken]:
    assigned: Dict[str, ColorToken] = {}
    claimed: Set[str] = set()

    def claim(name: str, key: str, fallback: Optional[str] = None) -> Optional[str]:
        if name in claimed:
            if fallback and fallback not in claimed:
                claimed.add(fallback)
                return fallback
            return None
        claimed.add(name)
        return name

    def make_token(name: str, key: str) -> ColorToken:
        meta = usages[key]
        hex_color = meta["hex"]
        r, g, b = _hex_to_rgb_tuple(hex_color)
        rgb = f"rgb({int(r*255)}, {int(g*255)}, {int(b*255)})"
        return ColorToken(
            name=name,
            hex=hex_color,
            rgb=rgb,
            css_var=_safe_css_var(name),
            contexts=sorted(meta["contexts"])[:5],
            is_alpha=_has_alpha(hex_color),
        )

    # 1. Map explicit Figma style/variable names to semantic tokens first.
    style_to_key: Dict[str, str] = {}
    for key, meta in usages.items():
        for style_name in meta["style_names"]:
            sem = _semantic_name_from_style(style_name)
            if sem:
                style_to_key.setdefault(sem, key)

    for sem, key in style_to_key.items():
        name = claim(sem, key)
        if name:
            assigned[name] = make_token(name, key)

    # Compute weighted scores by kind
    surface_scores: Dict[str, float] = {}
    text_scores: Dict[str, float] = {}
    button_scores: Dict[str, float] = {}
    all_scores: Dict[str, float] = {}

    for key, meta in usages.items():
        w = meta["weights"]
        kinds = meta["kinds"]
        if any(k in kinds for k in ("fill", "stroke", "effect")):
            surface_scores[key] = surface_scores.get(key, 0.0) + w["surface"]
        if "text" in kinds:
            text_scores[key] = text_scores.get(key, 0.0) + w["body"] + w["heading"]
        if any(k in kinds for k in ("fill", "stroke")):
            button_scores[key] = button_scores.get(key, 0.0) + w["button"]
        all_scores[key] = all_scores.get(key, 0.0) + sum(w.values())

    # 2. Foreground: highest text-weighted hex
    if text_scores:
        fg_key = max(text_scores, key=text_scores.get)
        name = claim("foreground", fg_key)
        if name:
            assigned[name] = make_token(name, fg_key)

    # 3. Background: highest surface-weighted hex, excluding foreground
    bg_candidates = {k: v for k, v in surface_scores.items() if k != (fg_key if text_scores else None)}
    if bg_candidates:
        bg_key = max(bg_candidates, key=bg_candidates.get)
        name = claim("background", bg_key)
        if name:
            assigned[name] = make_token(name, bg_key)
    elif surface_scores:
        bg_key = max(surface_scores, key=surface_scores.get)
        name = claim("background", bg_key)
        if name:
            assigned[name] = make_token(name, bg_key)

    # 4. Primary: highest button-weighted hex, fallback to saturated non-bg surface
    def saturation(key: str) -> float:
        r, g, b = _hex_to_rgb_tuple(usages[key]["hex"])
        _, s, _ = colorsys.rgb_to_hsv(r, g, b)
        return s

    primary_key: Optional[str] = None
    button_candidates = {k: v for k, v in button_scores.items() if k != bg_key}
    if button_candidates:
        primary_key = max(button_candidates, key=lambda k: (button_candidates[k], saturation(k)))
    else:
        non_bg_surface = {k: v for k, v in surface_scores.items() if k != bg_key}
        if non_bg_surface:
            sorted_by_score = sorted(non_bg_surface.items(), key=lambda kv: (-kv[1], -saturation(kv[0])))
            primary_key = sorted_by_score[0][0]

    if primary_key and primary_key != bg_key:
        name = claim("primary", primary_key)
        if name:
            assigned[name] = make_token(name, primary_key)

    # 5. Secondary: next best non-background surface color
    non_bg_surface = {k: v for k, v in surface_scores.items() if k != bg_key and k != primary_key}
    if non_bg_surface:
        secondary_key = max(non_bg_surface, key=non_bg_surface.get)
        name = claim("secondary", secondary_key)
        if name:
            assigned[name] = make_token(name, secondary_key)

    # 5b. Border: light gray surface color, distinct from background
    border_candidates = [
        k
        for k in surface_scores
        if k != bg_key
        and _hex_hue_category(usages[k]["hex"]) == "gray"
        and _hex_to_hsv(usages[k]["hex"])[2] >= 0.85
    ]
    if border_candidates:
        border_key = max(border_candidates, key=lambda k: surface_scores[k])
        name = claim("border", border_key)
        if name:
            assigned[name] = make_token(name, border_key)

    # 6. Muted: highest body-weighted gray-ish color
    gray_candidates = [
        k for k in usages
        if _hex_hue_category(usages[k]["hex"]) == "gray"
        and k not in {t.hex.strip().lstrip("#").lower() for t in assigned.values()}
    ]
    if gray_candidates:
        muted_key = max(gray_candidates, key=lambda k: text_scores.get(k, 0.0) + surface_scores.get(k, 0.0))
        name = claim("muted", muted_key)
        if name:
            assigned[name] = make_token(name, muted_key)

    # 7. Semantic hue buckets for remaining significant colors
    remaining = sorted(
        [k for k in usages if k not in {t.hex.strip().lstrip("#").lower() for t in assigned.values()}],
        key=lambda k: all_scores.get(k, 0.0),
        reverse=True,
    )
    hue_slots = {
        "destructive": "red",
        "success": "green",
        "warning": "orange",
    }
    for key in remaining:
        hue = _hex_hue_category(usages[key]["hex"])
        for token_name, expected in hue_slots.items():
            if expected and hue == expected and token_name not in claimed:
                name = claim(token_name, key)
                if name:
                    assigned[name] = make_token(name, key)
                break

    # 8. Accent: most saturated remaining non-alpha color
    for key in remaining:
        if key in {t.hex.strip().lstrip("#").lower() for t in assigned.values()}:
            continue
        meta = usages[key]
        if meta["hex"].startswith("#") and _has_alpha(meta["hex"]):
            continue
        hue = _hex_hue_category(meta["hex"])
        if hue != "gray":
            name = claim("accent", key)
            if name:
                assigned[name] = make_token(name, key)
            break

    return assigned


def _collect_typography(
    nodes: List[Dict[str, Any]],
    styles_map: Dict[str, Any],
    variables_map: Dict[str, Any],
) -> Tuple[Set[str], Dict[int, Set[int]], Dict[float, Set[str]]]:
    families: Set[str] = set()
    sizes: Dict[int, Set[int]] = {}
    line_heights: Dict[float, Set[str]] = {}

    for node in nodes:
        if node.get("type") != "TEXT":
            continue
        style = node.get("style") or {}
        family = style.get("fontFamily") or node.get("fontFamily")
        size = style.get("fontSize") or node.get("fontSize")
        weight = style.get("fontWeight") or node.get("fontWeight") or 400
        line_px = style.get("lineHeightPx")

        if family:
            families.add(family)
        if isinstance(size, (int, float)) and size > 0:
            px = int(round(size))
            sizes.setdefault(px, set()).add(int(weight))
            if isinstance(line_px, (int, float)) and line_px > 0:
                ratio = round(line_px / px, 3)
                line_heights.setdefault(ratio, set()).add(node.get("name", "unnamed"))

    return families, sizes, line_heights


def _extract_exact_variable_color_tokens(
    nodes: List[Dict[str, Any]],
    styles_map: Dict[str, Any],
    variables_map: Dict[str, Any],
) -> Tuple[Dict[str, ColorToken], Dict[str, str], Dict[str, str]]:
    """Create ColorTokens directly from Figma style/variable names (hierarchical path)."""
    id_to_hex = _resolve_id_to_hex(nodes, styles_map, variables_map)
    tokens: Dict[str, ColorToken] = {}
    style_token_map: Dict[str, str] = {}
    variable_token_map: Dict[str, str] = {}

    def make_token(path: str, hex_color: str, source: str) -> ColorToken:
        r, g, b = _hex_to_rgb_tuple(hex_color)
        rgb = f"rgb({int(r*255)}, {int(g*255)}, {int(b*255)})"
        return ColorToken(
            name=path,
            hex=hex_color,
            rgb=rgb,
            css_var=_css_var_from_path(path),
            contexts=[],
            source=source,
            is_alpha=_has_alpha(hex_color),
        )

    for vid, meta in variables_map.items():
        name = meta.get("name")
        if not name:
            continue
        collection = meta.get("collection")
        full_name = f"{collection}/{name}" if collection else name
        hex_color = id_to_hex.get(vid)
        if not hex_color:
            continue
        path = _safe_token_path(full_name)
        if not path:
            continue
        tokens[path] = make_token(path, hex_color, "variable")
        variable_token_map[vid] = path

    for sid, meta in styles_map.items():
        name = meta.get("name")
        if not name:
            continue
        hex_color = id_to_hex.get(sid)
        if not hex_color:
            continue
        path = _safe_token_path(name)
        if not path:
            continue
        # A style and a variable could define the same path; variable wins.
        if path in tokens:
            style_token_map[sid] = path
            continue
        tokens[path] = make_token(path, hex_color, "style")
        style_token_map[sid] = path

    return tokens, style_token_map, variable_token_map


def _assign_typography_tokens(
    families: Set[str],
    sizes: Dict[int, Set[int]],
    line_heights: Dict[float, Set[str]],
) -> Tuple[Dict[str, str], Dict[int, str], Dict[int, str], Dict[float, str]]:
    fonts: Dict[str, str] = {}
    if families:
        primary = sorted(families)[0]
        fonts[primary] = "sans"

    # Tailwind default scale mapping (px -> token name)
    scale = {
        12: "xs",
        14: "sm",
        16: "base",
        18: "lg",
        20: "xl",
        24: "2xl",
        30: "3xl",
        36: "4xl",
        48: "5xl",
        60: "6xl",
        72: "7xl",
        96: "8xl",
    }

    font_sizes: Dict[int, str] = {}
    for px in sorted(sizes.keys()):
        if px in scale:
            font_sizes[px] = scale[px]
        else:
            # pick nearest lower scale or create token
            nearest = max((s for s in scale if s <= px), default=16)
            font_sizes[px] = scale[nearest]

    font_weights: Dict[int, str] = {
        400: "normal",
        500: "medium",
        600: "semibold",
        700: "bold",
        800: "extrabold",
        900: "black",
    }
    # Only keep weights actually present
    present_weights: Set[int] = set()
    for weights in sizes.values():
        present_weights.update(weights)
    font_weights = {w: name for w, name in font_weights.items() if w in present_weights}

    line_height_tokens: Dict[float, str] = {}
    for ratio in sorted(line_heights.keys()):
        if abs(ratio - 1.0) < 0.05:
            line_height_tokens[ratio] = "none"
        elif abs(ratio - 1.25) < 0.05:
            line_height_tokens[ratio] = "tight"
        elif abs(ratio - 1.5) < 0.05:
            line_height_tokens[ratio] = "normal"
        elif abs(ratio - 1.625) < 0.05:
            line_height_tokens[ratio] = "relaxed"
        else:
            line_height_tokens[ratio] = "normal"

    return fonts, font_sizes, font_weights, line_height_tokens


class FigmaTokenExtractor:
    def __init__(self, node: Dict[str, Any]):
        self.root = node
        self.styles_map = self._build_styles_map()
        self.variables_map = self._build_variables_map()

    def _build_styles_map(self) -> Dict[str, Any]:
        styles = self.root.get("styles") or {}
        result: Dict[str, Any] = {}
        for sid, meta in styles.items():
            if isinstance(meta, dict):
                result[sid] = meta
        return result

    def _build_variables_map(self) -> Dict[str, Any]:
        variables = self.root.get("variables") or {}
        if isinstance(variables, dict):
            return variables
        return {}

    def extract(self) -> TokenRegistry:
        nodes = _walk_nodes(self.root)
        registry = TokenRegistry()

        # 1. Exact Figma style/variable tokens (hierarchical, name-driven) take precedence.
        exact_tokens, exact_style_map, exact_var_map = _extract_exact_variable_color_tokens(
            nodes, self.styles_map, self.variables_map
        )
        registry.colors.update(exact_tokens)
        registry.style_token_map.update(exact_style_map)
        registry.variable_token_map.update(exact_var_map)
        registry.exact_token_paths.extend(sorted(exact_tokens.keys()))

        # 2. Heuristic fallback for raw colors that are not bound to a style/variable.
        usages = _collect_color_usages(nodes, self.styles_map, self.variables_map)
        colors = _assign_color_tokens(usages, nodes)
        for name, token in colors.items():
            registry.colors.setdefault(name, token)
        registry.color_by_hex = {token.hex.lower().strip().lstrip("#"): name for name, token in colors.items()}
        # text colors may be same token as surface; build separate reverse map
        for name, token in colors.items():
            key = token.hex.lower().strip().lstrip("#")
            registry.text_color_by_hex[key] = name

        families, sizes, line_heights = _collect_typography(nodes, self.styles_map, self.variables_map)
        fonts, font_sizes, font_weights, line_height_tokens = _assign_typography_tokens(families, sizes, line_heights)
        registry.fonts = fonts
        registry.font_sizes = font_sizes
        registry.font_weights = font_weights
        registry.line_heights = line_height_tokens

        return registry


def _set_nested(obj: Dict[str, Any], path: List[str], value: Any) -> None:
    for key in path[:-1]:
        obj = obj.setdefault(key, {})
    obj[path[-1]] = value


def generate_tailwind_config(registry: TokenRegistry) -> str:
    colors = registry.colors
    color_config: Dict[str, Any] = {}
    for name, token in colors.items():
        if "." in name:
            # Hierarchical exact token, e.g. colors.primary.500
            _set_nested(color_config, name.split("."), f"var({token.css_var})")
            continue
        if name in {"background", "foreground", "border", "input", "ring"}:
            color_config[name] = f"var({token.css_var})"
        else:
            color_config[name] = {
                "DEFAULT": f"var({token.css_var})",
                "foreground": f"var({_safe_css_var(f'{name}-foreground')})",
            }

    font_family_config = {name: f"var({_safe_css_var(f'font-{name}')})" for name in registry.fonts.values()}
    font_size_config: Dict[str, str] = {}
    for px, name in registry.font_sizes.items():
        rem = round(px / 16, 3)
        font_size_config[name] = f"var({_safe_css_var(f'font-size-{name}')})"

    config = {
        "content": ["./src/app/**/*.{js,ts,jsx,tsx}", "./src/components/**/*.{js,ts,jsx,tsx}"],
        "theme": {
            "extend": {
                "colors": color_config,
                "fontFamily": font_family_config,
                "fontSize": font_size_config,
            },
        },
        "plugins": [],
    }

    json_str = json.dumps(config, indent=2, ensure_ascii=False)
    return f"""import type {{ Config }} from "tailwindcss";

const config: Config = {json_str};

export default config;
"""


def generate_globals_css(registry: TokenRegistry) -> str:
    lines: List[str] = ["@tailwind base;", "@tailwind components;", "@tailwind utilities;", ""]
    lines.append("@layer base {")
    lines.append("  :root {")

    # Colors
    for name, token in registry.colors.items():
        lines.append(f"    {token.css_var}: {token.hex};")
        if name not in {"background", "foreground", "border", "input", "ring"}:
            fg_var = _safe_css_var(f"{name}-foreground")
            # auto-compute readable foreground (white/black)
            lines.append(f"    {fg_var}: #ffffff;")

    # Typography
    for family, token_name in registry.fonts.items():
        safe_family = family.replace("\"", "'")
        lines.append(
            f"    {_safe_css_var(f'font-{token_name}')}: '{safe_family}', ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;"
        )

    for px, name in sorted(registry.font_sizes.items(), key=lambda kv: kv[0]):
        rem = round(px / 16, 3)
        lines.append(f"    {_safe_css_var(f'font-size-{name}')}: {rem}rem;")

    for ratio, name in sorted(registry.line_heights.items(), key=lambda kv: kv[0]):
        lines.append(f"    {_safe_css_var(f'line-height-{name}')}: {ratio};")

    lines.append("  }")
    lines.append("}")
    lines.append("")
    lines.append("@layer base {")
    lines.append("  * {")
    lines.append("    @apply border-border;")
    lines.append("  }")
    lines.append("  body {")
    if "background" in registry.colors:
        lines.append("    @apply bg-background text-foreground;")
    lines.append("  }")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def save_registry(registry: TokenRegistry, output_path: str) -> None:
    data = {
        "colors": {
            name: {
                "hex": token.hex,
                "rgb": token.rgb,
                "css_var": token.css_var,
                "contexts": token.contexts,
                "is_alpha": token.is_alpha,
            }
            for name, token in registry.colors.items()
        },
        "fonts": registry.fonts,
        "font_sizes": {str(px): name for px, name in registry.font_sizes.items()},
        "font_weights": {str(w): name for w, name in registry.font_weights.items()},
        "line_heights": {str(lh): name for lh, name in registry.line_heights.items()},
        "color_by_hex": registry.color_by_hex,
        "text_color_by_hex": registry.text_color_by_hex,
        "style_token_map": registry.style_token_map,
        "variable_token_map": registry.variable_token_map,
        "exact_token_paths": registry.exact_token_paths,
    }
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def generate_artifacts(
    node: Dict[str, Any],
    output_dir: str = DEFAULT_OUTPUT_DIR,
    registry_file: str = DEFAULT_REGISTRY_FILE,
    tailwind_config: str = DEFAULT_TAILWIND_CONFIG,
    globals_css: str = DEFAULT_GLOBALS_CSS,
) -> Dict[str, str]:
    extractor = FigmaTokenExtractor(node)
    registry = extractor.extract()

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    registry_path = out / registry_file
    tailwind_path = out / tailwind_config
    css_path = out / globals_css

    save_registry(registry, str(registry_path))
    tailwind_path.write_text(generate_tailwind_config(registry), encoding="utf-8")
    css_path.parent.mkdir(parents=True, exist_ok=True)
    css_path.write_text(generate_globals_css(registry), encoding="utf-8")

    return {
        "registry": str(registry_path),
        "tailwind_config": str(tailwind_path),
        "globals_css": str(css_path),
    }


def main():
    parser = argparse.ArgumentParser(description="Design Tokens Engine: Figma → Tailwind tokens")
    parser.add_argument("--file", default="figma_node.json", help="Path to Figma node JSON")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory")
    parser.add_argument("--registry", default=DEFAULT_REGISTRY_FILE, help="Token registry filename")
    parser.add_argument("--tailwind-config", default=DEFAULT_TAILWIND_CONFIG, help="Tailwind config filename")
    parser.add_argument("--globals-css", default=DEFAULT_GLOBALS_CSS, help="globals.css relative path inside output-dir")
    args = parser.parse_args()

    import analyzer

    data = analyzer.load_figma_json(args.file)
    if not data:
        print("[ERROR] Could not load Figma node JSON")
        return

    artifacts = generate_artifacts(
        data,
        output_dir=args.output_dir,
        registry_file=args.registry,
        tailwind_config=args.tailwind_config,
        globals_css=args.globals_css,
    )
    for key, path in artifacts.items():
        print(f"[TOKENS] {key}: {path}")


if __name__ == "__main__":
    main()
