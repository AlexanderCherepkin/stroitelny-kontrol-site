'use strict';

// safety_check.js — Three-circuit safety engine for pre-commit/pre-push
// Implements: safety-control → mutual_check → control
// Zero dependencies. Run: node scripts/safety_check.js [--staged] [--all] [--json]

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const CODE_EXTENSIONS = new Set([
  '.js', '.ts', '.jsx', '.tsx', '.py', '.rb', '.go', '.rs', '.java',
  '.c', '.cpp', '.h', '.hpp', '.sh', '.bash', '.zsh', '.ps1', '.bat',
  '.php', '.pl', '.swift', '.kt', '.scala', '.r', '.sql', '.psql',
  '.yaml', '.yml', '.toml', '.json', '.xml', '.dockerfile', '.makefile'
]);

const DOC_EXTENSIONS = new Set(['.md', '.mdx', '.txt', '.rst', '.adoc']);

function isCodeFile(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  if (CODE_EXTENSIONS.has(ext)) return true;
  if (DOC_EXTENSIONS.has(ext)) return false;
  // No extension = could be a script
  if (!ext) return true;
  // Unknown extension — check content for shebang or code-like patterns later
  return true;
}

// ── Configuration ────────────────────────────────────────────────────────

const SAFETYIGNORE_PATH = path.resolve(__dirname, '..', '.safetyignore');

function loadSafetyIgnore() {
  try {
    const content = fs.readFileSync(SAFETYIGNORE_PATH, 'utf8');
    return content
      .split('\n')
      .map(l => l.trim())
      .filter(l => l && !l.startsWith('#'));
  } catch {
    return [];
  }
}

function isIgnored(filePath, patterns) {
  const normalized = filePath.replace(/\\/g, '/');
  for (const p of patterns) {
    if (normalized === p) return true;
    if (normalized.startsWith(p + '/')) return true;
    if (normalized.endsWith('/' + p)) return true;
    if (p.includes('*')) {
      const re = new RegExp('^' + p.replace(/\*/g, '.*').replace(/\?/g, '.') + '$');
      if (re.test(normalized)) return true;
    }
  }
  return false;
}

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
const MAX_DIFF_SIZE = 500 * 1024;       // 500KB per file in diff

const SENSITIVE_PATHS = [
  /\.env$/i, /\.env\./i, /credentials/i, /\.pem$/i, /\.key$/i,
  /\.pkcs12$/i, /\.pfx$/i, /id_rsa/i, /id_ed25519/i,
  /\.htpasswd$/i, /\.netrc$/i, /\.npmrc$/i
];

const SECRET_PATTERNS = [
  { pattern: /(?:api[_-]?key|apikey|api_secret|secret_key)\s*[:=]\s*['"][A-Za-z0-9_\-]{20,}['"]/gi, label: 'API key in code' },
  { pattern: /(?:password|passwd|pwd)\s*[:=]\s*['"][^'"]+['"]/gi, label: 'Hardcoded password' },
  { pattern: /(?:-----BEGIN\s+(?:RSA|DSA|EC|OPENSSH)\s+PRIVATE\s+KEY-----)/, label: 'Private key in code' },
  { pattern: /(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}/, label: 'GitHub access token' },
  { pattern: /(?:sk-[A-Za-z0-9]{32,})/, label: 'OpenAI/Stripe secret key' },
  { pattern: /(?:AKIA[0-9A-Z]{16})/, label: 'AWS access key' },
  { pattern: /(?:xox[baprs]-[A-Za-z0-9-]{10,})/, label: 'Slack token' },
  { pattern: /(?:eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,})/, label: 'JWT token (potential secret)' },
  { pattern: /(?:connectionString|conn_str|connection_string)\s*[:=]\s*['"][^'"]*(?:password|pwd|secret)[^'"]*['"]/gi, label: 'Connection string with credentials' },
];

// Matches cli.js HIGH_RISK_PATTERNS (code files only)
const DESTRUCTIVE_PATTERNS = [
  { pattern: /\brm\s+-rf\b/i,              label: 'rm -rf' },
  { pattern: /\bdrop\s+table\b/i,          label: 'DROP TABLE' },
  { pattern: /\btruncate\s+table\b/i,      label: 'TRUNCATE TABLE' },
  { pattern: /\bdrop\s+database\b/i,       label: 'DROP DATABASE' },
  { pattern: /\bshutdown\b/i,              label: 'shutdown command' },
  { pattern: /\bkill\s+-9\b/i,             label: 'kill -9' },
  { pattern: /\bsudo\b/i,                  label: 'sudo' },
  { pattern: /chmod\s+777/i,              label: 'chmod 777' },
  { pattern: /force\s+push/i,             label: 'force push' },
  { pattern: /--no-verify/i,              label: '--no-verify bypass' },
  { pattern: /git\s+reset\s+--hard/i,     label: 'git reset --hard' },
  { pattern: /git\s+clean\s+-[fdx]/i,     label: 'git clean -f' },
];

// Files that should NOT be committed
const BLOCKED_FILE_PATTERNS = [
  { pattern: /^\.env$/, label: '.env file' },
  { pattern: /node_modules\//, label: 'node_modules' },
  { pattern: /\.pyc$/, label: 'Python bytecode' },
  { pattern: /__pycache__\//, label: 'Python cache' },
  { pattern: /\.pem$/, label: 'PEM certificate/key' },
  { pattern: /\.key$/i, label: 'Private key file' },
  { pattern: /\.pfx$/i, label: 'PFX certificate' },
];

// ── Severity ─────────────────────────────────────────────────────────────

const SEVERITY = { CRITICAL: 'critical', HIGH: 'high', MEDIUM: 'medium', LOW: 'low' };

// ── Circuit 1: Input Safety (safety-control) ─────────────────────────────

function sanitizeFileName(filePath) {
  const normalized = filePath.replace(/\\/g, '/');
  const suspicious = [
    /\.\./, /~/, /\0/, /[\x00-\x08]/, /[\x0B\x0C]/, /[\x0E-\x1F]/,
  ];
  for (const p of suspicious) {
    if (p.test(normalized)) {
      return { safe: false, reason: `Suspicious characters in path: ${filePath}` };
    }
  }
  return { safe: true, normalized };
}

function detectSecrets(content, filePath) {
  const findings = [];
  for (const { pattern, label } of SECRET_PATTERNS) {
    pattern.lastIndex = 0;
    const matches = content.match(pattern);
    if (matches) {
      findings.push({
        type: 'secret',
        severity: SEVERITY.CRITICAL,
        file: filePath,
        label,
        matches: matches.length
      });
    }
  }
  return findings;
}

function detectDestructiveCommands(content, filePath) {
  const findings = [];
  for (const { pattern, label } of DESTRUCTIVE_PATTERNS) {
    pattern.lastIndex = 0;
    if (pattern.test(content)) {
      findings.push({
        type: 'destructive_command',
        severity: SEVERITY.HIGH,
        file: filePath,
        label
      });
    }
  }
  return findings;
}

function checkBlockedFiles(filePath) {
  const normalized = filePath.replace(/\\/g, '/');
  for (const { pattern, label } of BLOCKED_FILE_PATTERNS) {
    if (pattern.test(normalized)) {
      return { blocked: true, label, severity: SEVERITY.HIGH };
    }
  }
  return { blocked: false };
}

function threatDetect(content, filePath) {
  const findings = [];
  const suspicious = [
    { pattern: /\beval\s*\(/g, label: 'eval() call' },
    { pattern: /child_process\.exec\s*\(/g, label: 'child_process.exec()' },
    { pattern: /os\.system\s*\(/g, label: 'os.system()' },
    { pattern: /subprocess\.call\s*\(\s*['"]/g, label: 'subprocess.call()' },
    { pattern: /new\s+Function\s*\(/g, label: 'new Function()' },
    { pattern: /document\.write\s*\(/g, label: 'document.write()' },
    { pattern: /innerHTML\s*=/g, label: 'innerHTML assignment' },
    { pattern: /dangerouslySetInnerHTML/g, label: 'dangerouslySetInnerHTML' },
  ];

  for (const { pattern, label } of suspicious) {
    pattern.lastIndex = 0;
    if (pattern.test(content)) {
      findings.push({
        type: 'security_threat',
        severity: SEVERITY.MEDIUM,
        file: filePath,
        label
      });
    }
  }

  const dataLeakPatterns = [
    { pattern: /console\.(log|warn|error)\s*\([^)]*\b(?:password|secret|token|key|credential)\b/gi, label: 'console.log with sensitive data' },
    { pattern: /(?:TODO|FIXME|HACK|XXX)\s*[:\-]\s*.*(?:password|secret|token|key)/gi, label: 'TODO/FIXME referencing secrets' },
  ];
  for (const { pattern, label } of dataLeakPatterns) {
    pattern.lastIndex = 0;
    if (pattern.test(content)) {
      findings.push({
        type: 'data_leak',
        severity: SEVERITY.MEDIUM,
        file: filePath,
        label
      });
    }
  }

  return findings;
}

// ── Circuit 2: Mutual Check (cross-validation) ───────────────────────────

function validateFileSize(filePath) {
  try {
    const stat = fs.statSync(filePath);
    if (stat.size > MAX_FILE_SIZE) {
      return {
        valid: false,
        reason: `File too large: ${filePath} (${(stat.size / 1024 / 1024).toFixed(1)}MB > ${MAX_FILE_SIZE / 1024 / 1024}MB)`,
        severity: SEVERITY.HIGH
      };
    }
    if (stat.size === 0) {
      return { valid: false, reason: `Empty file: ${filePath}`, severity: SEVERITY.LOW };
    }
    return { valid: true };
  } catch {
    return { valid: false, reason: `Cannot stat file: ${filePath}`, severity: SEVERITY.MEDIUM };
  }
}

function validateEncoding(filePath) {
  try {
    const buf = fs.readFileSync(filePath);
    // Check for null bytes (binary file)
    if (buf.includes(0x00)) {
      return { valid: false, reason: `Binary/null bytes in: ${filePath}`, severity: SEVERITY.MEDIUM };
    }
    return { valid: true };
  } catch {
    return { valid: false, reason: `Cannot read: ${filePath}`, severity: SEVERITY.HIGH };
  }
}

function checkConsistency(filePath, content) {
  const findings = [];
  const ext = path.extname(filePath).toLowerCase();

  if (ext === '.json') {
    try {
      JSON.parse(content);
    } catch (e) {
      findings.push({
        type: 'consistency',
        severity: SEVERITY.HIGH,
        file: filePath,
        label: `Invalid JSON: ${e.message}`
      });
    }
  }

  if (ext === '.md') {
    const linkPattern = /\[([^\]]+)\]\(([^)]+)\)/g;
    let match;
    while ((match = linkPattern.exec(content)) !== null) {
      if (match[2].startsWith('http')) continue;
      if (match[2].includes('..')) {
        findings.push({
          type: 'consistency',
          severity: SEVERITY.LOW,
          file: filePath,
          label: `Suspicious relative link: ${match[2]}`
        });
      }
    }
  }

  return findings;
}

function crossValidate(findings) {
  const criticalCount = findings.filter(f => f.severity === SEVERITY.CRITICAL).length;
  const highCount = findings.filter(f => f.severity === SEVERITY.HIGH).length;
  const mediumCount = findings.filter(f => f.severity === SEVERITY.MEDIUM).length;

  const status = criticalCount > 0 ? 'BLOCKED'
    : highCount > 0 ? 'WARNING'
    : 'PASS';

  return { status, criticalCount, highCount, mediumCount, totalFindings: findings.length };
}

// ── Circuit 3: Control (runtime enforcement) ─────────────────────────────

function enforcePolicy(findings, allowlist) {
  const allowSet = new Set(allowlist || []);
  const violations = [];

  for (const f of findings) {
    if (f.severity === SEVERITY.CRITICAL && !allowSet.has(f.label)) {
      violations.push({ ...f, action: 'BLOCK' });
    }
    if (f.severity === SEVERITY.HIGH && !allowSet.has(f.label)) {
      violations.push({ ...f, action: 'WARN' });
    }
  }

  return violations;
}

// ── Main scanner ─────────────────────────────────────────────────────────

function scanFile(filePath, options) {
  const findings = [];

  // Input sanitization
  const sanitize = sanitizeFileName(filePath);
  if (!sanitize.safe) {
    findings.push({ type: 'sanitization', severity: SEVERITY.HIGH, file: filePath, label: sanitize.reason });
    return findings; // don't proceed with unsafe paths
  }

  // Blocked file check
  const blocked = checkBlockedFiles(sanitize.normalized);
  if (blocked.blocked) {
    findings.push({ type: 'blocked_file', severity: blocked.severity, file: filePath, label: blocked.label });
    return findings;
  }

  // File size
  const sizeCheck = validateFileSize(filePath);
  if (!sizeCheck.valid) {
    findings.push({ type: 'file_size', severity: sizeCheck.severity, file: filePath, label: sizeCheck.reason });
  }

  // Encoding check
  const encodingCheck = validateEncoding(filePath);
  if (!encodingCheck.valid) {
    findings.push({ type: 'encoding', severity: encodingCheck.severity, file: filePath, label: encodingCheck.reason });
    return findings; // don't analyze binary files further
  }

  let content;
  try {
    content = fs.readFileSync(filePath, 'utf8');
  } catch {
    findings.push({ type: 'io_error', severity: SEVERITY.HIGH, file: filePath, label: 'Cannot read file' });
    return findings;
  }

  // Secret detection
  if (options.checkSecrets !== false) {
    findings.push(...detectSecrets(content, sanitize.normalized));
  }

  // Destructive command detection (code files only — not docs)
  if (options.checkDestructive !== false && isCodeFile(filePath)) {
    findings.push(...detectDestructiveCommands(content, sanitize.normalized));
  }

  // Threat detection (code files only)
  if (options.checkThreats !== false && isCodeFile(filePath)) {
    findings.push(...threatDetect(content, sanitize.normalized));
  }

  // Consistency (JSON, markdown)
  findings.push(...checkConsistency(filePath, content));

  return findings;
}

function scanFiles(filePaths, options) {
  const allFindings = [];
  const fileResults = [];
  const ignorePatterns = loadSafetyIgnore();
  const builtinIgnore = ['.safetyignore', 'package.json', 'package-lock.json', '.venv', '.tmp'];

  for (const fp of filePaths) {
    if (isIgnored(fp, builtinIgnore)) continue;
    if (isIgnored(fp, ignorePatterns)) continue;

    const findings = scanFile(fp, options || {});
    fileResults.push({ file: fp, findings, passed: findings.filter(f => f.severity === SEVERITY.CRITICAL || f.severity === SEVERITY.HIGH).length === 0 });
    allFindings.push(...findings);
  }

  const validation = crossValidate(allFindings);
  const violations = enforcePolicy(allFindings);

  return {
    files_scanned: filePaths.length,
    findings: allFindings,
    validation,
    violations,
    file_results: fileResults,
    timestamp: new Date().toISOString()
  };
}

function formatReport(result) {
  const lines = [];
  lines.push('='.repeat(60));
  lines.push('  SAFETY CHECK REPORT — ' + result.timestamp);
  lines.push('='.repeat(60));
  lines.push(`  Files scanned: ${result.files_scanned}`);
  lines.push(`  Findings: ${result.findings.length} (${result.validation.criticalCount} critical, ${result.validation.highCount} high, ${result.validation.mediumCount} medium)`);
  lines.push(`  Status: ${result.validation.status}`);
  lines.push('');

  if (result.findings.length === 0) {
    lines.push('  No issues found. Clean.');
    return lines.join('\n');
  }

  const bySeverity = {};
  for (const f of result.findings) {
    if (!bySeverity[f.severity]) bySeverity[f.severity] = [];
    bySeverity[f.severity].push(f);
  }

  for (const sev of [SEVERITY.CRITICAL, SEVERITY.HIGH, SEVERITY.MEDIUM, SEVERITY.LOW]) {
    const items = bySeverity[sev] || [];
    if (items.length === 0) continue;
    const prefix = sev === SEVERITY.CRITICAL ? 'CRIT' : sev === SEVERITY.HIGH ? 'HIGH' : sev === SEVERITY.MEDIUM ? 'MED ' : 'LOW ';
    for (const f of items) {
      lines.push(`  [${prefix}] ${f.file}: ${f.label}`);
    }
  }

  lines.push('');
  if (result.validation.status === 'BLOCKED') {
    lines.push('  RESULT: BLOCKED — critical issues must be resolved.');
  } else if (result.validation.status === 'WARNING') {
    lines.push('  RESULT: WARNING — review high-severity issues before proceeding.');
  } else {
    lines.push('  RESULT: PASS — no blocking issues.');
  }

  return lines.join('\n');
}

// ── CLI ──────────────────────────────────────────────────────────────────

function main() {
  const args = process.argv.slice(2);
  const jsonOutput = args.includes('--json');
  const checkStaged = args.includes('--staged');
  const checkAll = args.includes('--all');

  let files = [];

  if (checkStaged) {
    try {
      const { execFileSync } = require('child_process');
      const output = execFileSync('git', ['diff', '--cached', '--name-only', '--diff-filter=ACM'], { encoding: 'utf8' });
      files = output.trim().split('\n').filter(Boolean);
    } catch {
      console.error('Not a git repository or git not available.');
      process.exit(1);
    }
  } else if (checkAll) {
    function walk(dir) {
      const entries = fs.readdirSync(dir, { withFileTypes: true });
      for (const e of entries) {
        const full = path.join(dir, e.name);
        if (e.isDirectory()) {
          if (e.name === 'node_modules' || e.name === '.git' || e.name === '__pycache__' || e.name === '.backup') continue;
          walk(full);
        } else {
          files.push(full);
        }
      }
    }
    walk('.');
  } else {
    files = args.filter(a => !a.startsWith('--')).map(f => path.resolve(f));
    if (files.length === 0) {
      console.log('Usage: node scripts/safety_check.js [--staged|--all|file1 file2 ...] [--json]');
      console.log('  --staged   Scan git staged files');
      console.log('  --all      Scan all project files');
      console.log('  --json     Output JSON');
      process.exit(0);
    }
  }

  const result = scanFiles(files);

  if (jsonOutput) {
    console.log(JSON.stringify(result, null, 2));
  } else {
    console.log(formatReport(result));
  }

  if (result.validation.status === 'BLOCKED') {
    process.exit(1);
  }
}

module.exports = {
  scanFile, scanFiles, formatReport,
  detectSecrets, detectDestructiveCommands, threatDetect,
  checkBlockedFiles, validateFileSize, validateEncoding,
  crossValidate, enforcePolicy,
  SECRET_PATTERNS, DESTRUCTIVE_PATTERNS, BLOCKED_FILE_PATTERNS,
  SEVERITY
};

if (require.main === module) {
  main();
}
