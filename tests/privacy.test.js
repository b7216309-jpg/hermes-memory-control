'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const publicExtensions = new Set(['.css', '.html', '.js', '.json', '.md', '.py', '.yaml', '.yml']);
const privateMarkers = ['savi' + 'nien', 'aez' + 'aror', 'cau' + 'dry', 'sk-' + 'proj-'];

function publicFiles(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    if (['.git', 'dist', 'node_modules'].includes(entry.name)) return [];
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) return publicFiles(target);
    return publicExtensions.has(path.extname(entry.name).toLowerCase()) ? [target] : [];
  });
}

test('public tree contains no personal markers', () => {
  const findings = [];
  for (const file of publicFiles(root)) {
    const text = fs.readFileSync(file, 'utf8').toLowerCase();
    for (const marker of privateMarkers) {
      if (text.includes(marker)) findings.push(`${path.relative(root, file)}: ${marker}`);
    }
  }
  assert.deepEqual(findings, []);
});

test('README references only explicitly anonymous screenshots', () => {
  const readme = fs.readFileSync(path.join(root, 'README.md'), 'utf8');
  const imagePaths = [...readme.matchAll(/!\[[^\]]*\]\((screenshots\/[^)]+)\)/g)].map((match) => match[1]);
  const expected = [
    'screenshots/config-anonymous.png',
    'screenshots/dashboard-anonymous.png',
    'screenshots/educational-lab-anonymous.png',
    'screenshots/graph-anonymous.png',
    'screenshots/memory-anonymous.png',
  ];
  assert.deepEqual(imagePaths.sort(), expected);
  assert.deepEqual(
    fs.readdirSync(path.join(root, 'screenshots')).filter((name) => /\.(?:png|jpe?g)$/i.test(name)).sort(),
    expected.map((name) => path.basename(name)).sort(),
  );
});

test('screenshot demo profile is synthetic', () => {
  const demo = fs.readFileSync(path.join(root, 'renderer', 'demo-api.js'), 'utf8');
  assert.match(demo, /PUBLIC DEMO DATA ONLY/);
  assert.match(demo, /\/home\/demo\/\.hermes/);
  assert.doesNotMatch(demo, /\/home\/(?!demo\/)[^'"\s]+\/\.hermes/i);
  assert.match(demo, /deadc0de12345678cafefeed/);
  assert.deepEqual(
    [...demo.matchAll(/id: '([a-f0-9]{24})'/g)].map((match) => match[1]),
    ['deadc0de12345678cafefeed'],
  );
});
