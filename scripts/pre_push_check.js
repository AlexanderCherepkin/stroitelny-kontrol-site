'use strict';

// pre_push_check.js — Pre-push safety gate
// Runs three-circuit safety check and requires human approval for critical issues.
// Usage: node scripts/pre_push_check.js [--auto] [--json]

const { execFileSync } = require('child_process');
const path = require('path');
const readline = require('readline');
const { scanFiles, formatReport, crossValidate, enforcePolicy, SEVERITY } = require('./safety_check');

const C = { reset: '\x1b[0m', bold: '\x1b[1m', red: '\x1b[31m', green: '\x1b[32m', yellow: '\x1b[33m', cyan: '\x1b[36m', gray: '\x1b[90m' };

function git(args) {
  try {
    return execFileSync('git', args, { encoding: 'utf8' }).trim();
  } catch {
    return null;
  }
}

function getStagedFiles() {
  const out = git(['diff', '--cached', '--name-only', '--diff-filter=ACM']);
  if (out === null) return null;
  return out.split('\n').filter(Boolean);
}

function getChangedFiles() {
  const out = git(['diff', '--name-only', 'HEAD']);
  if (out === null) return [];
  return out.split('\n').filter(Boolean);
}

function getUnstagedFiles() {
  const out = git(['diff', '--name-only']);
  if (out === null) return [];
  return out.split('\n').filter(Boolean);
}

function getUntrackedFiles() {
  const out = git(['ls-files', '--others', '--exclude-standard']);
  if (out === null) return [];
  return out.split('\n').filter(Boolean);
}

function requestApproval(violations, rl) {
  return new Promise((resolve) => {
    console.log('');
    console.log(C.yellow + C.bold + '  === HUMAN APPROVAL REQUIRED ===' + C.reset);
    console.log(C.red + `  ${violations.length} critical/high-severity issue(s) detected:` + C.reset);
    for (const v of violations) {
      const tag = v.severity === SEVERITY.CRITICAL ? 'CRIT' : 'HIGH';
      console.log(C.red + `    [${tag}] ${v.file}: ${v.label}` + C.reset);
    }
    console.log('');
    console.log(C.gray + '  These may include secrets, destructive commands, or security threats.' + C.reset);
    console.log(C.gray + '  Proceeding without review could expose credentials or cause data loss.' + C.reset);
    console.log('');

    function prompt() {
      rl.question(C.cyan + '  Proceed anyway? (y)es / (n)o / (r)eview details: ' + C.reset, (answer) => {
        const a = answer.toLowerCase().trim();
        if (a === 'y' || a === 'yes') {
          console.log(C.green + '  [OK] Manual override granted. Proceeding with push.' + C.reset);
          resolve({ approved: true });
        } else if (a === 'n' || a === 'no') {
          console.log(C.red + '  [BLOCK] Push blocked by human decision.' + C.reset);
          resolve({ approved: false });
        } else if (a === 'r' || a === 'review') {
          console.log('');
          for (const v of violations) {
            console.log(C.yellow + `  File: ${v.file}` + C.reset);
            console.log(C.gray + `    Type: ${v.type}, Severity: ${v.severity}` + C.reset);
            console.log(C.gray + `    Detail: ${v.label}` + C.reset);
            console.log('');
          }
          prompt();
        } else {
          console.log(C.yellow + '  Please answer y, n, or r.' + C.reset);
          prompt();
        }
      });
    }
    prompt();
  });
}

async function main() {
  const args = process.argv.slice(2);
  const autoMode = args.includes('--auto');
  const jsonOutput = args.includes('--json');

  console.log(C.cyan + C.bold + '=== Agentic Loop — Pre-Push Safety Gate ===' + C.reset);
  console.log(C.gray + 'Three-circuit safety: safety-control → mutual_check → control' + C.reset);
  console.log('');

  // Gather files
  let files = getStagedFiles();

  if (files === null) {
    console.log(C.red + 'Not a git repository. Run: git init' + C.reset);
    process.exit(1);
  }

  if (files.length === 0) {
    console.log(C.green + 'No staged files to check. Clean push.' + C.reset);
    process.exit(0);
  }

  console.log(C.gray + `Scanning ${files.length} staged files...` + C.reset);

  const result = scanFiles(files);

  // Print quick summary
  if (!jsonOutput) {
    console.log(formatReport(result));
  }

  if (result.validation.status === 'PASS') {
    if (!jsonOutput) {
      console.log(C.green + C.bold + 'SAFETY CHECK PASSED — push allowed.' + C.reset);
    } else {
      console.log(JSON.stringify({ status: 'PASS', ...result }, null, 2));
    }
    process.exit(0);
  }

  // WARNING or BLOCKED
  const violations = result.violations;
  if (violations.length === 0) {
    if (!jsonOutput) {
      console.log(C.yellow + 'Warnings found but no blocking violations.' + C.reset);
    }
    process.exit(0);
  }

  if (autoMode) {
    if (jsonOutput) {
      console.log(JSON.stringify({ status: 'BLOCKED', violations }, null, 2));
    } else {
      console.log(C.red + C.bold + 'BLOCKED — critical issues detected. Resolve before pushing.' + C.reset);
      console.log(C.gray + 'Or run without --auto for interactive approval.' + C.reset);
    }
    process.exit(1);
  }

  // Interactive approval
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  const approval = await requestApproval(violations, rl);
  rl.close();

  if (!approval.approved) {
    process.exit(1);
  }

  console.log(C.green + C.bold + 'SAFETY CHECK PASSED (with human approval) — push allowed.' + C.reset);
  process.exit(0);
}

module.exports = { getStagedFiles, getChangedFiles, getUnstagedFiles, getUntrackedFiles, requestApproval };

main().catch((e) => {
  console.error('Pre-push check error:', e.message);
  process.exit(1);
});
