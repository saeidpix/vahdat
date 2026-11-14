'use strict';
const { app, BrowserWindow, Menu, ipcMain, dialog } = require('electron');
const path = require('path'), fs = require('fs'), os = require('os');
const __mark = s => { if (process.argv.includes('--smoke') && process.env.SMOKE_OUT) { try { require('fs').writeFileSync(process.env.SMOKE_OUT + '.stage', s); } catch (_) {} } };
__mark('start');
let Database;
try { Database = require('better-sqlite3'); __mark('required'); }
catch (e) {
  if (process.argv.includes('--smoke') && process.env.SMOKE_OUT) { try { require('fs').writeFileSync(process.env.SMOKE_OUT, JSON.stringify({ ok: false, arch: process.arch, error: 'sqlite module: ' + String(e && e.message || e) })); } catch (_) {} process.exit(1); }
  require('electron').dialog.showErrorBox('باررسان', 'بخش ذخیره‌سازی برنامه بارگذاری نشد. برنامه را دوباره نصب کنید.\n\n' + String(e && e.message || e)); process.exit(1);
}
const { Store } = require('./storage');
const backup = require('./backup');

const SMOKE = process.argv.includes('--smoke');
// Forms and tables need no GPU; software rendering avoids crashes with old or missing graphics drivers (Windows 7, 32-bit machines).
app.disableHardwareAcceleration();
// 32-bit build: keep graphics inside the main process. On machines without a usable graphics driver the separate GPU process of the 32-bit build fails to start and takes the whole program down.
if (process.arch === 'ia32') app.commandLine.appendSwitch('in-process-gpu');
// Keep existing installations' database path stable when the visible product name changes.
app.setPath('userData', SMOKE ? fs.mkdtempSync(path.join(os.tmpdir(), 'avsmoke-')) : path.join(app.getPath('appData'), 'Barnameh'));

let store, win, backupBusy = false;
const dbPath = () => path.join(app.getPath('userData'), 'autobenz.db');
const settingsPath = () => path.join(app.getPath('userData'), 'backup-settings.json');
const upgradeDir = () => path.join(app.getPath('userData'), 'upgrade-backups');
const versionPath = () => path.join(app.getPath('userData'), 'data-version.json');
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
// First choice for backups is another fixed drive of this computer (a failed system disk must not take the backups with it).
// The folder is picked automatically until the admin chooses one by hand.
function parseDrives(text) {
  return String(text || '').split(/\r?\n/).map(l => l.trim().split('=')).filter(p => p.length >= 3 && /^[A-Za-z]:$/.test(p[0]))
    .map(p => ({ id: p[0].toUpperCase(), type: Number(p[1]), free: Number(p[2]) || 0 }));
}
function pickBackupDrive(drives, systemRoot) {
  const sys = String(systemRoot || '').slice(0, 2).toUpperCase();
  return drives.filter(d => d.type === 3 && d.id !== sys && d.free > 200 * 1024 * 1024).sort((a, b) => b.free - a.free);
}
function autoBackupDir() {
  return new Promise(resolve => {
    const s = readSettings();
    if (process.platform !== 'win32' || s.dirAuto === false) return resolve(null);
    const cp = require('child_process');
    const cmd = "Get-WmiObject Win32_LogicalDisk | ForEach-Object { $_.DeviceID + '=' + $_.DriveType + '=' + $_.FreeSpace }";
    cp.execFile('powershell.exe', ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', cmd], { timeout: 15000, windowsHide: true }, (err, out) => {
      if (err) return resolve(null);
      for (const d of pickBackupDrive(parseDrives(out), path.parse(app.getPath('userData')).root)) {
        const dir = d.id + '\\BarnamehBackup';
        try {
          fs.mkdirSync(dir, { recursive: true });
          const probe = path.join(dir, '.write-test'); fs.writeFileSync(probe, '1'); fs.unlinkSync(probe);
          const cur = readSettings();
          if (cur.dirAuto === false) return resolve(null);
          if (path.resolve(cur.dir).toLowerCase() !== path.resolve(dir).toLowerCase()) { cur.dir = dir; cur.dirAuto = true; writeSettings(cur); }
          return resolve(dir);
        } catch (_) { /* not writable: try the next drive */ }
      }
      resolve(null);
    });
  });
}
function backupState() {
  const s = readSettings();
  const root = p => path.parse(path.resolve(p)).root.toLowerCase();
  const due = Math.max(3 * s.intervalMinutes * 60000, 24 * 3600000);
  const warn = s.enabled ? ((s.lastErrorAt && s.lastErrorAt > (s.lastOk || 0)) ? 'error' : (s.lastOk && Date.now() - s.lastOk > due ? 'stale' : '')) : 'off';
  return { settings: s, warn, list: [...backup.list(s.dir), ...backup.list(upgradeDir())].sort((a,b) => b.time-a.time), upgradeDir: upgradeDir(), sameDrive: root(s.dir) === root(dbPath()), dbPath: dbPath() };
}

// Before an updated app can change existing data, keep and verify a recoverable snapshot.
async function protectUpgrade(hadDatabase) {
  const version = app.getVersion();
  let previous = '';
  try { previous = JSON.parse(fs.readFileSync(versionPath(), 'utf8')).version || ''; } catch (_) {}
  if (previous === version) return;
  if (hadDatabase) {
    const dir = upgradeDir();
    fs.mkdirSync(dir, { recursive: true });
    const saved = await backup.makeBackup(store, dir, 'pre-upgrade');
    const testPath = path.join(dir, 'verify-' + process.pid + '.db');
    const restored = await backup.unpackForRestore(saved.file, testPath, Database);
    fs.unlinkSync(restored);
    for (const file of [seqPath(), settingsPath()]) {
      if (fs.existsSync(file)) fs.copyFileSync(file, path.join(dir, path.basename(file) + '-before-' + version));
    }
  }
  const temp = versionPath() + '.tmp';
  fs.writeFileSync(temp, JSON.stringify({ version }));
  fs.renameSync(temp, versionPath());
}

function registerIpc() {
  ipcMain.on('kv:all', e => { e.returnValue = store.getAll(); });
  const fail = (e, err) => { console.error('storage', err); try { e.sender.send('kv:error', String(err && err.message || err)); } catch (_) {} };
  ipcMain.on('kv:set', (e, k, v) => { try { store.set(k, v); if (k === SEQ_KEY) guardSeq(v); } catch (err) { fail(e, err); } });
  ipcMain.on('kv:remove', (e, k) => { try { store.remove(k); } catch (err) { fail(e, err); } });
  // native, synchronous confirm/alert: avoids the Electron/Windows problem where inputs stop accepting focus after window.confirm()
  ipcMain.on('dlg:confirm', (e, msg) => { e.returnValue = dialog.showMessageBoxSync(win, { type: 'question', buttons: ['بله', 'خیر'], defaultId: 0, cancelId: 1, noLink: true, title: 'باررسان', message: String(msg || '') }) === 0; });
  ipcMain.on('dlg:alert', (e, msg) => { dialog.showMessageBoxSync(win, { type: 'info', buttons: ['متوجه شدم'], noLink: true, title: 'باررسان', message: String(msg || '') }); e.returnValue = true; });
  // Print only the app window to the Windows default printer, without a dialog.
  ipcMain.handle('waybill:print-silent', e => new Promise(resolve => {
    if (!win || e.sender !== win.webContents) return resolve({ ok: false, error: 'invalid sender' });
    try {
      e.sender.print({ silent: true, printBackground: true, pageSize: 'A4' },
        (success, reason) => resolve({ ok: success, error: reason || '' }));
    } catch (err) { resolve({ ok: false, error: String(err && err.message || err) }); }
  }));
  ipcMain.handle('backup:state', () => backupState());
  ipcMain.handle('backup:set', (_e, patch) => {
    const s = readSettings();
    if (typeof patch.enabled === 'boolean') s.enabled = patch.enabled;
    if (Number.isFinite(+patch.intervalMinutes)) s.intervalMinutes = Math.min(1440, Math.max(5, Math.round(+patch.intervalMinutes)));
    if (typeof patch.dir === 'string' && patch.dir) { s.dir = patch.dir; s.dirAuto = false; }
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
    if (![path.resolve(s.dir), path.resolve(upgradeDir())].includes(path.dirname(resolved)) || !/\.db\.gz$/.test(resolved)) return { ok: false, error: 'فایل بکاپ معتبر نیست.' };
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
    width: 1366, height: 820, show: false, title: 'باررسان', autoHideMenuBar: true,
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
  __mark('smoke-begin');
  const out = { electron: process.versions.electron, node: process.versions.node, arch: process.arch };
  try { const d = pickBackupDrive(parseDrives('C:=3=5000000000\r\nD:=3=900000000000\r\nE:=5=0\r\nF:=2=8000000000\r\n'), 'C:\\'); out.drivePick = d.map(x => x.id).join(','); } catch (e) { out.drivePick = 'ERR ' + e; }
  __mark('drive-pick-done');
  if (process.platform === 'win32') { try { out.autoDir = await Promise.race([new Promise(r => require('child_process').execFile('powershell.exe', ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', "Get-WmiObject Win32_LogicalDisk | ForEach-Object { $_.DeviceID + '=' + $_.DriveType + '=' + $_.FreeSpace }"], { timeout: 15000, windowsHide: true }, (e, o) => r(e ? 'ERR ' + e.message : JSON.stringify(parseDrives(o))))), new Promise(r => setTimeout(() => r('timeout'), 20000))]); } catch (e) { out.autoDir = 'ERR ' + e; } }
  __mark('powershell-done');
  try {
    const arr = []; for (let i = 1; i <= 2000; i++) arr.unshift({ id: String(i), status: 'صادرشده', n: 'گیرنده ' + i });
    __mark('store-open');
    store.set('k', 'v'); store.set('autobenz-preview-waybills-v2', JSON.stringify(arr));
    arr.unshift({ id: '2001', status: 'x' }); store.set('autobenz-preview-waybills-v2', JSON.stringify(arr));
    const all = store.getAll(); const w = JSON.parse(all['autobenz-preview-waybills-v2']);
    out.rows = w.length; out.firstId = w[0].id; out.kv = all.k;
    __mark('before-backup');
    const b = await runBackup('smoke'); out.backup = b;
    __mark('after-backup');
    const tmp = await backup.unpackForRestore(b.file, path.join(app.getPath('userData'), 'r.db'), Database);
    const s2 = new Store(tmp, Database); out.restoredRows = JSON.parse(s2.getAll()['autobenz-preview-waybills-v2']).length; s2.close();
    await protectUpgrade(true);
    const upgradeSnapshots = backup.list(upgradeDir());
    out.upgradeBackupCount = upgradeSnapshots.length;
    const upgradeCopy = await backup.unpackForRestore(upgradeSnapshots[0].file, path.join(app.getPath('userData'), 'upgrade-check.db'), Database);
    const s3 = new Store(upgradeCopy, Database);
    out.upgradeRestoredRows = JSON.parse(s3.getAll()['autobenz-preview-waybills-v2']).length;
    s3.close(); fs.unlinkSync(upgradeCopy);
    out.versionMarker = JSON.parse(fs.readFileSync(versionPath(), 'utf8')).version;
    out.ok = out.drivePick === 'D:' && out.rows === 2001 && out.firstId === '2001' && out.kv === 'v' && b.ok && out.restoredRows === 2001
      && out.upgradeBackupCount === 1 && out.upgradeRestoredRows === 2001 && out.versionMarker === app.getVersion();
  } catch (e) { out.ok = false; out.error = String(e && e.stack || e); }
  console.log('SMOKE_RESULT ' + JSON.stringify(out));
  if (process.env.SMOKE_OUT) { try { fs.writeFileSync(process.env.SMOKE_OUT, JSON.stringify(out)); } catch (_) {} }
  try { store.close(); } catch (_) {}
  app.exit(out.ok ? 0 : 1);
}

if (!SMOKE && !app.requestSingleInstanceLock()) app.quit();
else app.whenReady().then(async () => {
  const hadDatabase = fs.existsSync(dbPath());
  store = new Store(dbPath(), Database);
  if (SMOKE) return smoke();
  try { await protectUpgrade(hadDatabase); }
  catch (e) {
    dialog.showErrorBox('باررسان', 'پشتیبان ایمنی پیش از به‌روزرسانی ساخته یا بررسی نشد؛ برنامه برای محافظت از اطلاعات باز نمی‌شود. فضای دیسک و دسترسی پوشه اطلاعات را بررسی کنید.\n\n' + String(e && e.message || e));
    try { store.close(); } catch (_) {}
    app.exit(1); return;
  }
  applySeqGuard(); registerIpc(); createWindow(); autoBackupDir().catch(() => {}); schedule();
  app.on('second-instance', () => { if (win) { if (win.isMinimized()) win.restore(); win.focus(); } });
});
app.on('window-all-closed', () => { try { store && store.close(); } catch (_) {} app.quit(); });
