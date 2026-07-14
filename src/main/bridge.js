'use strict';

const path = require('node:path');
const { spawn } = require('node:child_process');

const MAX_OUTPUT = 16 * 1024 * 1024;
const DEFAULT_TIMEOUT = 45_000;
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
    const timer = setTimeout(() => {
      child.kill();
      if (!settled) reject(new Error(`Operation timed out after ${timeout / 1000}s`));
      settled = true;
    }, timeout);
    const append = (current, chunk) => {
      const next = Buffer.concat([current, chunk]);
      if (next.length > maxOutput) {
        child.kill();
        throw new Error('WSL bridge output exceeded the safety limit');
      }
      return next;
    };
    child.stdout.on('data', (chunk) => { try { stdout = append(stdout, chunk); } catch (error) { reject(error); } });
    child.stderr.on('data', (chunk) => { try { stderr = append(stderr, chunk); } catch (error) { reject(error); } });
    child.on('error', (error) => { clearTimeout(timer); if (!settled) reject(error); settled = true; });
    child.on('close', (code) => {
      clearTimeout(timer);
      if (settled) return;
      settled = true;
      if (code !== 0) {
        reject(new Error(stderr.toString('utf8').trim() || `WSL bridge exited with code ${code}`));
      } else resolve(stdout.toString('utf8'));
    });
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
  const script = await bridgeScript(profile);
  const python = `${profile.home}/hermes-agent/venv/bin/python3`;
  const request = JSON.stringify({
    protocol: 2,
    operation,
    payload,
    mutation: Boolean(mutation),
  });
  const raw = await run(
    'wsl.exe',
    ['-d', profile.distro, '--', 'env', `HERMES_HOME=${profile.home}`, python, script],
    { input: request, timeout: mutation ? 120_000 : DEFAULT_TIMEOUT },
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
