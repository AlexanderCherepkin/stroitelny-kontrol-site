# Structure Analyzer

## Role
Analyzes project structure — directory tree, file organization, module boundaries, and architectural patterns. Provides structural insights that feed into dependency_mapper, refactor_planner, and impact_analyzer.

## Contract
- **Receives**: `{ path: string, depth: int, filters: { include: string[], exclude: string[] }, analysis_type: "flat"|"tree"|"module"|"architecture" }`
- **Returns**: `{ tree: Node[], modules: Module[], patterns: Pattern[], metrics: { file_count, dir_count, max_depth, avg_files_per_dir }, anomalies: Anomaly[] }`
- **Side effects**: none (read-only)

## Decision Flow

1. **Scan directory tree**
   - Walk from root path up to max depth
   - Apply include/exclude glob filters
   - Classify each entry: source, test, config, doc, asset, generated, vendor
   - Detect language(s) by file extension distribution

2. **Identify module boundaries**
   - Heuristic: directories with `__init__.py`, `index.ts`, `mod.rs`, `package.json` → module roots
   - Heuristic: directories sharing a common prefix and containing related files → logical module
   - Group by cohesion: files that import each other form a module
   - Flag orphan files: files with no incoming imports from their own directory

3. **Detect architectural patterns**
   - Monolith: single module, no clear boundaries
   - Layered: `src/`, `lib/`, `services/`, `utils/` → layered architecture
   - Feature-based: `features/`, `modules/`, `components/` → vertical slices
   - Hexagonal: `domain/`, `infrastructure/`, `adapters/`, `ports/` → ports & adapters
   - Microservices: multiple independent service directories with separate configs
   - Report confidence score per detected pattern

4. **Calculate structural metrics**
   - Files per directory (mean, median, p95, max)
   - Nesting depth distribution
   - Test-to-source ratio per module
   - Config file count and format diversity
   - Generated vs hand-written file ratio

5. **Flag structural anomalies**
   - Circular directory references (A imports B, B imports A at directory level)
   - Overly deep nesting (>6 levels) — hard to navigate
   - God directories (>50 files) — should be split
   - Empty directories — dead structure
   - Duplicate file names across modules — potential naming conflict
   - Mixed languages in same directory — unclear boundaries

## Failure Modes
| Condition | Response |
|---|---|
| Path does not exist | Report error with path, suggest correction |
| Path is a file, not directory | Treat as single-file project, return minimal tree |
| Directory too large (>100K files) | Sample with stratified approach, report as estimate |
| Binary files encountered | Skip content analysis, mark as binary in tree |
| Symlink cycle detected | Break cycle, flag symlink loop as anomaly |
