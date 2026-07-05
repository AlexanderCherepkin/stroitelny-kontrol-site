"""Interactive Layer Mapper — translates Figma prototype reactions and variants
into React interactivity: onClick, hover, overlays, page transitions, variants.

Reads:
  - figma_node.json (raw Figma nodes with `reactions` and `variantProperties`)
  - page_ast.json or layout_ast.json (Tailwind AST produced by layout_engine)
  - backend_mapping.json (optional, to wire form actions)

Writes:
  - interactive_ast.json — AST annotated with interaction metadata
  - interactive_registry.json — registry of handlers, state keys, routes
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


OUTPUT_AST = "interactive_ast.json"
OUTPUT_REGISTRY = "interactive_registry.json"


def _safe_name(name: str) -> str:
    return re.sub(r"[^\w]", "_", name or "unnamed").strip("_") or "unnamed"


def _camel_case(name: str) -> str:
    parts = _safe_name(name).split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _pascal_case(name: str) -> str:
    parts = _safe_name(name).split("_")
    return "".join(p.capitalize() for p in parts)


def _extract_reaction_type(reaction: Dict[str, Any]) -> str:
    action = reaction.get("action", {})
    return action.get("type", "UNKNOWN")


def _extract_navigation_info(reaction: Dict[str, Any], nodes_by_id: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    action = reaction.get("action", {})
    if action.get("type") != "NODE":
        return None
    destination_id = action.get("destinationId")
    if not destination_id:
        return None
    destination = nodes_by_id.get(destination_id, {})
    page_name = _safe_name(destination.get("name") or "Page")
    return {
        "type": "navigate",
        "destination_id": destination_id,
        "destination_name": page_name,
        "route": f"/{page_name.lower()}",
        "transition": action.get("navigationType", "NAVIGATE"),
    }


def _extract_overlay_info(reaction: Dict[str, Any], nodes_by_id: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    action = reaction.get("action", {})
    if action.get("type") != "OVERLAY":
        return None
    destination_id = action.get("destinationId")
    if not destination_id:
        return None
    destination = nodes_by_id.get(destination_id, {})
    return {
        "type": "overlay",
        "destination_id": destination_id,
        "destination_name": _safe_name(destination.get("name") or "Overlay"),
        "overlay_position": action.get("overlayPositionType", "CENTER"),
    }


def _extract_url_info(reaction: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    action = reaction.get("action", {})
    if action.get("type") != "URL":
        return None
    url = action.get("url", "")
    external = bool(url and (url.startswith("http://") or url.startswith("https://")))
    return {
        "type": "url",
        "url": url,
        "external": external,
    }


def _extract_variant_switch_info(reaction: Dict[str, Any], node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    action = reaction.get("action", {})
    if action.get("type") != "SWAP_VARIANT" and "variantProperties" not in node:
        return None
    return {
        "type": "variant",
        "variant_properties": node.get("variantProperties", {}),
    }


def _build_interaction(node: Dict[str, Any], nodes_by_id: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    reactions = node.get("reactions")
    if not reactions:
        return None

    triggers: List[Dict[str, Any]] = []
    for reaction in reactions:
        trigger = reaction.get("trigger", {})
        trigger_type = trigger.get("type", "ON_CLICK")
        info = (
            _extract_navigation_info(reaction, nodes_by_id)
            or _extract_overlay_info(reaction, nodes_by_id)
            or _extract_url_info(reaction)
            or _extract_variant_switch_info(reaction, node)
        )
        if info:
            triggers.append({"event": trigger_type.lower(), **info})

    if not triggers:
        return None

    node_id = node.get("id", "")
    name = _safe_name(node.get("name") or f"node_{node_id}")
    return {
        "figma_id": node_id,
        "name": name,
        "component_name": _pascal_case(name),
        "state_key": _camel_case(name) + "State",
        "triggers": triggers,
        "needs_client": True,
    }


def _index_nodes(root: Dict[str, Any]) -> Dict[str, Any]:
    by_id: Dict[str, Any] = {}

    def walk(n: Any) -> None:
        if not isinstance(n, dict):
            return
        if n.get("id"):
            by_id[n["id"]] = n
        for child in n.get("children", []):
            walk(child)

    walk(root)
    return by_id


def _find_matching_ast_node(ast: Dict[str, Any], figma_id: str) -> Optional[Dict[str, Any]]:
    if ast.get("figma_id") == figma_id:
        return ast
    for child in ast.get("children", []):
        found = _find_matching_ast_node(child, figma_id)
        if found:
            return found
    return None


def _attach_interactions(ast: Dict[str, Any], interactions: List[Dict[str, Any]]) -> None:
    for interaction in interactions:
        target = _find_matching_ast_node(ast, interaction["figma_id"])
        if target is None:
            continue
        target["interactive"] = {
            "state_key": interaction["state_key"],
            "component_name": interaction["component_name"],
            "needs_client": interaction["needs_client"],
            "triggers": interaction["triggers"],
        }


def _collect_routes(registry: List[Dict[str, Any]]) -> List[str]:
    routes: set = set()
    for entry in registry:
        for trigger in entry.get("triggers", []):
            if trigger.get("type") == "navigate":
                routes.add(trigger.get("route", "/"))
    return sorted(routes)


def map_interactions(
    figma_node: Dict[str, Any],
    ast: Dict[str, Any],
) -> Dict[str, Any]:
    nodes_by_id = _index_nodes(figma_node)
    interactions: List[Dict[str, Any]] = []

    def walk(n: Any) -> None:
        if not isinstance(n, dict):
            return
        interaction = _build_interaction(n, nodes_by_id)
        if interaction:
            interactions.append(interaction)
        for child in n.get("children", []):
            walk(child)

    walk(figma_node)

    _attach_interactions(ast, interactions)

    registry = {
        "interactions": interactions,
        "client_component_ids": [i["figma_id"] for i in interactions],
        "state_keys": [i["state_key"] for i in interactions],
        "routes": _collect_routes(interactions),
    }
    return {"ast": ast, "registry": registry}


def run_mapping(
    figma_file: str = "figma_node.json",
    ast_file: str = "page_ast.json",
    ast_output: str = OUTPUT_AST,
    registry_output: str = OUTPUT_REGISTRY,
) -> Dict[str, Any]:
    figma_path = Path(figma_file)
    ast_path = Path(ast_file)
    if not figma_path.exists():
        raise FileNotFoundError(f"Figma node file not found: {figma_file}")
    if not ast_path.exists():
        raise FileNotFoundError(f"AST file not found: {ast_file}")

    with figma_path.open("r", encoding="utf-8") as f:
        figma_node = json.load(f)
    with ast_path.open("r", encoding="utf-8") as f:
        ast = json.load(f)

    result = map_interactions(figma_node, ast)

    out_dir = Path(ast_output).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(ast_output, "w", encoding="utf-8") as f:
        json.dump(result["ast"], f, ensure_ascii=False, indent=2)
    with open(registry_output, "w", encoding="utf-8") as f:
        json.dump(result["registry"], f, ensure_ascii=False, indent=2)

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Map Figma prototype interactions to React interactivity")
    parser.add_argument("--figma-file", default="figma_node.json")
    parser.add_argument("--ast", default="page_ast.json")
    parser.add_argument("--ast-output", default=OUTPUT_AST)
    parser.add_argument("--registry-output", default=OUTPUT_REGISTRY)
    args = parser.parse_args()

    try:
        run_mapping(
            figma_file=args.figma_file,
            ast_file=args.ast,
            ast_output=args.ast_output,
            registry_output=args.registry_output,
        )
        print(f"Interactive layer mapped: {args.ast_output}, {args.registry_output}")
        return 0
    except Exception as e:
        print(f"Interactive layer mapping failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
