import gzip, json, os, pathlib, sqlite3, tempfile
p=pathlib.Path(os.environ['APPDATA'])/'Barnameh'
def check(file):
 c=sqlite3.connect(str(file))
 assert c.execute('PRAGMA quick_check').fetchone()[0]=='ok'
 assert c.execute("SELECT v FROM kv WHERE k='upgrade-test-sentinel'").fetchone()[0]=='preserve-me'
 assert json.loads(c.execute("SELECT v FROM kv WHERE k='autobenz-company-v1'").fetchone()[0])['name']=='Test Company'
 assert {x[0] for x in c.execute('SELECT id FROM waybills')}=={'101','102'}
 c.close()
check(p/'autobenz.db')
assert json.loads((p/'waybill-seq.json').read_text(encoding='utf8'))['max']>=102
assert json.loads((p/'data-version.json').read_text(encoding='utf8'))['version']=='1.0.3'
backups=list((p/'upgrade-backups').glob('*-pre-upgrade.db.gz'))
assert backups, 'no pre-upgrade backup'
with tempfile.TemporaryDirectory() as d:
 q=pathlib.Path(d)/'backup.db'
 with gzip.open(max(backups,key=lambda v:v.stat().st_mtime),'rb') as src: q.write_bytes(src.read())
 check(q)
print('Installer upgrade preserved and backed up company, sequence, and waybills.')
