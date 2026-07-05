import json
import re
import argparse
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml
except Exception:
    yaml = None


DEFAULT_OUTPUT_DIR = "backend_bridge_output"
DEFAULT_MAPPING_FILE = "backend_mapping.json"


@dataclass
class ModelField:
    name: str
    field_type: str
    required: bool = True
    is_id: bool = False
    is_unique: bool = False
    default: Optional[str] = None
    description: Optional[str] = None
    is_email: bool = False
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    pattern: Optional[str] = None
    enum_values: List[str] = field(default_factory=list)


@dataclass
class Model:
    name: str
    fields: List[ModelField] = field(default_factory=list)
    is_enum: bool = False


@dataclass
class Endpoint:
    path: str
    method: str
    operation_id: Optional[str] = None
    summary: Optional[str] = None
    request_model: Optional[str] = None
    response_model: Optional[str] = None
    tags: List[str] = field(default_factory=list)


@dataclass
class BackendSpec:
    models: List[Model] = field(default_factory=list)
    endpoints: List[Endpoint] = field(default_factory=list)
    datasource: Optional[Dict[str, Any]] = None

    def model_by_name(self, name: str) -> Optional[Model]:
        for m in self.models:
            if m.name == name:
                return m
        return None


class OpenApiParser:
    """Парсит OpenAPI 3.x JSON/YAML в нормализованный BackendSpec."""

    def __init__(self) -> None:
        self._type_map = {
            "string": "String",
            "integer": "Int",
            "number": "Float",
            "boolean": "Boolean",
            "array": "Json",
            "object": "Json",
        }

    def parse(self, source: str) -> BackendSpec:
        path = Path(source)
        text = path.read_text(encoding="utf-8")
        if path.suffix in (".yaml", ".yml"):
            if yaml is None:
                raise RuntimeError("PyYAML is required for YAML OpenAPI specs")
            data = yaml.safe_load(text)
        else:
            data = json.loads(text)

        spec = BackendSpec()
        schemas = data.get("components", {}).get("schemas", {})
        for name, schema in schemas.items():
            spec.models.append(self._parse_schema(name, schema))

        paths = data.get("paths", {})
        for p, methods in paths.items():
            for method, op in methods.items():
                if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                    continue
                spec.endpoints.append(self._parse_endpoint(p, method, op))

        return spec

    def _parse_schema(self, name: str, schema: Dict[str, Any]) -> Model:
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        fields: List[ModelField] = []
        for field_name, field_schema in props.items():
            ftype = self._openapi_type_to_prisma(field_schema)
            is_email = "email" in field_name.lower() or "format" in field_schema and field_schema["format"] == "email"
            enum_values = field_schema.get("enum", []) if isinstance(field_schema.get("enum"), list) else []
            fields.append(
                ModelField(
                    name=field_name,
                    field_type=ftype,
                    required=field_name in required,
                    description=field_schema.get("description"),
                    is_email=is_email,
                    min_length=field_schema.get("minLength"),
                    max_length=field_schema.get("maxLength"),
                    min_value=field_schema.get("minimum"),
                    max_value=field_schema.get("maximum"),
                    pattern=field_schema.get("pattern"),
                    enum_values=enum_values,
                )
            )
        return Model(name=name, fields=fields)

    def _openapi_type_to_prisma(self, schema: Dict[str, Any]) -> str:
        ftype = schema.get("type", "string")
        fmt = schema.get("format", "")
        if fmt == "date-time":
            return "DateTime"
        if fmt == "email":
            return "String"
        if ftype == "array":
            items = schema.get("items", {})
            inner = self._openapi_type_to_prisma(items)
            return f"{inner}[]"
        return self._type_map.get(ftype, "String")

    def _parse_endpoint(self, path: str, method: str, op: Dict[str, Any]) -> Endpoint:
        req_model = None
        body = op.get("requestBody", {}).get("content", {})
        if "application/json" in body:
            ref = body["application/json"].get("schema", {}).get("$ref", "")
            req_model = ref.split("/")[-1] if ref else None

        resp_model = None
        responses = op.get("responses", {})
        for code, resp in responses.items():
            if code.startswith("2"):
                content = resp.get("content", {})
                if "application/json" in content:
                    ref = content["application/json"].get("schema", {}).get("$ref", "")
                    resp_model = ref.split("/")[-1] if ref else None
                break

        return Endpoint(
            path=path,
            method=method.upper(),
            operation_id=op.get("operationId"),
            summary=op.get("summary"),
            request_model=req_model,
            response_model=resp_model,
            tags=op.get("tags", []),
        )


class PrismaParser:
    """Легковесный парсер Prisma schema без WASM."""

    def parse(self, source: str) -> BackendSpec:
        text = Path(source).read_text(encoding="utf-8")
        spec = BackendSpec()
        spec.datasource = self._parse_datasource(text)

        for model_match in re.finditer(r"^\s*model\s+(\w+)\s*\{([^}]*)\}", text, re.MULTILINE | re.DOTALL):
            name = model_match.group(1)
            body = model_match.group(2)
            spec.models.append(self._parse_model(name, body))

        enum_values_by_name: Dict[str, List[str]] = {}
        for enum_match in re.finditer(r"^\s*enum\s+(\w+)\s*\{([^}]*)\}", text, re.MULTILINE | re.DOTALL):
            name = enum_match.group(1)
            body = enum_match.group(2)
            values = [v.strip() for v in re.findall(r"(\w+)", body)]
            enum_values_by_name[name] = values
            spec.models.append(Model(name=name, fields=[ModelField(name=v, field_type="Enum") for v in values], is_enum=True))

        for model in spec.models:
            if model.is_enum:
                continue
            for field in model.fields:
                if field.field_type in enum_values_by_name:
                    field.enum_values = enum_values_by_name[field.field_type]

        return spec

    def _parse_datasource(self, text: str) -> Optional[Dict[str, Any]]:
        match = re.search(r"^\s*datasource\s+\w+\s*\{([^}]*)\}", text, re.MULTILINE | re.DOTALL)
        if not match:
            return None
        body = match.group(1)
        provider = self._extract_assignment(body, "provider")
        url = self._extract_assignment(body, "url")
        return {"provider": provider, "url": url}

    def _extract_assignment(self, body: str, key: str) -> Optional[str]:
        pattern = rf"{key}\s*=\s*(.+?)(?:\n|$)"
        m = re.search(pattern, body)
        if not m:
            return None
        value = m.group(1).strip().strip('"').strip("'")
        return value

    def _parse_model(self, name: str, body: str) -> Model:
        fields: List[ModelField] = []
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            parts = line.split(None, 2)
            if len(parts) < 2:
                continue
            field_name = parts[0]
            field_type = parts[1]
            attrs = parts[2] if len(parts) > 2 else ""
            required = "?" not in field_type
            field_type = field_type.rstrip("?")
            is_id = "@id" in attrs
            is_unique = "@unique" in attrs
            default = None
            default_match = re.search(r"@default\(([^)]*)\)", attrs)
            if default_match:
                default = default_match.group(1).strip().strip('"').strip("'")
            is_email = "email" in field_name.lower()
            max_length = None
            varchar_match = re.search(r"@db\.VarChar\((\d+)\)", attrs)
            if varchar_match:
                max_length = int(varchar_match.group(1))
            fields.append(
                ModelField(
                    name=field_name,
                    field_type=field_type,
                    required=required,
                    is_id=is_id,
                    is_unique=is_unique,
                    default=default,
                    is_email=is_email,
                    max_length=max_length,
                )
            )
        return Model(name=name, fields=fields)


class TextSpecParser:
    """Парсит структурированный JSON-бриф."""

    def parse(self, source: str) -> BackendSpec:
        data = json.loads(Path(source).read_text(encoding="utf-8"))
        spec = BackendSpec()
        for entity in data.get("entities", []):
            fields: List[ModelField] = []
            for f in entity.get("fields", []):
                fields.append(
                    ModelField(
                        name=f["name"],
                        field_type=f.get("type", "String"),
                        required=f.get("required", True),
                        description=f.get("description"),
                        is_email=f.get("is_email", False),
                        min_length=f.get("min_length"),
                        max_length=f.get("max_length"),
                        min_value=f.get("min_value"),
                        max_value=f.get("max_value"),
                        pattern=f.get("pattern"),
                        enum_values=f.get("enum_values", []),
                    )
                )
            spec.models.append(Model(name=entity["name"], fields=fields))

        for ep in data.get("endpoints", []):
            spec.endpoints.append(
                Endpoint(
                    path=ep["path"],
                    method=ep["method"].upper(),
                    operation_id=ep.get("operation_id"),
                    request_model=ep.get("request_model"),
                    response_model=ep.get("response_model"),
                    tags=ep.get("tags", []),
                )
            )
        return spec


class SemanticMapper:
    """Сопоставляет UI-ноды из Tailwind AST с backend-моделями и эндпоинтами."""

    def __init__(self, spec: BackendSpec) -> None:
        self.spec = spec

    def map(self, layout_ast: Dict[str, Any]) -> Dict[str, Any]:
        root = layout_ast.get("root", layout_ast)
        forms = self._find_forms(root)
        mappings: List[Dict[str, Any]] = []

        for form in forms:
            model, endpoint, confidence = self._match_form_to_model(form)
            if not model:
                continue
            field_mappings: List[Dict[str, Any]] = []
            for input_node in form.get("inputs", []):
                field, fconf = self._match_input_to_field(input_node, model)
                if field:
                    field_mappings.append({
                        "node_id": input_node.get("figma_id"),
                        "node_name": input_node.get("figma_name"),
                        "field": field.name,
                        "type": field.field_type,
                        "required": field.required,
                        "confidence": fconf,
                    })
                    input_node["backend_field"] = field.name
                    input_node["backend_model"] = model.name
                    input_node["input_type"] = self._field_to_input_type(field)
                    input_node["required"] = field.required
                    if field.min_length is not None:
                        input_node["min_length"] = field.min_length
                    if field.max_length is not None:
                        input_node["max_length"] = field.max_length
                    if field.min_value is not None:
                        input_node["min_value"] = field.min_value
                    if field.max_value is not None:
                        input_node["max_value"] = field.max_value
                    if field.pattern:
                        input_node["pattern"] = field.pattern
                    if field.enum_values:
                        input_node["enum_values"] = field.enum_values

            if field_mappings:
                form["backend_action"] = self._action_name(model.name)
                form["backend_endpoint"] = endpoint.path if endpoint else self._default_path(model.name)
                form["backend_model"] = model.name
                mappings.append({
                    "node_id": form.get("figma_id"),
                    "node_name": form.get("figma_name"),
                    "kind": "form",
                    "model": model.name,
                    "endpoint": endpoint.path if endpoint else self._default_path(model.name),
                    "action": form["backend_action"],
                    "confidence": confidence,
                    "field_mappings": field_mappings,
                })

        return {
            "mappings": mappings,
            "models": [self._model_to_dict(m) for m in self.spec.models],
            "endpoints": [self._endpoint_to_dict(e) for e in self.spec.endpoints],
        }

    def _find_forms(self, node: Dict[str, Any]) -> List[Dict[str, Any]]:
        forms: List[Dict[str, Any]] = []
        name_lower = (node.get("figma_name") or "").lower()
        children = node.get("children", [])
        inputs = [
            c for c in children
            if c.get("tag") in ("input", "textarea", "select") or self._looks_like_input(c)
        ]
        if inputs or any(k in name_lower for k in ("form", "contact", "lead", "signup", "subscribe", "login")):
            form = dict(node)
            form["inputs"] = inputs if inputs else self._collect_input_candidates(children)
            if form["inputs"]:
                forms.append(form)
        for child in children:
            forms.extend(self._find_forms(child))
        return forms

    def _looks_like_input(self, node: Dict[str, Any]) -> bool:
        name = (node.get("figma_name") or "").lower()
        classes = " ".join(node.get("classes", []))
        return (
            "input" in name
            or "field" in name
            or "email" in name
            or "name" in name
            or "border" in classes
        )

    def _collect_input_candidates(self, children: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        for c in children:
            if c.get("text") is not None:
                continue
            if self._looks_like_input(c):
                candidates.append(c)
            candidates.extend(self._collect_input_candidates(c.get("children", [])))
        return candidates

    def _match_form_to_model(self, form: Dict[str, Any]) -> Tuple[Optional[Model], Optional[Endpoint], float]:
        name = (form.get("figma_name") or "").lower()
        labels = " ".join(self._collect_text(form)).lower()
        best_model: Optional[Model] = None
        best_score = 0.0
        for model in self.spec.models:
            score = self._score(model.name, name)
            for f in model.fields:
                score += self._score(f.name, labels) * 0.3
            if score > best_score:
                best_score = score
                best_model = model

        if best_model is None:
            return None, None, 0.0

        endpoint = None
        for ep in self.spec.endpoints:
            if ep.request_model == best_model.name and ep.method in ("POST", "PUT", "PATCH"):
                endpoint = ep
                break
        if endpoint is None:
            for ep in self.spec.endpoints:
                if best_model.name.lower() in ep.path.lower() and ep.method == "POST":
                    endpoint = ep
                    break

        confidence = min(1.0, best_score)
        return best_model, endpoint, confidence

    def _match_input_to_field(self, input_node: Dict[str, Any], model: Model) -> Tuple[Optional[ModelField], float]:
        candidates = []
        name = (input_node.get("figma_name") or "").lower()
        texts = " ".join(self._collect_text(input_node)).lower()
        for field in model.fields:
            score = self._score(field.name, name)
            score += self._score(field.name, texts) * 0.5
            if field.is_email and "email" in name:
                score += 1.0
            candidates.append((field, score))
        candidates.sort(key=lambda x: x[1], reverse=True)
        if candidates and candidates[0][1] > 0.0:
            return candidates[0][0], min(1.0, candidates[0][1])
        return None, 0.0

    def _collect_text(self, node: Dict[str, Any]) -> List[str]:
        texts: List[str] = []
        if node.get("text"):
            texts.append(str(node["text"]))
        for child in node.get("children", []):
            texts.extend(self._collect_text(child))
        return texts

    def _score(self, a: str, b: str) -> float:
        a = a.lower().replace("_", " ").replace("-", " ")
        b = b.lower().replace("_", " ").replace("-", " ")
        if a == b:
            return 1.0
        if a in b or b in a:
            return 0.8
        return SequenceMatcher(None, a, b).ratio() * 0.5

    def _field_to_input_type(self, field: ModelField) -> str:
        if field.is_email:
            return "email"
        if field.field_type in ("Int", "Float", "Decimal"):
            return "number"
        if field.field_type == "Boolean":
            return "checkbox"
        if field.field_type == "DateTime":
            return "date"
        return "text"

    def _action_name(self, model_name: str) -> str:
        return f"create{model_name}Action"

    def _default_path(self, model_name: str) -> str:
        return f"/api/{self._pluralize(model_name.lower())}"

    def _pluralize(self, word: str) -> str:
        if word.endswith("s"):
            return word
        if word.endswith("y"):
            return word[:-1] + "ies"
        return word + "s"

    def _model_to_dict(self, model: Model) -> Dict[str, Any]:
        return {
            "name": model.name,
            "fields": [
                {
                    "name": f.name,
                    "type": f.field_type,
                    "required": f.required,
                    "is_id": f.is_id,
                    "is_unique": f.is_unique,
                    "default": f.default,
                    "is_email": f.is_email,
                    "min_length": f.min_length,
                    "max_length": f.max_length,
                    "min_value": f.min_value,
                    "max_value": f.max_value,
                    "pattern": f.pattern,
                    "enum_values": f.enum_values,
                }
                for f in model.fields
            ],
            "is_enum": model.is_enum,
        }

    def _endpoint_to_dict(self, endpoint: Endpoint) -> Dict[str, Any]:
        return {
            "path": endpoint.path,
            "method": endpoint.method,
            "operation_id": endpoint.operation_id,
            "summary": endpoint.summary,
            "request_model": endpoint.request_model,
            "response_model": endpoint.response_model,
            "tags": endpoint.tags,
        }


class PrismaGenerator:
    def generate(self, spec: BackendSpec) -> str:
        lines = [
            "generator client {",
            '  provider = "prisma-client-js"',
            "}",
            "",
            "datasource db {",
            '  provider = "postgresql"',
            '  url      = env("DATABASE_URL")',
            "}",
            "",
        ]
        for model in spec.models:
            if model.is_enum:
                lines.append(f"enum {model.name} {{")
                for f in model.fields:
                    lines.append(f"  {f.name}")
                lines.append("}")
            else:
                lines.append(f"model {model.name} {{")
                for f in model.fields:
                    attr_parts = [f.field_type]
                    if not f.required:
                        attr_parts.append("?")
                    attrs = " ".join(attr_parts)
                    extra = ""
                    if f.is_id:
                        extra += " @id"
                    if f.is_unique:
                        extra += " @unique"
                    if f.default:
                        extra += f' @default({f.default})'
                    if f.description:
                        extra += f" // {f.description}"
                    lines.append(f"  {f.name} {attrs}{extra}")
                lines.append("}")
            lines.append("")
        return "\n".join(lines)


class RouteGenerator:
    def generate(self, model_name: str, endpoint: Optional[Endpoint] = None) -> str:
        plural = self._pluralize(model_name.lower())
        path = endpoint.path if endpoint else f"/api/{plural}"
        return f"""import {{ NextRequest, NextResponse }} from "next/server";
import {{ prisma }} from "@/lib/prisma";

export async function GET() {{
  const items = await prisma.{plural}.findMany({{ orderBy: {{ createdAt: "desc" }} }});
  return NextResponse.json(items);
}}

export async function POST(request: NextRequest) {{
  const body = await request.json();
  const item = await prisma.{plural}.create({{ data: body }});
  return NextResponse.json(item, {{ status: 201 }});
}}

export async function PUT(request: NextRequest) {{
  const {{ id, ...data }} = await request.json();
  const item = await prisma.{plural}.update({{ where: {{ id }}, data }});
  return NextResponse.json(item);
}}

export async function DELETE(request: NextRequest) {{
  const {{ id }} = await request.json();
  await prisma.{plural}.delete({{ where: {{ id }} }});
  return NextResponse.json({{ success: true }});
}}
"""

    def _pluralize(self, word: str) -> str:
        if word.endswith("s"):
            return word
        if word.endswith("y"):
            return word[:-1] + "ies"
        return word + "s"


class ActionGenerator:
    def generate(self, model_name: str, endpoint: Optional[Endpoint] = None) -> str:
        plural = self._pluralize(model_name.lower())
        action_name = f"create{model_name}Action"
        schema_name = f"{model_name}Schema"
        return f""""use server";

import {{ revalidatePath }} from "next/cache";
import {{ prisma }} from "@/lib/prisma";
import {{ {schema_name} }} from "@/lib/schemas";

export async function {action_name}(prevState: any, formData: FormData) {{
  const raw = Object.fromEntries(formData.entries());
  const parsed = {schema_name}.safeParse(raw);

  if (!parsed.success) {{
    return {{ success: false, error: parsed.error.flatten().fieldErrors }};
  }}

  const item = await prisma.{plural}.create({{ data: parsed.data }});
  revalidatePath("/");
  return {{ success: true, id: item.id }};
}}
"""

    def _pluralize(self, word: str) -> str:
        if word.endswith("s"):
            return word
        if word.endswith("y"):
            return word[:-1] + "ies"
        return word + "s"


class ZodSchemaGenerator:
    """Генерирует Zod-схемы валидации из ModelField."""

    def generate(self, models: List[Model]) -> str:
        lines = ['import { z } from "zod";', ""]
        for model in models:
            if model.is_enum:
                continue
            schema_name = self._schema_name(model.name)
            type_name = self._type_name(model.name)
            lines.append(f"export const {schema_name} = z.object({{")
            for f in model.fields:
                if f.is_id:
                    continue
                lines.append(f"  {f.name}: {self._field_schema(f)},")
            lines.append("});")
            lines.append(f"export type {type_name} = z.infer<typeof {schema_name}>;")
            lines.append("")
        return "\n".join(lines)

    def _schema_name(self, model_name: str) -> str:
        return f"{model_name}Schema"

    def _type_name(self, model_name: str) -> str:
        return f"{model_name}Values"

    def _field_schema(self, field: ModelField) -> str:
        base = self._base_schema(field)
        if field.is_email:
            base += '.email()'
        if field.enum_values:
            values = ", ".join(json.dumps(v) for v in field.enum_values)
            base = f"z.enum([{values}])"
        if field.min_length is not None:
            base += f'.min({field.min_length})'
        if field.max_length is not None:
            base += f'.max({field.max_length})'
        if field.min_value is not None and field.field_type in ("Int", "Float"):
            base += f'.min({field.min_value})'
        if field.max_value is not None and field.field_type in ("Int", "Float"):
            base += f'.max({field.max_value})'
        if field.min_value is not None and field.field_type == "DateTime":
            base += f'.min(new Date({json.dumps(str(field.min_value))}))'
        if field.max_value is not None and field.field_type == "DateTime":
            base += f'.max(new Date({json.dumps(str(field.max_value))}))'
        if field.pattern:
            base += f'.regex(new RegExp({json.dumps(field.pattern)}))'
        if not field.required:
            base += '.optional()'
        return base

    def _base_schema(self, field: ModelField) -> str:
        ftype = field.field_type
        if ftype == "Int":
            return "z.coerce.number().int()"
        if ftype == "Float":
            return "z.coerce.number()"
        if ftype == "Boolean":
            return "z.boolean()"
        if ftype == "DateTime":
            return "z.coerce.date()"
        return "z.string()"


class BackendBridge:
    def __init__(
        self,
        output_dir: str = DEFAULT_OUTPUT_DIR,
        mapping_file: str = DEFAULT_MAPPING_FILE,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.mapping_file = Path(mapping_file)
        self.openapi_parser = OpenApiParser()
        self.prisma_parser = PrismaParser()
        self.text_parser = TextSpecParser()
        self.prisma_generator = PrismaGenerator()
        self.route_generator = RouteGenerator()
        self.action_generator = ActionGenerator()
        self.zod_schema_generator = ZodSchemaGenerator()

    def run(
        self,
        layout_ast: Dict[str, Any],
        openapi_path: Optional[str] = None,
        prisma_path: Optional[str] = None,
        text_spec_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        spec = self._load_spec(openapi_path, prisma_path, text_spec_path)
        if spec is None:
            raise ValueError("At least one backend spec input is required")

        mapper = SemanticMapper(spec)
        mapping = mapper.map(layout_ast)

        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "api").mkdir(exist_ok=True)
        (self.output_dir / "actions").mkdir(exist_ok=True)
        (self.output_dir / "lib").mkdir(exist_ok=True)

        schema_path = self.output_dir / "schema.prisma"
        schema_path.write_text(self.prisma_generator.generate(spec), encoding="utf-8")

        generated_routes: List[str] = []
        generated_actions: List[str] = []
        generated_schemas: List[str] = []
        seen_models: set = set()
        mapped_models: List[Model] = []
        zod_schemas: List[str] = []
        validation_rules: List[Dict[str, Any]] = []

        for m in mapping["mappings"]:
            model_name = m["model"]
            if model_name in seen_models:
                continue
            seen_models.add(model_name)
            model = spec.model_by_name(model_name)
            if model:
                mapped_models.append(model)
                zod_schemas.append(self.zod_schema_generator._schema_name(model_name))
                for f in model.fields:
                    if f.is_id:
                        continue
                    validation_rules.append({
                        "model": model_name,
                        "field": f.name,
                        "type": f.field_type,
                        "required": f.required,
                        "is_email": f.is_email,
                        "min_length": f.min_length,
                        "max_length": f.max_length,
                        "min_value": f.min_value,
                        "max_value": f.max_value,
                        "pattern": f.pattern,
                        "enum_values": f.enum_values,
                    })

            endpoint = next((e for e in spec.endpoints if e.request_model == model_name and e.method == "POST"), None)
            route_code = self.route_generator.generate(model_name, endpoint)
            route_path = self.output_dir / "api" / f"{self._slug(model_name)}.ts"
            route_path.write_text(route_code, encoding="utf-8")
            generated_routes.append(str(route_path))

            action_code = self.action_generator.generate(model_name, endpoint)
            action_path = self.output_dir / "actions" / f"{self._slug(model_name)}Action.ts"
            action_path.write_text(action_code, encoding="utf-8")
            generated_actions.append(str(action_path))

        if mapped_models:
            zod_schema_path = self.output_dir / "lib" / "schemas.ts"
            zod_schema_path.write_text(
                self.zod_schema_generator.generate(mapped_models),
                encoding="utf-8",
            )
            generated_schemas.append(str(zod_schema_path))

        mapping["generated_files"] = {
            "schema": str(schema_path),
            "routes": generated_routes,
            "actions": generated_actions,
            "schemas": generated_schemas,
        }
        mapping["zod_schemas"] = zod_schemas
        mapping["validation_rules"] = validation_rules
        self.mapping_file.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
        return mapping

    def _load_spec(
        self,
        openapi_path: Optional[str],
        prisma_path: Optional[str],
        text_spec_path: Optional[str],
    ) -> Optional[BackendSpec]:
        specs: List[BackendSpec] = []
        if openapi_path:
            specs.append(self.openapi_parser.parse(openapi_path))
        if prisma_path:
            specs.append(self.prisma_parser.parse(prisma_path))
        if text_spec_path:
            specs.append(self.text_parser.parse(text_spec_path))
        if not specs:
            return None
        merged = specs[0]
        for s in specs[1:]:
            merged.models.extend(s.models)
            merged.endpoints.extend(s.endpoints)
        return merged

    def _slug(self, name: str) -> str:
        return re.sub(r"([a-z])([A-Z])", r"\1-\2", name).lower()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backend Spec Bridge: map backend specs to UI and generate code")
    parser.add_argument("--openapi", help="Path to OpenAPI JSON/YAML spec")
    parser.add_argument("--prisma", help="Path to Prisma schema file")
    parser.add_argument("--text-spec", help="Path to structured text spec JSON")
    parser.add_argument("--layout-ast", default="layout_ast.json", help="Path to Tailwind AST JSON")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Directory for generated backend artifacts")
    parser.add_argument("--mapping-file", default=DEFAULT_MAPPING_FILE, help="Path for backend_mapping.json")
    args = parser.parse_args()

    ast = json.loads(Path(args.layout_ast).read_text(encoding="utf-8"))
    bridge = BackendBridge(output_dir=args.output_dir, mapping_file=args.mapping_file)
    result = bridge.run(
        ast,
        openapi_path=args.openapi,
        prisma_path=args.prisma,
        text_spec_path=args.text_spec,
    )
    print(f"[BACKEND] Mapping written to {args.mapping_file}")
    print(f"[BACKEND] Generated schema: {result['generated_files']['schema']}")
    print(f"[BACKEND] Generated routes: {len(result['generated_files']['routes'])}")
    print(f"[BACKEND] Generated actions: {len(result['generated_files']['actions'])}")


if __name__ == "__main__":
    main()
