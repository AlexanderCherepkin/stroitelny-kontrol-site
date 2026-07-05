"""Content Model Extractor.

Thin wrapper around `content_model.py` that exposes a dedicated Page/Section/Data
separation entry point matching the `figma_design_analyst.md` pipeline stage.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from content_model import ContentModelResult, build_content_model


def extract_content_model(
    ast: Dict[str, Any],
    output_dir: str = "src/app/sections",
    page_output: str = "src/app/page.tsx",
    data_output: str = "src/app/page.data.ts",
    content_model_output: str = "content_model.json",
    root_dir: str = ".",
    component_mapper: Optional[Dict[str, Any]] = None,
) -> ContentModelResult:
    """Split a Tailwind AST into Page, Section components, and external data.

    Args:
        ast: Tailwind AST produced by the layout engine / responsive composer.
        output_dir: directory where per-section `.tsx` files are written.
        page_output: path for the generated `page.tsx`.
        data_output: path for the generated `page.data.ts`.
        content_model_output: path for the generated `content_model.json`.
        root_dir: workspace root used for path-traversal guard.
        component_mapper: optional `figma_component_map.json` mapping object.

    Returns:
        A `ContentModelResult` with generated code, data, and the content model tree.
    """
    return build_content_model(
        ast,
        output_dir=output_dir,
        page_output=page_output,
        data_output=data_output,
        content_model_output=content_model_output,
        root_dir=root_dir,
        component_mapper=component_mapper,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Content Model Extractor: Page + Sections + Data")
    parser.add_argument("--ast", default="layout_ast.json", help="Path to Tailwind AST JSON")
    parser.add_argument("--output-dir", default="src/app/sections", help="Directory for section components")
    parser.add_argument("--page-output", default="src/app/page.tsx", help="Path for generated page.tsx")
    parser.add_argument("--data-output", default="src/app/page.data.ts", help="Path for generated page.data.ts")
    parser.add_argument("--content-model-output", default="content_model.json", help="Path for generated content_model.json")
    parser.add_argument("--workspace-root", default=".", help="Workspace root for path traversal guard")
    parser.add_argument("--components-mapper", default="figma_component_map.json", help="Path to figma_component_map.json")
    args = parser.parse_args()

    ast_path = Path(args.ast)
    if not ast_path.exists():
        print(f"[ERROR] AST file not found: {ast_path}", file=sys.stderr)
        raise SystemExit(1)

    ast = json.loads(ast_path.read_text(encoding="utf-8"))
    mapper: Optional[Dict[str, Any]] = None
    if args.components_mapper and Path(args.components_mapper).exists():
        mapper = json.loads(Path(args.components_mapper).read_text(encoding="utf-8"))

    result = extract_content_model(
        ast,
        output_dir=args.output_dir,
        page_output=args.page_output,
        data_output=args.data_output,
        content_model_output=args.content_model_output,
        root_dir=args.workspace_root,
        component_mapper=mapper,
    )
    print(f"[CONTENT-MODEL-EXTRACTOR] {len(result.sections)} section(s) written to {args.output_dir}")
    for s in result.sections:
        print(f"  - {s.name}")
    print(f"[CONTENT-MODEL-EXTRACTOR] Page -> {args.page_output}")
    print(f"[CONTENT-MODEL-EXTRACTOR] Data -> {args.data_output}")
    print(f"[CONTENT-MODEL-EXTRACTOR] Content Model -> {args.content_model_output}")


if __name__ == "__main__":
    main()
