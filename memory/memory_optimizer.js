'use strict';

const { getDb } = require('./db');
const { rebuildIndexes, optimizeIndexes } = require('./index_manager');
const { checkConsistency } = require('./consistency_checker');

function optimizeStorage(dbPath) {
  const db = getDb(dbPath);
  const results = [];

  const before = db.prepare('SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()').get().size;

  db.exec('PRAGMA optimize');
  db.exec('VACUUM');

  const after = db.prepare('SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()').get().size;

  results.push({
    optimization: 'storage_compact',
    saving_bytes: before - after,
    description: 'Compacted database file via VACUUM'
  });

  return { before_bytes: before, after_bytes: after, savings: before - after, optimizations: results };
}

function optimizeRetrieval(dbPath) {
  const db = getDb(dbPath);
  const results = [];

  db.exec('ANALYZE memory_entries');
  results.push({ optimization: 'statistics_update', description: 'Updated query planner statistics' });

  const rebuildResult = rebuildIndexes(dbPath);
  results.push({ optimization: 'index_rebuild', description: 'Rebuilt FTS5 and vector indexes' });

  return { optimizations: results };
}

function optimizeIndex(dbPath) {
  const result = optimizeIndexes(dbPath);
  return { optimizations: [{ optimization: 'index_merge', description: 'Merged FTS5 segments' }], ...result };
}

function healthAnalytics(dbPath) {
  const health = checkConsistency('full', false, dbPath);
  const db = getDb(dbPath);

  const total = db.prepare('SELECT count(*) as cnt FROM memory_entries').get().cnt;
  const accessed = db.prepare('SELECT count(*) as cnt FROM memory_entries WHERE access_count > 0').get().cnt;
  const totalSize = db.prepare('SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()').get().size;

  return {
    health_score: health.health_score,
    total_entries: total,
    accessed_entries: accessed,
    vitality_pct: total > 0 ? Math.round(accessed / total * 100) : 0,
    db_size_bytes: totalSize,
    issues: health.issues.length,
    recommendations: health.recommendations
  };
}

function applyOptimizations(dbPath, target) {
  const before = {
    db_size_bytes: getDb(dbPath).prepare('SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()').get().size
  };

  let optimizations = [];
  if (target === 'storage' || target === 'full') {
    const storageResult = optimizeStorage(dbPath);
    optimizations.push(...storageResult.optimizations);
  }
  if (target === 'retrieval' || target === 'full') {
    const retrievalResult = optimizeRetrieval(dbPath);
    optimizations.push(...retrievalResult.optimizations);
  }
  if (target === 'index' || target === 'full') {
    const indexResult = optimizeIndex(dbPath);
    optimizations.push(...indexResult.optimizations);
  }
  if (target === 'health' || target === 'full') {
    const healthResult = healthAnalytics(dbPath);
    optimizations.push({ optimization: 'health_check', health: healthResult });
  }

  const after = {
    db_size_bytes: getDb(dbPath).prepare('SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()').get().size
  };

  return {
    optimizations,
    before,
    after,
    savings: { storage_mb: (before.db_size_bytes - after.db_size_bytes) / 1024 / 1024 },
    health_score: healthAnalytics(dbPath).health_score
  };
}

function processOptimization(input, dbPath) {
  const { target, baseline, budget } = input;
  return applyOptimizations(dbPath, target || 'full');
}

module.exports = {
  optimizeStorage, optimizeRetrieval, optimizeIndex,
  healthAnalytics, applyOptimizations, processOptimization
};
