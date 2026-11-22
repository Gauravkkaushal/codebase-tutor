#!/usr/bin/env node
'use strict';
// Codebase Tutor launcher for npx.
//   npx codebase-tutor install --agent claude|codex|antigravity [--scope user|project] [--project DIR]
//   npx codebase-tutor <engine command...>      e.g.  npx codebase-tutor -C ./my-repo scan
// Requires Python 3.9+ on PATH (python3, python, or the Windows "py" launcher).
const { spawnSync } = require('child_process');
const path = require('path');

const root = path.resolve(__dirname, '..');
const args = process.argv.slice(2);

function findPython() {
  const candidates = process.platform === 'win32'
    ? [['py', ['-3']], ['python', []], ['python3', []]]
    : [['python3', []], ['python', []]];
  for (const [cmd, pre] of candidates) {
    const r = spawnSync(cmd, [...pre, '-c', 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'], { stdio: 'ignore' });
    if (r.status === 0) return [cmd, pre];
  }
  return null;
}

if (args.length === 0 || args[0] === '-h' || args[0] === '--help') {
  console.log(`Codebase Tutor — evidence-backed codebase learning skill

Usage:
  npx codebase-tutor install --agent claude|codex|antigravity [--scope user|project] [--project DIR] [--force]
  npx codebase-tutor -C <repo> scan | overview | trace "POST /login" --text | report --lang hinglish | ...
  npx codebase-tutor --version

Python 3.9+ is required. For JS/TS parsing also run: pip install -r <installed skill>/requirements.txt`);
  process.exit(0);
}

const py = findPython();
if (!py) {
  console.error('codebase-tutor: Python 3.9+ was not found on PATH (tried python3, python, py -3).');
  process.exit(1);
}
const [cmd, pre] = py;
const script = args[0] === 'install' ? path.join(root, 'scripts', 'install_skill.py') : path.join(root, 'scripts', 'ct.py');
const rest = args[0] === 'install' ? args.slice(1) : args;
const r = spawnSync(cmd, [...pre, script, ...rest], { stdio: 'inherit' });
process.exit(r.status === null ? 1 : r.status);
