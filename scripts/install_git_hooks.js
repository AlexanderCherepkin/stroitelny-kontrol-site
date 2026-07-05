'use strict';

// install_git_hooks.js — Install git hooks from .githooks/ to .git/hooks/
// Run: node scripts/install_git_hooks.js
// Also handles first-time git init if needed.

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..');
const HOOKS_SRC = path.join(ROOT, '.githooks');
const GIT_DIR = path.join(ROOT, '.git');
const HOOKS_DST = path.join(GIT_DIR, 'hooks');

console.log('=== Agentic Loop — Git Hooks Installer ===\n');

// Check git repo
if (!fs.existsSync(GIT_DIR)) {
  console.log('No .git directory found. Initializing git repository...');
  try {
    execFileSync('git', ['init'], { cwd: ROOT, encoding: 'utf8' });
    console.log('  Git repository initialized.\n');
  } catch (e) {
    console.error('  Failed to initialize git:', e.message);
    console.error('  Run "git init" manually first.');
    process.exit(1);
  }
}

if (!fs.existsSync(HOOKS_SRC)) {
  console.error('No .githooks/ directory found. Nothing to install.');
  process.exit(1);
}

const hookFiles = fs.readdirSync(HOOKS_SRC).filter(f => !f.startsWith('.'));

if (hookFiles.length === 0) {
  console.log('No hooks found in .githooks/.');
  process.exit(0);
}

console.log(`Installing ${hookFiles.length} hook(s) from .githooks/ → .git/hooks/:\n`);

for (const hook of hookFiles) {
  const src = path.join(HOOKS_SRC, hook);
  const dst = path.join(HOOKS_DST, hook);

  fs.copyFileSync(src, dst);

  try { fs.chmodSync(dst, 0o755); } catch { /* Windows — chmod not needed */ }

  console.log(`  ✓ ${hook}`);
}

console.log('\nHooks installed successfully.');
console.log('Hooks will now run automatically on git commit/push.');
console.log('To bypass: git commit --no-verify  or  git push --no-verify');
