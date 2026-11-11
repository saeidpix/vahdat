'use strict';
// SQLite-backed storage. Everything the app used to keep in localStorage lives here.
// Waybills get their own table (one row per waybill) so only changed rows are written.
const crypto = require('crypto');
const WAYBILLS_KEY = 'autobenz-preview-waybills-v2';
const hash = s => crypto.createHash('md5').update(s).digest('base64');

class Store {
  constructor(dbPath, Database) {
    this.Database = Database;
    this.path = dbPath;
    this.db = new Database(dbPath);
    this.db.pragma('journal_mode = WAL');
    this.db.pragma('synchronous = NORMAL');
    this.db.exec(`CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS waybills(id TEXT PRIMARY KEY, seq REAL NOT NULL, j TEXT NOT NULL);
      CREATE INDEX IF NOT EXISTS waybills_seq ON waybills(seq);`);
    this.stmt = {
      kvSet: this.db.prepare('INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v'),
      kvDel: this.db.prepare('DELETE FROM kv WHERE k=?'),
      wUp: this.db.prepare('INSERT INTO waybills(id,seq,j) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET seq=excluded.seq, j=excluded.j'),
      wSeq: this.db.prepare('UPDATE waybills SET seq=? WHERE id=?'),
      wDel: this.db.prepare('DELETE FROM waybills WHERE id=?'),
    };
    // cache: id -> {h, seq}; order: ids in array order
    this.cache = new Map();
    this.order = [];
    for (const r of this.db.prepare('SELECT id,seq,j FROM waybills ORDER BY seq').iterate()) {
      this.cache.set(r.id, { h: hash(r.j), seq: r.seq });
      this.order.push(r.id);
    }
  }

  getAll() {
    const out = {};
    for (const r of this.db.prepare('SELECT k,v FROM kv').iterate()) out[r.k] = r.v;
    if (this.order.length) {
      const parts = [];
      for (const r of this.db.prepare('SELECT j FROM waybills ORDER BY seq').iterate()) parts.push(r.j);
      out[WAYBILLS_KEY] = '[' + parts.join(',') + ']';
    }
    return out;
  }

  remove(key) {
    if (key === WAYBILLS_KEY) { this._setWaybills('[]'); return; }
    this.stmt.kvDel.run(key);
  }

  set(key, value) {
    if (key === WAYBILLS_KEY) { this._setWaybills(value); return; }
    this.stmt.kvSet.run(key, String(value));
  }

  _setWaybills(value) {
    let arr;
    try { arr = JSON.parse(value); } catch (_) { return; }
    if (!Array.isArray(arr)) return;
    const items = [];
    const seen = new Set();
    for (const r of arr) {
      if (!r || r.id == null) continue;
      const id = String(r.id);
      if (seen.has(id)) continue;
      seen.add(id);
      items.push({ id, j: JSON.stringify(r) });
    }
    const newIds = items.map(x => x.id);
    const isNew = x => !this.cache.has(x.id);
    const tx = this.db.transaction(() => {
      // deletions
      for (const id of this.order) if (!seen.has(id)) { this.stmt.wDel.run(id); this.cache.delete(id); }
      // relative order of survivors unchanged?
      const survivorsOld = this.order.filter(id => seen.has(id));
      const survivorsNew = newIds.filter(id => this.cache.has(id));
      let same = survivorsOld.length === survivorsNew.length && survivorsOld.every((id, i) => id === survivorsNew[i]);
      // new items only at the front (newest first) or only at the back?
      let front = 0;
      while (front < items.length && isNew(items[front])) front++;
      let back = 0;
      while (back < items.length - front && isNew(items[items.length - 1 - back])) back++;
      const newCount = items.filter(isNew).length;
      const simple = same && (front + back === newCount);
      if (simple) {
        let minSeq = 0, maxSeq = 0;
        for (const v of this.cache.values()) { if (v.seq < minSeq) minSeq = v.seq; if (v.seq > maxSeq) maxSeq = v.seq; }
        for (let i = front - 1, s = minSeq - 1; i >= 0; i--, s--) this._put(items[i], s);
        for (let i = items.length - back, s = maxSeq + 1; i < items.length; i++, s++) this._put(items[i], s);
        for (let i = front; i < items.length - back; i++) { // survivors: rewrite only if changed
          const c = this.cache.get(items[i].id), h = hash(items[i].j);
          if (c.h !== h) { this.stmt.wUp.run(items[i].id, c.seq, items[i].j); c.h = h; }
        }
      } else { // general case: renumber everything that moved or changed
        items.forEach((it, i) => {
          const c = this.cache.get(it.id), h = hash(it.j);
          if (!c || c.h !== h || c.seq !== i) this._put(it, i, h);
        });
      }
      this.order = newIds;
    });
    tx();
  }

  _put(it, seq, h) {
    this.stmt.wUp.run(it.id, seq, it.j);
    this.cache.set(it.id, { h: h || hash(it.j), seq });
  }

  close() { try { this.db.pragma('wal_checkpoint(TRUNCATE)'); } catch (_) {} this.db.close(); }
}
module.exports = { Store, WAYBILLS_KEY };
