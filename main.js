'use strict';

const { app, BrowserWindow, ipcMain } = require('electron');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { discoverProfiles, runBridge } = require('./src/main/bridge');
const {
  LAB_PHRASE,
  READ_ACTIONS,
  buildPlan,
  cleanPayload,
  isLabAction,
} = require('./src/main/plans');

let win;
const smokeTest = process.argv.includes('--smoke-test');
let smokeProfile = null;
if (smokeTest) {
  smokeProfile = fs.mkdtempSync(path.join(os.tmpdir(), 'hermes-control-smoke-'));
  app.setPath('userData', path.join(smokeProfile, 'user-data'));
  app.setPath('sessionData', path.join(smokeProfile, 'session-data'));
  app.commandLine.appendSwitch('disk-cache-dir', path.join(smokeProfile, 'cache'));
}
let activeProfile = null;
let labUnlockedUntil = 0;
const plans = new Map();
const PLAN_TTL_MS = 2 * 60 * 1000;

function trusted(event) {
  return Boolean(win && event.sender === win.webContents && event.senderFrame === win.webContents.mainFrame);
}

function requireTrusted(event) {
  if (!trusted(event)) throw new Error('Rejected IPC call from an untrusted frame');
}

function requireConnected() {
  if (!activeProfile) throw new Error('Connect to a Hermes profile first');
  return activeProfile;
}

function createWindow() {
  win = new BrowserWindow({
    width: 1380,
    height: 900,
    minWidth: 920,
    minHeight: 620,
    frame: false,
    show: false,
    backgroundColor: '#0c0c0c',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      allowRunningInsecureContent: false,
      spellcheck: false,
    },
  });
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  win.webContents.on('will-navigate', (event, url) => {
    if (url !== win.webContents.getURL()) event.preventDefault();
  });
  win.once('ready-to-show', () => { if (!smokeTest) win.show(); });
  if (smokeTest) {
    win.webContents.once('did-finish-load', () => {
      setTimeout(async () => {
        try {
          const report = await win.webContents.executeJavaScript(`({
            title: document.title,
            views: document.querySelectorAll('.view').length,
            csp: document.querySelector('meta[http-equiv="Content-Security-Policy"]')?.content || '',
            api: typeof window.hermesControl?.profiles === 'function'
          })`);
          if (report.title !== 'Hermes Control Center' || report.views < 8 || !report.csp || !report.api) throw new Error('Renderer smoke assertions failed');
          process.stdout.write(JSON.stringify({ electronSmoke: true, ...report }) + '\n');
          app.exit(0);
        } catch (error) {
          process.stderr.write(`${error.stack || error}\n`);
          app.exit(1);
        }
      }, 1500);
    });
  }
  void win.loadFile(path.join(__dirname, 'renderer', 'index.html'));
}

function prunePlans() {
  const now = Date.now();
  for (const [id, plan] of plans) {
    if (now - plan.createdAt > PLAN_TTL_MS) plans.delete(id);
  }
}

function registerIpc() {
  ipcMain.on('window:minimize', (event) => { requireTrusted(event); win?.minimize(); });
  ipcMain.on('window:maximize', (event) => {
    requireTrusted(event);
    if (win?.isMaximized()) win.unmaximize(); else win?.maximize();
  });
  ipcMain.on('window:close', (event) => { requireTrusted(event); win?.close(); });

  ipcMain.handle('control:profiles', async (event) => {
    requireTrusted(event);
    return discoverProfiles();
  });

  ipcMain.handle('control:connect', async (event, candidate) => {
    requireTrusted(event);
    const profile = cleanPayload(candidate, { maxDepth: 2 });
    if (typeof profile.distro !== 'string' || !/^[\w .-]{1,80}$/.test(profile.distro)) {
      throw new Error('Invalid WSL distribution');
    }
    if (typeof profile.home !== 'string' || !/^\/[\w@+.,/ -]{1,500}\/\.hermes$/.test(profile.home)) {
      throw new Error('Hermes home must be an absolute Linux path ending in /.hermes');
    }
    const available = await discoverProfiles();
    if (!available.some((item) => item.distro === profile.distro && item.home === profile.home)) {
      throw new Error('The selected Hermes profile was not discovered in WSL');
    }
    const result = await runBridge(profile, 'probe', {});
    activeProfile = { distro: profile.distro, home: profile.home };
    plans.clear();
    labUnlockedUntil = 0;
    return result;
  });

  ipcMain.handle('control:read', async (event, action, rawPayload) => {
    requireTrusted(event);
    if (!READ_ACTIONS.has(action)) throw new Error('Unsupported read operation');
    return runBridge(requireConnected(), action, cleanPayload(rawPayload || {}));
  });

  ipcMain.handle('control:preview', async (event, action, rawPayload) => {
    requireTrusted(event);
    prunePlans();
    const payload = cleanPayload(rawPayload || {});
    const plan = buildPlan(action, payload);
    plans.set(plan.id, { ...plan, createdAt: Date.now() });
    return {
      id: plan.id,
      title: plan.title,
      summary: plan.summary,
      risk: plan.risk,
      phrase: plan.phrase,
      expiresInSeconds: Math.floor(PLAN_TTL_MS / 1000),
      labRequired: isLabAction(action, payload),
    };
  });

  ipcMain.handle('control:commit', async (event, planId, phrase) => {
    requireTrusted(event);
    prunePlans();
    const plan = plans.get(String(planId || ''));
    if (!plan) throw new Error('This action preview expired; preview it again');
    plans.delete(plan.id); // one shot, even when confirmation is wrong
    if (String(phrase || '') !== plan.phrase) throw new Error('Confirmation phrase does not match');
    if (isLabAction(plan.action, plan.payload) && Date.now() >= labUnlockedUntil) {
      throw new Error('Educational Lab is locked or its 15-minute session expired');
    }
    return runBridge(requireConnected(), plan.action, plan.payload, { mutation: true });
  });

  ipcMain.handle('control:lab-unlock', async (event, phrase) => {
    requireTrusted(event);
    if (String(phrase || '') !== LAB_PHRASE) throw new Error('Educational Lab phrase does not match');
    labUnlockedUntil = Date.now() + 15 * 60 * 1000;
    return { unlocked: true, expiresAt: new Date(labUnlockedUntil).toISOString() };
  });

  ipcMain.handle('control:lab-status', (event) => {
    requireTrusted(event);
    return { unlocked: Date.now() < labUnlockedUntil, expiresAt: labUnlockedUntil || null };
  });
}

app.whenReady().then(() => {
  registerIpc();
  createWindow();
});
app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
app.on('window-all-closed', () => app.quit());
app.on('quit', () => {
  if (smokeProfile) {
    try { fs.rmSync(smokeProfile, { recursive: true, force: true, maxRetries: 3 }); } catch { /* best effort */ }
  }
});
