'use strict';
// User-initiated update state machine. No download or install happens on startup.
function createUpdater({ updater, app, arch, backupBeforeInstall, notify, setWindowEnabled }) {
  const channel = arch === 'ia32' ? 'latest-ia32' : arch === 'x64' ? 'latest-x64' : null;
  let state = { phase: channel && app.isPackaged ? 'idle' : 'unsupported', version: app.getVersion(), arch };
  let busy = false;
  const getState = () => ({ ...state });
  function set(patch) { state = { ...state, ...patch }; notify(getState()); }
  function message(err) { return String(err && err.message || err || 'خطای نامشخص'); }
  if (channel && app.isPackaged) {
    updater.autoDownload = false;
    updater.autoInstallOnAppQuit = false;
    updater.allowDowngrade = false;
    updater.setFeedURL({ provider: 'generic', url: 'https://github.com/saeidpix/vahdat/releases/latest/download/', channel, useMultipleRangeRequest: false });
    updater.on('update-available', info => set({ phase: 'available', availableVersion: info.version, error: '' }));
    updater.on('update-not-available', () => set({ phase: 'current', availableVersion: '', error: '' }));
    updater.on('download-progress', p => set({ phase: 'downloading', percent: Math.max(0, Math.min(100, Math.round(p.percent || 0))) }));
    updater.on('update-downloaded', info => set({ phase: 'downloaded', availableVersion: info.version, percent: 100, error: '' }));
    // An error event must always be handled; the invoking action reports its failure as well.
    updater.on('error', err => { if (state.phase === 'installing') setWindowEnabled(true); set({ phase: 'error', error: message(err) }); });
  }
  async function check() {
    if (busy || !channel || !app.isPackaged) return getState();
    busy = true; set({ phase: 'checking', error: '' });
    try { await updater.checkForUpdates(); }
    catch (err) { set({ phase: 'error', error: message(err) }); }
    finally { busy = false; }
    return getState();
  }
  async function download() {
    if (busy || state.phase !== 'available') return getState();
    busy = true; set({ phase: 'downloading', percent: 0, error: '' });
    try { await updater.downloadUpdate(); }
    catch (err) { set({ phase: 'error', error: message(err) }); }
    finally { busy = false; }
    return getState();
  }
  async function install() {
    if (busy || state.phase !== 'downloaded') return getState();
    busy = true; set({ phase: 'backing-up', error: '' });
    let disabled = false;
    try {
      setWindowEnabled(false); disabled = true;
      await backupBeforeInstall();
      set({ phase: 'installing' });
      updater.quitAndInstall(false, true);
    } catch (err) {
      set({ phase: 'downloaded', error: 'نصب آغاز نشد؛ پشتیبان ایمنی یا نصب‌کننده را بررسی کنید: ' + message(err) });
      if (disabled) setWindowEnabled(true);
    } finally { busy = false; }
    return getState();
  }
  return { getState, check, download, install };
}
module.exports = { createUpdater };
