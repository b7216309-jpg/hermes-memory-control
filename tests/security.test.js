'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const read = (name) => fs.readFileSync(path.join(root, name), 'utf8');

test('Electron renderer is isolated and sandboxed', () => {
  const source = read('main.js');
  assert.match(source, /contextIsolation:\s*true/);
  assert.match(source, /nodeIntegration:\s*false/);
  assert.match(source, /sandbox:\s*true/);
  assert.match(source, /webSecurity:\s*true/);
  assert.doesNotMatch(source, /contextIsolation:\s*false/);
  assert.doesNotMatch(source, /nodeIntegration:\s*true/);
  assert.match(source, /setWindowOpenHandler\(\(\) => \(\{ action: 'deny' \}\)\)/);
});

test('preload exposes a narrow contextBridge API and no raw IPC object', () => {
  const source = read('preload.js');
  assert.match(source, /contextBridge\.exposeInMainWorld/);
  assert.doesNotMatch(source, /window\.api/);
  assert.doesNotMatch(source, /exposeInMainWorld\([^,]+,\s*ipcRenderer/);
});

test('bridge launches WSL without a shell or command-string interpolation', () => {
  const source = read('src/main/bridge.js');
  assert.match(source, /shell:\s*false/);
  assert.doesNotMatch(source, /exec\s*\(/);
  assert.doesNotMatch(source, /execSync/);
});

test('renderer CSP blocks remote code and unsafe inline script', () => {
  const source = read('renderer/index.html');
  assert.match(source, /default-src 'self'/);
  assert.match(source, /script-src 'self'/);
  assert.match(source, /object-src 'none'/);
  assert.doesNotMatch(source, /unsafe-inline|unsafe-eval|https:/);
});

test('retired unrestricted database helper is gone', () => {
  assert.equal(fs.existsSync(path.join(root, 'db_query.py')), false);
});

test('the complete test command includes the Electron smoke gate', () => {
  const pkg = JSON.parse(read('package.json'));
  assert.match(pkg.scripts['test:all'], /npm run test:electron/);
});

test('renderer serializes confirmed mutations and main bounds previews', () => {
  assert.match(read('renderer/app.js'), /mutationInFlight/);
  assert.match(read('main.js'), /MAX_PENDING_PLANS\s*=\s*100/);
});
