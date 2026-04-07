/* ── Wiki Viewer (Markdown rendering) ── */
'use strict';

const { marked } = require('marked');

// Configure marked for safe rendering
marked.setOptions({
  gfm: true,
  breaks: false,
});

let wikiFiles = [];
let currentWikiFile = '';

async function loadWikiNav() {
  if (!hermesHome) return;
  const nav = document.getElementById('wiki-nav');
  nav.innerHTML = '<div class="wiki-nav-sec">loading...</div>';

  const r = await dbq('wiki_list');
  if (!r || r.error) {
    nav.innerHTML = `<div class="wiki-nav-sec" style="color:var(--rd)">${r?.error || 'failed to load'}</div>`;
    return;
  }
  wikiFiles = r.files || [];
  if (!wikiFiles.length) {
    nav.innerHTML = '<div class="wiki-nav-sec">no wiki files found</div><div class="wiki-nav-item" style="color:var(--fg3)">enable wiki_export in config</div>';
    return;
  }

  nav.innerHTML = '';

  // Group by directory
  const groups = {};
  wikiFiles.forEach(f => {
    const parts = f.split('/');
    const dir = parts.length > 1 ? parts[0] : '';
    if (!groups[dir]) groups[dir] = [];
    groups[dir].push(f);
  });

  // Render index first
  if (groups['']) {
    groups[''].forEach(f => {
      nav.appendChild(makeNavItem(f, f));
    });
  }

  // Then each directory
  Object.keys(groups).sort().forEach(dir => {
    if (dir === '') return;
    const sec = document.createElement('div');
    sec.className = 'wiki-nav-sec';
    sec.textContent = dir;
    nav.appendChild(sec);
    groups[dir].sort().forEach(f => {
      const label = f.split('/').pop().replace('.md', '');
      nav.appendChild(makeNavItem(f, label));
    });
  });

  // Auto-load index.md if exists
  if (wikiFiles.includes('index.md')) {
    loadWikiPage('index.md');
  }
}

function makeNavItem(file, label) {
  const el = document.createElement('div');
  el.className = 'wiki-nav-item';
  el.textContent = label;
  el.title = file;
  el.addEventListener('click', () => loadWikiPage(file));
  return el;
}

async function loadWikiPage(file) {
  currentWikiFile = file;
  const content = document.getElementById('wiki-content');
  content.innerHTML = '<p style="color:var(--fg3)">loading...</p>';

  // Highlight active nav
  document.querySelectorAll('.wiki-nav-item').forEach(el => {
    el.classList.toggle('active', el.title === file);
  });

  const r = await dbq('wiki_read', { file });
  if (!r || r.error) {
    content.innerHTML = `<p style="color:var(--rd)">${r?.error || 'failed to load'}</p>`;
    return;
  }

  const md = r.content || '';

  // Override link click handler to navigate internally
  const html = marked.parse(md);
  content.innerHTML = html;

  // Intercept internal links
  content.querySelectorAll('a').forEach(a => {
    const href = a.getAttribute('href') || '';
    if (href.startsWith('http://') || href.startsWith('https://')) return;
    if (href.endsWith('.md') || href.includes('/')) {
      a.addEventListener('click', e => {
        e.preventDefault();
        // Resolve relative path
        const resolved = resolveRelativePath(currentWikiFile, href);
        if (wikiFiles.includes(resolved)) {
          loadWikiPage(resolved);
        }
      });
    }
  });
}

function resolveRelativePath(from, to) {
  if (!to.includes('..') && !to.startsWith('./')) {
    // Already relative to root or same directory
    const dir = from.includes('/') ? from.substring(0, from.lastIndexOf('/')) : '';
    return dir ? dir + '/' + to : to;
  }
  const fromParts = from.split('/');
  fromParts.pop(); // remove filename
  const toParts = to.split('/');
  for (const part of toParts) {
    if (part === '..') fromParts.pop();
    else if (part !== '.') fromParts.push(part);
  }
  return fromParts.join('/');
}

document.getElementById('btn-load-wiki')?.addEventListener('click', loadWikiNav);

window.loadWikiNav = loadWikiNav;
