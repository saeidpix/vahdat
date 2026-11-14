'use strict';
// Runs in the page world (contextIsolation:false, the page is a local file). Replaces localStorage with the SQLite store
// and exposes backup controls as window.autobenzDesktop.
const { ipcRenderer } = require('electron');
const data = new Map(Object.entries(ipcRenderer.sendSync('kv:all')));
const real = window.localStorage, P = Storage.prototype;
const own = self => self === real;
const o = { get: P.getItem, set: P.setItem, rem: P.removeItem, clr: P.clear, key: P.key };
const lenDesc = Object.getOwnPropertyDescriptor(P, 'length');
P.getItem = function (k) { return own(this) ? (data.has(String(k)) ? data.get(String(k)) : null) : o.get.call(this, k); };
P.setItem = function (k, v) { if (!own(this)) return o.set.call(this, k, v); k = String(k); v = String(v); data.set(k, v); ipcRenderer.send('kv:set', k, v); };
P.removeItem = function (k) { if (!own(this)) return o.rem.call(this, k); k = String(k); data.delete(k); ipcRenderer.send('kv:remove', k); };
P.clear = function () { if (!own(this)) return o.clr.call(this); for (const k of [...data.keys()]) ipcRenderer.send('kv:remove', k); data.clear(); };
P.key = function (i) { return own(this) ? ([...data.keys()][i] ?? null) : o.key.call(this, i); };
Object.defineProperty(P, 'length', { configurable: true, get() { return own(this) ? data.size : lenDesc.get.call(this); } });
window.confirm = msg => ipcRenderer.sendSync('dlg:confirm', String(msg == null ? '' : msg));
window.alert = msg => { ipcRenderer.sendSync('dlg:alert', String(msg == null ? '' : msg)); };
ipcRenderer.on('kv:error', (_e, msg) => { try { window.dispatchEvent(new CustomEvent('autobenz:storage-error', { detail: msg })); } catch (_) {} });
window.autobenzDesktop = {
  isDesktop: true,
  printWaybillSilent: () => ipcRenderer.invoke('waybill:print-silent'),
  updateState: () => ipcRenderer.invoke('updates:state'),
  updateCheck: () => ipcRenderer.invoke('updates:check'),
  updateDownload: () => ipcRenderer.invoke('updates:download'),
  updateInstall: () => ipcRenderer.invoke('updates:install'),
  onUpdateState: fn => { const listener = (_e, state) => fn(state); ipcRenderer.on('updates:state', listener); return () => ipcRenderer.removeListener('updates:state', listener); },
  backupState: () => ipcRenderer.invoke('backup:state'),
  backupSet: p => ipcRenderer.invoke('backup:set', p),
  backupChoose: () => ipcRenderer.invoke('backup:choose'),
  backupRun: () => ipcRenderer.invoke('backup:run'),
  backupRestore: f => ipcRenderer.invoke('backup:restore', f)
};
