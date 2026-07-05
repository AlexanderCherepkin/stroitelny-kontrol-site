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


class BackendMCPServer(MCPServer):
    """MCP server that wraps the Backend Spec Bridge.

    Provides tools to parse backend specs (OpenAPI, Prisma, structured text),
    map them to a Tailwind AST, and generate Next.js API routes / Server Actions.
    """

    def __init__(self, workspace_root: str = "."):
        super().__init__(name="backend", version="1.0.0")
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
        self.register(
            "backend_analyze_spec",
            "Parse OpenAPI/Prisma/text spec into normalized JSON model/endpoints",
            s({"openapi?": "string", "prisma?": "string", "text_spec?": "string"}),
            self.backend_analyze_spec,
        )
        self.register(
            "backend_map_ui",
            "Map a Tailwind AST to backend models/endpoints and return backend_mapping.json",
            s({
                "layout_ast": "string",
                "openapi?": "string",
                "prisma?": "string",
                "text_spec?": "string",
                "mapping_file?": "string",
            }),
            self.backend_map_ui,
        )
        self.register(
            "backend_generate_routes",
            "Generate Next.js API route.ts files for mapped models",
            s({"layout_ast?": "string", "openapi?": "string", "prisma?": "string", "text_spec?": "string", "output_dir?": "string"}),
            self.backend_generate_routes,
        )
        self.register(
            "backend_generate_actions",
            "Generate Next.js Server Action files for mapped forms",
            s({"layout_ast?": "string", "openapi?": "string", "prisma?": "string", "text_spec?": "string", "output_dir?": "string"}),
            self.backend_generate_actions,
        )
        self.register(
            "backend_sync_schema",
            "Write/update prisma/schema.prisma from spec",
            s({"openapi?": "string", "prisma?": "string", "text_spec?": "string", "output_dir?": "string"}),
            self.backend_sync_schema,
        )
        self.register(
            "backend_run_bridge",
            "Run the full Backend Spec Bridge pipeline",
            s({
                "layout_ast": "string",
                "openapi?": "string",
                "prisma?": "string",
                "text_spec?": "string",
                "output_dir?": "string",
                "mapping_file?": "string",
            }),
            self.backend_run_bridge,
        )
        self.register(
            "backend_generate_schemas",
            "Generate Zod validation schemas for mapped backend models",
            s({"layout_ast?": "string", "openapi?": "string", "prisma?": "string", "text_spec?": "string", "output_dir?": "string"}),
            self.backend_generate_schemas,
        )

    @staticmethod
    def _schema(props: dict[str, str]) -> dict[str, Any]:
        required = [k for k in props if not k.endswith("?")]
        properties: dict[str, Any] = {}
        type_map = {
            "string": "string",
            "int": "integer",
            "bool": "boolean",
            "float": "number",
            "array": "array",
            "object": "object",
        }
        for k, v in props.items():
            name = k.rstrip("?")
            properties[name] = {"type": type_map.get(v, "string"), "description": f"The {name} parameter"}
        return {"type": "object", "properties": properties, "required": required}

    def _check_degraded(self) -> dict[str, Any] | None:
        if self._degraded_reason:
            return {
                "status": "degraded",
                "error": self._degraded_reason,
                "fallback": "Install figma-agent-core and provide OpenAPI/Prisma/text spec paths",
            }
        return None

    def _run_core_script(self, script_name: str, args: list[str]) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded

        cmd = [sys.executable, script_name, *args]
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self._core_dir),
                env=os.environ.copy(),
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

    def _bridge_args(
        self,
        openapi: str = "",
        prisma: str = "",
        text_spec: str = "",
        output_dir: str = "",
        mapping_file: str = "",
        layout_ast: str = "",
    ) -> list[str]:
        args: list[str] = []
        if openapi:
            args.extend(["--openapi", openapi])
        if prisma:
            args.extend(["--prisma", prisma])
        if text_spec:
            args.extend(["--text-spec", text_spec])
        if output_dir:
            args.extend(["--output-dir", output_dir])
        if mapping_file:
            args.extend(["--mapping-file", mapping_file])
        if layout_ast:
            args.extend(["--layout-ast", layout_ast])
        return args

    def backend_analyze_spec(
        self,
        openapi: str = "",
        prisma: str = "",
        text_spec: str = "",
    ) -> dict[str, Any]:
        return self._run_core_script(
            "backend_bridge.py",
            self._bridge_args(openapi=openapi, prisma=prisma, text_spec=text_spec),
        )

    def backend_map_ui(
        self,
        layout_ast: str,
        openapi: str = "",
        prisma: str = "",
        text_spec: str = "",
        mapping_file: str = "backend_mapping.json",
    ) -> dict[str, Any]:
        return self._run_core_script(
            "backend_bridge.py",
            self._bridge_args(
                layout_ast=layout_ast,
                openapi=openapi,
                prisma=prisma,
                text_spec=text_spec,
                mapping_file=mapping_file,
            ),
        )

    def backend_generate_routes(
        self,
        layout_ast: str = "",
        openapi: str = "",
        prisma: str = "",
        text_spec: str = "",
        output_dir: str = "",
    ) -> dict[str, Any]:
        return self._run_core_script(
            "backend_bridge.py",
            self._bridge_args(
                layout_ast=layout_ast,
                openapi=openapi,
                prisma=prisma,
                text_spec=text_spec,
                output_dir=output_dir,
            ),
        )

    def backend_generate_actions(
        self,
        layout_ast: str = "",
        openapi: str = "",
        prisma: str = "",
        text_spec: str = "",
        output_dir: str = "",
    ) -> dict[str, Any]:
        return self._run_core_script(
            "backend_bridge.py",
            self._bridge_args(
                layout_ast=layout_ast,
                openapi=openapi,
                prisma=prisma,
                text_spec=text_spec,
                output_dir=output_dir,
            ),
        )

    def backend_sync_schema(
        self,
        openapi: str = "",
        prisma: str = "",
        text_spec: str = "",
        output_dir: str = "",
    ) -> dict[str, Any]:
        return self._run_core_script(
            "backend_bridge.py",
            self._bridge_args(
                openapi=openapi,
                prisma=prisma,
                text_spec=text_spec,
                output_dir=output_dir,
            ),
        )

    def backend_run_bridge(
        self,
        layout_ast: str,
        openapi: str = "",
        prisma: str = "",
        text_spec: str = "",
        output_dir: str = "backend_bridge_output",
        mapping_file: str = "backend_mapping.json",
    ) -> dict[str, Any]:
        return self._run_core_script(
            "backend_bridge.py",
            self._bridge_args(
                layout_ast=layout_ast,
                openapi=openapi,
                prisma=prisma,
                text_spec=text_spec,
                output_dir=output_dir,
                mapping_file=mapping_file,
            ),
        )

    def backend_generate_schemas(
        self,
        layout_ast: str = "",
        openapi: str = "",
        prisma: str = "",
        text_spec: str = "",
        output_dir: str = "",
    ) -> dict[str, Any]:
        return self._run_core_script(
            "backend_bridge.py",
            self._bridge_args(
                layout_ast=layout_ast,
                openapi=openapi,
                prisma=prisma,
                text_spec=text_spec,
                output_dir=output_dir,
            ),
        )

    async def ping(self) -> bool:
        return True
