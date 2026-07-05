# Summarizer

## Role
Generates summaries of memory content — creates titles, descriptions, and multi-level condensations for fast browsing and context-aware retrieval. Makes memory skimmable.

## Contract
- **Receives**: `{ content: string, level: "title"|"oneliner"|"short"|"detailed", target_length?: int, focus?: string[], audience?: string }`
- **Returns**: `{ summary: string, title: string, keywords: string[], compression_ratio: float, confidence: float }`
- **Side effects**: none (pure generation)

## Decision Flow

1. **Content analysis**
   - Detect type: conversation, documentation, code, log, decision record
   - Identify key entities: people, projects, files, dates, metrics
   - Identify sentiment/urgency: neutral, positive, negative, critical
   - Extract topic distribution: what subjects are covered and in what proportion
   - Note contradictions: places where content says two conflicting things

2. **Title generation**
   - Length: 5–12 words, actionable noun phrase
   - Pattern: "Decision: [what]" / "Incident: [what happened]" / "Note: [topic]"
   - Include: main entity + primary action/state
   - Avoid: dates (they go in metadata), vague words ("stuff", "things", "update")
   - Multiple candidates: generate 3, score by informativeness × conciseness

3. **Summary by level**
   - `oneliner`: 1 sentence, <30 words — answers "what is this entry about?"
   - `short`: 2–4 sentences, <100 words — adds key details and outcome
   - `detailed`: paragraph per topic, <500 words — structured with bullet points
   - Preserve: decisions, action items, error details, links to other memories
   - Drop: greetings, filler, formatting, repeated information
   - Front-load: most important information first (inverted pyramid)

4. **Keyword extraction**
   - Frequency: term frequency normalized by corpus frequency
   - Named entities: file paths, function names, project names, people
   - Phrases: 2–3 word collocations that appear together
   - Filter: remove stop words, keep domain-specific terms
   - Count: return top 5–10 keywords ranked by relevance

5. **Quality estimation**
   - Coverage: does summary capture all main topics?
   - Faithfulness: does summary contradict or add to original?
   - Coherence: does summary read as natural text?
   - Confidence: composite score 0–1 based on above metrics
   - Low confidence (<0.6): flag for human review alongside summary

## Failure Modes
| Condition | Response |
|---|---|
| Content too short to summarize (<50 chars) | Return content as-is with note "too short to summarize" |
| Content is non-text (code, JSON, log) | Generate structural summary (file types, line counts, key symbols) |
| Summarization introduces hallucination | Flag low confidence, mark passages as uncertain, suggest verification |
| Mixed-language content | Summarize in dominant language, quote other-language passages verbatim |
| Key information ambiguous | Preserve ambiguity rather than resolving incorrectly, note uncertainty |
