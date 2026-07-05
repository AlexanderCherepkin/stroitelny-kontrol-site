"""Unit tests for figma-agent-core/backend_bridge.py.

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
BACKEND_BRIDGE_PATH = ROOT / "figma-agent-core" / "backend_bridge.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load_backend_bridge() -> Any:
    spec = importlib.util.spec_from_file_location("backend_bridge", str(BACKEND_BRIDGE_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["backend_bridge"] = module
    spec.loader.exec_module(module)
    return module


backend_bridge = _load_backend_bridge()


def _sample_ast() -> dict[str, Any]:
    return {
        "root": {
            "figma_id": "10:1",
            "figma_name": "Lead Form",
            "tag": "section",
            "children": [
                {
                    "figma_id": "10:2",
                    "figma_name": "name input",
                    "tag": "input",
                    "classes": ["border", "rounded"],
                },
                {
                    "figma_id": "10:3",
                    "figma_name": "email field",
                    "tag": "input",
                    "classes": ["border", "rounded"],
                },
                {
                    "figma_id": "10:4",
                    "figma_name": "company input",
                    "tag": "input",
                    "classes": ["border", "rounded"],
                },
            ],
        }
    }


def test_openapi_parser_extracts_models_and_endpoints() -> None:
    parser = backend_bridge.OpenApiParser()
    spec = parser.parse(str(FIXTURES / "openapi.yaml"))
    assert len(spec.models) == 1
    assert spec.models[0].name == "Lead"
    assert {f.name for f in spec.models[0].fields} == {"id", "name", "email", "company", "budget", "createdAt"}
    assert len(spec.endpoints) == 2
    methods = {e.method for e in spec.endpoints}
    assert methods == {"POST", "GET"}


def test_prisma_parser_extracts_models_enums_and_datasource() -> None:
    parser = backend_bridge.PrismaParser()
    spec = parser.parse(str(FIXTURES / "prisma.schema"))
    assert spec.datasource == {"provider": "postgresql", "url": 'env("DATABASE_URL")'}
    lead = next(m for m in spec.models if m.name == "Lead")
    assert lead is not None
    email = next(f for f in lead.fields if f.name == "email")
    assert email.is_unique is True
    assert email.required is True
    company = next(f for f in lead.fields if f.name == "company")
    assert company.required is False
    status_enum = next((m for m in spec.models if m.name == "Status"), None)
    assert status_enum is not None
    assert status_enum.is_enum is True


def test_text_spec_parser_extracts_models_and_endpoints() -> None:
    parser = backend_bridge.TextSpecParser()
    spec = parser.parse(str(FIXTURES / "text_spec.json"))
    assert len(spec.models) == 1
    assert spec.models[0].name == "Lead"
    assert len(spec.endpoints) == 1
    assert spec.endpoints[0].path == "/api/leads"
    assert spec.endpoints[0].method == "POST"


def test_semantic_mapper_matches_form_to_lead_model() -> None:
    spec = backend_bridge.TextSpecParser().parse(str(FIXTURES / "text_spec.json"))
    mapper = backend_bridge.SemanticMapper(spec)
    mapping = mapper.map(_sample_ast())
    assert len(mapping["mappings"]) == 1
    form_mapping = mapping["mappings"][0]
    assert form_mapping["model"] == "Lead"
    assert form_mapping["action"] == "createLeadAction"
    assert form_mapping["endpoint"] == "/api/leads"
    field_names = {fm["field"] for fm in form_mapping["field_mappings"]}
    assert "name" in field_names
    assert "email" in field_names


def test_semantic_mapper_sets_input_types_on_ast() -> None:
    ast = _sample_ast()
    spec = backend_bridge.TextSpecParser().parse(str(FIXTURES / "text_spec.json"))
    backend_bridge.SemanticMapper(spec).map(ast)
    root = ast["root"]
    email_node = next(c for c in root["children"] if "email" in c.get("figma_name", ""))
    assert email_node["backend_field"] == "email"
    assert email_node["input_type"] == "email"
    assert email_node["backend_model"] == "Lead"


def test_prisma_generator_writes_valid_schema(tmp_path: Path) -> None:
    spec = backend_bridge.PrismaParser().parse(str(FIXTURES / "prisma.schema"))
    generator = backend_bridge.PrismaGenerator()
    output = generator.generate(spec)
    assert "model Lead" in output
    assert "enum Status" in output
    assert 'provider = "postgresql"' in output
    assert "email String @unique" in output


def test_route_generator_produces_crud_route() -> None:
    route = backend_bridge.RouteGenerator().generate("Lead")
    assert "export async function GET" in route
    assert "export async function POST" in route
    assert "export async function PUT" in route
    assert "export async function DELETE" in route
    assert 'prisma.leads.findMany' in route


def test_action_generator_produces_server_action() -> None:
    action = backend_bridge.ActionGenerator().generate("Lead")
    assert '"use server"' in action
    assert "export async function createLeadAction" in action
    assert "import { LeadSchema }" in action
    assert "LeadSchema.safeParse" in action
    assert "prisma.leads.create" in action
    assert "return { success: false, error:" in action


def test_backend_bridge_run_generates_artifacts(tmp_path: Path) -> None:
    output_dir = tmp_path / "backend_out"
    mapping_file = tmp_path / "backend_mapping.json"
    bridge = backend_bridge.BackendBridge(
        output_dir=str(output_dir),
        mapping_file=str(mapping_file),
    )
    result = bridge.run(
        _sample_ast(),
        text_spec_path=str(FIXTURES / "text_spec.json"),
    )
    assert (output_dir / "schema.prisma").exists()
    assert (output_dir / "api" / "lead.ts").exists()
    assert (output_dir / "actions" / "leadAction.ts").exists()
    assert mapping_file.exists()
    mapping = json.loads(mapping_file.read_text(encoding="utf-8"))
    assert len(mapping["mappings"]) == 1
    assert mapping["mappings"][0]["model"] == "Lead"


def test_backend_bridge_requires_at_least_one_spec() -> None:
    bridge = backend_bridge.BackendBridge()
    with pytest.raises(ValueError, match="At least one backend spec input"):
        bridge.run(_sample_ast())
