# Result Mapper

## Role
Maps raw database rows into typed application objects — struct/class hydration, relationship assembly, lazy-loading proxies, and format conversion. Transforms flat SQL result sets into domain models and nested object graphs.

## Contract
- **Receives**: `{ rows: any[], mapping: MappingConfig, target: "object"|"json"|"csv"|"nested"|"graph", type_def?: TypeDefinition }`
- **Returns**: `{ result: any | any[], metadata: { row_count, mapped_count, skipped_count, warnings } }`
- **Side effects**: none (pure transformation)

## Decision Flow

1. **Resolve mapping strategy**
   - Auto-map: column names → object properties by naming convention (user_id → userId)
   - Explicit map: user-provided column-to-field mapping
   - ORM map: use existing ORM entity definitions (TypeORM, Prisma, SQLAlchemy models)
   - Type inference: VARCHAR → string, INTEGER → number, BOOLEAN → boolean, JSON → parsed object, TIMESTAMP → Date
   - Nullable columns → optional/nullable fields, non-nullable → required fields

2. **Transform row values**
   - Type coercion: string "123" → number 123 if target is integer
   - Date parsing: ISO 8601 string → Date/Timestamp object
   - JSON parsing: stringified JSON → nested object/array
   - Enum mapping: DB enum value → application enum constant
   - Binary: hex string → Buffer/Uint8Array
   - Decimal: string → BigDecimal (avoid floating point loss)
   - Null: null/None/undefined per target language convention

3. **Assemble relationships**
   - Nested: single query with JOINs → nested object tree (user with orders with items)
   - Batch: separate queries → stitch by foreign key (avoid N+1)
   - Lazy: populate placeholder proxy → real query only if accessed (opt-in N+1)
   - Detect circular references: user → posts → user → break at second appearance
   - Deduplicate: same entity referenced multiple times → single object instance

4. **Format conversion**
   - Object: typed struct/class instances with methods
   - JSON: plain objects, camelCase keys, ISO dates, no circular refs
   - CSV: flat rows, arrays in columns as JSON strings, dates as ISO
   - Graph: nodes + edges for visualization (schema_analyzer relationships)
   - Nested: hierarchical by foreign key (parent → children → grandchildren)

5. **Validation**
   - Missing required fields → flag, fill with null, warn
   - Type mismatch with coercion failure → flag, keep original, warn
   - Extra columns not in mapping → include or strip per config
   - Truncation: string too long for target type → flag
   - Report: mapping coverage (mapped/total columns), any skipped rows

## Failure Modes
| Condition | Response |
|---|---|
| Ambiguous column name (same name in joined tables) | Prefer table-qualified name, warn, suggest alias in query |
| Type coercion loss (float→int truncation) | Refuse to coerce, return original value, flag precision loss |
| Circular reference in nested mapping | Break at duplicate, insert `"__circular_ref": "EntityType#id"` |
| NULL in non-nullable target field | Flag as mapping error, use zero-value for field, warn |
| JSON parse failure on JSON column | Return raw string, flag malformed JSON, suggest column type check |
