'use strict';

const path = require('path');
const { DatabaseSync } = require('node:sqlite');

let _db = null;

function getDb(dbPath) {
  if (_db) return _db;

  const resolved = dbPath || path.join(__dirname, 'memory_store.db');
  _db = new DatabaseSync(resolved);
  _db.exec('PRAGMA journal_mode = WAL');
  _db.exec('PRAGMA foreign_keys = ON');
  _db.exec('PRAGMA busy_timeout = 5000');

  return _db;
}

function closeDb() {
  if (_db) {
    _db.close();
    _db = null;
  }
}

const SCHEMA_SQL = `
CREATE TABLE IF NOT EXISTS memory_entries (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL CHECK(type IN ('user', 'feedback', 'project', 'reference')),
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  body TEXT NOT NULL,
  tags TEXT NOT NULL DEFAULT '[]',
  priority INTEGER NOT NULL DEFAULT 5 CHECK(priority >= 1 AND priority <= 10),
  version INTEGER NOT NULL DEFAULT 1,
  source TEXT NOT NULL DEFAULT '',
  ttl_ms INTEGER,
  expires_at TEXT,
  pinned INTEGER NOT NULL DEFAULT 0,
  access_count INTEGER NOT NULL DEFAULT 0,
  last_accessed_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
  entry_id UNINDEXED,
  title,
  description,
  body,
  tags,
  tokenize='porter unicode61'
);

CREATE TABLE IF NOT EXISTS memory_vectors (
  entry_id TEXT PRIMARY KEY REFERENCES memory_entries(id) ON DELETE CASCADE,
  vector BLOB NOT NULL,
  dimensions INTEGER NOT NULL DEFAULT 384,
  model TEXT NOT NULL DEFAULT 'keyword-frequency',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS memory_links (
  source_id TEXT NOT NULL REFERENCES memory_entries(id) ON DELETE CASCADE,
  target_id TEXT NOT NULL REFERENCES memory_entries(id) ON DELETE CASCADE,
  link_type TEXT NOT NULL DEFAULT 'reference',
  PRIMARY KEY (source_id, target_id)
);

CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entry_id TEXT,
  action TEXT NOT NULL,
  agent TEXT NOT NULL DEFAULT '',
  details TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_entries_type ON memory_entries(type);
CREATE INDEX IF NOT EXISTS idx_entries_priority ON memory_entries(priority);
CREATE INDEX IF NOT EXISTS idx_entries_created ON memory_entries(created_at);
CREATE INDEX IF NOT EXISTS idx_entries_expires ON memory_entries(expires_at);
CREATE INDEX IF NOT EXISTS idx_audit_entry ON audit_log(entry_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);

CREATE TABLE IF NOT EXISTS schema_version (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);
`;

function initSchema(dbPath) {
  const db = getDb(dbPath);
  db.exec(SCHEMA_SQL);

  const current = db.prepare('SELECT MAX(version) as v FROM schema_version').get();
  if (!current || current.v === null || current.v < 1) {
    db.prepare('INSERT INTO schema_version (version) VALUES (1)').run();
  }
  return db;
}

module.exports = { getDb, closeDb, initSchema, SCHEMA_SQL };
