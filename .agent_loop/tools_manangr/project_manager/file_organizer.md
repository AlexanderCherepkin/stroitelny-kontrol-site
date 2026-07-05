# File Organizer

## Role
Organizes project files — enforces naming conventions, detects misplaced files, plans and executes file moves/renames with dependency-aware safety. The structural housekeeping agent.

## Contract
- **Receives**: `{ path: string, action: "audit"|"plan"|"execute", rules: Convention[], dry_run: bool, update_imports: bool }`
- **Returns**: `{ violations: Violation[], plan: MovePlan[], executed: MoveResult[], stats: { moved, renamed, skipped, failed } }`
- **Side effects**: moves/renames files on disk (execute action only), updates import paths

## Decision Flow

1. **Audit current state**
   - Scan all files against naming conventions
   - Check: file name case (snake_case, camelCase, kebab-case, PascalCase)
   - Check: file-extension-to-directory mapping (.test.ts in __tests__/, .css in styles/)
   - Check: file size outliers (empty files, oversized files >1000 LOC)
   - Check: index/barrel files vs named files ratio
   - Check: dead files — not imported by any other file, not in build config
   - Report violations with severity: error (breaks build), warning (convention break), info (suggestion)

2. **Generate organization plan**
   - For each misplaced file: compute target path from naming rules
   - For each dead file: suggest archive or deletion
   - For oversized files: suggest split points (class boundaries, function groups)
   - For misplaced tests: co-locate with source or move to test directory
   - Dependency-aware ordering: move least-depended-on files first
   - Group moves into atomic batches: files in same batch have no inter-dependencies

3. **Validate plan safety**
   - Each move: check target path does not exist (or is identical)
   - Each rename: check all import references are resolvable to new path
   - Cross-reference with dependency graph: verify no broken imports after all moves
   - Git-aware: ensure moved files retain git history (`git mv` where possible)
   - CI-aware: check if build configs, Dockerfiles, CI scripts reference old paths
   - Generate rollback plan: reverse move list with pre-move state snapshot

4. **Execute (if not dry_run)**
   - Create target directories if needed
   - Move files with `git mv` (preserves history) or `mv` (no git)
   - If `update_imports`: walk all source files, rewrite import paths to new locations
   - If `update_imports`: update config files (tsconfig paths, webpack aliases, jest moduleNameMapper)
   - Batch commits: one commit per logical group with descriptive message

5. **Post-move validation**
   - Verify no broken imports remain (re-run dependency_mapper)
   - Verify build passes (delegate to build_manager clean + compile)
   - Verify tests pass (delegate to build_manager test)
   - If any check fails: attempt auto-fix or rollback

## Failure Modes
| Condition | Response |
|---|---|
| Target path already exists | Append suffix, warn about conflict, suggest manual merge |
| Import path rewrite would break string literals | Skip that reference, flag for manual review |
| Git history preservation failed | Fall back to plain move, note history loss in report |
| Rollback fails mid-execution | Halt, report irrecoverable state, list manually-fixable items |
| Cyclic import created by move | Reject that specific move, continue with rest of plan |
