'use strict';
const assert = require('assert');
const { EventEmitter } = require('events');
const { createUpdater } = require('../updater');
class FakeUpdater extends EventEmitter {
  setFeedURL(v) { this.feed = v; }
  async checkForUpdates() { this.emit('update-available', { version: '1.0.4' }); }
  async downloadUpdate() { this.emit('download-progress', { percent: 48 }); this.emit('update-downloaded', { version: '1.0.4' }); }
  quitAndInstall() { this.installed = true; }
}
function setup(arch, failing) {
 const updater = new FakeUpdater(), events = [], windows = [];
 let backups = 0;
 const controller = createUpdater({ updater, arch, app: { isPackaged: true, getVersion: () => '1.0.3' }, notify: s => events.push(s.phase),
  setWindowEnabled: v => windows.push(v), backupBeforeInstall: async () => { backups++; if (failing) throw Error('backup failed'); } });
 return { updater, controller, events, windows, backups: () => backups };
}
(async () => {
 for (const arch of ['x64','ia32']) {
  const t=setup(arch,false);
  assert.equal(t.updater.feed.channel,'latest-'+arch);
  assert.equal(t.updater.autoDownload,false); assert.equal(t.updater.autoInstallOnAppQuit,false);
  assert.equal(t.updater.allowDowngrade,false);
  await t.controller.install(); assert.equal(t.backups(),0);
  await t.controller.check(); assert.equal(t.controller.getState().phase,'available');
  await t.controller.download(); assert.equal(t.controller.getState().phase,'downloaded');
  await t.controller.install(); assert.equal(t.backups(),1); assert.equal(t.updater.installed,true);
  assert(t.events.includes('backing-up')); assert.deepEqual(t.windows,[false]);
 }
 const f=setup('x64',true);await f.controller.check();await f.controller.download();await f.controller.install();
 assert.equal(f.updater.installed,undefined);assert.equal(f.controller.getState().phase,'downloaded');assert.deepEqual(f.windows,[false,true]);
 const t=setup('x64',false);await t.controller.check();await t.controller.download();await t.controller.install();
 t.updater.emit('error',new Error('installer failed'));assert.equal(t.controller.getState().phase,'error');assert.deepEqual(t.windows,[false,true]);
 console.log('Updater state, architecture, consent, backup failure and installer failure tests passed.');
})().catch(e=>{console.error(e);process.exit(1)});
