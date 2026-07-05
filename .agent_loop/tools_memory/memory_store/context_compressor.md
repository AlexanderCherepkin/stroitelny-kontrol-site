# Context Compressor

## Role
Compresses conversation context for memory storage — extracts salient information, removes redundancy, preserves decisions and intent, and fits within context window budgets. Bridges raw conversation to structured memory.

## Contract
- **Receives**: `{ content: string, target_size: int, preserve: ("decisions"|"facts"|"actions"|"intent"|"errors"|"all")[], format: "summary"|"bullets"|"structured" }`
- **Returns**: `{ compressed: string, original_size: int, compressed_size: int, ratio: float, extracted: ExtractedItem[], fidelity_estimate: float }`
- **Side effects**: none (pure transformation)

## Decision Flow

1. **Analyze input content**
   - Tokenize: count tokens (not characters) for accurate size estimation
   - Segment: split into logical sections (user messages, assistant responses, tool calls, results)
   - Classify segments: decision made, fact stated, action taken, error encountered, filler
   - Information density: bits of novel information per segment
   - Redundancy: repeated information across segments

2. **Extract salient items**
   - Decisions: "we decided to use X because Y" → structured decision record
   - Facts: "the database schema has N tables" → factoid
   - Actions: "ran migration 0042, took 3.2s, succeeded" → action log entry
   - Intent: "the goal is to implement user authentication" → goal statement
   - Errors: "build failed with type error in auth.ts:42" → error record with context
   - Dependencies: "blocked by PR #342" → dependency link
   - Filter out: greetings, acknowledgments, repetition, formatting noise

3. **Compress by strategy**
   - Summarization: condense paragraphs to key points
   - Omission: drop low-information segments entirely
   - Generalization: replace specific examples with general patterns
   - Construction: combine related segments into concise statement
   - Prioritization: retain high-priority information first, trim low-priority
   - Hybrid: use multiple strategies, select best by compression ratio × fidelity

4. **Fit to target size**
   - Greedy: add items in priority order until token budget exhausted
   - Budget allocation: X% decisions, Y% facts, Z% actions
   - Truncation indicator: `[... N items omitted due to size]`
   - Progressive: generate at multiple sizes, return best fit under budget
   - Hard cutoff: never exceed target_size tokens

5. **Estimate fidelity**
   - Coverage: what fraction of extracted items made it into compressed output?
   - Information preservation: did any unique information get dropped?
   - Hallucination check: did compression introduce any new claims not in original?
   - Key decision check: were all marked decisions preserved?
   - Fidelity score: 0–1, where 1 = all critical information preserved

## Failure Modes
| Condition | Response |
|---|---|
| Content entirely filler (no signal) | Return empty compressed output, note "no extractable information" |
| Target size too small (<10 tokens) | Return minimum viable compression, warn about extreme information loss |
| Language detection fails (mixed languages) | Process each segment in detected language, flag mixed-language content |
| Compression introduces ambiguity | Flag ambiguous passages, mark lower fidelity, suggest human review |
| Critical information would be lost at target size | Return best-effort + explicit list of dropped critical items |
