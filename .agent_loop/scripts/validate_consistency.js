const fs = require('fs');
const path = require('path');

/**
 * Consistency Validator for Agentic Loop
 * Checks:
 * 1. Algorithmic template completeness (Role, Contract, Decision Flow, Failure Modes)
 * 2. File naming convention (snake_case)
 * 3. Circular references between agents
 * 4. Safety-before-execution invariant references
 * 5. Contract field consistency (Receives/Returns/Side effects sections present)
 * 6. Directory structure matches ARCHITECTURE.md tree
 * Usage: node scripts/validate_consistency.js
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

function parseAgent(content) {
  const lines = content.split(/\r?\n/);
  const sections = new Set();
  const subSections = new Set();
  let currentSection = null;
  for (const line of lines) {
    if (line.startsWith('## ')) {
      currentSection = line.slice(3).trim().toLowerCase();
      sections.add(currentSection);
    } else if (line.startsWith('### ') && currentSection) {
      subSections.add(`${currentSection}::${line.slice(4).trim().toLowerCase()}`);
    }
  }
  // Also detect inline Contract fields: "- **Receives**:" or "- **Returns**:" etc.
  const hasInlineReceives = /\*\*Receives\*\*/.test(content);
  const hasInlineReturns = /\*\*Returns\*\*/.test(content);
  const hasInlineSideEffects = /\*\*Side effects\*\*/.test(content);
  return { sections, subSections, hasInlineReceives, hasInlineReturns, hasInlineSideEffects };
}

function extractReferences(content, ownBase) {
  const refs = new Set();
  const re1 = /(?<![\w/.])\b([\w_]+)\.md\b/g;
  const re2 = /(?<![\w/.])\b([\w_]+)\b/g;
  let m;
  while ((m = re1.exec(content)) !== null) {
    if (m[1] !== ownBase) refs.add(m[1]);
  }
  while ((m = re2.exec(content)) !== null) {
    if (m[1] !== ownBase) refs.add(m[1]);
  }
  return [...refs];
}

function findCycles(adj, baseNames) {
  const cycles = [];
  const visited = new Set();
  const recStack = new Set();
  const pathStack = [];

  function dfs(node) {
    visited.add(node);
    recStack.add(node);
    pathStack.push(node);

    const neighbors = adj.get(node) || [];
    for (const n of neighbors) {
      if (!baseNames.has(n)) continue; // skip non-agent refs
      if (!visited.has(n)) {
        dfs(n);
      } else if (recStack.has(n)) {
        const idx = pathStack.indexOf(n);
        cycles.push(pathStack.slice(idx).concat([n]));
      }
    }

    pathStack.pop();
    recStack.delete(node);
  }

  for (const node of baseNames) {
    if (!visited.has(node)) dfs(node);
  }
  return cycles;
}

function main() {
  const allFiles = getAllMdFiles(ROOT);
  const issues = [];
  let warningCount = 0;

  const relNames = [];
  const baseNames = new Set();
  const baseToRel = new Map();
  for (const f of allFiles) {
    const rel = path.relative(ROOT, f).replace(/\\/g, '/');
    const base = path.basename(f, '.md');
    relNames.push({ rel, base, full: f });
    baseNames.add(base);
    baseToRel.set(base, rel);
  }

  // 1. Algorithmic template completeness
  const requiredSections = ['role', 'contract', 'decision flow', 'failure modes'];
  for (const { rel, base, full } of relNames) {
    if (rel === 'ARCHITECTURE.md' || rel === 'TECHNICAL_ASSIGNMENT.md') continue;
    const content = fs.readFileSync(full, 'utf8');
    const parsed = parseAgent(content);
    for (const req of requiredSections) {
      if (!parsed.sections.has(req)) {
        issues.push(`[TEMPLATE] ${rel}: missing "## ${req.charAt(0).toUpperCase() + req.slice(1)}"`);
      }
    }
    // Check Contract subsections (either h3 or inline list)
    const hasReceives = parsed.subSections.has('contract::receives') || parsed.hasInlineReceives;
    const hasReturns = parsed.subSections.has('contract::returns') || parsed.hasInlineReturns;
    const hasSideEffects = parsed.subSections.has('contract::side effects') || parsed.hasInlineSideEffects;
    if (!hasReceives) {
      issues.push(`[TEMPLATE] ${rel}: missing "Receives" in Contract`);
    }
    if (!hasReturns) {
      issues.push(`[TEMPLATE] ${rel}: missing "Returns" in Contract`);
    }
    if (!hasSideEffects) {
      issues.push(`[TEMPLATE] ${rel}: missing "Side effects" in Contract`);
    }
  }

  // 2. File naming convention
  const snakeCaseRe = /^[a-z][a-z0-9_]*\.md$/;
  for (const { rel, base } of relNames) {
    if (rel === 'CLAUDE.md' || rel === 'ARCHITECTURE.md' || rel === 'TECHNICAL_ASSIGNMENT.md') continue;
    if (!snakeCaseRe.test(base + '.md')) {
      issues.push(`[NAMING] ${rel}: filename not snake_case or contains uppercase/numbers incorrectly`);
    }
  }

  // 3. Circular references (treated as warnings — cross-references in docs are not runtime calls)
  const adj = new Map();
  for (const { base, full } of relNames) {
    const content = fs.readFileSync(full, 'utf8');
    const refs = extractReferences(content, base);
    adj.set(base, refs.filter(r => baseNames.has(r)));
  }
  const cycles = findCycles(adj, baseNames);
  if (cycles.length > 0) {
    for (const c of cycles) {
      const pathStr = c.map(b => baseToRel.get(b) || b).join(' -> ');
      warningCount++;
      issues.push(`[CYCLE] Circular reference detected (warning): ${pathStr}`);
    }
  }

  // 4. Safety-before-execution invariant check
  const safetyAgents = [
    'input_sanitizer', 'permission_checker', 'command_guard', 'threat_detector',
    'data_leak_preventer', 'output_reviewer', 'bias_detector', 'safety_assessor', 'content_checker'
  ];
  const executionAgents = [
    'tool_invocation', 'write_executor', 'executor_agent', 'command_builder',
    'run_command', 'replace_in_file', 'database_query', 'web_request'
  ];
  for (const { rel, base, full } of relNames) {
    if (!executionAgents.includes(base) && !rel.includes('execution/')) continue;
    const content = fs.readFileSync(full, 'utf8');
    const hasSafetyRef = safetyAgents.some(sa => content.includes(sa));
    if (!hasSafetyRef && !rel.includes('safety')) {
      warningCount++;
      issues.push(`[SAFETY] ${rel}: execution agent does not reference any safety-control agent (warning)`);
    }
  }

  // 5. Directory structure check (known dirs from ARCHITECTURE)
  const knownDirs = new Set([
    'orchestrator', 'safety-control', 'safety-control/mutual_check', 'control',
    'tooll_subagents', 'tooll_subagents/user', 'tooll_subagents/planning',
    'tooll_subagents/execution', 'tooll_subagents/observability',
    'tooll_subagents/self_correction', 'tooll_subagents/result',
    'tools_read', 'tools_read/read_file',
    'tools_search', 'tools_search/search_code',
    'tools_replace', 'tools_replace/replace_in_file',
    'tools_runcom', 'tools_runcom/run_command',
    'tools_runtest', 'tools_runtest/run_tests',
    'tools_terminal', 'tools_terminal/terminal_io',
    'tools_manangr', 'tools_manangr/project_manager',
    'tools_database', 'tools_database/database_query',
    'tools_web', 'tools_web/web_request',
    'tools_memory', 'tools_memory/memory_store',
    'tools_browser', 'tools_browser/headless_automation',
    'tools_lighthouse', 'tools_lighthouse/audit',
    'scripts', 'data'
  ]);
  const actualDirs = new Set();
  function collectDirs(dir) {
    const items = fs.readdirSync(dir, { withFileTypes: true });
    for (const item of items) {
      if (item.isDirectory()) {
        const relDir = path.relative(ROOT, path.join(dir, item.name)).replace(/\\/g, '/');
        actualDirs.add(relDir);
        collectDirs(path.join(dir, item.name));
      }
    }
  }
  collectDirs(ROOT);
  for (const d of actualDirs) {
    if (!knownDirs.has(d) && d !== '.' && d !== 'scripts') {
      warningCount++;
      issues.push(`[STRUCTURE] Unknown directory: ${d} (warning)`);
    }
  }
  for (const d of knownDirs) {
    if (!actualDirs.has(d)) {
      issues.push(`[STRUCTURE] Missing directory: ${d}`);
    }
  }

  // 6. Summary
  console.log('=== Agentic Loop Consistency Report ===');
  console.log('Total files checked:', allFiles.length);
  console.log('Errors:', issues.length - warningCount);
  console.log('Warnings:', warningCount);
  console.log('');

  const errorCount = issues.length - warningCount;
  if (errorCount === 0) {
    if (warningCount > 0) {
      for (const issue of issues) {
        console.log(issue);
      }
      console.log('');
      console.log(`Found 0 errors and ${warningCount} warnings. Warnings only — validation passed.`);
    } else {
      console.log('All consistency checks passed.');
    }
    process.exit(0);
  } else {
    for (const issue of issues) {
      console.log(issue);
    }
    console.log('');
    console.log(`Found ${errorCount} errors and ${warningCount} warnings.`);
    process.exit(1);
  }
}

main();
