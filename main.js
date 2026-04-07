const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const fs = require('fs');
const os = require('os');
const yaml = require('js-yaml');
const { execSync } = require('child_process');
const { mockQuery, MOCK_CONFIG } = require('./mock_data');

let win;
const MOCK_MODE = process.argv.includes('--mock');

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

/* ── mock mode IPC ── */
ipcMain.handle('is-mock', () => MOCK_MODE);

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

/* ── load config ── */
ipcMain.handle('load-config', async (_e, hermesHome) => {
  if (MOCK_MODE) return MOCK_CONFIG;
  try {
    const cfgPath = resolveConfigPath(hermesHome);
    if (!fs.existsSync(cfgPath)) return { error: `config.yaml not found at ${cfgPath}` };
    const raw = fs.readFileSync(cfgPath, 'utf-8');
    const doc = yaml.load(raw);
    const pluginCfg = doc?.plugins?.['consolidating-local-memory'] || {};
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

/* ── universal DB query via WSL python ── */
function wslTempScript() {
  const src = path.join(__dirname, 'db_query.py');
  const tmp = path.join(os.tmpdir(), 'hmc_db_query.py');
  fs.copyFileSync(src, tmp);
  return tmp.replace(/^([A-Z]):/i, (_, d) => `/mnt/${d.toLowerCase()}`).replace(/\\/g, '/');
}

ipcMain.handle('db-query', async (_e, hermesHome, queryType, queryArgs) => {
  if (MOCK_MODE) return mockQuery(queryType, queryArgs);
  try {
    const wsl = parseWslPath(hermesHome);
    if (!wsl) return { error: 'Use a WSL path (\\\\wsl$\\...).' };

    const cfgPath = resolveConfigPath(hermesHome);
    const raw = fs.readFileSync(cfgPath, 'utf-8');
    const doc = yaml.load(raw);
    const pluginCfg = doc?.plugins?.['consolidating-local-memory'] || {};

    let dbRelative = pluginCfg.db_path || '$HERMES_HOME/consolidating_memory.db';
    const linuxDbPath = dbRelative.replace('$HERMES_HOME', wsl.linuxPath);

    // For wiki queries, resolve wiki dir
    if (queryType === 'wiki_list' || queryType === 'wiki_read') {
      let wikiDir = pluginCfg.wiki_export_dir || '$HERMES_HOME/consolidating_memory_wiki';
      wikiDir = wikiDir.replace('$HERMES_HOME', wsl.linuxPath);
      if (!queryArgs) queryArgs = {};
      if (queryType === 'wiki_list') queryArgs.wiki_dir = wikiDir;
      if (queryType === 'wiki_read' && queryArgs.file) {
        queryArgs.path = wikiDir + '/' + queryArgs.file;
      }
    }

    const scriptPath = wslTempScript();
    const argsJson = JSON.stringify(queryArgs || {});
    const argsTmp = path.join(os.tmpdir(), 'hmc_args.json');
    fs.writeFileSync(argsTmp, argsJson, 'utf-8');
    const argsWsl = argsTmp.replace(/^([A-Z]):/i, (_, d) => `/mnt/${d.toLowerCase()}`).replace(/\\/g, '/');
    const cmd = `wsl -e python3 "${scriptPath}" "${linuxDbPath}" "${queryType}" "${argsWsl}"`;
    const out = execSync(cmd, { timeout: 20000, encoding: 'utf-8', maxBuffer: 10 * 1024 * 1024 }).trim();
    return JSON.parse(out);
  } catch (e) {
    return { error: e.message };
  }
});
