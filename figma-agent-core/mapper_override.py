"""Manual override layer for Figma-to-local component mappings.

Provides persistent, human-curated overrides that take precedence over
automatic semantic/per-component mapper decisions. The override file is
intended to be committed in `.agent_loop/figma_overrides.json` or a
project-specific path.

Priority order (highest first):
1. manual override file (this module)
2. per-component `*.mapper.json` files
3. aggregate `figma_component_mappings.json`
4. semantic/name matching fallback
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


class MapperOverrideError(Exception):
    pass


@dataclass
class OverrideRule:
    figma_component_id: Optional[str] = None
    figma_component_key: Optional[str] = None
    figma_name: Optional[str] = None
    react_component: Dict[str, Any] = field(default_factory=dict)
    prop_mapping: Optional[Dict[str, str]] = None
    value_mapping: Optional[Dict[str, Dict[str, str]]] = None
    default_props: Optional[Dict[str, str]] = None
    disabled: bool = False
    reason: str = ""

    def matches(self, component_id: str, component_key: str, name: str) -> bool:
        if self.disabled:
            return False
        if self.figma_component_id and self.figma_component_id == component_id:
            return True
        if self.figma_component_key and self.figma_component_key == component_key:
            return True
        if self.figma_name:
            normalized = self.figma_name.lower().strip()
            if normalized == name.lower().strip():
                return True
        return False


@dataclass
class OverrideSet:
    version: str = "1.0"
    rules: List[OverrideRule] = field(default_factory=list)

    def get(self, component_id: str, component_key: str, name: str) -> Optional[OverrideRule]:
        for rule in self.rules:
            if rule.matches(component_id, component_key, name):
                return rule
        return None


def _load_optional(path: Optional[Path | str]) -> Optional[Path]:
    if path is None:
        return None
    p = Path(path)
    return p if p.exists() else None


def load_override_set(path: Optional[Path | str]) -> OverrideSet:
    file_path = _load_optional(path)
    if file_path is None:
        return OverrideSet()
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise MapperOverrideError(f"Invalid JSON in override file {file_path}: {e}") from e
    except Exception as e:
        raise MapperOverrideError(f"Cannot read override file {file_path}: {e}") from e

    rules: List[OverrideRule] = []
    for raw in data.get("rules", []):
        rules.append(
            OverrideRule(
                figma_component_id=raw.get("figma_component_id") or raw.get("figmaComponentId"),
                figma_component_key=raw.get("figma_component_key") or raw.get("figmaComponentKey"),
                figma_name=raw.get("figma_name") or raw.get("figmaName"),
                react_component=raw.get("react_component", {}),
                prop_mapping=raw.get("prop_mapping") or raw.get("propMapping"),
                value_mapping=raw.get("value_mapping") or raw.get("valueMapping"),
                default_props=raw.get("default_props") or raw.get("defaultProps"),
                disabled=raw.get("disabled", False),
                reason=raw.get("reason", ""),
            )
        )
    return OverrideSet(version=data.get("version", "1.0"), rules=rules)


def validate_override_set(override_set: OverrideSet, local_export_names: Optional[Set[str]] = None) -> List[str]:
    """Validate override rules and return a list of human-readable issues."""
    issues: List[str] = []
    seen: Set[str] = set()
    for idx, rule in enumerate(override_set.rules):
        keys = [
            rule.figma_component_id,
            rule.figma_component_key,
            rule.figma_name,
        ]
        if not any(keys):
            issues.append(f"Rule {idx}: no figma_component_id, figma_component_key, or figma_name.")
            continue
        identifier = rule.figma_component_id or rule.figma_component_key or rule.figma_name or f"rule-{idx}"
        if identifier in seen:
            issues.append(f"Rule {idx}: duplicate identifier '{identifier}'.")
        seen.add(identifier)
        react = rule.react_component
        export_name = react.get("export_name")
        if not export_name:
            issues.append(f"Rule {identifier}: missing react_component.export_name.")
        if local_export_names and export_name and export_name not in local_export_names:
            issues.append(f"Rule {identifier}: export_name '{export_name}' not found in local components.")
        if not react.get("import_path"):
            issues.append(f"Rule {identifier}: missing react_component.import_path.")
    return issues


def apply_override(mapping: Dict[str, Any], rule: OverrideRule) -> Dict[str, Any]:
    """Return a new mapping with manual override merged on top."""
    merged = dict(mapping)
    merged["action"] = "reuse"
    merged["react_component"] = dict(rule.react_component)
    if rule.prop_mapping is not None:
        merged["prop_mapping"] = dict(rule.prop_mapping)
        merged["variant_prop_map"] = dict(rule.prop_mapping)
    if rule.value_mapping is not None:
        merged["value_mapping"] = dict(rule.value_mapping)
    if rule.default_props is not None:
        merged["default_props"] = dict(rule.default_props)
    merged["manual_override"] = {
        "figma_component_id": rule.figma_component_id,
        "figma_component_key": rule.figma_component_key,
        "figma_name": rule.figma_name,
        "reason": rule.reason,
    }
    return merged


def merge_overrides_into_mapper(
    mapper: Dict[str, Any],
    override_set: OverrideSet,
    registry: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Merge manual overrides into an aggregate mapper keyed by figma_component_id."""
    merged: Dict[str, Any] = {
        "version": mapper.get("version", "1.0"),
        "mappings": dict(mapper.get("mappings", {})),
    }
    for eid, mapping in list(merged["mappings"].items()):
        entry = None
        if registry and "components" in registry:
            entry = registry["components"].get(eid)
        rule = override_set.get(
            eid,
            entry.get("figma_component_key", "") if entry else "",
            entry.get("name", "") if entry else mapping.get("figma_name", ""),
        )
        if rule:
            merged["mappings"][eid] = apply_override(mapping, rule)
    return merged


def save_override_set(path: Path | str, override_set: OverrideSet) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": override_set.version,
        "rules": [
            {
                "figma_component_id": r.figma_component_id,
                "figma_component_key": r.figma_component_key,
                "figma_name": r.figma_name,
                "react_component": r.react_component,
                "prop_mapping": r.prop_mapping,
                "value_mapping": r.value_mapping,
                "default_props": r.default_props,
                "disabled": r.disabled,
                "reason": r.reason,
            }
            for r in override_set.rules
        ],
    }
    file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def add_override(
    path: Path | str,
    figma_component_id: Optional[str] = None,
    figma_component_key: Optional[str] = None,
    figma_name: Optional[str] = None,
    react_component: Optional[Dict[str, Any]] = None,
    prop_mapping: Optional[Dict[str, str]] = None,
    value_mapping: Optional[Dict[str, Dict[str, str]]] = None,
    default_props: Optional[Dict[str, str]] = None,
    reason: str = "",
) -> OverrideSet:
    override_set = load_override_set(path)
    # Remove existing rule for the same identifier to avoid duplicates.
    identifiers = {figma_component_id, figma_component_key, figma_name}
    override_set.rules = [
        r
        for r in override_set.rules
        if not (
            (figma_component_id and r.figma_component_id == figma_component_id)
            or (figma_component_key and r.figma_component_key == figma_component_key)
            or (figma_name and r.figma_name and r.figma_name.lower() == figma_name.lower())
        )
    ]
    override_set.rules.append(
        OverrideRule(
            figma_component_id=figma_component_id,
            figma_component_key=figma_component_key,
            figma_name=figma_name,
            react_component=react_component or {},
            prop_mapping=prop_mapping,
            value_mapping=value_mapping,
            default_props=default_props,
            reason=reason,
        )
    )
    save_override_set(path, override_set)
    return override_set


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Manual component mapping override manager")
    parser.add_argument("--file", default=".agent_loop/figma_overrides.json", help="Path to override file")
    sub = parser.add_subparsers(dest="command")

    add_parser = sub.add_parser("add", help="Add or replace an override rule")
    add_parser.add_argument("--figma-component-id", default=None)
    add_parser.add_argument("--figma-component-key", default=None)
    add_parser.add_argument("--figma-name", default=None)
    add_parser.add_argument("--export-name", required=True)
    add_parser.add_argument("--import-path", required=True)
    add_parser.add_argument("--file-path", default=None)
    add_parser.add_argument("--reason", default="")

    validate_parser = sub.add_parser("validate", help="Validate override file")
    list_parser = sub.add_parser("list", help="List override rules")

    args = parser.parse_args()

    if args.command == "add":
        react = {
            "export_name": args.export_name,
            "import_path": args.import_path,
        }
        if args.file_path:
            react["file_path"] = args.file_path
        add_override(
            args.file,
            figma_component_id=args.figma_component_id,
            figma_component_key=args.figma_component_key,
            figma_name=args.figma_name,
            react_component=react,
            reason=args.reason,
        )
        print(f"[OVERRIDE] wrote {args.file}")
    elif args.command == "validate":
        override_set = load_override_set(args.file)
        issues = validate_override_set(override_set)
        if issues:
            for issue in issues:
                print(f"[OVERRIDE ISSUE] {issue}")
            raise SystemExit(1)
        print("[OVERRIDE] valid")
    elif args.command == "list":
        override_set = load_override_set(args.file)
        for idx, rule in enumerate(override_set.rules):
            status = "disabled" if rule.disabled else "active"
            print(f"{idx}: [{status}] {rule.figma_name or rule.figma_component_id or rule.figma_component_key} -> {rule.react_component.get('export_name')} ({rule.react_component.get('import_path')})")
    else:
        parser.print_help()
