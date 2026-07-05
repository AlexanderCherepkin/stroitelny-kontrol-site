'use strict';

const { getDb } = require('./db');
const { embed, bufferToVector, cosineSimilarity } = require('./embedding_agent');

function getById(id, dbPath) {
  const db = getDb(dbPath);
  const entry = db.prepare('SELECT * FROM memory_entries WHERE id = ?').get(id);
  if (!entry) return null;

  db.prepare(`
    UPDATE memory_entries
    SET access_count = access_count + 1, last_accessed_at = datetime('now')
    WHERE id = ?
  `).run(id);

  return enrichEntry(db, entry);
}

function enrichEntry(db, entry) {
  const tags = JSON.parse(entry.tags || '[]');
  const links = db.prepare(
    'SELECT target_id, link_type FROM memory_links WHERE source_id = ?'
  ).all(entry.id);

  const backlinks = db.prepare(
    'SELECT source_id, link_type FROM memory_links WHERE target_id = ?'
  ).all(entry.id);

  return {
    ...entry,
    tags,
    links: links.map(l => ({ id: l.target_id, type: l.link_type })),
    backlinks: backlinks.map(l => ({ id: l.source_id, type: l.link_type }))
  };
}

function keywordSearch(query, dbPath, filters) {
  const db = getDb(dbPath);
  const conditions = [];
  const params = [];

  let where = '';
  if (filters && filters.length > 0) {
    if (filters.type) {
      conditions.push('e.type = ?');
      params.push(filters.type);
    }
    if (filters.priority_min) {
      conditions.push('e.priority >= ?');
      params.push(filters.priority_min);
    }
    if (filters.tags && filters.tags.length > 0) {
      for (const tag of filters.tags) {
        conditions.push('e.tags LIKE ?');
        params.push('%"' + tag + '"%');
      }
    }
  }

  where = conditions.length > 0 ? 'AND ' + conditions.join(' AND ') : '';

  const limit = (filters && filters.limit) || 50;
  const offset = (filters && filters.offset) || 0;

  const stmt = db.prepare(`
    SELECT e.*, rank
    FROM memory_fts f
    JOIN memory_entries e ON f.entry_id = e.id
    WHERE memory_fts MATCH ? ${where}
    ORDER BY rank
    LIMIT ? OFFSET ?
  `);

  const results = stmt.all(query, ...params, limit, offset);
  const total = results.length;

  return {
    results: results.map(e => enrichEntry(db, e)),
    total,
    search_time_ms: 0
  };
}

function semanticSearch(query, dbPath, filters) {
  const db = getDb(dbPath);
  const queryEmbedding = embed(query).embeddings[0];

  let sql = 'SELECT v.entry_id, v.vector FROM memory_vectors v';
  const conditions = [];
  const params = [];

  if (filters && filters.type) {
    sql += ' JOIN memory_entries e ON v.entry_id = e.id';
    conditions.push('e.type = ?');
    params.push(filters.type);
  }
  if (conditions.length > 0) {
    sql += ' WHERE ' + conditions.join(' AND ');
  }

  const vectors = params.length > 0
    ? db.prepare(sql).all(...params)
    : db.prepare(sql).all();
  const scored = vectors.map(v => {
    const vec = bufferToVector(v.vector);
    return {
      entry_id: v.entry_id,
      score: cosineSimilarity(queryEmbedding, vec)
    };
  });

  scored.sort((a, b) => b.score - a.score);
  const limit = (filters && filters.limit) || 50;
  const offset = (filters && filters.offset) || 0;
  const page = scored.slice(offset, offset + limit);

  const entries = page.map(s => {
    const entry = db.prepare('SELECT * FROM memory_entries WHERE id = ?').get(s.entry_id);
    if (!entry) return null;
    return { ...enrichEntry(db, entry), semantic_score: s.score };
  }).filter(Boolean);

  return { results: entries, total: scored.length, search_time_ms: 0 };
}

function hybridSearch(query, dbPath, filters) {
  const keyword = keywordSearch(query, dbPath, { ...filters, limit: 100 });
  const semantic = semanticSearch(query, dbPath, { ...filters, limit: 100 });

  const rrfScores = new Map();
  const k = 60;

  keyword.results.forEach((r, i) => {
    rrfScores.set(r.id, (rrfScores.get(r.id) || 0) + 1 / (k + i + 1));
  });
  semantic.results.forEach((r, i) => {
    rrfScores.set(r.id, (rrfScores.get(r.id) || 0) + 1 / (k + i + 1));
  });

  const allEntries = new Map();
  for (const r of keyword.results) allEntries.set(r.id, r);
  for (const r of semantic.results) allEntries.set(r.id, r);

  const merged = [...rrfScores.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([id]) => allEntries.get(id))
    .filter(Boolean);

  const limit = (filters && filters.limit) || 50;
  return { results: merged.slice(0, limit), total: merged.length, search_time_ms: 0 };
}

function listByType(type, dbPath, filters) {
  const db = getDb(dbPath);
  const limit = (filters && filters.limit) || 50;
  const offset = (filters && filters.offset) || 0;
  const sort = (filters && filters.sort) || 'date';

  let orderBy = 'ORDER BY created_at DESC';
  if (sort === 'priority') orderBy = 'ORDER BY priority DESC, created_at DESC';
  if (sort === 'relevance') orderBy = 'ORDER BY access_count DESC';

  const entries = db.prepare(`
    SELECT * FROM memory_entries WHERE type = ? ${orderBy} LIMIT ? OFFSET ?
  `).all(type, limit, offset);

  const total = db.prepare('SELECT count(*) as cnt FROM memory_entries WHERE type = ?').get(type).cnt;

  return { results: entries.map(e => enrichEntry(db, e)), total, search_time_ms: 0 };
}

function listByTags(tags, dbPath, filters) {
  const db = getDb(dbPath);
  const limit = (filters && filters.limit) || 50;
  const offset = (filters && filters.offset) || 0;

  const conditions = tags.map((t, i) => `tags LIKE '%"${t}"%'`).join(' OR ');
  const entries = db.prepare(`
    SELECT * FROM memory_entries WHERE ${conditions} ORDER BY created_at DESC LIMIT ? OFFSET ?
  `).all(limit, offset);

  return { results: entries.map(e => enrichEntry(db, e)), total: entries.length, search_time_ms: 0 };
}

function findLinks(entryId, dbPath, depth) {
  const db = getDb(dbPath);
  const maxDepth = depth || 1;
  const visited = new Set();
  const graph = { nodes: [], edges: [] };

  function traverse(id, d) {
    if (d > maxDepth || visited.has(id)) return;
    visited.add(id);
    const entry = db.prepare('SELECT id, title, type FROM memory_entries WHERE id = ?').get(id);
    if (!entry) return;
    graph.nodes.push(entry);

    const links = db.prepare('SELECT target_id, link_type FROM memory_links WHERE source_id = ?').all(id);
    for (const l of links) {
      graph.edges.push({ from: id, to: l.target_id, type: l.link_type });
      traverse(l.target_id, d + 1);
    }
  }

  traverse(entryId, 0);
  return graph;
}

function getFacets(dbPath) {
  const db = getDb(dbPath);
  const byType = db.prepare('SELECT type, count(*) as cnt FROM memory_entries GROUP BY type').all();
  const total = db.prepare('SELECT count(*) as cnt FROM memory_entries').get().cnt;

  return {
    total,
    by_type: byType
  };
}

function processRead(query, dbPath) {
  const { type, tags, sort, limit, offset } = query;

  const filters = { type, sort, limit: limit || 50, offset: offset || 0, tags };

  switch (query.mode) {
    case 'id':
      return { results: [getById(query.q, dbPath)].filter(Boolean), total: 1, search_time_ms: 0 };
    case 'keyword':
      return keywordSearch(query.q, dbPath, filters);
    case 'semantic':
      return semanticSearch(query.q, dbPath, filters);
    case 'hybrid':
      return hybridSearch(query.q, dbPath, filters);
    case 'tag':
      return listByTags(tags || [query.q], dbPath, filters);
    case 'type':
      return listByType(type, dbPath, filters);
    case 'links':
      return findLinks(query.q, dbPath, query.depth || 1);
    case 'facets':
      return getFacets(dbPath);
    default:
      return keywordSearch(query.q || '', dbPath, filters);
  }
}

module.exports = {
  getById, keywordSearch, semanticSearch, hybridSearch,
  listByType, listByTags, findLinks, getFacets,
  enrichEntry, processRead
};
