#!/usr/bin/env node
'use strict';

/**
 * Agentic Loop — Unified CLI Facade
 *
 * Node.js entry point that delegates to the Python runtime engine.
 * Commands: run, status, validate, list-agents, mcp-connect, tui
 *
 * Usage:
 *   node cli.js run "Analyze project structure"
 *   node cli.js status
 *   node cli.js validate
 *   node cli.js list-agents
 */

const { Command } = require('commander');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const ora = require('ora');
const chalk = require('chalk');

const pkg = JSON.parse(fs.readFileSync(path.join(__dirname, 'package.json'), 'utf8'));

function loadModelConfig() {
  const configPath = path.join(__dirname, 'config', 'models.json');
  if (!fs.existsSync(configPath)) return null;
  return JSON.parse(fs.readFileSync(configPath, 'utf8'));
}

function validateModelConfig(config, provider, model) {
  if (!config) return { ok: true };
  const p = config.providers[provider];
  if (!p) {
    return { ok: false, error: `Unknown provider: ${provider}. Available: ${Object.keys(config.providers).join(', ')}` };
  }
  if (model && !p.models[model]) {
    return { ok: false, error: `Unknown model: ${model} for provider ${provider}. Available: ${Object.keys(p.models).join(', ')}` };
  }
  return { ok: true, defaultModel: p.default_model };
}

// ── Helpers ───────────────────────────────────────────────────────────

function runPython(args, { inherit = false, silent = false } = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn('python', ['-m', 'runtime.main', ...args], {
      cwd: __dirname,
      stdio: inherit ? 'inherit' : ['ignore', 'pipe', 'pipe'],
    });

    let stdout = '';
    let stderr = '';

    if (!inherit) {
      child.stdout.on('data', (d) => {
        stdout += d.toString();
        if (!silent) process.stdout.write(d.toString());
      });
      child.stderr.on('data', (d) => {
        stderr += d.toString();
        if (!silent) process.stderr.write(d.toString());
      });
    }

    child.on('close', (code) => resolve({ code, stdout, stderr }));
    child.on('error', (err) => reject(err));
  });
}

function runPythonCli(args) {
  return new Promise((resolve, reject) => {
    const child = spawn('python', ['-m', 'runtime.cli', ...args], {
      cwd: __dirname,
      stdio: 'inherit',
    });
    child.on('close', (code) => resolve(code));
    child.on('error', (err) => reject(err));
  });
}

function runJs(scriptPath) {
  return new Promise((resolve, reject) => {
    const child = spawn('node', [scriptPath], {
      cwd: __dirname,
      stdio: 'inherit',
    });
    child.on('close', (code) => resolve(code));
    child.on('error', (err) => reject(err));
  });
}

function extractJsonFromOutput(stdout) {
  const lines = stdout.trim().split('\n');
  for (let i = lines.length - 1; i >= 0; i--) {
    const line = lines[i].trim();
    if (!line) continue;
    try {
      return JSON.parse(line);
    } catch {
      continue;
    }
  }
  return null;
}

function formatDuration(ms) {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

// ── Commands ─────────────────────────────────────────────────────────

const program = new Command();
program
  .name('agentic-loop')
  .description('Agentic Loop — unified CLI facade for Python runtime + MCP')
  .version(pkg.version);

program
  .command('run <task>')
  .description('Execute a task through the agent pipeline')
  .option('-i, --max-iterations <n>', 'max ReAct iterations', '5')
  .option('-p, --provider <provider>', 'LLM provider', 'anthropic')
  .option('-m, --model <model>', 'model override')
  .option('-s, --session-id <id>', 'resume existing session')
  .option('--demo', 'run in demo mode')
  .option('--tui', 'launch TUI dashboard (Python)')
  .action(async (task, options) => {
    const modelConfig = loadModelConfig();
    const validation = validateModelConfig(modelConfig, options.provider, options.model);
    if (!validation.ok) {
      console.error(chalk.red(`[CLI] ${validation.error}`));
      process.exit(1);
    }
    const effectiveModel = options.model || validation.defaultModel;
    if (modelConfig && !options.model) {
      console.log(chalk.dim(`[CLI] Using default model: ${effectiveModel} (${options.provider})`));
    }

    if (options.tui) {
      const tuiArgs = ['-m', 'runtime.tui'];
      if (options.sessionId) tuiArgs.push('--session', options.sessionId);
      const child = spawn('python', tuiArgs, { cwd: __dirname, stdio: 'inherit' });
      child.on('close', (code) => process.exit(code));
      child.on('error', (err) => { console.error(chalk.red(`TUI error: ${err.message}`)); process.exit(1); });
      return;
    }

    const pyArgs = [task, '--max-iterations', options.maxIterations, '--provider', options.provider];
    if (effectiveModel) pyArgs.push('--model', effectiveModel);
    if (options.sessionId) pyArgs.push('--session-id', options.sessionId);
    if (options.demo) pyArgs.push('--demo');

    const spinner = ora({
      text: chalk.cyan(`Running ReAct pipeline: ${chalk.bold(task)}`),
      spinner: 'dots',
    }).start();

    const start = Date.now();
    let result;
    try {
      result = await runPython(pyArgs, { silent: true });
    } catch (err) {
      spinner.fail(chalk.red(`Failed to start runtime: ${err.message}`));
      process.exit(1);
    }

    const elapsed = Date.now() - start;
    spinner.stop();

    if (result.code !== 0) {
      console.error(chalk.red(`\n[CLI] Runtime exited with code ${result.code}`));
      if (result.stderr) console.error(result.stderr);
      process.exit(1);
    }

    const json = extractJsonFromOutput(result.stdout);
    if (json && json.status) {
      const statusColor = json.status === 'success' ? chalk.green : json.status === 'partial' ? chalk.yellow : chalk.red;
      console.log(`\n${chalk.bold('Status:')} ${statusColor(json.status)}  ${chalk.dim(`(${formatDuration(json.time_ms || elapsed)})`)}`);
      console.log(`${chalk.bold('Iterations:')} ${json.iterations || '?'}`);
      console.log(`${chalk.bold('Session:')} ${chalk.dim(json.session_id || 'unknown')}`);
      if (json.response) {
        console.log(`\n${chalk.bold('Response:')}`);
        console.log(json.response);
      }
    } else {
      console.log(result.stdout);
    }
  });

program
  .command('status')
  .description('Show active sessions and runtime stats')
  .action(async () => {
    await runPythonCli(['status']);
  });

program
  .command('list-agents')
  .description('List all loaded agents from .agent_loop/')
  .action(async () => {
    await runPython(['--list-agents'], { inherit: true });
  });

program
  .command('validate')
  .description('Run runtime component validators')
  .action(async () => {
    let ok = true;

    console.log(chalk.bold.cyan('\n=== Validating Python Runtime ===\n'));
    const pyResult = await runPython(['--validate'], { inherit: true });
    if (pyResult.code !== 0) {
      ok = false;
      console.error(chalk.red('Python validation failed'));
    }

    console.log(chalk.bold.cyan('\n=== Validating Cross-References ===\n'));
    const crossRefCode = await runJs('.agent_loop/scripts/validate_cross_references.js');
    if (crossRefCode !== 0) {
      ok = false;
      console.error(chalk.red('Cross-reference validation failed'));
    }

    console.log(chalk.bold.cyan('\n=== Validating Consistency ===\n'));
    const consistencyCode = await runJs('.agent_loop/scripts/validate_consistency.js');
    if (consistencyCode !== 0) {
      ok = false;
      console.error(chalk.red('Consistency validation failed'));
    }

    if (ok) {
      console.log(chalk.bold.green('\n=== All validations passed ===\n'));
    } else {
      console.log(chalk.bold.red('\n=== Some validations failed ===\n'));
      process.exit(1);
    }
  });

program
  .command('mcp-connect')
  .description('Connect to all configured MCP servers and list tools')
  .action(async () => {
    console.log(chalk.yellow('[CLI] mcp-connect: delegating to Python runtime...'));
    await runPythonCli(['mcp-connect']);
  });

program
  .command('tui')
  .description('Launch TUI dashboard')
  .action(() => {
    const child = spawn('python', ['-m', 'runtime.tui'], { cwd: __dirname, stdio: 'inherit' });
    child.on('close', (code) => process.exit(code));
    child.on('error', (err) => { console.error(chalk.red(`TUI error: ${err.message}`)); process.exit(1); });
  });

program
  .command('health')
  .description('Show runtime health status')
  .action(async () => {
    await runPythonCli(['health']);
  });

program
  .command('approve <id>')
  .description('Approve a pending human-approval gate')
  .action(async (id) => {
    await runPythonCli(['approve', id]);
  });

program
  .command('demo')
  .description('Run demo with sample request')
  .option('-i, --max-iterations <n>', 'max iterations', '3')
  .action(async (options) => {
    const pyArgs = ['--demo', '--max-iterations', options.maxIterations];
    await runPython(pyArgs, { inherit: true });
  });

// ── Entry ───────────────────────────────────────────────────────────

program.parse(process.argv);
if (!process.argv.slice(2).length) {
  program.help();
}
