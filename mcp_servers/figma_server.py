from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback
import warnings
from pathlib import Path
from typing import Any

from .base import MCPServer

warnings.filterwarnings("ignore", category=ResourceWarning)


class FigmaMCPServer(MCPServer):
    """MCP server that wraps the figma-agent-core Figma-to-code pipeline.

    The wrapped pipeline lives in `figma-agent-core/` and reads its configuration
    from environment variables (`FIGMA_TOKEN`, `FIGMA_URL`, `FIGMA_NODE_ID`) plus
    per-call arguments. This server exposes coarse-grained tools that match the
    pipeline stages, plus a full-pipeline convenience tool.
    """

    def __init__(self, workspace_root: str = "."):
        super().__init__(name="figma", version="1.0.0")
        self.workspace = Path(workspace_root).resolve()
        self._core_dir = self.workspace / "figma-agent-core"
        self._degraded_reason: str | None = None
        self._ensure_core()
        self._register_tools()
        self._initialized = True

    def _ensure_core(self) -> None:
        if not self._core_dir.exists():
            self._degraded_reason = f"figma-agent-core not found at {self._core_dir}"

    def _register_tools(self) -> None:
        s = self._schema
        self.register("figma_bootstrap", "Fetch a Figma file or node and cache it as figma_node.json",
                      s({"force_refresh?": "bool", "node_id?": "string", "api_depth?": "int"}),
                      self.figma_bootstrap)
        self.register("figma_analyze", "Analyze the cached Figma structure and return tree summary",
                      s({"file?": "string"}),
                      self.figma_analyze)
        self.register("figma_precise_mode_audit", "Run Builder.io-style Precise Mode readiness audit on the cached Figma structure",
                      s({"file?": "string", "node_id?": "string", "target_viewport?": "string"}),
                      self.figma_precise_mode_audit)
        self.register("figma_generate_spec", "Generate a technical assignment (spec.md) from the cached Figma structure",
                      s({"file?": "string", "node_id?": "string", "output?": "string"}),
                      self.figma_generate_spec)
        self.register("figma_extract_tokens", "Extract design tokens from a Figma file and generate tailwind.config.ts + globals.css + design_tokens.json",
                      s({"file?": "string", "output_dir?": "string", "registry_file?": "string",
                         "tailwind_config?": "string", "globals_css?": "string"}),
                      self.figma_extract_tokens)
        self.register("figma_generate_component", "Generate a React/TSX component for a Figma node",
                      s({"file?": "string", "node_id?": "string", "output_name?": "string",
                         "skip_assets?": "bool"}),
                      self.figma_generate_component)
        self.register("figma_build_component_registry", "Build a Figma Component Registry from a Figma document (COMPONENT_SET, COMPONENT, INSTANCE, variants, overrides, dependency DAG)",
                      s({"file?": "string", "output?": "string", "node_id?": "string", "scan_dirs?": "array"}),
                      self.figma_build_component_registry)
        self.register("figma_extract_components", "Extract reusable React components from the Tailwind AST",
                      s({"ast_file?": "string", "output_dir?": "string", "page_ast_output?": "string",
                         "component_map_output?": "string", "patterns?": "string", "min_duplicates?": "int"}),
                      self.figma_extract_components)
        self.register("figma_map_interactions", "Map Figma prototype interactions (clicks, hovers, overlays, navigation) to React state/handlers",
                      s({"figma_file?": "string", "ast_file?": "string", "ast_output?": "string",
                         "registry_output?": "string"}),
                      self.figma_map_interactions)
        self.register("figma_responsive_compose", "Generate responsive breakpoint variants from layout_ast and raw Figma constraints",
                      s({"layout_ast_file?": "string", "figma_file?": "string", "output?": "string",
                         "report?": "string", "node_id?": "string"}),
                      self.figma_responsive_compose)
        self.register("figma_download_assets", "Download, optimize and register image/SVG assets referenced by the cached Figma structure",
                      s({"file?": "string", "public_dir?": "string", "assets_dir?": "string",
                         "registry_file?": "string", "skip_download?": "bool", "optimize?": "bool"}),
                      self.figma_download_assets)
        self.register("figma_run_pipeline", "Run the full Figma-to-code/fullstack pipeline (bootstrap, analyze, spec, tokens, layout, backend_bridge, responsive, extract, compose, components, assets). Optional backend spec + Figma URL/file_key supported.",
                      s({"force_refresh?": "bool", "node_id?": "string", "all_sections?": "bool",
                         "skip_assets?": "bool", "api_depth?": "int", "spec_output?": "string",
                         "output_name?": "string", "dry_run?": "bool",
                         "figma_url?": "string", "file_key?": "string",
                         "openapi?": "string", "prisma?": "string", "backend_spec_text?": "string",
                         "backend_output_dir?": "string", "backend_mapping_file?": "string",
                         "enable_image_enrichment?": "bool", "image_provider?": "string",
                         "image_provider_api_key?": "string", "image_enrichment_output_dir?": "string",
                         "image_enrichment_max_images?": "int"}),
                      self.figma_run_pipeline)

    @staticmethod
    def _schema(props: dict[str, str]) -> dict[str, Any]:
        required = [k for k in props if not k.endswith("?")]
        properties: dict[str, Any] = {}
        type_map = {"string": "string", "int": "integer", "bool": "boolean", "float": "number",
                    "array": "array", "object": "object"}
        for k, v in props.items():
            name = k.rstrip("?")
            properties[name] = {"type": type_map.get(v, "string"), "description": f"The {name} parameter"}
        return {"type": "object", "properties": properties, "required": required}

    def _check_degraded(self) -> dict[str, Any] | None:
        if self._degraded_reason:
            return {
                "status": "degraded",
                "error": self._degraded_reason,
                "fallback": "Install figma-agent-core and set FIGMA_TOKEN / FIGMA_URL",
            }
        return None

    def _run_core_script(self, script_name: str, args: list[str], env: dict[str, str] | None = None) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded

        cmd = [sys.executable, script_name, *args]
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        # Do not persist temporary per-call env in the parent process.
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self._core_dir),
                env=merged_env,
                capture_output=True,
                text=True,
                timeout=600,
            )
            return {
                "status": "success" if result.returncode == 0 else "error",
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except subprocess.TimeoutExpired as e:
            return {"status": "timeout", "stdout": e.stdout or "", "stderr": e.stderr or ""}
        except Exception as e:
            return {"status": "error", "error": str(e), "traceback": traceback.format_exc()}

    def figma_bootstrap(self, force_refresh: bool = False, node_id: str = "", api_depth: int = 2) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded
        args = ["--api-depth", str(api_depth)]
        if force_refresh:
            args.append("--force")
        if node_id:
            args.extend(["--node-id", node_id])
        return self._run_core_script("bootstrap.py", args)

    def figma_analyze(self, file: str = "figma_node.json") -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded
        args = ["--file", file]
        return self._run_core_script("analyzer.py", args)

    def figma_precise_mode_audit(self, file: str = "figma_node.json", node_id: str = "", target_viewport: str = "") -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded
        args = ["--file", file]
        if node_id:
            args.extend(["--node-id", node_id])
        if target_viewport:
            args.extend(["--target-viewport", target_viewport])
        args.extend(["--output", "precise_mode_report.json"])
        return self._run_core_script("precise_mode_auditor.py", args)

    def figma_generate_spec(self, file: str = "figma_node.json", node_id: str = "", output: str = "spec.md") -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded
        args = ["--file", file, "--output", output]
        if node_id:
            args.extend(["--node-id", node_id])
        return self._run_core_script("spec_writer.py", args)

    def figma_extract_tokens(self, file: str = "figma_node.json", output_dir: str = ".",
                             registry_file: str = "design_tokens.json",
                             tailwind_config: str = "tailwind.config.ts",
                             globals_css: str = "src/app/globals.css") -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded
        args = [
            "--file", file,
            "--output-dir", output_dir,
            "--registry", registry_file,
            "--tailwind-config", tailwind_config,
            "--globals-css", globals_css,
        ]
        return self._run_core_script("design_tokens.py", args)

    def figma_generate_component(self, file: str = "figma_node.json", node_id: str = "",
                                  output_name: str = "", skip_assets: bool = False) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded
        args = ["--file", file]
        if node_id:
            args.extend(["--node-id", node_id])
        if output_name:
            args.extend(["--output-name", output_name])
        if skip_assets:
            args.append("--skip-assets")
        return self._run_core_script("agent.py", args)

    def figma_build_component_registry(self, file: str = "figma_node.json", output: str = "component_registry.json", node_id: str = "", scan_dirs: list[str] | None = None) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded
        args = ["--file", file, "--output", output]
        if node_id:
            args.extend(["--node-id", node_id])
        for d in scan_dirs or []:
            args.extend(["--scan-dir", d])
        return self._run_core_script("component_registry.py", args)

    def figma_extract_components(self, ast_file: str = "layout_ast.json", output_dir: str = "src/app/components",
                                  page_ast_output: str = "page_ast.json",
                                  component_map_output: str = "component_map.json",
                                  patterns: str = "", min_duplicates: int = 2) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded
        args = [
            "--ast", ast_file,
            "--output-dir", output_dir,
            "--page-ast-output", page_ast_output,
            "--component-map-output", component_map_output,
            "--min-duplicates", str(min_duplicates),
        ]
        if patterns:
            args.extend(["--patterns", patterns])
        return self._run_core_script("component_extractor.py", args)

    def figma_map_interactions(
        self,
        figma_file: str = "figma_node.json",
        ast_file: str = "page_ast.json",
        ast_output: str = "interactive_ast.json",
        registry_output: str = "interactive_registry.json",
    ) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded
        args = [
            "--figma-file", figma_file,
            "--ast", ast_file,
            "--ast-output", ast_output,
            "--registry-output", registry_output,
        ]
        return self._run_core_script("interactive_layer_mapper.py", args)

    def figma_responsive_compose(
        self,
        layout_ast_file: str = "layout_ast.json",
        figma_file: str = "figma_node.json",
        output: str = "responsive_ast.json",
        report: str = "responsive_report.json",
        node_id: str = "",
    ) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded
        args = [
            "--layout-ast", layout_ast_file,
            "--figma-file", figma_file,
            "--output", output,
            "--report", report,
        ]
        if node_id:
            args.extend(["--node-id", node_id])
        return self._run_core_script("responsive_composer.py", args)

    def figma_download_assets(
        self,
        file: str = "figma_node.json",
        public_dir: str = "public",
        assets_dir: str = "assets/figma",
        registry_file: str = "asset_registry.json",
        skip_download: bool = False,
        optimize: bool = True,
    ) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded
        args = [
            "--file", file,
            "--public-dir", public_dir,
            "--assets-dir", assets_dir,
            "--registry", registry_file,
        ]
        if skip_download:
            args.append("--skip-download")
        if not optimize:
            args.append("--no-optimize")
        return self._run_core_script("asset_pipeline.py", args)

    def figma_run_pipeline(self, force_refresh: bool = False, node_id: str = "", all_sections: bool = True,
                           skip_assets: bool = False, api_depth: int = 2, spec_output: str = "spec.md",
                           output_name: str = "", dry_run: bool = False,
                           figma_url: str = "", file_key: str = "",
                           openapi: str = "", prisma: str = "", backend_spec_text: str = "",
                           backend_output_dir: str = "backend_bridge_output",
                           backend_mapping_file: str = "backend_mapping.json",
                           enable_image_enrichment: bool = False, image_provider: str = "unsplash",
                           image_provider_api_key: str = "", image_enrichment_output_dir: str = "",
                           image_enrichment_max_images: int = 20) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded
        args = ["--all", "--api-depth", str(api_depth), "--spec-output", spec_output]
        if force_refresh:
            args.append("--force")
        if node_id:
            args.extend(["--node-id", node_id])
        if all_sections:
            args.append("--all-sections")
        if output_name:
            args.extend(["--output-name", output_name])
        if skip_assets:
            args.append("--skip-assets")
        if enable_image_enrichment:
            args.append("--enable-image-enrichment")
            args.extend(["--image-provider", image_provider])
            if image_provider_api_key:
                args.extend(["--image-provider-api-key", image_provider_api_key])
            if image_enrichment_output_dir:
                args.extend(["--image-enrichment-output-dir", image_enrichment_output_dir])
            args.extend(["--image-enrichment-max-images", str(image_enrichment_max_images)])
        if openapi:
            args.extend(["--openapi", openapi])
        if prisma:
            args.extend(["--prisma", prisma])
        if backend_spec_text:
            args.extend(["--backend-spec-text", backend_spec_text])
        if backend_output_dir:
            args.extend(["--backend-output-dir", backend_output_dir])
        if backend_mapping_file:
            args.extend(["--backend-mapping-file", backend_mapping_file])
        if dry_run:
            args.append("--dry-run")

        env: dict[str, str] = {}
        if figma_url:
            env["FIGMA_URL"] = figma_url
        if file_key:
            env["FIGMA_FILE_KEY"] = file_key
        return self._run_core_script("conductor.py", args, env=env if env else None)



    async def ping(self) -> bool:
        return True
