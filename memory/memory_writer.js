'use strict';

const crypto = require('crypto');
const { getDb } = require('./db');
const { indexEntryBoth } = require('./index_manager');
const { embed, vectorToBuffer } = require('./embedding_agent');

const VALID_TYPES = new Set(['user', 'feedback', 'project', 'reference']);
const MAX_BODY_SIZE = 64 * 1024;
const MAX_TAGS = 10;
const MAX_TAG_LENGTH = 50;

function generateId(type, data) {
  const hash = crypto.createHash('sha256')
    .update(type + ':' + JSON.stringify(data))
    .digest('hex')
    .slice(0, 12);
  return `${type}_${hash}`;
}

function generateSlug(title) {
  return title
    .toLowerCase()
    .replace(/[^a-zа-яё0-9\s-]/g, '')
    .replace(/[\s]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 60) || 'entry';
}

function contentHash(body) {
  return crypto.createHash('sha256').update(body, 'utf8').digest('hex');
}

function normalizeTags(tags) {
  if (!Array.isArray(tags)) return [];
  return [...new Set(
    tags
      .map(t => String(t).toLowerCase().trim())
      .filter(t => t.length > 0 && t.length <= MAX_TAG_LENGTH)
  )].slice(0, MAX_TAGS);
}

function validateEntry(action, type, data, metadata) {
  const errors = [];

  if (!VALID_TYPES.has(type)) {
    errors.push(`Invalid type "${type}". Must be one of: ${[...VALID_TYPES].join(', ')}`);
  }

  if (!data || typeof data !== 'object') {
    errors.push('data must be a non-empty object');
    return errors;
  }

  if (action !== 'delete') {
    if (!data.title && !data.body) {
      errors.push('data must have at least title or body');
    }

    const body = data.body || '';
    if (Buffer.byteLength(body, 'utf8') > MAX_BODY_SIZE) {
      errors.push(`Body exceeds max size of ${MAX_BODY_SIZE} bytes`);
    }
  }

  if (metadata && metadata.priority !== undefined) {
    const p = metadata.priority;
    if (!Number.isInteger(p) || p < 1 || p > 10) {
      errors.push('Priority must be integer 1-10');
    }
  }

  if (metadata && metadata.ttl_ms !== undefined) {
    const ttl = metadata.ttl_ms;
    if (ttl < 60000 || ttl > 365 * 24 * 60 * 60 * 1000) {
      errors.push('TTL must be between 60s and 1 year');
    }
  }

  return errors;
}

function checkDuplicates(db, type, data) {
  const body = data.body || '';
  const title = data.title || '';
  const hash = contentHash(body);

  const exact = db.prepare(
    'SELECT id, version FROM memory_entries WHERE type = ? AND title = ? AND body = ?'
  ).get(type, title, body);

  if (exact) return { duplicate: true, existingId: exact.id, reason: 'exact_match' };

  const sameTitleSameType = db.prepare(
    'SELECT id, title, body FROM memory_entries WHERE type = ? AND title = ? LIMIT 5'
  ).all(type, title);

  if (sameTitleSameType.length > 0) {
    for (const e of sameTitleSameType) {
      const existingHash = contentHash(e.body);
      const similarity = hash === existingHash ? 1 : 0;
      if (similarity > 0.95) {
        return { duplicate: true, existingId: e.id, reason: 'near_duplicate', similarity };
      }
    }
    return { duplicate: false, warning: 'similar_title_exists', candidates: sameTitleSameType.map(e => e.id) };
  }

  return { duplicate: false };
}

function create(dbPath, type, data, metadata) {
  const db = getDb(dbPath);
  const errors = validateEntry('create', type, data, metadata);
  if (errors.length > 0) return { status: 'rejected', errors };

  const dup = checkDuplicates(db, type, data);
  if (dup.duplicate) {
    return { status: 'skipped_duplicate', id: dup.existingId, reason: dup.reason };
  }

  const tags = normalizeTags(data.tags || (metadata && metadata.tags) || []);
  const priority = (metadata && metadata.priority) || 5;
  const ttlMs = metadata && metadata.ttl_ms;
  const source = (metadata && metadata.source) || '';
  const title = data.title || generateSlug(data.body || 'entry');
  const description = data.description || '';
  const body = data.body || '';
  const id = generateId(type, data);

  const expiresAt = ttlMs ? new Date(Date.now() + ttlMs).toISOString() : null;

  db.prepare(`
    INSERT INTO memory_entries (id, type, title, description, body, tags, priority, source, ttl_ms, expires_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).run(id, type, title, description, body, JSON.stringify(tags), priority, source, ttlMs ?? null, expiresAt ?? null);

  db.prepare('INSERT INTO audit_log (entry_id, action, agent, details) VALUES (?, ?, ?, ?)')
    .run(id, 'create', source, `Created ${type} memory: ${title}`);

  try { indexEntryBoth(id, dbPath); } catch (_) { /* non-fatal */ }

  return {
    id, created_at: new Date().toISOString(), version: 1,
    status: 'created'
  };
}

function update(dbPath, id, data, metadata) {
  const db = getDb(dbPath);
  const existing = db.prepare('SELECT * FROM memory_entries WHERE id = ?').get(id);
  if (!existing) return { status: 'error', error: `Entry ${id} not found` };

  const currentVersion = existing.version;
  if (metadata && metadata.expected_version !== undefined && metadata.expected_version !== currentVersion) {
    return {
      status: 'rejected',
      error: 'Version conflict',
      current_version: currentVersion,
      expected_version: metadata.expected_version
    };
  }

  const tags = data.tags ? normalizeTags(data.tags) : JSON.parse(existing.tags || '[]');
  const title = data.title !== undefined ? data.title : existing.title;
  const description = data.description !== undefined ? data.description : existing.description;
  const body = data.body !== undefined ? data.body : existing.body;

  db.prepare(`
    UPDATE memory_entries
    SET title = ?, description = ?, body = ?, tags = ?, version = version + 1, updated_at = datetime('now')
    WHERE id = ?
  `).run(title, description, body, JSON.stringify(tags), id);

  db.prepare('INSERT INTO audit_log (entry_id, action, agent, details) VALUES (?, ?, ?, ?)')
    .run(id, 'update', (metadata && metadata.source) || '', `Updated to version ${currentVersion + 1}`);

  try { indexEntryBoth(id, dbPath); } catch (_) {}

  return {
    id, created_at: existing.created_at, version: currentVersion + 1,
    status: 'updated'
  };
}

function upsert(dbPath, type, data, metadata) {
  const db = getDb(dbPath);
  const dup = checkDuplicates(db, type, data);

  if (dup.duplicate) {
    return update(dbPath, dup.existingId, data, metadata);
  }

  if (dup.warning) {
    const candidates = (dup.candidates || []);
    if (candidates.length === 1) {
      return update(dbPath, candidates[0], data, metadata);
    }
  }

  return create(dbPath, type, data, metadata);
}

function remove(dbPath, id) {
  const db = getDb(dbPath);
  const existing = db.prepare('SELECT * FROM memory_entries WHERE id = ?').get(id);
  if (!existing) return { status: 'error', error: `Entry ${id} not found` };

  db.prepare("UPDATE memory_entries SET body = '[DELETED] ' || body, updated_at = datetime('now') WHERE id = ?").run(id);
  db.prepare('DELETE FROM memory_fts WHERE entry_id = ?').run(id);
  db.prepare('DELETE FROM memory_vectors WHERE entry_id = ?').run(id);

  db.prepare('INSERT INTO audit_log (entry_id, action, agent, details) VALUES (?, ?, ?, ?)')
    .run(id, 'delete', '', 'Soft deleted');

  return {
    id, created_at: existing.created_at, version: existing.version,
    status: 'deleted'
  };
}

function processWrite(input, dbPath) {
  const { action, type, data, metadata } = input;

  switch (action) {
    case 'create':
      return create(dbPath, type, data, metadata || {});
    case 'update':
      return update(dbPath, data && data.id, data, metadata || {});
    case 'delete':
      return remove(dbPath, data && data.id);
    case 'upsert':
      return upsert(dbPath, type, data, metadata || {});
    default:
      return { status: 'error', error: `Unknown action: ${action}` };
  }
}

module.exports = {
  validateEntry, checkDuplicates, generateId, generateSlug, contentHash, normalizeTags,
  create, update, upsert, remove, processWrite
};
