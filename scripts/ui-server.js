'use strict';

const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.png': 'image/png', '.map': 'application/json' };
const server = http.createServer((request, response) => {
  const url = new URL(request.url, 'http://127.0.0.1');
  if (url.pathname === '/') {
    response.writeHead(302, { Location: '/renderer/index.html', 'Cache-Control': 'no-store' }).end();
    return;
  }
  const relative = decodeURIComponent(url.pathname.slice(1));
  const file = path.resolve(root, relative);
  if (root !== file && !file.startsWith(root + path.sep)) { response.writeHead(403).end('Forbidden'); return; }
  fs.readFile(file, (error, data) => {
    if (error) { response.writeHead(error.code === 'ENOENT' ? 404 : 500).end('Not found'); return; }
    response.writeHead(200, { 'Content-Type': types[path.extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
    response.end(data);
  });
});
server.listen(4173, '127.0.0.1', () => process.stdout.write('Hermes Control Center UI: http://127.0.0.1:4173/\n'));
