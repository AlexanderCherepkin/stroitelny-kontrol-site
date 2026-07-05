# Community 26

> 24 nodes

## Key Concepts

- **ContextCompressor** (20 connections) — `runtime/workers/context_compressor.py`
- **Any** (7 connections) — `runtime/workers/context_compressor.py`
- **.compress()** (7 connections) — `runtime/workers/context_compressor.py`
- **._estimate_saved_tokens()** (4 connections) — `runtime/workers/context_compressor.py`
- **._manual_summary()** (4 connections) — `runtime/workers/context_compressor.py`
- **CompressionSummary** (3 connections) — `runtime/workers/context_compressor.py`
- **.add_trace()** (3 connections) — `runtime/workers/context_compressor.py`
- **._build_summary_prompt()** (3 connections) — `runtime/workers/context_compressor.py`
- **._call_llm_summary()** (3 connections) — `runtime/workers/context_compressor.py`
- **.get_compressed_trace()** (3 connections) — `runtime/workers/context_compressor.py`
- **Context Isolation Architecture** (3 connections) — `runtime/workers/context_isolator.py`
- **context_compressor.py** (2 connections) — `runtime/workers/context_compressor.py`
- **.__init__()** (2 connections) — `runtime/workers/context_compressor.py`
- **.should_compress()** (2 connections) — `runtime/workers/context_compressor.py`
- **.stats()** (2 connections) — `runtime/workers/context_compressor.py`
- **Result of compressing a batch of traces.** (1 connections) — `runtime/workers/context_compressor.py`
- **Call the LLM engine to generate a summary.** (1 connections) — `runtime/workers/context_compressor.py`
- **Fallback summarization without LLM.** (1 connections) — `runtime/workers/context_compressor.py`
- **Estimate tokens kept out of the parent context.** (1 connections) — `runtime/workers/context_compressor.py`
- **Returns a synthetic trace entry representing the latest summary.** (1 connections) — `runtime/workers/context_compressor.py`
- **Summarizes pipeline iteration traces after every N steps.      Keeps the parent'** (1 connections) — `runtime/workers/context_compressor.py`
- **Buffer a raw trace for potential later compression.** (1 connections) — `runtime/workers/context_compressor.py`
- **Returns True if compression should run after this iteration.** (1 connections) — `runtime/workers/context_compressor.py`
- **Summarize buffered traces via LLM and return a summary record.** (1 connections) — `runtime/workers/context_compressor.py`

## Relationships

- [[Community 7]] (3 shared connections)
- [[Community 1]] (2 shared connections)
- [[Community 13]] (2 shared connections)
- [[Community 30]] (1 shared connections)
- [[Community 24]] (1 shared connections)

## Source Files

- `runtime/workers/context_compressor.py`
- `runtime/workers/context_isolator.py`

## Audit Trail

- EXTRACTED: 70 (91%)
- INFERRED: 7 (9%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*