'use strict';
const { app, BrowserWindow, Menu, ipcMain, dialog } = require('electron');
const path = require('path'), fs = require('fs'), os = require('os');
const Database = require('better-sqlite3');
const { Store } = require('./storage');
const backup = require('./backup');

const SMOKE = process.argv.includes('--smoke');
if (SMOKE) app.setPath('userData', fs.mkdtempSync(path.join(os.tmpdir(), 'avsmoke-')));

let store, win, backupBusy = false;
const dbPath = () => path.join(app.getPath('userData'), 'autobenz.db');
const settingsPath = () => path.join(app.getPath('userData'), 'backup-settings.json');
// Highest waybill number ever issued, kept outside the database: after restoring an older backup the numbers issued
// since that backup must not be handed out again.
const SEQ_KEY = 'autobenz-preview-waybill-sequence-v13';
const seqPath = () => path.join(app.getPath('userData'), 'waybill-seq.json');
const readSeqGuard = () => { try { return Number(JSON.parse(fs.readFileSync(seqPath(), 'utf8')).max) || 0; } catch (_) { return 0; } };
let seqGuard = 0;
function guardSeq(v) { let n = 0; try { n = Number(JSON.parse(v)) || 0; } catch (_) {} if (n > seqGuard) { seqGuard = n; try { fs.writeFileSync(seqPath(), JSON.stringify({ max: n })); } catch (_) {} } }
function applySeqGuard() {
  seqGuard = readSeqGuard();
  let cur = 0; try { cur = Number(JSON.parse(store.getAll()[SEQ_KEY] || '0')) || 0; } catch (_) {}
  if (seqGuard > cur) store.set(SEQ_KEY, JSON.stringify(seqGuard)); else if (cur > seqGuard) guardSeq(JSON.stringify(cur));
}
const defaults = () => ({ enabled: true, intervalMinutes: 60, dir: path.join(app.getPath('userData'), 'backups'), lastOk: null, lastError: null, lastFile: null });
function readSettings() { try { return { ...defaults(), ...JSON.parse(fs.readFileSync(settingsPath(), 'utf8')) }; } catch (_) { return defaults(); } }
function writeSettings(s) { fs.writeFileSync(settingsPath(), JSON.stringify(s, null, 1)); }

async function runBackup(tag) {
  if (backupBusy) return { ok: false, error: 'busy' };
  backupBusy = true;
  const s = readSettings();
  try {
    const r = await backup.makeBackup(store, s.dir, tag);
    s.lastOk = Date.now(); s.lastError = null; s.lastFile = r.file; writeSettings(s);
    return { ok: true, ...r };
  } catch (e) {
    s.lastError = String(e && e.message || e); s.lastErrorAt = Date.now(); writeSettings(s);
    return { ok: false, error: s.lastError };
  } finally { backupBusy = false; }
}
function schedule() {
  setInterval(() => {
    const s = readSettings();
    if (!s.enabled) return;
    const last = s.lastOk || 0;
    if (Date.now() - last >= Math.max(5, s.intervalMinutes) * 60000) runBackup();
  }, 60000);
  setTimeout(() => { const s = readSettings(); if (s.enabled && Date.now() - (s.lastOk || 0) >= s.intervalMinutes * 60000) runBackup(); }, 20000);
}
function backupState() {
  const s = readSettings();
  const root = p => path.parse(path.resolve(p)).root.toLowerCase();
  const due = Math.max(3 * s.intervalMinutes * 60000, 24 * 3600000);
  const warn = s.enabled ? ((s.lastErrorAt && s.lastErrorAt > (s.lastOk || 0)) ? 'error' : (s.lastOk && Date.now() - s.lastOk > due ? 'stale' : '')) : 'off';
  return { settings: s, warn, list: backup.list(s.dir), sameDrive: root(s.dir) === root(dbPath()), dbPath: dbPath() };
}

function registerIpc() {
  ipcMain.on('kv:all', e => { e.returnValue = store.getAll(); });
  const fail = (e, err) => { console.error('storage', err); try { e.sender.send('kv:error', String(err && err.message || err)); } catch (_) {} };
  ipcMain.on('kv:set', (e, k, v) => { try { store.set(k, v); if (k === SEQ_KEY) guardSeq(v); } catch (err) { fail(e, err); } });
  ipcMain.on('kv:remove', (e, k) => { try { store.remove(k); } catch (err) { fail(e, err); } });
  // native, synchronous confirm/alert: avoids the Electron/Windows problem where inputs stop accepting focus after window.confirm()
  ipcMain.on('dlg:confirm', (e, msg) => { e.returnValue = dialog.showMessageBoxSync(win, { type: 'question', buttons: ['بله', 'خیر'], defaultId: 0, cancelId: 1, noLink: true, title: 'اتوبنز وحدت', message: String(msg || '') }) === 0; });
  ipcMain.on('dlg:alert', (e, msg) => { dialog.showMessageBoxSync(win, { type: 'info', buttons: ['متوجه شدم'], noLink: true, title: 'اتوبنز وحدت', message: String(msg || '') }); e.returnValue = true; });
  ipcMain.handle('backup:state', () => backupState());
  ipcMain.handle('backup:set', (_e, patch) => {
    const s = readSettings();
    if (typeof patch.enabled === 'boolean') s.enabled = patch.enabled;
    if (Number.isFinite(+patch.intervalMinutes)) s.intervalMinutes = Math.min(1440, Math.max(5, Math.round(+patch.intervalMinutes)));
    if (typeof patch.dir === 'string' && patch.dir) s.dir = patch.dir;
    writeSettings(s); return backupState();
  });
  ipcMain.handle('backup:choose', async () => {
    const r = await dialog.showOpenDialog(win, { title: 'پوشه‌ی بکاپ (ترجیحاً روی درایو دیگر)', properties: ['openDirectory', 'createDirectory'] });
    return r.canceled ? null : r.filePaths[0];
  });
  ipcMain.handle('backup:run', async () => { const r = await runBackup('manual'); return { result: r, state: backupState() }; });
  ipcMain.handle('backup:restore', async (_e, file) => {
    const s = readSettings();
    const resolved = path.resolve(file);
    if (path.dirname(resolved) !== path.resolve(s.dir) || !/\.db\.gz$/.test(resolved)) return { ok: false, error: 'فایل بکاپ معتبر نیست.' };
    try {
      const tmp = await backup.unpackForRestore(resolved, dbPath(), Database);
      const pre = await runBackup('pre-restore');
      if (!pre.ok) { fs.unlinkSync(tmp); return { ok: false, error: 'قبل از بازگردانی بکاپ ایمنی ساخته نشد: ' + pre.error }; }
      store.close();
      for (const ext of ['-wal', '-shm']) { try { fs.unlinkSync(dbPath() + ext); } catch (_) {} }
      fs.renameSync(dbPath(), dbPath() + '.before-restore-' + Date.now());
      fs.renameSync(tmp, dbPath());
      try { // keep only the 3 newest pre-restore copies of the live database
        const dir = path.dirname(dbPath()), base = path.basename(dbPath()) + '.before-restore-';
        fs.readdirSync(dir).filter(n => n.startsWith(base)).sort().reverse().slice(3).forEach(n => { try { fs.unlinkSync(path.join(dir, n)); } catch (_) {} });
      } catch (_) {}
      app.relaunch(); app.exit(0);
      return { ok: true };
    } catch (e) { return { ok: false, error: String(e && e.message || e) }; }
  });
}

function createWindow() {
  win = new BrowserWindow({
    width: 1366, height: 820, show: false, title: 'اتوبنز وحدت', autoHideMenuBar: true,
    icon: path.join(__dirname, 'build', 'icon.png'),
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: false, nodeIntegration: false, sandbox: false, spellcheck: false }
  });
  Menu.setApplicationMenu(null);
  // the window must never leave the app page (a dropped file or a stray link would replace the whole program)
  win.webContents.on('will-navigate', (e, url) => { if (url.split('#')[0] !== win.webContents.getURL().split('#')[0]) e.preventDefault(); });
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  win.loadFile(path.join(__dirname, 'app', 'index.html'));
  win.once('ready-to-show', () => { win.maximize(); win.show(); });
}

async function smoke() {
  const out = { electron: process.versions.electron, node: process.versions.node };
  try {
    const arr = []; for (let i = 1; i <= 2000; i++) arr.unshift({ id: String(i), status: 'صادرشده', n: 'گیرنده ' + i });
    store.set('k', 'v'); store.set('autobenz-preview-waybills-v2', JSON.stringify(arr));
    arr.unshift({ id: '2001', status: 'x' }); store.set('autobenz-preview-waybills-v2', JSON.stringify(arr));
    const all = store.getAll(); const w = JSON.parse(all['autobenz-preview-waybills-v2']);
    out.rows = w.length; out.firstId = w[0].id; out.kv = all.k;
    const b = await runBackup('smoke'); out.backup = b;
    const tmp = await backup.unpackForRestore(b.file, path.join(app.getPath('userData'), 'r.db'), Database);
    const s2 = new Store(tmp, Database); out.restoredRows = JSON.parse(s2.getAll()['autobenz-preview-waybills-v2']).length; s2.close();
    out.ok = out.rows === 2001 && out.firstId === '2001' && out.kv === 'v' && b.ok && out.restoredRows === 2001;
  } catch (e) { out.ok = false; out.error = String(e && e.stack || e); }
  console.log('SMOKE_RESULT ' + JSON.stringify(out));
  if (process.env.SMOKE_OUT) { try { fs.writeFileSync(process.env.SMOKE_OUT, JSON.stringify(out)); } catch (_) {} }
  try { store.close(); } catch (_) {}
  app.exit(out.ok ? 0 : 1);
}

if (!SMOKE && !app.requestSingleInstanceLock()) app.quit();
else app.whenReady().then(() => {
  store = new Store(dbPath(), Database);
  if (SMOKE) return smoke();
  applySeqGuard(); registerIpc(); createWindow(); schedule();
  app.on('second-instance', () => { if (win) { if (win.isMinimized()) win.restore(); win.focus(); } });
});
app.on('window-all-closed', () => { try { store && store.close(); } catch (_) {} app.quit(); });
