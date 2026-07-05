# Scope Detector

## Role
Determines the search universe — which directories, file types, and patterns to include or exclude. Transforms "search the codebase" into a precise, bounded target set.

## Contract
- **Receives**: `{ target: string, options: { include_paths, exclude_paths, file_types, max_depth, respect_gitignore } }`
- **Returns**: `{ roots: [path], include_globs: [glob], exclude_globs: [glob], estimated_file_count }`
- **Side effects**: none (read-only filesystem scan)

## Decision Flow

1. **Resolve target**
   - Explicit paths provided → use directly, validate each
   - Bare name (`"auth module"`) → scan project structure for matching directories/files
   - `.` or empty → entire project root
   - Multiple targets → union of all resolved paths

2. **Build include set**
   - File type filters: `.ts,.tsx,.js,.py,.go,.rs,.java` etc. → convert to extension globs
   - Pattern filters: `src/**`, `lib/**` → explicit include paths
   - No include filters → all files in root
   - Merge with defaults from project config

3. **Build exclude set**
   - Standard ignores: `node_modules/`, `.git/`, `dist/`, `build/`, `__pycache__/`, `.next/`, `coverage/`
   - Respect `.gitignore` if flag is set
   - Add user-specified exclusions
   - Hidden files/directories excluded by default unless explicitly included

4. **Estimate scope size**
   - Quick file count estimation (list directories, not stat every file)
   - Flag if scope is empty (no matching files)
   - Flag if scope is unusually large (>10K files) — suggest narrowing

5. **Return bounded scope**
   - Absolute paths for roots
   - Compiled glob patterns for includes/excludes
   - Estimated file count for optimizer to allocate resources

## Failure Modes
| Condition | Response |
|---|---|
| Target path doesn't exist | Return empty scope + suggestion |
| Scope is empty (no files match filters) | Return empty + report which filter excluded everything |
| Scope too large (>10K files) | Return scope but warn, suggest narrowing |
| Mixed file types without explicit filter | Include all, but note ambiguity in metadata |
| Target is a file, not directory | Return single-file scope, valid for targeted search |
