import os, sqlite3, pathlib, json
p=pathlib.Path(os.environ['APPDATA'])/'Barnameh'
p.mkdir(parents=True,exist_ok=True)
db=sqlite3.connect(p/'autobenz.db')
db.executescript('CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT NOT NULL); CREATE TABLE IF NOT EXISTS waybills(id TEXT PRIMARY KEY, seq REAL NOT NULL, j TEXT NOT NULL);')
company={'name':'Test Company','origin':'Tehran','setupDone':True}
values={'upgrade-test-sentinel':'preserve-me','autobenz-company-v1':json.dumps(company),'autobenz-preview-waybill-sequence-v13':'102'}
for k,v in values.items(): db.execute('INSERT OR REPLACE INTO kv(k,v) VALUES(?,?)',(k,v))
for i in (101,102): db.execute('INSERT OR REPLACE INTO waybills(id,seq,j) VALUES(?,?,?)',(str(i),i,json.dumps({'id':str(i),'senderName':'Test','recipientName':'Test','destination':'Test','status':'صادرشده'})))
db.commit();db.close()
(p/'waybill-seq.json').write_text(json.dumps({'max':102}),encoding='utf8')
(p/'data-version.json').write_text(json.dumps({'version':'1.0.2'}),encoding='utf8')
print('Seeded isolated upgrade fixture.')
