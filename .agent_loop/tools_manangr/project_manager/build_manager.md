# Build Manager

## Role
Manages the build lifecycle — compilation, linting, testing, packaging — across language ecosystems. The single entry point for any build operation regardless of project language or toolchain.

## Contract
- **Receives**: `{ target: string, action: "compile"|"lint"|"test"|"package"|"clean"|"full", config: { toolchain, flags, env, parallel_jobs } }`
- **Returns**: `{ status: "success"|"failure"|"partial", artifacts: [{ path, type, size }], logs: string, duration_ms: int }`
- **Side effects**: produces build artifacts on disk

## Decision Flow

1. **Detect toolchain**
   - Scan project root for build files: `package.json` → npm/yarn/pnpm, `Makefile` → make, `CMakeLists.txt` → cmake, `Cargo.toml` → cargo, `go.mod` → go, `pom.xml` → maven, `build.gradle` → gradle, `pyproject.toml` → poetry/pip, `setup.py` → setuptools
   - Respect lock files: `package-lock.json`, `yarn.lock`, `Cargo.lock`, `go.sum` → pinned versions
   - If multiple toolchains detected → run in dependency order, stop on first failure

2. **Resolve build order (DAG)**
   - Read dependency graph from dependency_mapper
   - Topological sort: build leaves first, then dependents
   - Parallelizable groups: same-depth nodes can build concurrently
   - Cyclic dependencies → flag as error, cannot build

3. **Execute build phase**
   - `clean`: remove previous artifacts (`dist/`, `build/`, `target/`, `*.o`, `*.class`)
   - `compile`: source → object code / bytecode / transpiled output
   - `lint`: run configured linter (ESLint, ruff, clippy, golangci-lint, checkstyle)
   - `test`: delegate to runtest framework (unit → integration → e2e)
   - `package`: bundle artifacts (tar, zip, docker image, wheel, jar, binary)
   - `full`: clean → compile → lint → test → package (full pipeline)

4. **Capture and classify output**
   - stdout: build progress, success messages, artifact paths
   - stderr: warnings (yellow), errors (red) → delegate to error_analyzer
   - Exit code: 0 = success, non-zero = classify (compile error, linker error, test failure, lint violation)
   - Extract artifact manifest: file path, type, size, checksum

5. **Cache and incremental builds**
   - Track input hashes (source files, config, toolchain version)
   - Cache hit: skip rebuild, return cached artifacts
   - Cache miss or config change: full rebuild
   - Stale cache detection: any input hash changed → invalidate downstream

## Failure Modes
| Condition | Response |
|---|---|
| Toolchain not installed | Report missing tool + install command, do not proceed |
| Build timeout (compile hangs) | Kill with SIGTERM, escalate to SIGKILL, capture partial output |
| Out of memory during build | Reduce parallel_jobs, retry, report if still failing |
| Artifact path conflict | Append unique suffix, warn about conflict |
| Mixed toolchains with conflicting flags | Isolate per-toolchain, run serially, merge results |
