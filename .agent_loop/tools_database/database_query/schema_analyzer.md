# Schema Analyzer

## Role
Analyzes database schema — tables, columns, indexes, constraints, relationships, and schema health. The structural understanding engine for any database backend.

## Contract
- **Receives**: `{ connection: ConnectionConfig, scope: "full"|"table"|"indexes"|"constraints"|"relationships", target?: string }`
- **Returns**: `{ schema: Schema, tables: TableDef[], relationships: Relationship[], indexes: IndexDef[], metrics: SchemaMetrics, issues: SchemaIssue[] }`
- **Side effects**: none (read-only)

## Decision Flow

1. **Connect and introspect**
   - Query `information_schema.tables` / `pg_catalog` / `sqlite_master` for table list
   - Query `information_schema.columns` for column definitions per table
   - Classify column types: integer, float, decimal, text, varchar, boolean, date, timestamp, json, blob, enum
   - Detect ORM meta-tables (sequelize, typeorm, prisma, alembic, knex) and flag

2. **Analyze table structure**
   - Per table: column name, type, nullable, default value, ordinal position
   - Detect: primary key (single or composite), natural vs surrogate keys
   - Detect: generated columns, computed columns, virtual columns
   - Flag: tables without primary keys, tables with >50 columns, tables with only nullable columns

3. **Analyze indexes**
   - List all indexes: name, columns, unique flag, partial filter, method (btree, hash, gin, gist)
   - Detect: missing indexes — foreign key columns without index, frequently queried columns
   - Detect: redundant indexes — index A on (a,b) makes index B on (a) redundant
   - Detect: unused indexes — no scans in pg_stat_user_indexes or equivalent
   - Composite index column order vs query pattern mismatch

4. **Analyze constraints**
   - Foreign keys: source table+column → target table+column, ON DELETE/UPDATE action
   - Unique constraints: single column or composite
   - Check constraints: parse constraint expression, flag complex/non-obvious ones
   - Not-null constraints on columns with default values
   - Detect: missing FK constraints where naming convention suggests relationship (user_id, order_id)

5. **Infer relationships**
   - Explicit: foreign key constraints → documented relationships
   - Implicit: column naming patterns (entity_id) without FK → undocumented relationships
   - One-to-one: FK + unique constraint on FK column
   - One-to-many: FK without unique constraint (standard)
   - Many-to-many: junction tables (two FK columns + composite PK)
   - Self-referencing: FK pointing to same table (tree/hierarchy)

6. **Calculate schema health**
   - Normalization level: 1NF, 2NF, 3NF, BCNF heuristics
   - Data type issues: text for dates, varchar for enums, missing timezone on timestamps
   - Naming inconsistencies: mixed conventions (snake vs camel), prefix/suffix variations
   - Table bloat: unused tables, empty tables, tables with only soft-deleted rows
   - Generate health score and prioritized fix list

## Failure Modes
| Condition | Response |
|---|---|
| Connection refused | Report connection error with host:port, suggest checking credentials |
| Permission denied on information_schema | Fall back to dialect-specific introspection, flag limited visibility |
| Schema too large (>1000 tables) | Paginate analysis, prioritize by table size, report sampling |
| Unrecognized column type | Flag as unknown, report raw type string, suggest manual review |
| Circular FK detected | Flag cycle, report participants, note that schema analysis may be incomplete |
