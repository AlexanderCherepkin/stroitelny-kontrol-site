'use strict';

const path = require('path');
const { initSchema, closeDb } = require('./db');

const DB_PATH = ':memory:';

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    passed++;
    process.stdout.write('.');
  } catch (e) {
    failed++;
    process.stdout.write('F');
    console.error('\nFAIL: ' + name + '\n  ' + e.message);
  }
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg || 'assertion failed');
}

function assertEqual(a, b, msg) {
  if (a !== b) throw new Error(msg || `expected ${JSON.stringify(b)}, got ${JSON.stringify(a)}`);
}

function runTests() {
  const db = initSchema(DB_PATH);

  // === embedding_agent ===
  console.log('\n--- embedding_agent ---');
  const emb = require('./embedding_agent');

  test('embed returns 384d vector', () => {
    const r = emb.embed('authentication security tokens');
    assertEqual(r.embeddings.length, 1);
    assertEqual(r.embeddings[0].length, 384);
    assertEqual(r.model, 'keyword-frequency');
  });

  test('batch embed returns multiple vectors', () => {
    const r = emb.batchEmbed(['text one', 'text two', 'text three']);
    assertEqual(r.embeddings.length, 3);
  });

  test('related texts have higher similarity', () => {
    const a = emb.embed('authentication OAuth2 JWT security').embeddings[0];
    const b = emb.embed('login token auth SSO password').embeddings[0];
    const c = emb.embed('weather sunny rain clouds').embeddings[0];
    const simAB = emb.cosineSimilarity(a, b);
    const simAC = emb.cosineSimilarity(a, c);
    assert(simAB > simAC, 'related texts should score higher than unrelated');
  });

  test('validate catches zero vector', () => {
    const v = emb.validate([new Float32Array(384)]);
    assert(!v.valid, 'zero vector should be invalid');
  });

  test('validate passes non-zero vector', () => {
    const r = emb.embed('valid text with sufficient content');
    assert(emb.validate(r.embeddings).valid);
  });

  test('buffer roundtrip preserves vector', () => {
    const r = emb.embed('roundtrip test');
    const buf = emb.vectorToBuffer(r.embeddings[0]);
    const restored = emb.bufferToVector(buf);
    assertEqual(restored.length, 384);
    const sim = emb.cosineSimilarity(r.embeddings[0], restored);
    assert(sim > 0.999, 'roundtrip should preserve vector');
  });

  // === memory_writer ===
  console.log('--- memory_writer ---');
  const writer = require('./memory_writer');

  test('create project entry', () => {
    const r = writer.create(DB_PATH, 'project', {
      title: 'Test Project',
      body: 'A test project body with enough content.',
      tags: ['test', 'project']
    }, { priority: 8, source: 'test-agent' });
    assertEqual(r.status, 'created');
    assert(r.id.startsWith('project_'));
  });

  test('create feedback entry', () => {
    const r = writer.create(DB_PATH, 'feedback', {
      title: 'Test Bug',
      body: 'Something is broken in the test environment.',
      tags: ['bug', 'test']
    }, { priority: 9 });
    assertEqual(r.status, 'created');
    assert(r.id.startsWith('feedback_'));
  });

  test('duplicate detection', () => {
    const r = writer.create(DB_PATH, 'project', {
      title: 'Test Project',
      body: 'A test project body with enough content.',
      tags: ['test']
    });
    assertEqual(r.status, 'skipped_duplicate');
  });

  test('update entry', () => {
    const created = writer.create(DB_PATH, 'project', {
      title: 'Update Test',
      body: 'Original body text.',
      tags: ['update']
    });
    const r = writer.update(DB_PATH, created.id,
      { body: 'Updated body text.', tags: ['update', 'modified'] }
    );
    assertEqual(r.status, 'updated');
    assertEqual(r.version, 2);
  });

  test('version conflict detection', () => {
    const created = writer.create(DB_PATH, 'project', {
      title: 'Version Test',
      body: 'Body for versioning.',
      tags: ['version']
    });
    const r = writer.update(DB_PATH, created.id,
      { body: 'New version' },
      { expected_version: 999 }
    );
    assertEqual(r.status, 'rejected');
  });

  test('delete entry (soft)', () => {
    const created = writer.create(DB_PATH, 'user', {
      title: 'Delete Test',
      body: 'This entry will be deleted.',
      tags: ['delete']
    });
    const r = writer.remove(DB_PATH, created.id);
    assertEqual(r.status, 'deleted');
  });

  test('upsert creates new entry', () => {
    const r = writer.upsert(DB_PATH, 'reference', {
      title: 'Upsert New',
      body: 'New unique entry via upsert.',
      tags: ['upsert']
    });
    assert(r.status === 'created' || r.status === 'updated');
  });

  test('validateEntry rejects invalid type', () => {
    const errors = writer.validateEntry('create', 'invalid_type', { title: 'X' });
    assert(errors.length > 0);
  });

  test('validateEntry rejects oversized body', () => {
    const errors = writer.validateEntry('create', 'project',
      { title: 'Big', body: 'x'.repeat(70000) }
    );
    assert(errors.length > 0);
  });

  // === memory_reader ===
  console.log('--- memory_reader ---');
  const reader = require('./memory_reader');

  const authId = writer.create(DB_PATH, 'project', {
    title: 'Auth System Design',
    description: 'Authentication architecture',
    body: 'We designed the auth system using OAuth2 with PKCE flow. JWT tokens for API access.',
    tags: ['auth', 'security', 'architecture']
  }, { priority: 8 }).id;

  const bugId = writer.create(DB_PATH, 'feedback', {
    title: 'Login Page Crash on Safari',
    body: 'The login page crashes on Safari 18 when clicking the submit button. Console shows TypeError.',
    tags: ['bug', 'ui', 'safari']
  }, { priority: 9 }).id;

  const dbId = writer.create(DB_PATH, 'project', {
    title: 'Database Performance Tuning',
    body: 'Optimized SQLite queries by adding composite indexes. Query time dropped from 500ms to 50ms.',
    tags: ['database', 'performance', 'sqlite']
  }, { priority: 7 }).id;

  test('getById returns entry with tags and links', () => {
    const e = reader.getById(authId, DB_PATH);
    assert(e !== null);
    assertEqual(e.title, 'Auth System Design');
    assert(Array.isArray(e.tags));
    assert(e.tags.includes('auth'));
  });

  test('keyword search finds auth entry', () => {
    const r = reader.keywordSearch('OAuth2 PKCE', DB_PATH);
    assert(r.results.length > 0);
    assert(r.results.some(e => e.id === authId));
  });

  test('keyword search finds bug entry', () => {
    const r = reader.keywordSearch('Safari crash', DB_PATH);
    assert(r.results.length > 0);
    assert(r.results.some(e => e.id === bugId));
  });

  test('semantic search finds relevant entries', () => {
    const r = reader.semanticSearch('web browser problem', DB_PATH);
    assert(r.results.length > 0);
  });

  test('hybrid search returns results', () => {
    const r = reader.hybridSearch('database optimization', DB_PATH);
    assert(r.results.length > 0);
  });

  test('listByType filters correctly', () => {
    const r = reader.listByType('project', DB_PATH);
    assert(r.results.length > 0);
    assert(r.results.every(e => e.type === 'project'));
  });

  test('listByTags filters by tags', () => {
    const r = reader.listByTags(['auth'], DB_PATH);
    assert(r.results.length > 0);
  });

  test('getFacets returns type counts', () => {
    const f = reader.getFacets(DB_PATH);
    assert(f.total > 0);
    assert(Array.isArray(f.by_type));
  });

  test('access_count increments on read', () => {
    const before = reader.getById(authId, DB_PATH);
    const after = reader.getById(authId, DB_PATH);
    assert(after.access_count >= before.access_count);
  });

  // === index_manager ===
  console.log('--- index_manager ---');
  const idx = require('./index_manager');

  test('index stats show entries', () => {
    const s = idx.getStats(DB_PATH);
    assert(s.total_entries > 0);
    assert(s.vector_indexed > 0);
  });

  test('validate indexes reports clean', () => {
    const v = idx.validateIndexes(DB_PATH);
    assertEqual(v.status, 'valid');
  });

  test('rebuild indexes succeeds', () => {
    const r = idx.rebuildIndexes(DB_PATH);
    assertEqual(r.status, 'rebuilt');
  });

  // === context_compressor ===
  console.log('--- context_compressor ---');
  const comp = require('./context_compressor');

  test('extracts decision from text', () => {
    const r = comp.extractSalient('We decided to use OAuth2 for authentication. Hello everyone!');
    assert(r.some(item => item.type === 'decision'));
  });

  test('extracts error from text', () => {
    const r = comp.extractSalient('The build failed with timeout error in auth.ts line 42.');
    assert(r.some(item => item.type === 'error'));
  });

  test('compression reduces size', () => {
    const content = 'Hello everyone.\n\nGood morning.\n\nThe weather is nice today.\n\nWe decided to use React for the frontend.\n\nThe backend will be Node.js with Express.\n\nTests are passing on all 42 suites.\n\nThe database is PostgreSQL with Redis cache.\n\nWe deployed to staging successfully.\n\nGreat work team, see you tomorrow.';
    const r = comp.compress(content, 30, ['all']);
    assert(r.extracted.length > 0);
    assert(r.compressed.length < content.length);
  });

  test('preserve filter works', () => {
    const content = 'We decided to use OAuth2. The build failed with error E001. Hello everyone.';
    const r = comp.compress(content, 200, ['decisions']);
    const r2 = comp.compress(content, 200, ['errors']);
    assert(r.compressed !== r2.compressed);
  });

  // === summarizer ===
  console.log('--- summarizer ---');
  const summ = require('./summarizer');

  test('generates title for entry', () => {
    const r = summ.generateEntrySummary('We decided to migrate from PostgreSQL to SQLite for the memory backend. The migration was completed in Q2 2026. Zero external dependencies.', { level: 'oneliner' });
    assert(r.title.length > 0);
  });

  test('oneliner is short', () => {
    const r = summ.generateEntrySummary('Long text. '.repeat(50) + 'Key decision: use SQLite.', { level: 'oneliner' });
    assert(r.summary.length <= 210); // first line + some margin
  });

  test('short summary includes keywords', () => {
    const r = summ.generateEntrySummary('The authentication system was migrated from JWT to OAuth2 PKCE. This improves security compliance and enables single sign-on.', { level: 'short' });
    assert(r.keywords.length > 0);
  });

  test('keywords are lowercase', () => {
    const r = summ.generateEntrySummary('AUTH Token Security LOGIN', { level: 'title' });
    assert(r.keywords.every(k => k === k.toLowerCase()));
  });

  // === recall_optimizer ===
  console.log('--- recall_optimizer ---');
  const recall = require('./recall_optimizer');

  test('expandQuery adds synonyms', () => {
    const r = recall.expandQuery('auth database');
    assert(r.terms.length > 2, 'should expand with synonyms');
  });

  test('parseIntent detects informational', () => {
    assertEqual(recall.parseIntent('how does auth work?'), 'informational');
  });

  test('parseIntent detects error lookup', () => {
    assertEqual(recall.parseIntent('what caused the login bug'), 'error_lookup');
  });

  test('mmrDiversify maintains result count', () => {
    const results = reader.keywordSearch('auth database performance', DB_PATH).results;
    const div = recall.mmrDiversify(results);
    assertEqual(div.length, results.length);
  });

  test('rankResults returns ranked array', () => {
    const results = reader.keywordSearch('security', DB_PATH).results;
    const r = recall.rankResults(results, 'authentication security', null, 'balanced');
    assert(Array.isArray(r.ranked));
    assert(r.ranked.length > 0);
  });

  // === consistency_checker ===
  console.log('--- consistency_checker ---');
  const checker = require('./consistency_checker');

  test('schema check finds no issues (clean db)', () => {
    const issues = checker.checkSchema(DB_PATH);
    assertEqual(issues.length, 0);
  });

  test('reference check runs without error', () => {
    const issues = checker.checkReferences(DB_PATH);
    assert(Array.isArray(issues));
  });

  test('duplicate check finds no false positives', () => {
    const issues = checker.checkDuplicates(DB_PATH);
    assert(Array.isArray(issues));
  });

  test('full consistency returns health score', () => {
    const r = checker.checkConsistency('full', false, DB_PATH);
    assert(r.health_score >= 0 && r.health_score <= 100);
    assert(Array.isArray(r.recommendations));
    assert(r.recommendations.length > 0);
  });

  // === eviction_policy ===
  console.log('--- eviction_policy ---');
  const evict = require('./eviction_policy');

  test('evaluateCapacity shows usage', () => {
    const r = evict.evaluateCapacity(DB_PATH, 100);
    assert(r.usage_pct >= 0);
    assert(['normal', 'soft_limit', 'hard_limit'].includes(r.level));
  });

  test('eviction stats returns counts', () => {
    const r = evict.getEvictionStats(DB_PATH);
    assert(r.total > 0);
  });

  test('generateCandidates sorts by priority', () => {
    const cands = evict.generateCandidates(DB_PATH);
    assert(cands.length > 0);
    for (let i = 1; i < cands.length; i++) {
      assert(cands[i].priority >= cands[i - 1].priority);
    }
  });

  test('setTtl updates expiry', () => {
    const testId = writer.create(DB_PATH, 'user', {
      title: 'TTL Test',
      body: 'Entry with TTL for testing.',
      tags: ['ttl']
    }).id;
    const r = evict.setTtl(DB_PATH, testId, 60000);
    assertEqual(r.id, testId);
    assert(r.expires_at !== null);
  });

  // === memory_optimizer ===
  console.log('--- memory_optimizer ---');
  const opt = require('./memory_optimizer');

  test('applyOptimizations storage', () => {
    const r = opt.applyOptimizations(DB_PATH, 'storage');
    assert(r.optimizations.length > 0);
  });

  test('applyOptimizations index', () => {
    const r = opt.applyOptimizations(DB_PATH, 'index');
    assert(r.optimizations.length > 0);
  });

  test('healthAnalytics returns score', () => {
    const r = opt.healthAnalytics(DB_PATH);
    assert(r.health_score >= 0 && r.health_score <= 100);
    assert(r.total_entries > 0);
  });

  closeDb();

  console.log('\n');
  console.log('='.repeat(50));
  console.log(`Results: ${passed} passed, ${failed} failed, ${passed + failed} total`);
  console.log('='.repeat(50));

  if (failed > 0) {
    process.exit(1);
  }
}

runTests();
