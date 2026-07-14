'use strict';

const { contextBridge, ipcRenderer } = require('electron');

const api = Object.freeze({
  minimize: () => ipcRenderer.send('window:minimize'),
  maximize: () => ipcRenderer.send('window:maximize'),
  close: () => ipcRenderer.send('window:close'),
  profiles: () => ipcRenderer.invoke('control:profiles'),
  connect: (profile) => ipcRenderer.invoke('control:connect', profile),
  read: (action, payload = {}) => ipcRenderer.invoke('control:read', action, payload),
  preview: (action, payload = {}) => ipcRenderer.invoke('control:preview', action, payload),
  commit: (planId, phrase) => ipcRenderer.invoke('control:commit', planId, phrase),
  unlockLab: (phrase) => ipcRenderer.invoke('control:lab-unlock', phrase),
  labStatus: () => ipcRenderer.invoke('control:lab-status'),
});

contextBridge.exposeInMainWorld('hermesControl', api);
