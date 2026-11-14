'use strict';
const fs = require('fs'), path = require('path'), zlib = require('zlib'), cp = require('child_process');
const { pipeline } = require('stream/promises');
const pad = n => String(n).padStart(2, '0');
const stamp = d => `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}`;
const RE = /^backup-(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(?:-([a-z-]+))?\.db\.gz$/;

function hideDir(dir) {
  if (process.platform !== 'win32') return;
  try { cp.execFile('attrib', ['+h', dir], () => {}); } catch (_) {}
}

function list(dir) {
  let names = [];
  try { names = fs.readdirSync(dir); } catch (_) { return []; }
  const out = [];
  for (const n of names) {
    const m = RE.exec(n); if (!m) continue;
    const t = new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]);
    let size = 0; try { size = fs.statSync(path.join(dir, n)).size; } catch (_) {}
    out.push({ name: n, file: path.join(dir, n), time: t.getTime(), tag: m[6] || '', size });
  }
  return out.sort((a, b) => b.time - a.time);
}

// keep: everything from the last 48h; older: one per day (the latest) for 30 days; tagged (manual / pre-restore) kept 30 days
function prune(dir, now = Date.now()) {
  const files = list(dir), day = 86400000, keep = new Set(), perDay = new Set();
  for (const f of files) {
    const age = now - f.time;
    if (f.tag === 'pre-upgrade') { keep.add(f.name); continue; }
    if (age <= 2 * day) { keep.add(f.name); continue; }
    if (age > 30 * day) continue;
    if (f.tag) { keep.add(f.name); continue; }
    const d = new Date(f.time), k = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
    if (!perDay.has(k)) { perDay.add(k); keep.add(f.name); }
  }
  // safety: the newest 10 backups are never deleted, whatever the clock says (a wrong system date must not wipe the history)
  files.slice(0, 10).forEach(f => keep.add(f.name));
  for (const f of files) if (!keep.has(f.name)) { try { fs.unlinkSync(f.file); } catch (_) {} }
  // leftovers of interrupted or older runs
  try { for (const n of fs.readdirSync(dir)) if (/\.db\.tmp(-shm|-wal)?$/.test(n)) { try { fs.unlinkSync(path.join(dir, n)); } catch (_) {} } } catch (_) {}
}
// a copied database is still in WAL mode; switch it to a plain single file so that checking it leaves no -shm/-wal files behind
function checkCopy(Database, file) {
  const c = new Database(file);
  try {
    c.pragma('journal_mode = DELETE');
    const r = c.pragma('quick_check', { simple: true });
    if (r !== 'ok') throw new Error('integrity check failed: ' + r);
    return c.prepare('SELECT count(*) n FROM waybills').get().n;
  } finally { c.close(); for (const ext of ['-shm', '-wal']) { try { fs.unlinkSync(file + ext); } catch (_) {} } }
}

async function makeBackup(store, dir, tag) {
  fs.mkdirSync(dir, { recursive: true }); hideDir(dir);
  const name = `backup-${stamp(new Date())}${tag ? '-' + tag : ''}.db`;
  const tmp = path.join(dir, name + '.tmp');
  await store.db.backup(tmp);
  const waybills = checkCopy(store.Database, tmp);
  const out = path.join(dir, name + '.gz');
  await pipeline(fs.createReadStream(tmp), zlib.createGzip({ level: 6 }), fs.createWriteStream(out));
  fs.unlinkSync(tmp);
  prune(dir);
  return { file: out, size: fs.statSync(out).size, waybills };
}

// unpack a backup next to the live DB and verify it; the caller swaps files in
async function unpackForRestore(gzFile, targetPath, Database) {
  const tmp = targetPath + '.restoring';
  await pipeline(fs.createReadStream(gzFile), zlib.createGunzip(), fs.createWriteStream(tmp));
  try { checkCopy(Database, tmp); } catch (e) { try { fs.unlinkSync(tmp); } catch (_) {} throw new Error('backup is damaged'); }
  return tmp;
}
module.exports = { makeBackup, list, prune, unpackForRestore, stamp };
