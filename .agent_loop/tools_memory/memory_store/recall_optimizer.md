# Recall Optimizer

## Role
Optimizes memory recall — relevance scoring, query expansion, personalized ranking, and result diversification. Ensures the most useful memories surface first for any given query.

## Contract
- **Receives**: `{ query: string, context: RecallContext, results: MemoryEntry[], strategy: "precision"|"recall"|"balanced" }`
- **Returns**: `{ ranked: RankedEntry[], expanded_queries: string[], relevance_model: string, confidence: float }`
- **Side effects**: updates relevance feedback for learning (optional)

## Decision Flow

1. **Query understanding**
   - Parse intent: informational (learn about X), navigational (find entry Y), transactional (update Z)
   - Extract entities: file paths, agent names, dates, memory types
   - Identify temporal needs: "recent" → boost last 7 days, "last week" → time-range filter
   - Detect implicit filters: "what did we decide" → filter type=decision, "error with" → filter type=feedback

2. **Query expansion**
   - Synonyms: expand query terms with equivalent terms from domain vocabulary
   - Hyponyms: include specific types (e.g., "auth" → "login", "JWT", "OAuth", "session", "password")
   - Stemming: match morphological variants (compress → compressing, compressed, compression)
   - Embedding: generate query embedding, find nearest neighbor terms
   - Pseudo-relevance feedback: take top-3 results, extract their keywords, add to query
   - Weight: original terms × 1.0, expanded terms × 0.3

3. **Contextual relevance scoring**
   - Base score: BM25 or cosine similarity from search
   - Recency boost: time_decay = 1 / (1 + days_since_creation/30)
   - Priority boost: priority/10 as multiplier
   - Personalization: entries authored by current agent or team → +10%
   - Context match: entries related to current task/topic → +20%
   - Negative signal: entries explicitly marked as outdated/wrong → −50%
   - Combine: base × recency × priority × personalization

4. **Diversification**
   - MMR (Maximal Marginal Relevance): λ × relevance − (1−λ) × max_similarity_to_already_selected
   - Type diversity: ensure at least one of each relevant memory type
   - Source diversity: don't show 5 entries all from the same conversation
   - Time diversity: don't show all entries from a single day
   - λ = 0.7 by default (70% relevance, 30% diversity)

5. **Learning from feedback**
   - Explicit: user marks result as helpful/unhelpful → adjust future rankings
   - Implicit: user clicks/opens result → positive signal
   - Ignored results: shown but not interacted with → weak negative signal
   - Per-query learning: adjust weights for specific query patterns over time
   - Decay: old feedback decays exponentially (half-life 30 days)

## Failure Modes
| Condition | Response |
|---|---|
| No results found for query | Return empty with query suggestions, do not fabricate results |
| Query too broad ("everything about X") | Return top diverse results, suggest adding filters |
| Query expansion introduces noise | Weight expanded terms lower, evaluate precision impact |
| Personalization cold start (new user/agent) | Fall back to global relevance, disable personalization boost |
| Feedback loop (popular results get more popular) | Apply diversity penalty proportional to historical click rate |
