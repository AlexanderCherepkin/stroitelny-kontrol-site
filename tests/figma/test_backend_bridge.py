"""Unit tests for figma-agent-core/backend_bridge.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_BRIDGE_PATH = ROOT / "figma-agent-core" / "backend_bridge.py"


def _load_backend_bridge() -> Any:
    spec = importlib.util.spec_from_file_location("figma_backend_bridge", str(BACKEND_BRIDGE_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_backend_bridge"] = module
    spec.loader.exec_module(module)
    return module


backend_bridge = _load_backend_bridge()


def test_openapi_parser_reads_json_spec(tmp_path: Path) -> None:
    spec_path = tmp_path / "api.json"
    spec_path.write_text(
        json.dumps({
            "openapi": "3.0.0",
            "components": {
                "schemas": {
                    "Contact": {
                        "type": "object",
                        "required": ["email"],
                        "properties": {
                            "email": {"type": "string", "format": "email"},
                            "name": {"type": "string", "maxLength": 100},
                        },
                    }
                }
            },
            "paths": {
                "/contacts": {
                    "post": {
                        "operationId": "createContact",
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Contact"}
                                }
                            }
                        },
                        "responses": {"201": {"description": "Created"}},
                    }
                }
            },
        }),
        encoding="utf-8",
    )
    parser = backend_bridge.OpenApiParser()
    spec = parser.parse(str(spec_path))
    contact = spec.model_by_name("Contact")
    assert contact is not None
    assert any(f.name == "email" and f.is_email for f in contact.fields)
    assert any(f.name == "name" and f.max_length == 100 for f in contact.fields)


def test_prisma_parser_reads_schema(tmp_path: Path) -> None:
    schema_path = tmp_path / "schema.prisma"
    schema_path.write_text(
        '''
datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

model User {
  id    String @id @default(uuid())
  email String @unique
  name  String?
}
''',
        encoding="utf-8",
    )
    parser = backend_bridge.PrismaParser()
    spec = parser.parse(str(schema_path))
    user = spec.model_by_name("User")
    assert user is not None
    assert any(f.name == "id" and f.is_id for f in user.fields)
    assert any(f.name == "email" and f.is_unique for f in user.fields)
    assert any(f.name == "name" and not f.required for f in user.fields)


def test_text_spec_parser_reads_entities_and_endpoints(tmp_path: Path) -> None:
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(
        json.dumps({
            "entities": [
                {
                    "name": "Lead",
                    "fields": [
                        {"name": "email", "type": "String", "required": True, "is_email": True},
                        {"name": "company", "type": "String"},
                    ],
                }
            ],
            "endpoints": [
                {"path": "/leads", "method": "post", "request_model": "Lead"}
            ],
        }),
        encoding="utf-8",
    )
    parser = backend_bridge.TextSpecParser()
    spec = parser.parse(str(spec_path))
    lead = spec.model_by_name("Lead")
    assert lead is not None
    assert any(f.name == "email" and f.is_email for f in lead.fields)
    assert any(e.path == "/leads" and e.method == "POST" for e in spec.endpoints)


def test_semantic_mapper_matches_form_to_model() -> None:
    spec = backend_bridge.BackendSpec()
    spec.models.append(backend_bridge.Model(name="Contact", fields=[
        backend_bridge.ModelField(name="email", field_type="String", is_email=True),
        backend_bridge.ModelField(name="message", field_type="String"),
    ]))
    spec.endpoints.append(backend_bridge.Endpoint(path="/contacts", method="POST", request_model="Contact"))
    mapper = backend_bridge.SemanticMapper(spec)
    layout_ast = {
        "root": {
            "figma_name": "Contact Form",
            "children": [
                {"figma_name": "email input", "tag": "input", "figma_id": "i1"},
                {"figma_name": "message input", "tag": "textarea", "figma_id": "i2"},
            ],
        }
    }
    result = mapper.map(layout_ast)
    assert any(m["model"] == "Contact" for m in result["mappings"])
    mapping = next(m for m in result["mappings"] if m["model"] == "Contact")
    assert any(fm["field"] == "email" for fm in mapping["field_mappings"])


def test_zod_schema_generator_emits_validation(tmp_path: Path) -> None:
    model = backend_bridge.Model(name="Contact", fields=[
        backend_bridge.ModelField(name="email", field_type="String", is_email=True, required=True),
        backend_bridge.ModelField(name="age", field_type="Int", min_value=18, max_value=120, required=True),
    ])
    gen = backend_bridge.ZodSchemaGenerator()
    code = gen.generate([model])
    assert "export const ContactSchema" in code
    assert "email: z.string().email()" in code
    assert "age: z.coerce.number().int().min(18).max(120)" in code


def test_backend_bridge_run_generates_artifacts(tmp_path: Path) -> None:
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(
        json.dumps({
            "entities": [
                {
                    "name": "Lead",
                    "fields": [
                        {"name": "email", "type": "String", "required": True, "is_email": True},
                    ],
                }
            ],
            "endpoints": [
                {"path": "/leads", "method": "post", "request_model": "Lead"}
            ],
        }),
        encoding="utf-8",
    )
    bridge = backend_bridge.BackendBridge(output_dir=str(tmp_path / "backend"), mapping_file=str(tmp_path / "mapping.json"))
    layout_ast = {
        "root": {
            "figma_name": "Lead Form",
            "children": [
                {"figma_name": "email input", "tag": "input", "figma_id": "i1"},
            ],
        }
    }
    result = bridge.run(layout_ast, text_spec_path=str(spec_path))
    assert result["mappings"]
    assert result["generated_files"]["schema"]
    assert result["generated_files"]["routes"]
    assert result["generated_files"]["actions"]
    assert result["generated_files"]["schemas"]
    mapping_file = tmp_path / "mapping.json"
    assert mapping_file.exists()
    assert (tmp_path / "backend" / "schema.prisma").exists()
