const fs = require('fs');
const path = require('path');

/**
 * Cross-Reference Integrity Validator for Agentic Loop
 * Usage: node scripts/validate_cross_references.js
 * Returns: exit code 0 if clean, 1 if issues found
 */

const ROOT = path.join(__dirname, '..'); // .agent_loop/

function getAllMdFiles(dir, list = []) {
  const items = fs.readdirSync(dir, { withFileTypes: true });
  for (const item of items) {
    const fullPath = path.join(dir, item.name);
    if (item.isDirectory()) getAllMdFiles(fullPath, list);
    else if (item.name.endsWith('.md')) list.push(fullPath);
  }
  return list;
}

function main() {
  const allFiles = getAllMdFiles(ROOT);

  const relNames = [];
  const baseNames = new Set();
  for (const f of allFiles) {
    const rel = path.relative(ROOT, f).replace(/\\/g, '/');
    const base = path.basename(f, '.md');
    relNames.push({ rel, base, full: f });
    baseNames.add(base);
  }

  const references = new Map();
  const referencedBy = new Map();
  for (const { rel, base, full } of relNames) {
    const content = fs.readFileSync(full, 'utf8');
    const found = new Set();
    const re1 = /(?<![\w/.])\b([\w_]+)\.md\b/g;
    const re2 = /(?<![\w/.])\b([\w_]+)\b/g;
    let m;
    while ((m = re1.exec(content)) !== null) {
      if (m[1] !== base) found.add(m[1]);
    }
    while ((m = re2.exec(content)) !== null) {
      if (m[1] !== base && baseNames.has(m[1])) found.add(m[1]);
    }
    references.set(rel, [...found]);
    for (const t of found) {
      if (!referencedBy.has(t)) referencedBy.set(t, []);
      referencedBy.get(t).push(rel);
    }
  }

  const broken = [];
  const isolated = [];
  for (const { rel, base } of relNames) {
    const refs = references.get(rel) || [];
    for (const r of refs) {
      if (!baseNames.has(r)) broken.push({ from: rel, to: r });
    }
    if (rel === 'main_loop.md' || rel === 'ARCHITECTURE.md') continue;
    const incoming = referencedBy.get(base) || [];
    if (incoming.length === 0) isolated.push(rel);
  }

  // Known false positives: documentation target files (not agents)
  const knownFalsePositives = ['README', 'API', 'CHANGELOG', 'MEMORY', 'project_rules'];
  const docFiles = ['ARCHITECTURE.md', 'TECHNICAL_ASSIGNMENT.md', 'CLAUDE.md'];
  const filteredBroken = broken.filter(b => {
    if (knownFalsePositives.includes(b.to)) return false;
    if (docFiles.some(d => b.from.includes(d))) return false;
    return true;
  });
  const filteredIsolated = isolated.filter(i => !docFiles.some(d => i.includes(d)));

  console.log('=== Agentic Loop Cross-Reference Integrity Report ===');
  console.log('Total agents/files:', allFiles.length);
  console.log('');

  if (filteredBroken.length === 0) {
    console.log('Broken links: NONE');
  } else {
    console.log('Broken links:', filteredBroken.length);
    for (const b of filteredBroken) console.log(`  ${b.from} -> ${b.to}`);
  }

  console.log('');
  if (filteredIsolated.length === 0) {
    console.log('Isolated agents (no incoming refs): NONE');
  } else {
    console.log('Isolated agents (no incoming refs):', filteredIsolated.length);
    for (const i of filteredIsolated) console.log(`  ${i}`);
  }

  console.log('');
  console.log('Top referenced agents:');
  const refCounts = [...referencedBy.entries()]
    .map(([k, v]) => ({ agent: k, count: v.length }))
    .sort((a, b) => b.count - a.count);
  for (const rc of refCounts.slice(0, 10)) {
    console.log(`  - ${rc.agent}: ${rc.count} refs`);
  }

  console.log('');
  if (filteredBroken.length === 0 && filteredIsolated.length === 0) {
    console.log('All cross-references are clean.');
    process.exit(0);
  } else {
    console.log('Issues found: broken=' + filteredBroken.length + ', isolated=' + filteredIsolated.length);
    process.exit(1);
  }
}

main();
