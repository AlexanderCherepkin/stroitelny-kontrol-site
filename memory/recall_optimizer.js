'use strict';

const { getDb } = require('./db');
const { embed, bufferToVector, cosineSimilarity } = require('./embedding_agent');

const SYNONYM_MAP = {
  'auth': ['login', 'jwt', 'oauth', 'session', 'password', 'token', 'sso', 'authentication', 'authorization'],
  'database': ['db', 'sqlite', 'postgresql', 'mysql', 'storage', 'schema', 'migration', 'query'],
  'security': ['vulnerability', 'exploit', 'threat', 'compliance', 'encryption', 'sandbox'],
  'ui': ['interface', 'button', 'layout', 'css', 'component', 'frontend', 'design', 'safari', 'chrome'],
  'api': ['endpoint', 'rest', 'graphql', 'request', 'response', 'http', 'route'],
  'test': ['testing', 'coverage', 'assert', 'mock', 'stub', 'integration', 'unit'],
  'memory': ['storage', 'cache', 'eviction', 'index', 'embedding', 'vector'],
  'deploy': ['deployment', 'release', 'production', 'staging', 'ci/cd', 'pipeline'],
  'error': ['bug', 'crash', 'failure', 'exception', 'timeout', 'broken', 'issue'],
  'performance': ['speed', 'latency', 'optimization', 'benchmark', 'throughput', 'fast', 'slow']
};

function expandQuery(query) {
  const tokens = query.toLowerCase().split(/[\s]+/);
  const expanded = new Set(tokens);

  for (const token of tokens) {
    if (SYNONYM_MAP[token]) {
      for (const syn of SYNONYM_MAP[token]) {
        expanded.add(syn);
      }
    }
    for (const [key, syns] of Object.entries(SYNONYM_MAP)) {
      if (syns.includes(token)) {
        expanded.add(key);
        for (const s of syns) expanded.add(s);
      }
    }
  }

  return {
    original: query,
    expanded: [...expanded].join(' OR '),
    terms: [...expanded]
  };
}

function parseIntent(query) {
  const lower = query.toLowerCase();

  if (/\b(?:error|bug|issue|problem|broken|fail)\b/.test(lower)) {
    return 'error_lookup';
  }
  if (/\b(?:decide|decision|chose|agreed|resolved)\b/.test(lower)) {
    return 'decision_lookup';
  }
  if (/\b(?:update|change|modify|delete|remove|create|add|set)\b/.test(lower)) {
    return 'transactional';
  }
  if (/\b(?:what|how|why|explain|describe|tell)\b/.test(lower)) {
    return 'informational';
  }
  if (/\b(?:find|search|look|show|list|get|retrieve)\b/.test(lower)) {
    return 'navigational';
  }
  return 'navigational';
}

function contextualScore(entry, context) {
  let score = 1;

  if (context) {
    if (context.daysRecency) {
      const daysSince = (Date.now() - new Date(entry.created_at).getTime()) / 86400000;
      score *= 1 / (1 + daysSince / context.daysRecency);
    }
    if (context.priorityBoost) {
      score *= (entry.priority || 5) / 5;
    }
    if (context.accessBoost && entry.access_count > 0) {
      score *= Math.log1p(entry.access_count) / Math.log1p(10);
    }
    if (context.typeBoost && entry.type === context.typeBoost) {
      score *= 1.2;
    }
  }

  return score;
}

function mmrDiversify(results, lambda = 0.7) {
  if (results.length <= 1) return results;

  const selected = [results[0]];
  const remaining = results.slice(1);

  while (remaining.length > 0) {
    let bestIdx = 0;
    let bestScore = -Infinity;

    for (let i = 0; i < remaining.length; i++) {
      const relevance = remaining[i].semantic_score || remaining[i].relevance_score || 0.5;
      let maxSim = 0;
      for (const s of selected) {
        const sim = entrySimilarity(remaining[i], s);
        if (sim > maxSim) maxSim = sim;
      }
      const mmr = lambda * relevance - (1 - lambda) * maxSim;
      if (mmr > bestScore) {
        bestScore = mmr;
        bestIdx = i;
      }
    }

    selected.push(remaining[bestIdx]);
    remaining.splice(bestIdx, 1);
  }

  return selected;
}

function entrySimilarity(a, b) {
  const at = (a.title || '').toLowerCase();
  const bt = (b.title || '').toLowerCase();
  const aTags = new Set(a.tags || []);
  const bTags = new Set(b.tags || []);

  if (at === bt) return 1;
  if (a.type === b.type && at === bt) return 0.9;

  let tagOverlap = 0;
  if (aTags.size > 0 && bTags.size > 0) {
    let common = 0;
    for (const t of aTags) { if (bTags.has(t)) common++; }
    tagOverlap = common / Math.max(aTags.size, bTags.size);
  }

  return tagOverlap;
}

function rankResults(results, query, context, strategy) {
  const expanded = expandQuery(query);
  const queryTerms = new Set(expanded.terms);
  const intent = parseIntent(query);

  const ranked = results.map((r, i) => {
    let score = 1;

    // base relevance
    score *= (r.semantic_score || r.rank_score || 0.5);

    // keyword match boost
    const text = ((r.title || '') + ' ' + (r.description || '') + ' ' + (r.body || '')).toLowerCase();
    let kwMatches = 0;
    for (const term of queryTerms) {
      if (text.includes(term)) kwMatches++;
    }
    if (kwMatches > 0) score *= 1 + 0.1 * kwMatches;

    // intent matching
    if (intent === 'error_lookup' && r.type === 'feedback') score *= 1.5;
    if (intent === 'decision_lookup' && r.type === 'project') score *= 1.3;

    // contextual
    score *= contextualScore(r, context);

    // priority
    score *= (r.priority || 5) / 5;

    return { ...r, relevance_score: score };
  });

  ranked.sort((a, b) => b.relevance_score - a.relevance_score);

  if (strategy === 'precision') {
    return { ranked: ranked.slice(0, 10), expanded_queries: [expanded.expanded], relevance_model: 'precision', confidence: 0.85 };
  }

  const diversified = mmrDiversify(ranked);

  return {
    ranked: diversified,
    expanded_queries: [expanded.expanded],
    relevance_model: strategy === 'recall' ? 'recall' : 'balanced',
    confidence: 0.8
  };
}

function processRecall(input, dbPath) {
  const { query, context, results, strategy } = input;

  return rankResults(results || [], query, context, strategy || 'balanced');
}

module.exports = {
  expandQuery, parseIntent, contextualScore, mmrDiversify,
  entrySimilarity, rankResults, processRecall
};
