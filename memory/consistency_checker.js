'use strict';

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { getDb } = require('./db');

function checkReferences(dbPath) {
  const db = getDb(dbPath);
  const issues = [];

  const entries = db.prepare('SELECT id, body FROM memory_entries').all();
  const allIds = new Set(entries.map(e => e.id));

  const wikilinkRe = /\[\[([^\]]+)\]\]/g;
  for (const entry of entries) {
    let match;
    while ((match = wikilinkRe.exec(entry.body)) !== null) {
      if (!allIds.has(match[1])) {
        issues.push({
          type: 'dangling_reference',
          entry_id: entry.id,
          target: match[1],
          severity: 'medium'
        });
      }
    }
  }

  const links = db.prepare('SELECT source_id, target_id FROM memory_links').all();
  for (const l of links) {
    if (!allIds.has(l.source_id)) {
      issues.push({ type: 'orphan_link_source', source_id: l.source_id, target_id: l.target_id, severity: 'high' });
    }
    if (!allIds.has(l.target_id)) {
      issues.push({ type: 'orphan_link_target', source_id: l.source_id, target_id: l.target_id, severity: 'high' });
    }
  }

  return issues;
}

function checkSchema(dbPath) {
  const db = getDb(dbPath);
  const issues = [];

  const entries = db.prepare('SELECT * FROM memory_entries').all();
  const VALID_TYPES = new Set(['user', 'feedback', 'project', 'reference']);

  for (const entry of entries) {
    if (!VALID_TYPES.has(entry.type)) {
      issues.push({ type: 'invalid_type', entry_id: entry.id, value: entry.type, severity: 'high' });
    }

    if (!entry.title || entry.title.trim().length === 0) {
      issues.push({ type: 'missing_title', entry_id: entry.id, severity: 'high' });
    }

    if (!entry.body || entry.body.trim().length === 0) {
      issues.push({ type: 'empty_body', entry_id: entry.id, severity: 'medium' });
    }

    try {
      JSON.parse(entry.tags || '[]');
    } catch {
      issues.push({ type: 'invalid_tags_json', entry_id: entry.id, severity: 'medium' });
    }

    if (isNaN(Date.parse(entry.created_at))) {
      issues.push({ type: 'invalid_created_date', entry_id: entry.id, severity: 'medium' });
    }

    const priority = entry.priority;
    if (priority < 1 || priority > 10 || !Number.isInteger(priority)) {
      issues.push({ type: 'invalid_priority', entry_id: entry.id, value: priority, severity: 'medium' });
    }
  }

  return issues;
}

function checkDuplicates(dbPath) {
  const db = getDb(dbPath);
  const issues = [];

  const entries = db.prepare('SELECT id, title, body, type, version FROM memory_entries ORDER BY created_at').all();

  for (let i = 0; i < entries.length; i++) {
    for (let j = i + 1; j < entries.length; j++) {
      if (entries[i].title === entries[j].title && entries[i].type === entries[j].type) {
        const hashA = crypto.createHash('sha256').update(entries[i].body, 'utf8').digest('hex');
        const hashB = crypto.createHash('sha256').update(entries[j].body, 'utf8').digest('hex');
        if (hashA === hashB) {
          issues.push({
            type: 'exact_duplicate',
            entry_a: entries[i].id,
            entry_b: entries[j].id,
            severity: 'high'
          });
        }
      }
    }
  }

  return issues;
}

function checkLogicalConsistency(dbPath) {
  const db = getDb(dbPath);
  const issues = [];

  const entries = db.prepare('SELECT * FROM memory_entries').all();

  for (const entry of entries) {
    const tags = JSON.parse(entry.tags || '[]');

    if (entry.priority >= 8 && tags.includes('optional')) {
      issues.push({
        type: 'priority_tag_mismatch',
        entry_id: entry.id,
        detail: 'High priority but tagged "optional"',
        severity: 'low'
      });
    }

    if (entry.priority <= 3 && tags.includes('critical')) {
      issues.push({
        type: 'priority_tag_mismatch',
        entry_id: entry.id,
        detail: 'Low priority but tagged "critical"',
        severity: 'low'
      });
    }

    if (entry.type === 'feedback' && !entry.body.toLowerCase().includes('issue') && !entry.body.toLowerCase().includes('bug') && !entry.body.toLowerCase().includes('problem')) {
      issues.push({
        type: 'type_content_mismatch',
        entry_id: entry.id,
        detail: 'Feedback type but body lacks issue/bug/problem indicators',
        severity: 'low'
      });
    }
  }

  return issues;
}

function calculateHealth(issues) {
  const criticalCount = issues.filter(i => i.severity === 'critical').length;
  const highCount = issues.filter(i => i.severity === 'high').length;
  const mediumCount = issues.filter(i => i.severity === 'medium').length;
  const lowCount = issues.filter(i => i.severity === 'low').length;

  let score = 100;
  score -= criticalCount * 20;
  score -= highCount * 10;
  score -= mediumCount * 3;
  score -= lowCount * 1;

  return Math.max(0, Math.min(100, score));
}

function checkConsistency(scope, fix, dbPath) {
  const allIssues = [];

  const refIssues = checkReferences(dbPath);
  allIssues.push(...refIssues);

  const schemaIssues = checkSchema(dbPath);
  allIssues.push(...schemaIssues);

  const dupIssues = checkDuplicates(dbPath);
  allIssues.push(...dupIssues);

  const logicIssues = checkLogicalConsistency(dbPath);
  allIssues.push(...logicIssues);

  const health = calculateHealth(allIssues);

  const autoFixable = allIssues.filter(i =>
    ['missing_title', 'invalid_tags_json', 'empty_body'].includes(i.type)
  );

  let fixed = 0;
  if (fix && autoFixable.length > 0) {
    const db = getDb(dbPath);
    for (const issue of autoFixable) {
      try {
        if (issue.type === 'missing_title') {
          db.prepare("UPDATE memory_entries SET title = 'Untitled', updated_at = datetime('now') WHERE id = ?").run(issue.entry_id);
          fixed++;
        } else if (issue.type === 'invalid_tags_json') {
          db.prepare("UPDATE memory_entries SET tags = '[]', updated_at = datetime('now') WHERE id = ?").run(issue.entry_id);
          fixed++;
        } else if (issue.type === 'empty_body') {
          db.prepare("UPDATE memory_entries SET body = '[empty]', updated_at = datetime('now') WHERE id = ?").run(issue.entry_id);
          fixed++;
        }
      } catch (_) { /* skip unfixable */ }
    }
  }

  const recommendations = [];
  if (health < 50) recommendations.push('Critical: significant data issues detected. Run full check and manual review.');
  else if (health < 70) recommendations.push('Moderate issues detected. Consider running with fix=true.');
  else if (health < 90) recommendations.push('Minor issues. Routine maintenance recommended.');
  else recommendations.push('Memory store is healthy.');

  return {
    issues: allIssues,
    fixed,
    unfixable: autoFixable.length - fixed,
    health_score: health,
    recommendations
  };
}

module.exports = {
  checkReferences, checkSchema, checkDuplicates, checkLogicalConsistency,
  calculateHealth, checkConsistency
};
