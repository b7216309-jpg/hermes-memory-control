const { ipcRenderer } = require('electron');

window.api = {
  minimize:       () => ipcRenderer.send('win:minimize'),
  maximize:       () => ipcRenderer.send('win:maximize'),
  close:          () => ipcRenderer.send('win:close'),
  pickHermesHome: () => ipcRenderer.invoke('pick-hermes-home'),
  loadConfig:     (h) => ipcRenderer.invoke('load-config', h),
  saveConfig:     (h, c) => ipcRenderer.invoke('save-config', h, c),
  dbQuery:        (h, type, args) => ipcRenderer.invoke('db-query', h, type, args),
  isMock:         () => ipcRenderer.invoke('is-mock'),
};
