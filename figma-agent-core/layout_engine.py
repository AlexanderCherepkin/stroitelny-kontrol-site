import importlib.util
import json
import re
import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _import_component_registry() -> Any:
    if "component_registry" in sys.modules:
        return sys.modules["component_registry"]
    if "figma_component_registry" in sys.modules:
        return sys.modules["figma_component_registry"]
    spec = importlib.util.spec_from_file_location(
        "component_registry", str(Path(__file__).with_name("component_registry.py"))
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["component_registry"] = module
    spec.loader.exec_module(module)
    return module


_SPACING_CACHE: Dict[int, str] = {}


def _spacing_class(value: float) -> str:
    """Возвращает Tailwind-класс для spacing-значения в px."""
    if value < 0:
        return f"-{_spacing_class(abs(value))}"
    rounded = int(round(value))
    if rounded in _SPACING_CACHE:
        return _SPACING_CACHE[rounded]
    if rounded == 0:
        return "0"
    scale = {
        1: "px",
        2: "0.5",
        4: "1",
        6: "1.5",
        8: "2",
        10: "2.5",
        12: "3",
        14: "3.5",
        16: "4",
        20: "5",
        24: "6",
        28: "7",
        32: "8",
        36: "9",
        40: "10",
        44: "11",
        48: "12",
        56: "14",
        64: "16",
        80: "20",
        96: "24",
        112: "28",
        128: "32",
        144: "36",
        160: "40",
        176: "44",
        192: "48",
        208: "52",
        224: "56",
        240: "60",
        256: "64",
        288: "72",
        320: "80",
        384: "96",
    }
    if rounded in scale:
        _SPACING_CACHE[rounded] = scale[rounded]
        return scale[rounded]
    arbitrary = f"{rounded}px"
    _SPACING_CACHE[rounded] = arbitrary
    return arbitrary


def _arbitrary(class_base: str, value: Any, unit: str = "px") -> str:
    """Собирает Tailwind-класс с произвольным значением."""
    return f"{class_base}-[{value}{unit}]"


def _hex_to_tailwind(hex_color: Optional[str]) -> Optional[str]:
    if not hex_color:
        return None
    hex_color = hex_color.lower().strip()
    if not re.match(r"^#[0-9a-f]{3,8}$", hex_color):
        return None
    palette = {
        "#000000": "black",
        "#ffffff": "white",
        "#ef4444": "red-500",
        "#f97316": "orange-500",
        "#eab308": "yellow-500",
        "#22c55e": "green-500",
        "#06b6d4": "cyan-500",
        "#3b82f6": "blue-500",
        "#6366f1": "indigo-500",
        "#a855f7": "purple-500",
        "#ec4899": "pink-500",
        "#f43f5e": "rose-500",
        "#94a3b8": "slate-400",
        "#64748b": "slate-500",
        "#475569": "slate-600",
    }
    return palette.get(hex_color, hex_color)


def _class_for_color(prefix: str, hex_color: Optional[str]) -> Optional[str]:
    mapped = _hex_to_tailwind(hex_color)
    if not mapped:
        return None
    if mapped.startswith("#"):
        return _arbitrary(prefix, mapped, unit="")
    return f"{prefix}-{mapped}"


def _token_for_hex(hex_color: Optional[str], token_map: Optional[Dict[str, str]]) -> Optional[str]:
    if not hex_color or not token_map:
        return None
    key = hex_color.lower().strip().lstrip("#")
    return token_map.get(key)


def _color_to_hex(color: Optional[Dict[str, float]]) -> Optional[str]:
    """Конвертирует raw Figma RGBA в HEX, если в ноде нет precomputed hex."""
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


def _hex_to_rgba(hex_color: Optional[str]) -> Optional[str]:
    """Превращает HEX с альфа или без в CSS rgba()/rgb() строку."""
    if not hex_color:
        return None
    hex_color = hex_color.lower().strip().lstrip("#")
    if not re.match(r"^[0-9a-f]{3,8}$", hex_color):
        return None
    if len(hex_color) == 3:
        r = int(hex_color[0] * 2, 16)
        g = int(hex_color[1] * 2, 16)
        b = int(hex_color[2] * 2, 16)
        return f"rgb({r}, {g}, {b})"
    if len(hex_color) == 4:
        r = int(hex_color[0] * 2, 16)
        g = int(hex_color[1] * 2, 16)
        b = int(hex_color[2] * 2, 16)
        a = int(hex_color[3] * 2, 16) / 255
        return f"rgba({r}, {g}, {b}, {a:.2f})"
    if len(hex_color) == 6:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return f"rgb({r}, {g}, {b})"
    if len(hex_color) == 8:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        a = int(hex_color[6:8], 16) / 255
        return f"rgba({r}, {g}, {b}, {a:.2f})"
    return None


def _has_alpha(hex_color: Optional[str]) -> bool:
    if not hex_color:
        return False
    hex_color = hex_color.strip().lstrip("#")
    return len(hex_color) in (4, 8)


def _px(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_name(name: Any) -> str:
    return re.sub(r"[^\w\-]", "_", str(name or "unnamed")).strip("_") or "unnamed"


def _has_image_fill(node: Dict[str, Any]) -> bool:
    for f in node.get("fills", []) or []:
        if f.get("type") == "IMAGE":
            return True
    return False


def _infer_data_role(node: Dict[str, Any]) -> str:
    """Map a leaf Figma node to a data-model field role."""
    name = _safe_name(node.get("name", "")).lower()
    node_type = node.get("type", "")
    if node_type == "IMAGE" or _has_image_fill(node):
        return "imageUrl"
    triggers = node.get("prototype", {}).get("triggers", []) or []
    for trigger in triggers:
        if trigger.get("type") in ("URL", "NODE"):
            return "href"
    if "title" in name or "heading" in name or "headline" in name:
        return "title"
    if "subtitle" in name:
        return "subtitle"
    if "cta" in name or "button" in name:
        return "ctaText"
    if "name" in name:
        return "name"
    if "label" in name:
        return "label"
    if "description" in name or "body" in name or "copy" in name:
        return "description"
    return "text"


def _load_data_models(value: Any) -> Dict[str, Dict[str, Any]]:
    """Build a lookup from Figma node id to its data model definition."""
    data: Optional[Dict[str, Any]] = None
    if isinstance(value, dict):
        data = value
    elif isinstance(value, (str, Path)):
        path = Path(value)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                data = None
    if not data:
        return {}
    mapping: Dict[str, Dict[str, Any]] = {}
    for model in data.get("models", []):
        for node_id in model.get("occurrence_ids", []):
            mapping[str(node_id)] = model
    return mapping


@dataclass
class TailwindNode:
    tag: str = "div"
    classes: List[str] = field(default_factory=list)
    inline_styles: Dict[str, str] = field(default_factory=dict)
    text: Optional[str] = None
    src: Optional[str] = None
    alt: Optional[str] = None
    asset_type: Optional[str] = None
    asset_width: Optional[int] = None
    asset_height: Optional[int] = None
    inline_svg: Optional[str] = None
    backend_action: Optional[str] = None
    backend_endpoint: Optional[str] = None
    backend_model: Optional[str] = None
    backend_field: Optional[str] = None
    input_type: Optional[str] = None
    required: Optional[bool] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    pattern: Optional[str] = None
    enum_values: List[str] = field(default_factory=list)
    children: List["TailwindNode"] = field(default_factory=list)
    rich_text: Optional[List[Dict[str, Any]]] = None
    figma_id: Optional[str] = None
    figma_name: Optional[str] = None
    figma_type: Optional[str] = None
    component_ref: Optional[str] = None
    figma_component_key: Optional[str] = None
    component_set_id: Optional[str] = None
    component_id: Optional[str] = None
    variant_props: Dict[str, str] = field(default_factory=dict)
    overrides: List[Dict[str, Any]] = field(default_factory=list)
    is_instance: bool = False
    component_context: Optional[str] = None
    bbox: Optional[Dict[str, Optional[float]]] = None
    data_model: Optional[Dict[str, Any]] = None
    data_binding: Optional[Dict[str, Any]] = None
    alt_binding: Optional[Dict[str, Any]] = None

    def add_class(self, *classes: str) -> None:
        for cls in classes:
            if cls and cls not in self.classes:
                self.classes.append(cls)

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "tag": self.tag,
            "classes": self.classes,
        }
        if self.inline_styles:
            result["inline_styles"] = self.inline_styles
        if self.text is not None:
            result["text"] = self.text
        if self.rich_text:
            result["rich_text"] = self.rich_text
        if self.src is not None:
            result["src"] = self.src
        if self.alt is not None:
            result["alt"] = self.alt
        if self.children:
            result["children"] = [c.to_dict() for c in self.children]
        if self.figma_id is not None:
            result["figma_id"] = self.figma_id
        if self.figma_name is not None:
            result["figma_name"] = self.figma_name
        if self.figma_type is not None:
            result["figma_type"] = self.figma_type
        if self.component_ref is not None:
            result["component_ref"] = self.component_ref
        if self.figma_component_key is not None:
            result["figma_component_key"] = self.figma_component_key
        if self.component_set_id is not None:
            result["component_set_id"] = self.component_set_id
        if self.component_id is not None:
            result["component_id"] = self.component_id
        if self.variant_props:
            result["variant_props"] = self.variant_props
        if self.overrides:
            result["overrides"] = self.overrides
        if self.is_instance:
            result["is_instance"] = self.is_instance
        if self.component_context is not None:
            result["component_context"] = self.component_context
        if self.bbox is not None:
            result["bbox"] = self.bbox
        if self.data_model is not None:
            result["data_model"] = self.data_model
        if self.data_binding is not None:
            result["data_binding"] = self.data_binding
        if self.alt_binding is not None:
            result["alt_binding"] = self.alt_binding
        if self.asset_type is not None:
            result["asset_type"] = self.asset_type
        if self.asset_width is not None:
            result["asset_width"] = self.asset_width
        if self.asset_height is not None:
            result["asset_height"] = self.asset_height
        if self.inline_svg is not None:
            result["inline_svg"] = self.inline_svg
        if self.backend_action is not None:
            result["backend_action"] = self.backend_action
        if self.backend_endpoint is not None:
            result["backend_endpoint"] = self.backend_endpoint
        if self.backend_model is not None:
            result["backend_model"] = self.backend_model
        if self.backend_field is not None:
            result["backend_field"] = self.backend_field
        if self.input_type is not None:
            result["input_type"] = self.input_type
        if self.required is not None:
            result["required"] = self.required
        if self.min_length is not None:
            result["min_length"] = self.min_length
        if self.max_length is not None:
            result["max_length"] = self.max_length
        if self.min_value is not None:
            result["min_value"] = self.min_value
        if self.max_value is not None:
            result["max_value"] = self.max_value
        if self.pattern is not None:
            result["pattern"] = self.pattern
        if self.enum_values:
            result["enum_values"] = self.enum_values
        return result


@dataclass
class LayoutResult:
    root: TailwindNode
    node_count: int = 0
    text_node_count: int = 0
    asset_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root": self.root.to_dict(),
            "node_count": self.node_count,
            "text_node_count": self.text_node_count,
            "asset_count": self.asset_count,
        }


class FigmaLayoutEngine:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._use_arbitrary_sizes = self.config.get("use_arbitrary_sizes", True)
        self.tokens = self.config.get("tokens")
        self.assets = self.config.get("assets")
        self.backend_mapping = self.config.get("backend_mapping")
        self._form_by_node_id: Dict[str, Dict[str, Any]] = {}
        self._field_by_node_id: Dict[str, Dict[str, Any]] = {}
        if self.backend_mapping:
            for m in self.backend_mapping.get("mappings", []):
                self._form_by_node_id[m.get("node_id", "")] = m
                for fm in m.get("field_mappings", []):
                    self._field_by_node_id[fm.get("node_id", "")] = fm
        self.component_registry: Optional[Any] = None
        registry_path = self.config.get("component_registry")
        if registry_path:
            try:
                mod = _import_component_registry()
                if isinstance(registry_path, dict):
                    self.component_registry = mod.ComponentRegistry(registry_path)
                else:
                    self.component_registry = mod.ComponentRegistry.load(registry_path)
            except Exception as e:
                print(f"[LAYOUT] could not load component registry: {e}")

        self.component_mapper: Optional[Any] = None
        mapper_path = self.config.get("component_mapper")
        if mapper_path:
            try:
                mod = _import_component_registry()
                if isinstance(mapper_path, dict):
                    self.component_mapper = mapper_path
                else:
                    self.component_mapper = json.loads(Path(mapper_path).read_text(encoding="utf-8"))
            except Exception as e:
                print(f"[LAYOUT] could not load component mapper: {e}")

        # Manual override file takes precedence and is merged into the loaded mapper.
        self.override_path: Optional[Path] = None
        override_path = self.config.get("component_mapper_override")
        if override_path and Path(override_path).exists():
            try:
                from mapper_override import load_override_set, merge_overrides_into_mapper
            except ImportError:
                import importlib.util
                override_module_path = Path(__file__).with_name("mapper_override.py")
                spec = importlib.util.spec_from_file_location("mapper_override", str(override_module_path))
                override_module = importlib.util.module_from_spec(spec)
                sys.modules["mapper_override"] = override_module
                spec.loader.exec_module(override_module)
                load_override_set = override_module.load_override_set
                merge_overrides_into_mapper = override_module.merge_overrides_into_mapper
            try:
                override_set = load_override_set(override_path)
                self.component_mapper = merge_overrides_into_mapper(
                    self.component_mapper or {"version": "1.0", "mappings": {}},
                    override_set,
                    self.component_registry.data if self.component_registry else None,
                )
            except Exception as e:
                print(f"[LAYOUT] could not load component mapper override: {e}")

        self.data_models = _load_data_models(self.config.get("data_models"))

    def _token_for_style_or_variable(self, node: Optional[Dict[str, Any]], kind: str) -> Optional[str]:
        if not node or not self.tokens:
            return None
        style_id = (node.get("styles") or {}).get(kind)
        if style_id:
            # Exact style binding only; no silent semantic renaming.
            return self.tokens.get("style_token_map", {}).get(style_id)
        var_id = (node.get("boundVariables") or {}).get(kind)
        if var_id:
            # Exact variable binding only; no silent semantic renaming.
            return self.tokens.get("variable_token_map", {}).get(var_id)
        return None

    def _class_for_color(self, prefix: str, hex_color: Optional[str], node: Optional[Dict[str, Any]] = None, kind: str = "fill") -> Optional[str]:
        token_name = self._token_for_style_or_variable(node, kind)
        if token_name:
            # Dotted token paths (e.g. colors.primary.500) become dash-separated classes.
            class_segment = token_name.replace(".", "-")
            return f"{prefix}-{class_segment}"
        token_name = _token_for_hex(hex_color, self.tokens.get("color_by_hex") if self.tokens else None)
        if token_name:
            return f"{prefix}-{token_name}"
        return _class_for_color(prefix, hex_color)

    def _font_class(self, family: str) -> str:
        if self.tokens:
            token = self.tokens.get("fonts", {}).get(family)
            if token:
                return f"font-{token}"
        return _arbitrary("font", family.replace(" ", "_"), unit="")

    def _font_size_class(self, size_px: float) -> str:
        px = int(round(size_px))
        if self.tokens:
            token = self.tokens.get("font_sizes", {}).get(str(px))
            if token:
                return f"text-{token}"
        return _arbitrary("text", px)

    def _font_weight_class(self, weight: int) -> str:
        if self.tokens:
            token = self.tokens.get("font_weights", {}).get(str(weight))
            if token:
                return f"font-{token}"
        return _arbitrary("font", weight, unit="")

    def _line_height_class(self, ratio: float) -> str:
        if self.tokens:
            token = self.tokens.get("line_heights", {}).get(str(ratio))
            if token:
                return f"leading-{token}"
        return _arbitrary("leading", ratio, unit="")

    def convert(self, node: Dict[str, Any]) -> LayoutResult:
        root = self._convert_node(node, parent_box=node.get("box"))
        self._ensure_relative_for_absolute_children(root)
        stats = self._collect_stats(root)
        return LayoutResult(
            root=root,
            node_count=stats["nodes"],
            text_node_count=stats["texts"],
            asset_count=stats["assets"],
        )

    def _ensure_relative_for_absolute_children(self, node: TailwindNode) -> None:
        has_absolute_child = any(
            "absolute" in child.classes for child in node.children
        )
        if has_absolute_child:
            node.add_class("relative")
        for child in node.children:
            self._ensure_relative_for_absolute_children(child)

    def _collect_stats(self, node: TailwindNode) -> Dict[str, int]:
        stats = {"nodes": 1, "texts": 0, "assets": 0}
        if node.text is not None or node.rich_text:
            stats["texts"] += 1
        if node.src is not None:
            stats["assets"] += 1
        for child in node.children:
            child_stats = self._collect_stats(child)
            stats["nodes"] += child_stats["nodes"]
            stats["texts"] += child_stats["texts"]
            stats["assets"] += child_stats["assets"]
        return stats

    def _convert_node(
        self,
        node: Dict[str, Any],
        parent_box: Optional[Dict[str, Any]] = None,
        depth: int = 0,
        parent_layout_mode: Optional[str] = None,
        data_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[TailwindNode]:
        if not isinstance(node, dict) or not node.get("visible", True):
            return None

        node_id = node.get("id")
        model = self.data_models.get(str(node_id)) if node_id else None
        if model:
            data_context = {
                "model": model.get("name", "DataItem"),
                "field_map": model.get("field_map", {}),
                "sample_data": model.get("sample_data", []),
                "item_var": "item",
            }

        node_type = node.get("type", "UNKNOWN")
        name = _safe_name(node.get("name"))

        if node_type == "TEXT":
            return self._convert_text(node, parent_layout_mode=parent_layout_mode, data_context=data_context)

        if node_type == "IMAGE" or node.get("isAsset"):
            return self._convert_asset(node, data_context=data_context)

        if node_type in ("RECTANGLE", "ELLIPSE"):
            return self._convert_shape(node)

        if node_type == "VECTOR":
            has_image_fill = any(f.get("type") == "IMAGE" for f in (node.get("fills") or []))
            if not has_image_fill:
                return self._convert_shape(node)
            return self._convert_asset(node, data_context=data_context)

        tw_node = TailwindNode(
            tag=self._semantic_tag(node, depth),
            figma_id=node_id,
            figma_name=name,
            figma_type=node.get("type"),
        )
        if data_context and model:
            tw_node.data_model = {
                "model": data_context["model"],
                "field_map": data_context["field_map"],
                "sample_data": data_context["sample_data"],
                "list": True,
            }
        if node.get("box"):
            tw_node.bbox = {
                "x": node["box"].get("x"),
                "y": node["box"].get("y"),
                "width": node["box"].get("width"),
                "height": node["box"].get("height"),
            }

        box = node.get("box") or node.get("absoluteBoundingBox")
        absolute_box = node.get("absoluteBoundingBox") or box
        self._apply_size(tw_node, box, node)
        self._apply_layout(tw_node, node)
        self._apply_position(tw_node, node, parent_box)
        self._apply_fills(tw_node, node)
        self._apply_strokes(tw_node, node)
        self._apply_effects(tw_node, node)
        self._apply_radius(tw_node, node)
        self._apply_opacity(tw_node, node)
        self._apply_blend_mode(tw_node, node)
        self._apply_mask(tw_node, node)
        self._apply_boolean(tw_node, node)
        self._apply_backend_hints(tw_node, node)
        self._apply_component_refs(tw_node, node)
        if node.get("clipContent"):
            tw_node.add_class("overflow-hidden")

        if not tw_node.component_ref:
            layout_mode = node.get("layoutMode")
            for child in node.get("children", []):
                child_parent_box = absolute_box if absolute_box else box
                converted = self._convert_node(
                    child,
                    parent_box=child_parent_box,
                    depth=depth + 1,
                    parent_layout_mode=layout_mode,
                    data_context=data_context,
                )
                if converted:
                    tw_node.children.append(converted)

        return tw_node

    def _semantic_tag(self, node: Dict[str, Any], depth: int) -> str:
        name_lower = (node.get("name") or "").lower()
        name_words = set(re.split(r"[^\w]+", name_lower))
        node_type = node.get("type", "")

        if depth == 0:
            return "section"
        if any(k in name_lower for k in ("form", "contact", "lead", "signup", "subscribe", "login")):
            return "form"
        if node_type in ("COMPONENT", "INSTANCE") and "button" in name_words:
            return "button"
        if "image" in name_words or node.get("isAsset"):
            return "div"
        if "nav" in name_words or "navbar" in name_words:
            return "header"
        if "footer" in name_words:
            return "footer"
        if "article" in name_words or "card" in name_words:
            return "article"
        if "section" in name_words:
            return "section"
        if "hero" in name_words and "section" in name_words and depth <= 1:
            return "header"
        if "header" in name_words and "section" in name_words and depth <= 1:
            return "header"
        if name_words == {"hero"} and depth <= 1:
            return "header"
        return "div"

    def _convert_text(
        self,
        node: Dict[str, Any],
        parent_layout_mode: Optional[str] = None,
        data_context: Optional[Dict[str, Any]] = None,
    ) -> TailwindNode:
        characters = node.get("characters", "")
        tw_node = TailwindNode(
            tag=self._text_tag(node),
            text=characters,
            figma_id=node.get("id"),
            figma_name=_safe_name(node.get("name")),
        )
        box = node.get("box") or node.get("absoluteBoundingBox")
        self._apply_size(tw_node, box, node)
        self._apply_text_snug_fit(tw_node, node, box, parent_layout_mode=parent_layout_mode)
        style = node.get("style", {})
        self._apply_text_style(tw_node, style, node)
        self._apply_position(tw_node, node, None)
        self._apply_backend_hints(tw_node, node)

        override_table = node.get("styleOverrideTable") or {}
        char_overrides = node.get("characterStyleOverrides") or []
        if override_table and char_overrides and any(o for o in char_overrides):
            tw_node.rich_text = self._build_rich_text(characters, char_overrides, override_table, style)

        if data_context:
            role = _infer_data_role(node)
            field = data_context["field_map"].get(role, role)
            tw_node.data_binding = {"model": data_context["model"], "field": field, "item": True}
            tw_node.text = None
            tw_node.rich_text = None

        return tw_node

    def _apply_text_snug_fit(
        self,
        tw_node: TailwindNode,
        node: Dict[str, Any],
        box: Optional[Dict[str, Any]],
        parent_layout_mode: Optional[str] = None,
    ) -> None:
        """Heuristic: if Figma text box is wider than its content, constrain width."""
        if not box:
            return
        auto_resize = node.get("textAutoResize") or "NONE"
        if auto_resize in ("WIDTH_AND_HEIGHT", "HEIGHT_AND_WIDTH", "WIDTH", "HEIGHT"):
            # Figma controls at least one dimension; don't clamp the width with max-w.
            return
        width = _px(box.get("width"))
        if not width or width <= 0:
            return
        text = (node.get("characters") or "").strip()
        if not text:
            return
        # crude single-line heuristic: no newlines and parent lays out horizontally
        is_horizontal = parent_layout_mode == "HORIZONTAL"
        has_newline = "\n" in text
        if is_horizontal and not has_newline:
            tw_node.add_class("whitespace-nowrap")
            # Ensure the text can shrink inside a flex container instead of overflowing.
            tw_node.add_class("min-w-0")
            return
        # otherwise cap max width to Figma bbox
        tw_node.add_class(f"max-w-[{int(round(width))}px]")
        tw_node.inline_styles["maxWidth"] = f"{int(round(width))}px"

    def _build_rich_text(
        self,
        characters: str,
        char_overrides: List[Any],
        override_table: Dict[str, Any],
        base_style: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Группирует символы по override-id и собирает span-описания."""
        base_classes = set(self._text_style_classes(base_style))

        raw_spans: List[Dict[str, Any]] = []
        i = 0
        n = len(characters)
        while i < n:
            override_id = char_overrides[i] if i < len(char_overrides) else ""
            j = i
            while j < n and j < len(char_overrides) and char_overrides[j] == override_id:
                j += 1
            if j == i:
                j = i + 1
            text = characters[i:j]
            override_style = override_table.get(str(override_id), {}) if override_id else {}
            merged_style = {**base_style, **override_style}
            classes = [c for c in self._text_style_classes(merged_style) if c not in base_classes]
            span: Dict[str, Any] = {"text": text, "classes": classes}
            hyperlink = merged_style.get("hyperlink")
            if hyperlink and hyperlink.get("type") == "URL":
                span["tag"] = "a"
                span["href"] = hyperlink.get("url", "#")
            raw_spans.append(span)
            i = j

        final_spans: List[Dict[str, Any]] = []
        for span in raw_spans:
            parts = span["text"].split("\n")
            common = {k: v for k, v in span.items() if k not in ("text", "newline_before")}
            for idx, part in enumerate(parts):
                newline_before = idx > 0
                if not part and not newline_before:
                    continue
                seg = {"text": part, "newline_before": newline_before, **common}
                final_spans.append(seg)
        return final_spans

    def _text_tag(self, node: Dict[str, Any]) -> str:
        name = (node.get("name") or "").lower()
        words = set(re.split(r"[^\w]+", name))
        if "h1" in words:
            return "h1"
        if "h2" in words:
            return "h2"
        if "h3" in words:
            return "h3"
        if "headline" in words:
            return "h1"
        if "card" in words and "title" in words:
            return "h3"
        if "subtitle" in words or "description" in words or "body" in words:
            return "p"
        if "title" in words:
            return "h2"
        if "button" in words or node.get("type") == "COMPONENT":
            return "span"
        return "p"

    def _resolve_asset(self, ref: str) -> Optional[Dict[str, Any]]:
        if not self.assets:
            return None
        return self.assets.get("assets", {}).get(ref)

    def _convert_asset(
        self,
        node: Dict[str, Any],
        data_context: Optional[Dict[str, Any]] = None,
    ) -> TailwindNode:
        node_id = node.get("id", "")
        ref = node.get("imageRef") or node_id
        resolved = self._resolve_asset(ref)

        tw_node = TailwindNode(
            tag="img",
            src=resolved.get("publicPath") if resolved else node.get("publicPath") or ref,
            alt=_safe_name(node.get("name")),
            figma_id=node_id,
            figma_name=_safe_name(node.get("name")),
        )
        if resolved:
            tw_node.asset_type = resolved.get("type", "raster")
            tw_node.asset_width = resolved.get("width")
            tw_node.asset_height = resolved.get("height")
            if resolved.get("type") == "svg" and resolved.get("inlineSvg"):
                tw_node.inline_svg = resolved.get("inlineSvg")

        box = node.get("box") or node.get("absoluteBoundingBox")
        self._apply_size(tw_node, box, node)
        self._apply_position(tw_node, node, None)
        self._apply_backend_hints(tw_node, node)

        if data_context:
            field = data_context["field_map"].get("imageUrl", "imageUrl")
            tw_node.data_binding = {"model": data_context["model"], "field": field, "item": True}
            alt_field = data_context["field_map"].get("imageAlt")
            if alt_field:
                tw_node.alt_binding = {"model": data_context["model"], "field": alt_field, "item": True}
            tw_node.src = None
            tw_node.inline_svg = None

        return tw_node

    def _convert_shape(self, node: Dict[str, Any]) -> TailwindNode:
        tw_node = TailwindNode(
            tag="div",
            figma_id=node.get("id"),
            figma_name=_safe_name(node.get("name")),
        )
        box = node.get("box") or node.get("absoluteBoundingBox")
        self._apply_size(tw_node, box, node)
        self._apply_position(tw_node, node, None)
        self._apply_fills(tw_node, node)
        self._apply_strokes(tw_node, node)
        self._apply_effects(tw_node, node)
        self._apply_radius(tw_node, node)
        self._apply_backend_hints(tw_node, node)
        return tw_node

    def _apply_size(
        self,
        tw_node: TailwindNode,
        box: Optional[Dict[str, Any]],
        node: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not box:
            return

        constraints = (node.get("constraints") or {}) if node else {}
        lsh = node.get("layoutSizingHorizontal") if node else None
        lsv = node.get("layoutSizingVertical") if node else None

        # Width behavior
        width_behavior = "fixed"
        if lsh == "FILL" or constraints.get("horizontal") in ("STRETCH", "LEFT_RIGHT"):
            width_behavior = "full"
        elif lsh == "HUG":
            width_behavior = "auto"
        elif node and node.get("layoutGrow") == 1:
            width_behavior = "grow"

        # Height behavior
        height_behavior = "fixed"
        if lsv == "FILL" or constraints.get("vertical") in ("STRETCH", "TOP_BOTTOM"):
            height_behavior = "full"
        elif lsv == "HUG":
            height_behavior = "auto"

        # Text auto-resize overrides fixed sizing so the DOM owns text dimensions.
        if node and node.get("type") == "TEXT":
            auto_resize = node.get("textAutoResize") or "NONE"
            if auto_resize in ("WIDTH_AND_HEIGHT", "HEIGHT_AND_WIDTH"):
                width_behavior = "auto"
                height_behavior = "auto"
            elif auto_resize == "HEIGHT":
                height_behavior = "auto"
            elif auto_resize == "WIDTH":
                width_behavior = "auto"

        if width_behavior == "full":
            tw_node.add_class("w-full")
        elif width_behavior == "auto":
            tw_node.add_class("w-auto")
        elif width_behavior == "grow":
            tw_node.add_class("flex-1")

        if height_behavior == "full":
            tw_node.add_class("h-full")
        elif height_behavior == "auto":
            tw_node.add_class("h-auto")

        if node and node.get("layoutAlign") == "STRETCH":
            tw_node.add_class("self-stretch")

        width = _px(box.get("width"))
        height = _px(box.get("height"))

        skip_fixed_width = width_behavior in ("full", "auto", "grow")
        skip_fixed_height = height_behavior in ("full", "auto")

        if node and self.config.get("skip_fixed_size_when_auto", True):
            primary_axis = node.get("primaryAxisSizingMode")
            counter_axis = node.get("counterAxisSizingMode")
            if primary_axis == "AUTO":
                skip_fixed_width = True
            if counter_axis == "AUTO":
                skip_fixed_height = True

        if width is not None and width > 0 and not skip_fixed_width:
            tw_node.add_class(_arbitrary("w", int(round(width))))
        if height is not None and height > 0 and not skip_fixed_height:
            tw_node.add_class(_arbitrary("h", int(round(height))))

        if node:
            min_w = _px(node.get("minWidth"))
            max_w = _px(node.get("maxWidth"))
            min_h = _px(node.get("minHeight"))
            max_h = _px(node.get("maxHeight"))
            if min_w is not None and min_w > 0:
                tw_node.add_class(_arbitrary("min-w", int(round(min_w))))
            if max_w is not None and max_w > 0:
                tw_node.add_class(_arbitrary("max-w", int(round(max_w))))
            if min_h is not None and min_h > 0:
                tw_node.add_class(_arbitrary("min-h", int(round(min_h))))
            if max_h is not None and max_h > 0:
                tw_node.add_class(_arbitrary("max-h", int(round(max_h))))

    def _apply_layout(self, tw_node: TailwindNode, node: Dict[str, Any]) -> None:
        layout_mode = node.get("layoutMode")
        if not layout_mode:
            return

        is_wrap = node.get("layoutWrap") == "WRAP"
        use_grid = self.config.get("grid_for_wrap") and is_wrap
        if use_grid:
            tw_node.add_class("grid")
            cols = node.get("counterAxisCount") or self.config.get("grid_wrap_columns", 2)
            tw_node.add_class(f"grid-cols-{cols}")
        else:
            tw_node.add_class("flex")
            if layout_mode == "VERTICAL":
                tw_node.add_class("flex-col")
            else:
                tw_node.add_class("flex-row")
            if is_wrap:
                tw_node.add_class("flex-wrap")

        spacing_mode = node.get("spacingMode")
        spacing = _px(node.get("itemSpacing"))
        if spacing_mode == "SPACE_BETWEEN":
            tw_node.add_class("justify-between")
        else:
            if spacing is not None and spacing > 0:
                tw_node.add_class(_arbitrary("gap", int(round(spacing))))
            elif spacing is not None and spacing == 0:
                tw_node.add_class("gap-0")

            primary = node.get("primaryAxisAlignItems")
            justify_map = {
                "MIN": "justify-start",
                "CENTER": "justify-center",
                "MAX": "justify-end",
                "SPACE_BETWEEN": "justify-between",
            }
            if primary in justify_map:
                tw_node.add_class(justify_map[primary])

        counter = node.get("counterAxisAlignItems")
        if counter == "SPACE_BETWEEN":
            tw_node.add_class("content-between")
            if not is_wrap:
                tw_node.add_class("flex-wrap")
        else:
            items_map = {
                "MIN": "items-start",
                "CENTER": "items-center",
                "MAX": "items-end",
                "BASELINE": "items-baseline",
                "STRETCH": "items-stretch",
            }
            if counter in items_map:
                tw_node.add_class(items_map[counter])

        self._apply_padding(tw_node, node)

    def _apply_padding(self, tw_node: TailwindNode, node: Dict[str, Any]) -> None:
        top = _px(node.get("paddingTop", 0)) or 0
        right = _px(node.get("paddingRight", 0)) or 0
        bottom = _px(node.get("paddingBottom", 0)) or 0
        left = _px(node.get("paddingLeft", 0)) or 0

        if top == right == bottom == left:
            if top > 0:
                tw_node.add_class(_arbitrary("p", int(round(top))))
            return

        if top == bottom and left == right:
            if top > 0:
                tw_node.add_class(_arbitrary("py", int(round(top))))
            if left > 0:
                tw_node.add_class(_arbitrary("px", int(round(left))))
            return

        if top > 0:
            tw_node.add_class(_arbitrary("pt", int(round(top))))
        if right > 0:
            tw_node.add_class(_arbitrary("pr", int(round(right))))
        if bottom > 0:
            tw_node.add_class(_arbitrary("pb", int(round(bottom))))
        if left > 0:
            tw_node.add_class(_arbitrary("pl", int(round(left))))

    def _apply_position(
        self,
        tw_node: TailwindNode,
        node: Dict[str, Any],
        parent_box: Optional[Dict[str, Any]],
    ) -> None:
        node_type = node.get("type")
        if node_type == "TEXT":
            return

        positioning = node.get("layoutPositioning")
        constraints = node.get("constraints") or {}
        is_absolute = positioning == "ABSOLUTE"
        has_fixed_constraints = bool(
            constraints.get("horizontal") or constraints.get("vertical")
        )
        is_non_autolayout_child = not node.get("layoutMode") and not is_absolute

        if is_absolute:
            pass
        elif node.get("layoutMode"):
            return
        elif not has_fixed_constraints and not is_non_autolayout_child:
            return

        box = node.get("box") or node.get("absoluteBoundingBox")
        if not box or not parent_box:
            if is_absolute or has_fixed_constraints:
                tw_node.add_class("absolute")
            return

        parent_x = _px(parent_box.get("x")) or 0
        parent_y = _px(parent_box.get("y")) or 0
        parent_w = _px(parent_box.get("width")) or 0
        parent_h = _px(parent_box.get("height")) or 0
        x = _px(box.get("x")) or 0
        y = _px(box.get("y")) or 0
        w = _px(box.get("width")) or 0
        h = _px(box.get("height")) or 0

        rel_x = int(round(x - parent_x))
        rel_y = int(round(y - parent_y))

        tw_node.add_class("absolute")

        horizontal = constraints.get("horizontal")
        vertical = constraints.get("vertical")

        if horizontal == "LEFT":
            tw_node.inline_styles["left"] = f"{rel_x}px"
        elif horizontal == "RIGHT":
            tw_node.inline_styles["right"] = f"{int(round(parent_w - rel_x - w))}px"
        elif horizontal == "LEFT_RIGHT":
            tw_node.inline_styles["left"] = f"{rel_x}px"
            tw_node.inline_styles["right"] = f"{int(round(parent_w - rel_x - w))}px"
        elif horizontal == "CENTER":
            offset = int(round(x - parent_x - parent_w / 2 + w / 2))
            tw_node.inline_styles["left"] = f"calc(50% + {offset}px)"
        elif horizontal == "SCALE":
            left_pct = (rel_x / parent_w * 100) if parent_w else 0
            right_pct = ((parent_w - rel_x - w) / parent_w * 100) if parent_w else 0
            width_pct = (w / parent_w * 100) if parent_w else 0
            tw_node.inline_styles["left"] = f"{left_pct:.2f}%"
            tw_node.inline_styles["right"] = f"{right_pct:.2f}%"
            tw_node.inline_styles["width"] = f"{width_pct:.2f}%"

        if vertical == "TOP":
            tw_node.inline_styles["top"] = f"{rel_y}px"
        elif vertical == "BOTTOM":
            tw_node.inline_styles["bottom"] = f"{int(round(parent_h - rel_y - h))}px"
        elif vertical == "TOP_BOTTOM":
            tw_node.inline_styles["top"] = f"{rel_y}px"
            tw_node.inline_styles["bottom"] = f"{int(round(parent_h - rel_y - h))}px"
        elif vertical == "CENTER":
            offset = int(round(y - parent_y - parent_h / 2 + h / 2))
            tw_node.inline_styles["top"] = f"calc(50% + {offset}px)"
        elif vertical == "SCALE":
            top_pct = (rel_y / parent_h * 100) if parent_h else 0
            bottom_pct = ((parent_h - rel_y - h) / parent_h * 100) if parent_h else 0
            height_pct = (h / parent_h * 100) if parent_h else 0
            tw_node.inline_styles["top"] = f"{top_pct:.2f}%"
            tw_node.inline_styles["bottom"] = f"{bottom_pct:.2f}%"
            tw_node.inline_styles["height"] = f"{height_pct:.2f}%"

        if not horizontal and not vertical:
            tw_node.inline_styles["left"] = f"{rel_x}px"
            tw_node.inline_styles["top"] = f"{rel_y}px"


    def _apply_fills(self, tw_node: TailwindNode, node: Dict[str, Any]) -> None:
        fills = node.get("fills") or []
        for fill in fills:
            fill_type = fill.get("type")
            if fill_type == "SOLID":
                hex_color = fill.get("hex") or _color_to_hex(fill.get("color"))
                if _has_alpha(hex_color):
                    rgba = _hex_to_rgba(hex_color)
                    if rgba:
                        tw_node.inline_styles["backgroundColor"] = rgba
                else:
                    cls = self._class_for_color("bg", hex_color, node, "fill")
                    if cls:
                        tw_node.add_class(cls)
                opacity = fill.get("opacity")
                if opacity is not None and opacity < 1.0:
                    tw_node.inline_styles["opacity"] = str(opacity)
            elif fill_type == "GRADIENT_LINEAR":
                stops = fill.get("stops") or fill.get("gradientStops", [])
                if stops:
                    gradient = self._build_gradient(stops)
                    tw_node.inline_styles["background"] = gradient
            elif fill_type == "IMAGE":
                ref = fill.get("imageRef", "")
                resolved = self._resolve_asset(ref) if ref else None
                public_path = resolved.get("publicPath") if resolved else ref
                tw_node.inline_styles["background-image"] = f"url('{public_path}')"
                tw_node.inline_styles["background-size"] = "cover"

    def _build_gradient(self, stops: List[Dict[str, Any]]) -> str:
        parts = []
        for stop in stops:
            color = stop.get("hex") or stop.get("rgb") or _color_to_hex(stop.get("color")) or "transparent"
            pos = stop.get("position", 0)
            parts.append(f"{color} {int(round(pos * 100))}%")
        return f"linear-gradient(180deg, {', '.join(parts)})"

    def _apply_strokes(self, tw_node: TailwindNode, node: Dict[str, Any]) -> None:
        strokes = node.get("strokes") or []
        if not strokes:
            return
        for stroke in strokes:
            if stroke.get("type") == "SOLID":
                hex_color = stroke.get("hex") or _color_to_hex(stroke.get("color"))
                cls = self._class_for_color("border", hex_color, node, "stroke")
                if cls:
                    tw_node.add_class(cls)
                width = _px(node.get("strokeWeight", 1))
                if width is not None and width > 0:
                    tw_node.add_class(_arbitrary("border", int(round(width))))
                break

    def _apply_effects(self, tw_node: TailwindNode, node: Dict[str, Any]) -> None:
        effects = node.get("effects") or []
        shadows: List[str] = []
        filters: List[str] = []
        for effect in effects:
            e_type = effect.get("type")
            if e_type in ("DROP_SHADOW", "INNER_SHADOW"):
                color = (
                    effect.get("hex")
                    or effect.get("rgb")
                    or _color_to_hex(effect.get("color"))
                    or "rgba(0,0,0,0.25)"
                )
                offset = effect.get("offset", {"x": 0, "y": 0})
                radius = effect.get("radius", 0)
                spread = _px(effect.get("spread")) or 0
                x = int(round(offset.get("x", 0)))
                y = int(round(offset.get("y", 0)))
                inset = "inset " if e_type == "INNER_SHADOW" else ""
                shadows.append(
                    f"{inset}{x}px {y}px {int(round(radius))}px {int(round(spread))}px {color}"
                )
                if e_type == "INNER_SHADOW":
                    tw_node.add_class("isolate")
            elif e_type == "LAYER_BLUR":
                filters.append(f"blur({int(round(effect.get("radius", 0)))}px)")
            elif e_type == "BACKGROUND_BLUR":
                tw_node.inline_styles["backdrop-filter"] = f"blur({int(round(effect.get("radius", 0)))}px)"

        if shadows:
            tw_node.inline_styles["box-shadow"] = ", ".join(shadows)
        if filters:
            tw_node.inline_styles["filter"] = " ".join(filters)

    def _apply_opacity(self, tw_node: TailwindNode, node: Dict[str, Any]) -> None:
        opacity = node.get("opacity")
        if opacity is not None and opacity < 1.0:
            tw_node.inline_styles["opacity"] = str(opacity)

    def _apply_blend_mode(self, tw_node: TailwindNode, node: Dict[str, Any]) -> None:
        blend = node.get("blendMode")
        if not blend:
            return
        css_blend = blend.lower().replace("_", "-")
        tw_node.inline_styles["mix-blend-mode"] = css_blend

    def _apply_mask(self, tw_node: TailwindNode, node: Dict[str, Any]) -> None:
        if node.get("isMask") or node.get("maskType"):
            tw_node.add_class("overflow-hidden")
            mask_type = node.get("maskType") or "ALPHA"
            if mask_type == "VECTOR":
                tw_node.inline_styles["clip-path"] = "inset(0 0 0 0)"
            else:
                tw_node.inline_styles["mask-image"] = "linear-gradient(#000 0 0)"

    def _apply_boolean(self, tw_node: TailwindNode, node: Dict[str, Any]) -> None:
        op = node.get("booleanOperation")
        if op and op in ("UNION", "SUBTRACT", "INTERSECT", "EXCLUDE"):
            tw_node.inline_styles["clip-rule"] = op.lower()

    def _apply_radius(self, tw_node: TailwindNode, node: Dict[str, Any]) -> None:
        radius = _px(node.get("cornerRadius"))
        if radius is None or radius <= 0:
            return
        rounded = int(round(radius))
        scale = {
            2: "rounded-sm",
            4: "rounded",
            6: "rounded-md",
            8: "rounded-lg",
            12: "rounded-xl",
            16: "rounded-2xl",
            24: "rounded-3xl",
            9999: "rounded-full",
        }
        if rounded in scale:
            tw_node.add_class(scale[rounded])
        else:
            tw_node.add_class(_arbitrary("rounded", rounded))

    def _apply_component_refs(self, tw_node: TailwindNode, node: Dict[str, Any]) -> None:
        node_type = node.get("type")
        set_id = node.get("componentSetId")
        comp_id = node.get("componentId")
        tw_node.component_set_id = set_id
        tw_node.component_id = comp_id
        if node_type in ("COMPONENT", "COMPONENT_SET"):
            tw_node.component_context = node.get("name")
        if self.component_registry and node_type == "INSTANCE":
            entry = self.component_registry.lookup_by_instance(node)
            if entry:
                tw_node.component_ref = entry.get("pascal_name")
                tw_node.figma_component_key = entry.get("figma_component_key")
                tw_node.is_instance = True
                tw_node.variant_props = node.get("variantProperties") or {}
                tw_node.overrides = node.get("overrides") or []
                if self.component_mapper:
                    mapping = self.component_mapper.get("mappings", {}).get(entry.get("id"))
                    if mapping:
                        reg_mod = _import_component_registry()
                        tw_node.component_ref = mapping.get("react_component", {}).get("export_name", tw_node.component_ref)
                        tw_node.figma_component_key = mapping.get("figma_component_key", tw_node.figma_component_key)
                        tw_node.variant_props = reg_mod.ComponentMapper.props_for_instance(mapping, tw_node.variant_props)
                        tw_node.is_instance = True

    def _apply_backend_hints(self, tw_node: TailwindNode, node: Dict[str, Any]) -> None:
        node_id = node.get("id")
        if not node_id:
            return
        if node_id in self._form_by_node_id:
            m = self._form_by_node_id[node_id]
            tw_node.backend_action = m.get("action")
            tw_node.backend_endpoint = m.get("endpoint")
            tw_node.backend_model = m.get("model")
        if node_id in self._field_by_node_id:
            fm = self._field_by_node_id[node_id]
            tw_node.backend_field = fm.get("field")
            tw_node.input_type = fm.get("type", "text")
            tw_node.required = fm.get("required", True)
            if "min_length" in fm:
                tw_node.min_length = fm["min_length"]
            if "max_length" in fm:
                tw_node.max_length = fm["max_length"]
            if "min_value" in fm:
                tw_node.min_value = fm["min_value"]
            if "max_value" in fm:
                tw_node.max_value = fm["max_value"]
            if "pattern" in fm:
                tw_node.pattern = fm["pattern"]
            if "enum_values" in fm:
                tw_node.enum_values = list(fm["enum_values"])
            self._refine_input_type(tw_node, node)

    def _refine_input_type(self, tw_node: TailwindNode, node: Dict[str, Any]) -> None:
        name_lower = (node.get("name") or "").lower()
        if tw_node.input_type == "text" and any(k in name_lower for k in ("message", "comment", "bio", "description")):
            tw_node.input_type = "textarea"
        if tw_node.enum_values or any(k in name_lower for k in ("select", "country", "role", "status")):
            tw_node.input_type = "select"

    def _text_style_classes(self, style: Dict[str, Any], node: Optional[Dict[str, Any]] = None) -> List[str]:
        """Возвращает Tailwind-классы для Figma TypeStyle (без side-эффектов)."""
        classes: List[str] = []
        font_size = _px(style.get("fontSize"))
        if font_size is not None and font_size > 0:
            classes.append(self._font_size_class(font_size))

        weight = style.get("fontWeight")
        if weight is not None:
            classes.append(self._font_weight_class(int(weight)))

        family = style.get("fontFamily")
        if family:
            classes.append(self._font_class(family))

        align = style.get("textAlignHorizontal")
        align_map = {
            "LEFT": "text-left",
            "CENTER": "text-center",
            "RIGHT": "text-right",
            "JUSTIFIED": "text-justify",
        }
        if align in align_map:
            classes.append(align_map[align])

        line_height_px = _px(style.get("lineHeightPx"))
        if line_height_px is not None and font_size:
            ratio = round(line_height_px / font_size, 3)
            classes.append(self._line_height_class(ratio))

        letter_spacing = _px(style.get("letterSpacing"))
        if letter_spacing is not None:
            classes.append(_arbitrary("tracking", int(round(letter_spacing))))

        fills = style.get("fills") or []
        for fill in fills:
            if fill.get("type") == "SOLID":
                hex_color = fill.get("hex") or _color_to_hex(fill.get("color"))
                cls = self._class_for_color("text", hex_color, node, "text")
                if cls:
                    classes.append(cls)
                break

        if style.get("italic"):
            classes.append("italic")

        case = style.get("textCase")
        case_map = {
            "UPPER": "uppercase",
            "LOWER": "lowercase",
            "TITLE": "capitalize",
        }
        if case in case_map:
            classes.append(case_map[case])

        decoration = style.get("textDecoration")
        decoration_map = {
            "UNDERLINE": "underline",
            "STRIKETHROUGH": "line-through",
        }
        if decoration in decoration_map:
            classes.append(decoration_map[decoration])

        return classes

    def _apply_text_style(self, tw_node: TailwindNode, style: Dict[str, Any], node: Optional[Dict[str, Any]] = None) -> None:
        for cls in self._text_style_classes(style, node):
            tw_node.add_class(cls)


def convert_figma_node(node: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> LayoutResult:
    engine = FigmaLayoutEngine(config)
    return engine.convert(node)


def _load_tokens(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description="Layout Engine: Figma JSON → Tailwind AST")
    parser.add_argument(
        "--file",
        default="figma_node.json",
        help="Путь к JSON-файлу Figma-структуры.",
    )
    parser.add_argument(
        "--node-id",
        default=None,
        help="ID конкретной ноды (пример: 662:808).",
    )
    parser.add_argument(
        "--output",
        default="layout_ast.json",
        help="Путь для сохранения AST.",
    )
    parser.add_argument(
        "--tokens",
        default="design_tokens.json",
        help="Путь к JSON-реестру дизайн-токенов (опционально).",
    )
    parser.add_argument(
        "--assets",
        default="asset_registry.json",
        help="Путь к JSON-реестру ассетов (опционально).",
    )
    parser.add_argument(
        "--backend-mapping",
        default="backend_mapping.json",
        help="Путь к backend_mapping.json (опционально).",
    )
    parser.add_argument(
        "--components",
        default="component_registry.json",
        help="Путь к component_registry.json (опционально).",
    )
    parser.add_argument(
        "--components-mapper",
        default="figma_component_map.json",
        help="Путь к figma_component_map.json (опционально).",
    )
    parser.add_argument(
        "--data-models",
        default=None,
        help="Путь к data_model.json для привязки повторяющихся структур к данным (опционально).",
    )
    parser.add_argument(
        "--components-mapper-override",
        default=".agent_loop/figma_overrides.json",
        help="Path to manual component mapping override file.",
    )
    args = parser.parse_args()

    import analyzer

    data = analyzer.load_figma_json(args.file)
    if not data:
        print(f"[ERROR] Could not load {args.file}")
        return

    node = data
    if args.node_id:
        target = analyzer.find_node_by_id(data, args.node_id)
        if not target:
            print(f"[ERROR] Node {args.node_id} not found in {args.file}")
            return
        node = target

    tokens = _load_tokens(args.tokens)
    assets = _load_tokens(args.assets)
    backend_mapping = _load_tokens(args.backend_mapping)
    config: Dict[str, Any] = {}
    if tokens:
        config["tokens"] = tokens
    if assets:
        config["assets"] = assets
    if backend_mapping:
        config["backend_mapping"] = backend_mapping
    if args.components:
        config["component_registry"] = args.components
    mapper_path = Path(args.components_mapper) if args.components_mapper else None
    if mapper_path and not mapper_path.exists():
        fallback = Path("figma_component_mappings.json")
        if fallback.exists():
            mapper_path = fallback
    if mapper_path and mapper_path.exists():
        config["component_mapper"] = str(mapper_path)
    override_path = Path(args.components_mapper_override)
    if override_path.exists():
        config["component_mapper_override"] = str(override_path)
    if args.data_models and Path(args.data_models).exists():
        config["data_models"] = str(Path(args.data_models).resolve())
    result = convert_figma_node(node, config=config)
    output_path = Path(args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
    print(f"[LAYOUT] AST saved to {output_path}")


if __name__ == "__main__":
    main()
