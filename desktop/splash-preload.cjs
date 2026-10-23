const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('goteetStartup', {
  onReady: (callback) => ipcRenderer.once('startup-ready', () => callback()),
  enter: () => ipcRenderer.send('startup-enter'),
  quit: () => ipcRenderer.send('startup-quit'),
});
