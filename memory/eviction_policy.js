'use strict';

const { getDb } = require('./db');

const DEFAULT_TTL_BY_TYPE = {
  project: 90 * 24 * 60 * 60 * 1000,
  feedback: 180 * 24 * 60 * 60 * 1000,
  user: 365 * 24 * 60 * 60 * 1000,
  reference: 365 * 24 * 60 * 60 * 1000
};

function evaluateCapacity(dbPath, quotaMb) {
  const db = getDb(dbPath);
  const quotaBytes = (quotaMb || 100) * 1024 * 1024;
  const stat = db.prepare('SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()').get();
  const usedBytes = stat.size;
  const usagePct = usedBytes / quotaBytes;

  const perType = db.prepare(`
    SELECT type, count(*) as cnt FROM memory_entries GROUP BY type
  `).all();

  return {
    used_bytes: usedBytes,
    quota_bytes: quotaBytes,
    usage_pct: Math.round(usagePct * 100) / 100,
    level: usagePct < 0.8 ? 'normal' : usagePct < 0.95 ? 'soft_limit' : 'hard_limit',
    per_type: perType
  };
}

function evaluateTtl(dbPath) {
  const db = getDb(dbPath);
  const now = new Date().toISOString();

  const expired = db.prepare(`
    SELECT id, type, title, expires_at, priority
    FROM memory_entries
    WHERE expires_at IS NOT NULL AND expires_at < ? AND pinned = 0
    ORDER BY priority ASC, expires_at ASC
  `).all(now);

  const staleByType = [];
  for (const [type, ttl] of Object.entries(DEFAULT_TTL_BY_TYPE)) {
    const cutoff = new Date(Date.now() - ttl).toISOString();
    const stale = db.prepare(`
      SELECT id, type, title, created_at, priority, access_count
      FROM memory_entries
      WHERE type = ? AND expires_at IS NULL AND created_at < ? AND pinned = 0
        AND last_accessed_at IS NULL
    `).all(type, cutoff);
    staleByType.push(...stale.map(s => ({ ...s, reason: 'implicit_ttl_expired', type_ttl_days: ttl / 86400000 })));
  }

  return { explicit_expired: expired, implicit_expired: staleByType };
}

function scoreLruLfu(entry) {
  const daysSinceAccess = entry.last_accessed_at
    ? (Date.now() - new Date(entry.last_accessed_at).getTime()) / 86400000
    : (Date.now() - new Date(entry.created_at).getTime()) / 86400000;

  const accessCount = Math.max(1, entry.access_count || 0);
  return (1 / accessCount) * Math.log1p(daysSinceAccess);
}

function generateCandidates(dbPath) {
  const db = getDb(dbPath);
  const entries = db.prepare(`
    SELECT * FROM memory_entries WHERE pinned = 0 ORDER BY priority ASC, access_count ASC
  `).all();

  return entries
    .map(e => ({
      ...e,
      eviction_score: scoreLruLfu(e),
      size_score: e.body ? e.body.length : 0
    }))
    .sort((a, b) => {
      if (a.priority !== b.priority) return a.priority - b.priority;
      return b.eviction_score - a.eviction_score;
    });
}

function checkDependency(entryId, dbPath) {
  const db = getDb(dbPath);
  const refs = db.prepare('SELECT count(*) as cnt FROM memory_links WHERE target_id = ?').get(entryId);
  return refs.cnt > 0;
}

function evict(dbPath, quotaMb) {
  const db = getDb(dbPath);
  const capacity = evaluateCapacity(dbPath, quotaMb);
  const results = { evicted: [], freed_bytes: 0, remaining_bytes: capacity.used_bytes, warnings: [] };

  if (capacity.level === 'normal') return results;

  const ttlResults = evaluateTtl(dbPath);
  let candidates = generateCandidates(dbPath)
    .filter(c => c.priority < 8)
    .filter(c => !checkDependency(c.id, dbPath));

  if (candidates.length === 0) {
    results.warnings.push('No evictable entries found (all high priority or referenced)');
    return results;
  }

  const targetFree = capacity.level === 'hard_limit'
    ? Math.ceil(capacity.used_bytes - capacity.quota_bytes * 0.8)
    : Math.ceil(capacity.used_bytes - capacity.quota_bytes * 0.75);

  let freed = 0;
  for (const c of candidates) {
    if (freed >= targetFree) break;

    db.prepare('DELETE FROM memory_fts WHERE entry_id = ?').run(c.id);
    db.prepare('DELETE FROM memory_vectors WHERE entry_id = ?').run(c.id);
    db.prepare('UPDATE memory_entries SET body = \'[EVICTED]\', updated_at = datetime(\'now\') WHERE id = ?').run(c.id);

    results.evicted.push({ id: c.id, title: c.title, type: c.type, score: c.eviction_score });
    freed += c.body ? Buffer.byteLength(c.body, 'utf8') : 0;
  }

  results.freed_bytes = freed;
  results.remaining_bytes = capacity.used_bytes - freed;

  return results;
}

function getEvictionStats(dbPath) {
  const db = getDb(dbPath);
  const byPriority = db.prepare(`
    SELECT priority, count(*) as cnt FROM memory_entries GROUP BY priority ORDER BY priority
  `).all();

  const expired = db.prepare(`
    SELECT count(*) as cnt FROM memory_entries
    WHERE expires_at IS NOT NULL AND expires_at < datetime('now')
  `).get().cnt;

  const total = db.prepare('SELECT count(*) as cnt FROM memory_entries').get().cnt;

  return { total, expired, by_priority: byPriority };
}

function setTtl(dbPath, entryId, ttlMs) {
  const db = getDb(dbPath);
  const expiresAt = new Date(Date.now() + ttlMs).toISOString();
  db.prepare('UPDATE memory_entries SET ttl_ms = ?, expires_at = ?, updated_at = datetime(\'now\') WHERE id = ?')
    .run(ttlMs, expiresAt, entryId);
  return { id: entryId, ttl_ms: ttlMs, expires_at: expiresAt };
}

function processEviction(input, dbPath) {
  const { action, policy, quota_mb } = input;

  switch (action) {
    case 'evaluate':
      return evaluateCapacity(dbPath, quota_mb);
    case 'evict':
      return evict(dbPath, quota_mb);
    case 'stats':
      return getEvictionStats(dbPath);
    case 'set_policy':
      return { status: 'policy_updated', policy };
    default:
      return { status: 'error', error: `Unknown action: ${action}` };
  }
}

module.exports = {
  evaluateCapacity, evaluateTtl, generateCandidates, scoreLruLfu,
  checkDependency, evict, getEvictionStats, setTtl, processEviction
};
