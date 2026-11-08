# -*- coding: utf-8 -*-
"""Vahdat Windows LAN application."""
import base64, gzip, io, json, os, pathlib, re, socket, sqlite3, sys
import tempfile, threading, time, uuid, webbrowser
from datetime import datetime, timedelta, timezone

import qrcode
from flask import Flask, jsonify, request, send_file, send_from_directory
from waitress import serve

PORT = 8765
TZ = timezone(timedelta(hours=3, minutes=30))
ROOT = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).parent))
DATA = pathlib.Path(os.environ.get("PROGRAMDATA", str(pathlib.Path.home()))) / "Vahdat"
DATA.mkdir(parents=True, exist_ok=True)
DB = DATA / "vahdat.sqlite3"
app = Flask(__name__)
FIELDS = ("id","origin","destination","sender","receiver","phone","pieces",
          "prepaid","post_fare","storage_fee","other_fee","total","created_at",
          "received_at","delivered_at","delivered_to","post_collected","origin_here")

def connect():
    conn=sqlite3.connect(str(DB),timeout=30)
    conn.row_factory=sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    return conn

def init():
    c=connect()
    try:
        # SQLite backup includes committed WAL data. Never copy an open database file.
        existed=c.execute("SELECT 1 FROM sqlite_master WHERE name='waybills'").fetchone()
        columns=[r[1] for r in c.execute("PRAGMA table_info(waybills)")]
        if existed and 'number' not in columns:
            folder=DATA/'backups'
            folder.mkdir(parents=True,exist_ok=True)
            target=sqlite3.connect(folder/('before-1.0.0-'+str(time.time_ns())+'.sqlite3'))
            try:c.backup(target)
            finally:target.close()
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript("""
        CREATE TABLE IF NOT EXISTS waybills (
          id TEXT PRIMARY KEY, origin TEXT NOT NULL, destination TEXT NOT NULL,
          sender TEXT NOT NULL DEFAULT '', receiver TEXT NOT NULL DEFAULT '',
          phone TEXT NOT NULL DEFAULT '', pieces INTEGER NOT NULL DEFAULT 1,
          prepaid INTEGER NOT NULL DEFAULT 0, post_fare INTEGER NOT NULL DEFAULT 0,
          storage_fee INTEGER NOT NULL DEFAULT 0, other_fee INTEGER NOT NULL DEFAULT 0,
          total INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL,
          received_at INTEGER, delivered_at INTEGER, delivered_to TEXT NOT NULL DEFAULT '',
          post_collected INTEGER NOT NULL DEFAULT 0, origin_here INTEGER NOT NULL DEFAULT 1);
        CREATE INDEX IF NOT EXISTS idx_created ON waybills(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_receiver ON waybills(receiver);
        CREATE INDEX IF NOT EXISTS idx_phone ON waybills(phone);
        CREATE TABLE IF NOT EXISTS settings(name TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(
          event_id INTEGER PRIMARY KEY AUTOINCREMENT, waybill_id TEXT NOT NULL,
          kind TEXT NOT NULL, amount INTEGER NOT NULL, happened_at INTEGER NOT NULL);
        """)
        c.execute('BEGIN IMMEDIATE')
        if 'number' not in columns:
            c.execute('ALTER TABLE waybills ADD COLUMN number INTEGER')
            for n,r in enumerate(c.execute('SELECT id FROM waybills ORDER BY created_at,id').fetchall(),1):
                c.execute('UPDATE waybills SET number=? WHERE id=?',(n,r['id']))
        c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_number ON waybills(number)')
        c.execute('PRAGMA user_version=1')
        c.execute("INSERT OR IGNORE INTO settings(name,value) VALUES('destinations',?)",
                  (json.dumps(["قائم‌شهر"],ensure_ascii=False),))
        c.commit()
    finally:c.close()

def to_jalali(gy,gm,gd):
    mm=[31,28,31,30,31,30,31,31,30,31,30,31]
    y,m=gy-1600,gm-1
    days=365*y+(y+3)//4-(y+99)//100+(y+399)//400+sum(mm[:m])+gd-1
    if m>1 and ((gy%4==0 and gy%100!=0) or gy%400==0):days+=1
    jd=days-79
    cycles,jd=divmod(jd,12053)
    jy=979+33*cycles+4*(jd//1461)
    jd%=1461
    if jd>=366:
        jy+=(jd-1)//365
        jd=(jd-1)%365
    if jd<186:return jy,1+jd//31,1+jd%31
    return jy,7+(jd-186)//30,1+(jd-186)%30

def local_date(ms):
    d=datetime.fromtimestamp(int(ms)/1000,TZ)
    jy,jm,jd=to_jalali(d.year,d.month,d.day)
    return (jy,jm,jd,d)

def shamsi(ms):
    if ms is None:return ""
    y,m,day,d=local_date(ms)
    return f"{y:04}/{m:02}/{day:02} - {d.hour:02}:{d.minute:02}:{d.second:02}".translate(
        str.maketrans("0123456789","۰۱۲۳۴۵۶۷۸۹"))

def number(value):
    t=str(value or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩","01234567890123456789"))
    return min(int(re.sub(r"\D","",t) or "0"),10**15)

def bill(row):
    x=dict(row);x["due"]=x["post_fare"]+x["storage_fee"]+x["other_fee"]
    x["outstanding"]=max(x["due"]-x["post_collected"],0)
    x["status"]="تحویل‌شده" if x["delivered_at"] else ("دریافت‌شده" if x["received_at"] else "صادرشده")
    for k in ("created_at","received_at","delivered_at"):x[k+"_fa"]=shamsi(x[k])
    return x

def log(conn,id,kind,amt=0):
    conn.execute("INSERT INTO events(waybill_id,kind,amount,happened_at) VALUES(?,?,?,?)",
                 (id,kind,amt,int(time.time()*1000)))

def one(c,id):return c.execute("SELECT * FROM waybills WHERE id=?",(id,)).fetchone()

def encode_qr(b):
    data={"v":2,"id":b["id"],"o":b["origin"],"d":b["destination"],
          "s":b["sender"],"r":b["receiver"],"p":b["phone"],"n":b["pieces"],
          "t":b["total"],"a":b["prepaid"],"c":b["created_at"],
          "k":b["post_fare"],"w":b["storage_fee"],"x":b["other_fee"]}
    payload=json.dumps(data,ensure_ascii=False,separators=(",",":")).encode("utf-8")
    return "VHD1:"+base64.urlsafe_b64encode(gzip.compress(payload,mtime=0)).decode()

def decode_qr(q):
    if not q.startswith("VHD1:"):raise ValueError("کد مربوط به اتوبنز وحدت نیست.")
    raw=base64.urlsafe_b64decode(q[5:].strip()+"===")
    if len(raw)>16000:raise ValueError("کد بیش از حد بزرگ است.")
    plain=gzip.GzipFile(fileobj=io.BytesIO(raw)).read(25001)
    if len(plain)>25000:raise ValueError("محتوای کد بیش از حد بزرگ است.")
    j=json.loads(plain.decode("utf-8"))
    if j.get("v") not in (1,2):raise ValueError("نسخه QR ناشناخته است.")
    ident=str(j.get("id",""))
    if not ident.startswith("VH-") or len(ident)>90:raise ValueError("شناسه بارنامه نامعتبر است.")
    pre=number(j.get("a"));post=number(j.get("k")) if j["v"]==2 else max(number(j.get("t"))-pre,0)
    storage=number(j.get("w")) if j["v"]==2 else 0
    other=number(j.get("x")) if j["v"]==2 else 0
    total=number(j.get("t"))
    if j["v"]==2 and total!=pre+post+storage+other:
        raise ValueError("جمع مبلغ‌ها با اطلاعات QR تطبیق ندارد.")
    return dict(id=ident,origin=str(j.get("o",""))[:180],
        destination=str(j.get("d",""))[:180],sender=str(j.get("s",""))[:180],
        receiver=str(j.get("r",""))[:180],phone=str(j.get("p",""))[:80],
        pieces=max(1,int(j.get("n") or 1)),prepaid=pre,post_fare=post,
        storage_fee=storage,other_fee=other,total=total,created_at=int(j.get("c")),
        received_at=None,delivered_at=None,delivered_to="",post_collected=0,origin_here=0)

def error(msg,code=400):return jsonify(error=msg),code

@app.get("/")
def home():return send_from_directory(str(ROOT),"ui.html",mimetype="text/html")

@app.get("/logo.png")
def logo():
    folder=ROOT if (ROOT/'logo.png').exists() else ROOT.parent/'app/src/main/res/drawable'
    return send_from_directory(str(folder),'logo.png' if folder==ROOT else 'brand_logo.png',mimetype="image/png")

@app.get('/assets/<path:name>')
def assets(name):return send_from_directory(str(ROOT/'assets'),name)

@app.get("/api/health")
def health():return jsonify(ok=True,version="1.1.0",host=socket.gethostname())

@app.get("/api/settings")
def settings():
    c=connect()
    try:
        r=c.execute("SELECT value FROM settings WHERE name='destinations'").fetchone()
        return jsonify(origin="تهران",destinations=json.loads(r["value"]) if r else ["قائم‌شهر"])
    finally:c.close()

@app.post("/api/settings")
def save_settings():
    v=(request.get_json(silent=True) or {}).get("destinations",[])
    if not isinstance(v,list):return error("فهرست مقصدها معتبر نیست.")
    v=list(dict.fromkeys(str(x).strip()[:120] for x in v if str(x).strip()))[:100]
    c=connect()
    try:
        with c:c.execute("UPDATE settings SET value=? WHERE name='destinations'",
                         (json.dumps(v,ensure_ascii=False),))
        return jsonify(ok=True,destinations=v)
    finally:c.close()

@app.post("/api/waybills")
def create():
    d=request.get_json(silent=True) or {}
    pre,post,storage,other=(number(d.get(k)) for k in
        ("prepaid","post_fare","storage_fee","other_fee"))
    now=int(time.time()*1000)
    try:pieces=max(1,min(number(d.get("pieces") or 1),1000000))
    except Exception:pieces=1
    b=dict(id=f"VH-{now}-{uuid.uuid4().hex[:6].upper()}",
        origin="تهران",destination=str(d.get("destination",""))[:180],
        sender=str(d.get("sender",""))[:180],receiver=str(d.get("receiver",""))[:180],
        phone=str(d.get("phone",""))[:80],pieces=pieces,prepaid=pre,post_fare=post,
        storage_fee=storage,other_fee=other,total=pre+post+storage+other,
        created_at=now,received_at=None,delivered_at=None,delivered_to="",
        post_collected=0,origin_here=1)
    c=connect()
    try:
        with c:
            c.execute('BEGIN IMMEDIATE')
            b['number']=c.execute('SELECT COALESCE(MAX(number),0)+1 FROM waybills').fetchone()[0]
            c.execute("INSERT INTO waybills("+",".join(FIELDS)+") VALUES("+",".join("?" for _ in FIELDS)+")",tuple(b[k] for k in FIELDS))
            c.execute('UPDATE waybills SET number=? WHERE id=?',(b['number'],b['id']))
            log(c,b["id"],"ISSUED",pre)
        return jsonify(waybill=bill(b)),201
    finally:c.close()

@app.get("/api/waybills")
def listings():
    q=request.args.get("q","")[:120]
    numeric_q=q.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩','01234567890123456789'))
    c=connect()
    try:
        if q:
            rows=c.execute("""SELECT * FROM waybills WHERE id LIKE ? OR sender LIKE ?
                OR receiver LIKE ? OR phone LIKE ? OR CAST(number AS TEXT) LIKE ? ORDER BY created_at DESC,number DESC LIMIT 300""",
                tuple("%"+q+"%" for _ in range(4))+("%"+numeric_q+"%",)).fetchall()
        else:rows=c.execute("SELECT * FROM waybills ORDER BY created_at DESC LIMIT 300").fetchall()
        return jsonify(items=[bill(x) for x in rows])
    finally:c.close()

@app.get("/api/waybills/<path:id>")
def details(id):
    c=connect()
    try:
        row=one(c,id)
        return jsonify(waybill=bill(row)) if row else error("بارنامه پیدا نشد.",404)
    finally:c.close()

@app.get("/api/qr/<path:id>")
def qr(id):
    c=connect()
    try:
        r=one(c,id)
        if r is None:return error("بارنامه پیدا نشد.",404)
        image=qrcode.make(encode_qr(r)).convert("RGB")
        buf=io.BytesIO();image.save(buf,format="PNG");buf.seek(0)
        return send_file(buf,mimetype="image/png")
    finally:c.close()

@app.post("/api/import")
def imported():
    try:b=decode_qr(str((request.get_json(silent=True) or {}).get("qr","")))
    except Exception as e:return error(str(e))
    c=connect()
    try:
        with c:
            c.execute('BEGIN IMMEDIATE')
            result=c.execute("INSERT OR IGNORE INTO waybills("+",".join(FIELDS)+") VALUES("+",".join("?" for _ in FIELDS)+")",
                 tuple(b[k] for k in FIELDS))
            fresh=result.rowcount>0
            if fresh:
                n=c.execute('SELECT COALESCE(MAX(number),0)+1 FROM waybills').fetchone()[0]
                c.execute('UPDATE waybills SET number=? WHERE id=?',(n,b['id']))
                log(c,b["id"],"IMPORTED")
            r=one(c,b["id"])
        return jsonify(waybill=bill(r),fresh=fresh)
    finally:c.close()

@app.post("/api/waybills/<path:id>/receive")
def receive(id):
    c=connect()
    try:
        with c:
            res=c.execute("UPDATE waybills SET received_at=? WHERE id=? AND received_at IS NULL",(int(time.time()*1000),id))
            if res.rowcount:log(c,id,"RECEIVED")
            row=one(c,id)
        return jsonify(waybill=bill(row),changed=bool(res.rowcount)) if row else error("بارنامه پیدا نشد.",404)
    finally:c.close()

@app.post("/api/waybills/<path:id>/deliver")
def deliver(id):
    d=request.get_json(silent=True) or {}
    paid=number(d.get("collected"));name=str(d.get("person",""))[:180]
    c=connect()
    try:
        with c:
            res=c.execute("""UPDATE waybills SET delivered_at=?,delivered_to=?,post_collected=?
                 WHERE id=? AND received_at IS NOT NULL AND delivered_at IS NULL""",
                (int(time.time()*1000),name,paid,id))
            if res.rowcount:log(c,id,"DELIVERED",paid)
            row=one(c,id)
        return jsonify(waybill=bill(row),changed=bool(res.rowcount)) if row else error("بارنامه پیدا نشد.",404)
    finally:c.close()

@app.get("/api/reports")
def reports():
    period=request.args.get("period","today")
    now=local_date(int(time.time()*1000))
    c=connect()
    try:items=[bill(x) for x in c.execute("SELECT * FROM waybills")]
    finally:c.close()
    def inside(ms):
        if ms is None:return False
        if period=="all":return True
        d=local_date(ms)
        return d[:2]==now[:2] if period=="month" else d[:3]==now[:3]
    origin=[x for x in items if x["origin_here"] and inside(x["created_at"])]
    dest=[x for x in items if inside(x["delivered_at"])]
    return jsonify(
      issued=len(origin),received=sum(1 for x in items if inside(x["received_at"])),
      delivered=len(dest),prepaid=sum(x["prepaid"] for x in origin),
      post_fare=sum(x["post_fare"] for x in origin),
      storage_fee=sum(x["storage_fee"] for x in origin),
      other_fee=sum(x["other_fee"] for x in origin),
      total=sum(x["total"] for x in origin),
      collected=sum(x["post_collected"] for x in dest),
      receivable=sum(x["outstanding"] for x in items if not x["origin_here"]),
      today=shamsi(int(time.time()*1000)).split(" - ")[0])

@app.get("/api/backup")
def backup():
    fn=pathlib.Path(tempfile.gettempdir())/("vahdat-"+str(int(time.time()))+".sqlite3")
    c=connect()
    try:
        target=sqlite3.connect(fn)
        try:c.backup(target)
        finally:target.close()
    finally:c.close()
    return send_file(fn,as_attachment=True,download_name="Vahdat-backup.sqlite3")

def run():
    with socket.socket() as check:
        check.settimeout(.4)
        if check.connect_ex(("127.0.0.1",PORT))==0:
            webbrowser.open(f"http://127.0.0.1:{PORT}")
            return
    init()
    threading.Timer(2.0,lambda:webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    serve(app,host="0.0.0.0",port=PORT,threads=8)

if __name__=="__main__":
    try:run()
    except Exception as exc:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0,str(exc),"اتوبنز وحدت - خطا",0x10)
        except Exception:print(exc)
        sys.exit(1)
