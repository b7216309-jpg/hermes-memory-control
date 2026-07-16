'use strict';

const path = require('node:path');
const { spawn } = require('node:child_process');

const MAX_OUTPUT = 16 * 1024 * 1024;
const DEFAULT_TIMEOUT = 45_000;
const MUTATION_TIMEOUT = 300_000;
const scriptCache = new Map();

function run(executable, args, { input = '', timeout = DEFAULT_TIMEOUT, maxOutput = MAX_OUTPUT } = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(executable, args, {
      windowsHide: true,
      stdio: ['pipe', 'pipe', 'pipe'],
      shell: false,
    });
    let stdout = Buffer.alloc(0);
    let stderr = Buffer.alloc(0);
    let settled = false;
    let timer;
    const finish = (error, value) => {
      if (settled) return;
      settled = true;
      if (timer) clearTimeout(timer);
      if (error) reject(error);
      else resolve(value);
    };
    const abort = (error) => {
      finish(error);
      if (!child.killed) child.kill();
    };
    timer = setTimeout(() => {
      abort(new Error(`Operation timed out after ${timeout / 1000}s`));
    }, timeout);
    const append = (current, chunk) => {
      if (current.length + chunk.length > maxOutput) return null;
      return Buffer.concat([current, chunk]);
    };
    child.stdout.on('data', (chunk) => {
      if (settled) return;
      const next = append(stdout, chunk);
      if (next === null) abort(new Error('WSL bridge output exceeded the safety limit'));
      else stdout = next;
    });
    child.stderr.on('data', (chunk) => {
      if (settled) return;
      const next = append(stderr, chunk);
      if (next === null) abort(new Error('WSL bridge output exceeded the safety limit'));
      else stderr = next;
    });
    child.on('error', finish);
    child.on('close', (code) => {
      if (settled) return;
      if (code !== 0) {
        finish(new Error(stderr.toString('utf8').trim() || `WSL bridge exited with code ${code}`));
      } else finish(null, stdout.toString('utf8'));
    });
    child.stdin.on('error', finish);
    child.stdin.end(input, 'utf8');
  });
}

function cleanWslText(value) {
  return String(value).replace(/\0/g, '').replace(/\r/g, '').trim();
}

async function discoverProfiles() {
  const raw = await run('wsl.exe', ['-l', '-q'], { timeout: 10_000, maxOutput: 128 * 1024 });
  const distros = cleanWslText(raw).split('\n').map((item) => item.trim()).filter(Boolean);
  const profiles = [];
  for (const distro of distros) {
    if (!/^[\w .-]{1,80}$/.test(distro)) continue;
    try {
      const home = cleanWslText(await run(
        'wsl.exe',
        ['-d', distro, '--', 'sh', '-c', 'printf %s "$HOME/.hermes"'],
        { timeout: 10_000, maxOutput: 16 * 1024 },
      ));
      if (/^\/[\w@+.,/ -]{1,500}\/\.hermes$/.test(home)) profiles.push({ distro, home });
    } catch {
      // An unavailable distro is omitted instead of breaking discovery for all profiles.
    }
  }
  return profiles;
}

async function bridgeScript(profile) {
  if (scriptCache.has(profile.distro)) return scriptCache.get(profile.distro);
  const windowsPath = path.resolve(__dirname, '..', '..', 'bridge', 'control_bridge.py');
  // wsl.exe treats backslashes as escape characters when forwarding an argv
  // item. Forward slashes preserve the Windows drive path for wslpath.
  const forwardedPath = windowsPath.replace(/\\/g, '/');
  const converted = cleanWslText(await run(
    'wsl.exe',
    ['-d', profile.distro, '--', 'wslpath', '-a', '-u', forwardedPath],
    { timeout: 10_000, maxOutput: 16 * 1024 },
  ));
  if (!converted.startsWith('/')) throw new Error('Could not resolve the controller bridge inside WSL');
  scriptCache.set(profile.distro, converted);
  return converted;
}

async function runBridge(profile, operation, payload, { mutation = false } = {}) {
  if (typeof mutation !== 'boolean') throw new Error('mutation must be boolean');
  const script = await bridgeScript(profile);
  const python = `${profile.home}/hermes-agent/venv/bin/python3`;
  const request = JSON.stringify({
    protocol: 2,
    operation,
    payload,
    mutation,
  });
  const raw = await run(
    'wsl.exe',
    ['-d', profile.distro, '--', 'env', `HERMES_HOME=${profile.home}`, python, script],
    { input: request, timeout: mutation ? MUTATION_TIMEOUT : DEFAULT_TIMEOUT },
  );
  let result;
  try {
    result = JSON.parse(raw);
  } catch {
    throw new Error('WSL bridge returned malformed JSON');
  }
  if (!result || result.protocol !== 2) throw new Error('WSL bridge protocol mismatch');
  if (!result.ok) throw new Error(result.error?.message || 'WSL bridge operation failed');
  return result.data;
}

module.exports = { cleanWslText, discoverProfiles, runBridge, run };
