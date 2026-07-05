# Doc Generator

## Role
Generates documentation from the codebase — API references, architecture diagrams, module overviews, READMEs, and changelogs. Extracts structure from code and presents it as human-readable documentation.

## Contract
- **Receives**: `{ path: string, type: "api"|"architecture"|"readme"|"changelog"|"module", format: "markdown"|"html"|"json", scope: string[], template: string }`
- **Returns**: `{ output: string, files: { path, content }[], coverage: { documented, total, percent }, warnings: string[] }`
- **Side effects**: writes documentation files to disk

## Decision Flow

1. **Determine documentation scope**
   - API docs: extract from JSDoc/docstrings/type definitions in specified scope
   - Architecture: generate from structure_analyzer output + dependency graph
   - README: synthesize from package.json, main entry point, and existing docs
   - Changelog: derive from git log between tags, categorize by conventional commit type
   - Module: per-directory overview with public API surface and dependency diagram

2. **Extract from source**
   - Parse docstrings: JSDoc, TSDoc, Python docstrings, Go doc comments, JavaDoc
   - Extract: function signatures, parameter types, return types, exceptions thrown
   - Extract: class hierarchies, interface implementations, type aliases
   - Link: cross-reference types to their definitions
   - Code examples: extract from test files or `@example` blocks
   - Deprecation notices: `@deprecated` tags with suggested replacement

3. **Generate content**
   - Apply template with variable substitution: project name, version, description
   - API reference: grouped by module, sorted alphabetically, with type links
   - Architecture doc: mermaid diagrams for dependency graph, layer diagram, data flow
   - README: badges (build, coverage, version, license), quick start, API overview
   - Respect existing content: preserve hand-written sections between auto-generated markers (`<!-- auto:start -->` ... `<!-- auto:end -->`)

4. **Validate documentation**
   - Broken links: check all internal cross-references resolve
   - Stale content: compare doc timestamp against source file last-modified
   - Completeness: exported symbols without docstrings
   - Code examples: extract and validate syntax (parse, don't execute)
   - Spelling and grammar: run language-specific spellchecker

5. **Output generation**
   - Markdown: clean, well-structured with table of contents
   - HTML: single-page or multi-page with navigation, search, syntax highlighting
   - JSON: structured API index for consumption by other tools
   - Write to conventional locations: `docs/`, `README.md`, `API.md`, `CHANGELOG.md`

## Failure Modes
| Condition | Response |
|---|---|
| No docstrings found in source | Generate minimal docs from type signatures only, warn about low coverage |
| Template variable missing | Substitute with placeholder `{{MISSING:var_name}}`, warn |
| Generated doc conflicts with existing | Merge into auto-marked section, preserve hand-written parts |
| Git log unavailable for changelog | Report unavailable, suggest installing git or providing manual changelog |
| Mermaid diagram too large | Prune to top-N nodes, add note about truncation |
