const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const fs = require('fs');
const os = require('os');
const yaml = require('js-yaml');
const { exec } = require('child_process');

let win;

/* ── cached state to avoid re-reading config on every query ── */
let cachedWsl = null;        // { distro, linuxPath }
let cachedDbPath = '';       // linux path to .db
let cachedWikiDir = '';      // linux path to wiki dir
let cachedScriptPath = '';   // WSL path to db_query.py

function createWindow() {
  win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 700,
    minHeight: 500,
    frame: false,
    backgroundColor: '#0c0c0c',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: false,
      nodeIntegration: true,
    },
  });
  win.loadFile('index.html');
}

app.whenReady().then(createWindow);
app.on('window-all-closed', () => app.quit());

/* ── window controls ── */
ipcMain.on('win:minimize', () => win?.minimize());
ipcMain.on('win:maximize', () => {
  if (win?.isMaximized()) win.unmaximize(); else win?.maximize();
});
ipcMain.on('win:close', () => win?.close());

/* ── pick hermes home ── */
ipcMain.handle('pick-hermes-home', async () => {
  const result = await dialog.showOpenDialog(win, {
    title: 'Select Hermes Home Directory',
    properties: ['openDirectory'],
    defaultPath: '\\\\wsl$\\Ubuntu\\home',
  });
  if (result.canceled || !result.filePaths.length) return null;
  return result.filePaths[0];
});

/* ── WSL path helpers ── */
function parseWslPath(p) {
  const m = p.match(/^\\\\wsl\$?\\([^\\]+)\\(.+)$/i) ||
            p.match(/^\/\/wsl\$?\/([^/]+)\/(.+)$/i);
  if (!m) return null;
  return { distro: m[1], linuxPath: '/' + m[2].replace(/\\/g, '/') };
}

function resolveConfigPath(hermesHome) {
  const direct = path.join(hermesHome, 'config.yaml');
  if (fs.existsSync(direct)) return direct;
  const wsl = parseWslPath(hermesHome);
  if (wsl) {
    const unc = `\\\\wsl$\\${wsl.distro}${wsl.linuxPath.replace(/\//g, '\\')}\\config.yaml`;
    if (fs.existsSync(unc)) return unc;
  }
  return direct;
}

/* ── copy db_query.py once, reuse path ── */
function ensureScript() {
  if (cachedScriptPath) return cachedScriptPath;
  const src = path.join(__dirname, 'db_query.py');
  const tmp = path.join(os.tmpdir(), 'hmc_db_query.py');
  fs.copyFileSync(src, tmp);
  cachedScriptPath = tmp.replace(/^([A-Z]):/i, (_, d) => `/mnt/${d.toLowerCase()}`).replace(/\\/g, '/');
  return cachedScriptPath;
}

/* ── load config (also caches paths for db-query) ── */
ipcMain.handle('load-config', async (_e, hermesHome) => {
  try {
    const cfgPath = resolveConfigPath(hermesHome);
    if (!fs.existsSync(cfgPath)) return { error: `config.yaml not found at ${cfgPath}` };
    const raw = fs.readFileSync(cfgPath, 'utf-8');
    const doc = yaml.load(raw);
    const pluginCfg = doc?.plugins?.['consolidating-local-memory'] || {};

    // Cache WSL paths for fast db-query calls
    cachedWsl = parseWslPath(hermesHome);
    if (cachedWsl) {
      let dbRel = pluginCfg.db_path || '$HERMES_HOME/consolidating_memory.db';
      cachedDbPath = dbRel.replace('$HERMES_HOME', cachedWsl.linuxPath);
      let wikiRel = pluginCfg.wiki_export_dir || '$HERMES_HOME/consolidating_memory_wiki';
      cachedWikiDir = wikiRel.replace('$HERMES_HOME', cachedWsl.linuxPath);
    }
    // Pre-copy the script
    ensureScript();

    return { config: pluginCfg, fullConfig: doc, configPath: cfgPath };
  } catch (e) {
    return { error: e.message };
  }
});

/* ── save config ── */
ipcMain.handle('save-config', async (_e, hermesHome, pluginCfg) => {
  try {
    const cfgPath = resolveConfigPath(hermesHome);
    if (!fs.existsSync(cfgPath)) return { error: `config.yaml not found at ${cfgPath}` };
    const raw = fs.readFileSync(cfgPath, 'utf-8');
    const doc = yaml.load(raw) || {};
    if (!doc.plugins) doc.plugins = {};
    doc.plugins['consolidating-local-memory'] = pluginCfg;
    const out = yaml.dump(doc, { lineWidth: 120, noRefs: true, sortKeys: false, quotingType: "'", forceQuotes: false });
    fs.writeFileSync(cfgPath, out, 'utf-8');
    return { success: true };
  } catch (e) {
    return { error: e.message };
  }
});

/* ── async exec helper (returns Promise) ── */
function execAsync(cmd, opts) {
  return new Promise((resolve, reject) => {
    exec(cmd, opts, (err, stdout, stderr) => {
      if (err) { err.stderr = stderr; reject(err); }
      else resolve(stdout);
    });
  });
}

/* ── universal DB query via WSL python (non-blocking) ── */
ipcMain.handle('db-query', async (_e, hermesHome, queryType, queryArgs) => {
  try {
    // Use cached paths when available, fall back to parsing fresh
    let wsl = cachedWsl;
    let linuxDbPath = cachedDbPath;
    let wikiDir = cachedWikiDir;

    if (!wsl) {
      wsl = parseWslPath(hermesHome);
      if (!wsl) return { error: 'Use a WSL path (\\\\wsl$\\...).' };
      const cfgPath = resolveConfigPath(hermesHome);
      const raw = fs.readFileSync(cfgPath, 'utf-8');
      const doc = yaml.load(raw);
      const pluginCfg = doc?.plugins?.['consolidating-local-memory'] || {};
      let dbRel = pluginCfg.db_path || '$HERMES_HOME/consolidating_memory.db';
      linuxDbPath = dbRel.replace('$HERMES_HOME', wsl.linuxPath);
      let wikiRel = pluginCfg.wiki_export_dir || '$HERMES_HOME/consolidating_memory_wiki';
      wikiDir = wikiRel.replace('$HERMES_HOME', wsl.linuxPath);
      // Cache for next time
      cachedWsl = wsl;
      cachedDbPath = linuxDbPath;
      cachedWikiDir = wikiDir;
    }

    // For wiki queries, inject the wiki dir
    if (queryType === 'wiki_list' || queryType === 'wiki_read') {
      if (!queryArgs) queryArgs = {};
      if (queryType === 'wiki_list') queryArgs.wiki_dir = wikiDir;
      if (queryType === 'wiki_read' && queryArgs.file) {
        queryArgs.path = wikiDir + '/' + queryArgs.file;
      }
    }

    const scriptPath = ensureScript();
    const argsJson = JSON.stringify(queryArgs || {});
    const argsTmp = path.join(os.tmpdir(), 'hmc_args.json');
    fs.writeFileSync(argsTmp, argsJson, 'utf-8');
    const argsWsl = argsTmp.replace(/^([A-Z]):/i, (_, d) => `/mnt/${d.toLowerCase()}`).replace(/\\/g, '/');
    const cmd = `wsl -e python3 "${scriptPath}" "${linuxDbPath}" "${queryType}" "${argsWsl}"`;
    const out = await execAsync(cmd, { timeout: 20000, encoding: 'utf-8', maxBuffer: 10 * 1024 * 1024 });
    return JSON.parse(out.trim());
  } catch (e) {
    return { error: e.message };
  }
});
