# Semantic Searcher

## Role
Finds code by meaning, not by exact text match. When the user asks "where is authentication logic?" rather than `grep "auth"`. Complements regex_searcher — each solves half the search problem.

## Contract
- **Receives**: `{ query: string, scope, index_id: string|null, options: { strategy: "keywords"|"embeddings"|"hybrid", max_results } }`
- **Returns**: `{ matches: [{ file, line, relevance_score, why: string }], match_count, search_time_ms }`
- **Side effects**: none (read-only, may call embedding service)

## Decision Flow

1. **Parse query intent**
   - Natural language question ("how does the login flow work?")
   - Entity search ("UserAuth class", "handleLogin function")
   - Concept search ("error handling", "database connection")
   - Determine strategy from query shape

2. **Execute by strategy**
   - **keywords**: extract key terms from query → search symbol table (names, comments, docstrings) → rank by term frequency and proximity
   - **embeddings**: vectorize query → cosine similarity against indexed code embeddings → highest similarity wins
   - **hybrid**: run both → merge results with weighted scoring (keywords 0.4, embeddings 0.6 by default)

3. **Code-specific signals**
   - Boost: symbol names that match query terms (function named `authenticate` for query "auth logic")
   - Boost: docstrings and comments near matching symbols
   - Boost: files whose path matches query terms (`auth/login.ts` for query "login")
   - Penalize: boilerplate, imports, generated code unless query targets them

4. **Rank and return**
   - Sort by relevance_score descending
   - Each result includes `why`: short explanation of what matched ("function name match", "docstring similarity", "file path match")
   - Cap at `max_results`

## Failure Modes
| Condition | Response |
|---|---|
| Query too vague ("fix it", "the thing") | Ask for clarification via `why: "query too vague, suggest rephrasing"` |
| No semantic matches (all scores < threshold) | Return empty + suggest alternative search terms |
| Embedding service unavailable | Fall back to keywords-only, note in metadata |
| Query language doesn't match code language | Still search (concepts transcend language), note mismatch |
| Very large scope with no embeddings index | Warn about speed, fall back to keywords-only |
