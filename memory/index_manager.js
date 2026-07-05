'use strict';

const { getDb } = require('./db');
const { embed, vectorToBuffer, bufferToVector, cosineSimilarity, tokenize } = require('./embedding_agent');

function indexEntry(entryId, dbPath) {
  const db = getDb(dbPath);
  const entry = db.prepare('SELECT * FROM memory_entries WHERE id = ?').get(entryId);
  if (!entry) return { status: 'error', error: `Entry ${entryId} not found` };

  const tagsText = JSON.parse(entry.tags || '[]').join(' ');

  db.prepare('DELETE FROM memory_fts WHERE entry_id = ?').run(entryId);
  db.prepare(
    'INSERT INTO memory_fts(entry_id, title, description, body, tags) VALUES (?, ?, ?, ?, ?)'
  ).run(entryId, entry.title, entry.description, entry.body, tagsText);

  return { status: 'indexed', id: entryId, method: 'fulltext' };
}

function indexEntryVector(entryId, dbPath) {
  const db = getDb(dbPath);
  const entry = db.prepare('SELECT * FROM memory_entries WHERE id = ?').get(entryId);
  if (!entry) return { status: 'error', error: `Entry ${entryId} not found` };

  const enriched = `[type: ${entry.type}] [tags: ${entry.tags}] ${entry.title} ${entry.description} ${entry.body}`;
  const result = embed(enriched);
  const buf = vectorToBuffer(result.embeddings[0]);

  db.prepare(`
    INSERT INTO memory_vectors (entry_id, vector, dimensions, model)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(entry_id) DO UPDATE SET vector=excluded.vector, dimensions=excluded.dimensions, model=excluded.model
  `).run(entryId, buf, result.dimensions, result.model);

  return { status: 'indexed', id: entryId, method: 'vector', dimensions: result.dimensions };
}

function indexEntryBoth(entryId, dbPath) {
  const ft = indexEntry(entryId, dbPath);
  const vec = indexEntryVector(entryId, dbPath);
  return { status: 'indexed', id: entryId, methods: ['fulltext', 'vector'] };
}

function rebuildIndexes(dbPath) {
  const db = getDb(dbPath);
  const entries = db.prepare('SELECT id FROM memory_entries').all();
  const errors = [];

  db.exec("DELETE FROM memory_fts");
  db.exec("DELETE FROM memory_vectors");

  for (const { id } of entries) {
    try {
      indexEntryBoth(id, dbPath);
    } catch (e) {
      errors.push({ id, error: e.message });
    }
  }

  return {
    status: 'rebuilt',
    entries: entries.length,
    errors: errors.length > 0 ? errors : []
  };
}

function optimizeIndexes(dbPath) {
  const db = getDb(dbPath);
  db.exec("INSERT INTO memory_fts(memory_fts) VALUES('optimize')");

  const ftsStats = db.prepare("SELECT count(*) as cnt FROM memory_fts_data").get();
  const vecStats = db.prepare("SELECT count(*) as cnt FROM memory_vectors").get();

  return {
    status: 'optimized',
    ft_entries: ftsStats.cnt,
    vector_entries: vecStats.cnt
  };
}

function getStats(dbPath) {
  const db = getDb(dbPath);
  const entryCount = db.prepare('SELECT count(*) as cnt FROM memory_entries').get().cnt;
  const ftsCount = db.prepare('SELECT count(*) as cnt FROM memory_fts_data').get().cnt;
  const vecCount = db.prepare('SELECT count(*) as cnt FROM memory_vectors').get().cnt;
  const totalSize = db.prepare("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()").get().size;

  return {
    total_entries: entryCount,
    ft_indexed: ftsCount,
    vector_indexed: vecCount,
    db_size_bytes: totalSize
  };
}

function validateIndexes(dbPath) {
  const db = getDb(dbPath);
  const issues = [];

  const orphans = db.prepare(`
    SELECT v.entry_id FROM memory_vectors v
    LEFT JOIN memory_entries e ON v.entry_id = e.id
    WHERE e.id IS NULL
  `).all();
  for (const o of orphans) {
    issues.push({ type: 'orphan_vector', entry_id: o.entry_id });
  }

  const vectors = db.prepare('SELECT entry_id, vector, dimensions FROM memory_vectors').all();
  for (const v of vectors) {
    const vec = bufferToVector(v.vector);
    for (let i = 0; i < vec.length; i++) {
      if (!Number.isFinite(vec[i])) {
        issues.push({ type: 'corrupt_vector', entry_id: v.entry_id, index: i });
        break;
      }
    }
  }

  return { status: issues.length === 0 ? 'valid' : 'issues_found', issues };
}

function handleAction(action, scope, method, dbPath) {
  const start = Date.now();

  switch (action) {
    case 'index': {
      if (method === 'vector') indexEntryVector(scope, dbPath);
      else if (method === 'fulltext') indexEntry(scope, dbPath);
      else indexEntryBoth(scope, dbPath);
      return { status: 'indexed', id: scope, method: method || 'both', duration_ms: Date.now() - start };
    }
    case 'reindex':
      return { ...rebuildIndexes(dbPath), duration_ms: Date.now() - start };
    case 'optimize':
      return { ...optimizeIndexes(dbPath), duration_ms: Date.now() - start };
    case 'rebuild':
      return { ...rebuildIndexes(dbPath), duration_ms: Date.now() - start };
    case 'stats':
      return { ...getStats(dbPath), duration_ms: Date.now() - start };
    case 'validate':
      return { ...validateIndexes(dbPath), duration_ms: Date.now() - start };
    default:
      return { status: 'error', error: `Unknown action: ${action}` };
  }
}

module.exports = {
  indexEntry, indexEntryVector, indexEntryBoth,
  rebuildIndexes, optimizeIndexes, getStats, validateIndexes,
  handleAction
};
