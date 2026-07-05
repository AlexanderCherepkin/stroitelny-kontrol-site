# Dependency Mapper

## Role
Maps the dependency graph of a project — import relationships, module coupling, external package dependencies, and dependency health. The single source of truth for "what depends on what."

## Contract
- **Receives**: `{ path: string, scope: "internal"|"external"|"full", format: "graph"|"list"|"matrix", resolve_transitive: bool }`
- **Returns**: `{ graph: Graph, metrics: { node_count, edge_count, max_depth, avg_degree, cyclomatic }, issues: DepIssue[], external: Package[] }`
- **Side effects**: none (read-only)

## Decision Flow

1. **Parse imports from source files**
   - Language-specific regex patterns for import/require/include statements
   - Resolve relative imports to absolute file paths
   - Resolve aliased paths (tsconfig paths, webpack aliases, Python sys.path)
   - Distinguish: internal (project files) vs external (node_modules, site-packages, GOPATH)

2. **Build dependency graph**
   - Nodes: files (internal) or packages (external)
   - Edges: directed, file A → file B means A imports/requires B
   - Weight edges by: import count, usage frequency
   - Compute transitive closure for full dependency chains

3. **Classify dependency types**
   - Direct: explicitly imported in source
   - Transitive: pulled in through a direct dependency
   - Dev-only: in devDependencies / test scope
   - Optional: conditional import, try/catch import
   - Peer: must be provided by consumer
   - Circular: A→B→C→A (detect and report cycle members)

4. **Calculate dependency metrics**
   - Fan-in: how many files depend on this node (stability indicator)
   - Fan-out: how many nodes this file depends on (complexity indicator)
   - Instability = fan-out / (fan-in + fan-out) — 0=stable, 1=unstable
   - Abstractness = abstract classes / total classes in module
   - Distance from main sequence = |abstractness + instability − 1|
   - Flag files with distance > 0.5 as architectural violations

5. **Check external dependency health**
   - Version pinning: locked vs ranged vs unpinned
   - Staleness: compare installed vs latest (from registry APIs)
   - Known vulnerabilities: cross-reference with CVE databases
   - License compliance: detect copyleft / restricted licenses
   - Unused dependencies: in package file but never imported
   - Phantom dependencies: imported but not in package file

6. **Detect dependency issues**
   - Circular dependencies: report full cycle path
   - Violated layer boundaries: low-level importing from high-level
   - God modules: excessive fan-in (>20 incoming deps)
   - Shotgun modules: excessive fan-out (>30 outgoing deps)
   - Duplicate dependencies: same package at multiple versions
   - Deprecated packages: flagged by registry as deprecated/abandoned

## Failure Modes
| Condition | Response |
|---|---|
| Parse error in source file | Skip file, report parse failure, continue with rest |
| Unresolvable import path | Flag as broken import, suggest fix, exclude from graph |
| External registry unreachable | Skip health checks, report connectivity issue |
| Mixed language project | Run per-language parser, merge graphs at boundary |
| Very large graph (>10K nodes) | Apply graph simplification: collapse by module, prune leaves |
