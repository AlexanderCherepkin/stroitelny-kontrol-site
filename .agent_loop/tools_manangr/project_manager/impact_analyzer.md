# Impact Analyzer

## Role
Analyzes the impact of a proposed or actual change on the project — which files, modules, tests, and downstream consumers are affected, and how severely. The "what breaks if I change this?" answering machine.

## Contract
- **Receives**: `{ change: { type: "file"|"symbol"|"dependency"|"config", target: string, from?: string, to?: string }, depth: "direct"|"transitive"|"full" }`
- **Returns**: `{ impact: ImpactResult, affected: AffectedNode[], risk_score: number 0-100, test_gap: string[], recommendations: string[] }`
- **Side effects**: none (read-only)

## Decision Flow

1. **Identify change type and scope**
   - File change: one or more files modified (diff input)
   - Symbol change: function/class/type renamed, added, removed, or signature changed
   - Dependency change: external package added, removed, or version bumped
   - Config change: build flag, env variable, or runtime setting modified
   - Determine analysis depth: direct (immediate dependents), transitive (full dependency chain), full (including test and config impact)

2. **Trace direct dependents**
   - From dependency graph: all files that import the changed file/symbol
   - From type system: all files using the changed type/interface
   - From config references: all code referencing the changed config key
   - From build graph: all targets that depend on the changed target
   - Classify by coupling: direct call, type reference, string reference, config reference

3. **Trace transitive impact**
   - Breadth-first walk: for each direct dependent, find what depends on IT
   - Apply dependency graph transitive closure
   - Stop at: module boundaries (if change is internal), public API (if library), or max depth
   - Weight by distance: direct = 1.0x, 1 hop = 0.5x, 2 hops = 0.25x, etc.

4. **Assess test impact**
   - Map affected source files to their test files
   - Identify uncovered affected paths (test gap)
   - Flag tests that will break: snapshot tests, type-only tests, integration tests
   - Estimate test update effort: number of test files × average test complexity

5. **Calculate risk score (0–100)**
   - Blast radius component: count of affected files / total project files
   - Coupling component: average fan-out of changed files
   - Test coverage component: 1 − (covered_lines / affected_lines)
   - API surface component: is public API changed? (binary: +30)
   - Config component: is runtime behavior gated by config? (−15 if gated)
   - Sum weighted components, clamp to 0–100

6. **Generate recommendations**
   - If risk > 70: suggest feature flag, canary deploy, phased rollout
   - If test gap > 20%: suggest adding tests before change
   - If transitive impact spans teams: suggest cross-team review
   - If dependency change: suggest reading changelog for breaking changes
   - Generate impact report: summary, heatmap of affected areas, action items

## Failure Modes
| Condition | Response |
|---|---|
| Dependency graph unavailable | Build it first (delegate to dependency_mapper), warn about stale analysis |
| Change description ambiguous | Ask for clarification, return partial analysis with assumptions listed |
| Symbol not found in codebase | Report as unknown symbol, suggest possible alternatives |
| Impact spans >50% of codebase | Flag as architectural change — requires refactor_planner, not just impact analysis |
| Type information unavailable (dynamic language) | Fall back to name-based heuristics, flag lower confidence |
