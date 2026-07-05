# Read Optimizer

## Role
Cross-cutting strategist. Analyzes the read request and selects the optimal pipeline configuration — which agents to run, in what order, with what parameters. Maximizes speed and minimizes resource use.

## Contract
- **Receives**: `{ request: { paths, query }, constraints: { latency_budget_ms, memory_limit_mb, token_budget } }`
- **Returns**: `{ plan: { pipeline: [agent_name], params: {...}, strategy: "streaming"|"buffered"|"parallel" }, estimated_cost: { time_ms, memory_mb, tokens } }`
- **Side effects**: none (planning only — execution is upstream)

## Decision Flow

1. **Analyze request shape**
   - Single file, small (<100 KB) → simplest path: full read, skip chunking
   - Single file, large (>1 MB) → enable chunking, streaming strategy
   - Multiple files → consider parallel reads
   - Directory scan → glob expand first, then parallel
   - Query present → route to content_extractor after parser

2. **Select strategy**
   - **Streaming**: for large files where latency matters. Read in sequential chunks, process incrementally.
   - **Buffered**: for small-to-medium files. Read once, process in memory. Fastest per-byte, highest memory.
   - **Parallel**: for multiple independent files. Run N read pipelines concurrently. Best for many small files.

3. **Configure pipeline**
   - Skip `cache_agent` if `request.skip_cache` is set or TTL is 0
   - Skip `chunking_agent` if file fits within `max_chunk_size`
   - Skip `encoding_agent` if content is known UTF-8 (saves detection cost)
   - Skip `content_extractor` if no query is provided (full read, not targeted)
   - Always include `path_resolver` + `permission_agent` (safety, never skippable)
   - Always include `parser_agent` to convert raw text into a structured representation before extraction or downstream use
   - Always include `integrity_checker` + `result_formatter` (quality gate, never skippable)

4. **Estimate cost**
   - Time: I/O time (file size / disk speed) + processing time (size × complexity factor)
   - Memory: peak allocation (largest intermediate structure × parallelism)
   - Tokens: input tokens from chunked reads (for LLM consumption)

5. **Validate against constraints**
   - Estimated time > latency budget → try parallel strategy or increase chunk size
   - Estimated memory > memory limit → reduce parallelism, use streaming
   - Estimated tokens > token budget → increase chunk overlap, reduce max_chunk_size, or prioritize files
   - If no configuration satisfies all constraints → return best-effort plan with constraint violations flagged

## Failure Modes
| Condition | Response |
|---|---|
| All strategies violate constraints | Return best-effort plan + violation report, let caller decide |
| Request is empty (no paths) | Return empty plan, no error |
| Path list is huge (>1000 files) | Warn, suggest batching, cap parallelism |
| Conflicting constraints (low latency + low memory) | Prioritize latency, flag memory as at-risk |
| Unknown file size (streaming source) | Assume worst-case (max file size), plan conservatively |
