# Search Optimizer

## Role
Cross-cutting strategist for the search pipeline. Analyzes the query and scope, chooses search strategies, allocates resources, and merges results into a unified response. The conductor of the search orchestra.

## Contract
- **Receives**: `{ query, scope, constraints: { latency_budget_ms, max_results, token_budget } }`
- **Returns**: `{ plan: { searchers: ["regex"|"semantic"|"both"], index_strategy, parallel: bool }, estimated_cost: { time_ms, files_scanned } }`
- **Side effects**: none (planning only)

## Decision Flow

1. **Analyze query type**
   - Contains regex special chars (`.*+?[]{}()|^$\` ) → route to regex_searcher
   - Natural language question (>5 words, contains "how", "where", "what") → route to semantic_searcher
   - Short identifier-like string (`authLogin`, `UserClass`) → route to BOTH (symbol match + semantic)
   - Mixed (regex + natural language) → both, merge results
   - Explicit query type override → respect user choice

2. **Assess index availability**
   - Fresh index exists → use it, skip indexer_agent in pipeline
   - Stale index → decide: rebuild (if scope is large) or full scan (if scope is small)
   - No index → quick build (if scope < 1000 files) or full scan with parallelism
   - Tradeoff: index build costs O(files) up front but O(1) per search after

3. **Resource allocation**
   - Small scope (<100 files) → serial full scan, skip index overhead
   - Medium scope (100-1000 files) → build/use index, single searcher
   - Large scope (>1000 files) → build index, run regex + semantic in parallel
   - Parallelism cap: 4 concurrent searchers max

4. **Pipeline configuration**
   - Safety chain (always): scope_detector → permission_agent
   - Indexing (conditional): indexer_agent (if index needed)
   - Search (parallel or serial): regex_searcher + semantic_searcher
   - Post-processing chain: relevance_scorer → deduplicator → snippet_builder
   - diff_generator runs independently, only when explicitly requested

5. **Validate plan**
   - Estimated time > latency budget → reduce scope or use index instead of full scan
   - Estimated results > max_results → tighten relevance threshold
   - No feasible plan → return best-effort with violations flagged

## Failure Modes
| Condition | Response |
|---|---|
| Query is empty | Return empty plan, request query clarification |
| No searcher applicable | Return error + suggest query reformulation |
| All strategies exceed latency budget | Return best-effort plan + violation report |
| Scope + query combination is too broad | Suggest scope narrowing before executing |
| Index rebuild required but scope is huge | Warn + offer incremental index update as faster alternative |
