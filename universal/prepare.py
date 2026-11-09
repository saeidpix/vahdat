# -*- coding: utf-8 -*-
"""Strict, verified build-time changes to the full v1.5.7 source.

The old web/Flask version and central Laravel site remain untouched.
The desktop runs Flask handlers IN-PROCESS via test_client: no port, no browser,
no LAN/firewall rule. All branches receive exactly the same installer.
"""
from pathlib import Path

ROOT = Path("Vahdat-1.5.7")
APP = ROOT / "windows/app.py"
OPS = ROOT / "windows/operations.py"
SYNC = ROOT / "windows/sync_engine.py"
INNO = ROOT / "windows/install.iss"


def replace_once(text, before, after, label):
    count = text.count(before)
    if count != 1:
        raise RuntimeError("{}: expected 1 match, found {}".format(label, count))
    return text.replace(before, after, 1)


app = APP.read_text(encoding="utf-8")
app = replace_once(app,
  ' / "Vahdat"\n', ' / "VahdatUniversal"\n', "independent data folder")
app = replace_once(app, 'json.dumps(["قائم‌شهر"],ensure_ascii=False)',
                   'json.dumps([],ensure_ascii=False)', "no default branch destination")
app = replace_once(app, 'version="1.5.6-beta"',
                   'version="1.6.0-universal-desktop-beta"', "desktop version")
app = replace_once(app,
    '    b=dict(id=f"VH-{now}-{uuid.uuid4().hex[:6].upper()}",',
    '    cfg=sync_engine.load_config(DATA)\n'
    '    if not cfg.get("enabled") or not cfg.get("branch_id"):\n'
    '        return error("فقط سوپرمدیر می‌تواند ابتدا شعبه و ارتباط مرکزی را فعال کند.",409)\n'
    '    b=dict(id=f"VH-{now}-{uuid.uuid4().hex[:6].upper()}",',
    "prevent unprovisioned issuance")
app = replace_once(app,
    "            allowed=permitted if permitted is not None else (json.loads(r['value']) if r else [])",
    '            if permitted is None:\n'
    '                return error("ابتدا باید فهرست مسیرها یک‌بار از مرکز دریافت شود.",409)\n'
    '            allowed=permitted',
    "require centrally verified routes")
APP.write_text(app, encoding="utf-8")

ops = OPS.read_text(encoding="utf-8")
ops = replace_once(ops,
    "ROLE_PERMS={\n    'admin':",
    "ROLE_PERMS={\n    'superadmin': {'issue','drivers','handover','receive','settle','list','reports','users','settings','backup'},\n    'admin':",
    "superadmin role")
ops = replace_once(ops,
    "ROLES=['admin','issuance','warehouse','accountant','viewer']",
    "ROLES=['superadmin','admin','issuance','warehouse','accountant','viewer']",
    "role list")
ops = replace_once(ops,
    "uid,name,mobile,password_hash,role,created_at) VALUES(?,?,?,?,?,?)',\n                      (uid,name,mobile,password_hash(pwd),'admin',now()))",
    "uid,name,mobile,password_hash,role,created_at) VALUES(?,?,?,?,?,?)',\n                      (uid,name,mobile,password_hash(pwd),'superadmin',now()))",
    "bootstrap becomes superadmin")
ops = replace_once(ops,
    "        perms=d.get('permissions',None)\n",
    "        if role=='superadmin' and g.current_user['role']!='superadmin':\n"
    "            return out('فقط سوپرمدیر مجاز به ایجاد سوپرمدیر جدید است.',403)\n"
    "        perms=d.get('permissions',None)\n",
    "superadmin user creation check")
ops = replace_once(ops,
    "        custom=d.get('permissions',None)\n",
    "        if role=='superadmin' and g.current_user['role']!='superadmin':\n"
    "            return out('فقط سوپرمدیر مجاز به انتخاب نقش سوپرمدیر است.',403)\n"
    "        custom=d.get('permissions',None)\n",
    "superadmin role change check")
ops = replace_once(ops,
    "            if row['role']=='admin' and (role!='admin' or not enabled):\n"
    '                if c.execute("SELECT COUNT(*) FROM users WHERE role=\'admin\' AND enabled=1").fetchone()[0]<=1:',
    "            if row['role'] in ('admin','superadmin') and (role!=row['role'] or not enabled):\n"
    "                if c.execute('SELECT COUNT(*) FROM users WHERE role=? AND enabled=1',(row['role'],)).fetchone()[0]<=1:",
    "prevent deleting final supervisor")
OPS.write_text(ops, encoding="utf-8")

sync = SYNC.read_text(encoding="utf-8")
sync = replace_once(sync,
    "version='1.5.6-beta'",
    "version='1.6.0-universal-desktop-beta'",
    "hub heartbeat version")
SYNC.write_text(sync, encoding="utf-8")

inno = '''#define MyAppName "اتوبنز وحدت - نسخه دسکتاپ شعب"
#define MyAppVersion "1.6.0-beta"
#define MyExeName "VahdatDesktop.exe"

[Setup]
AppId={{A32E7A4E-8FA7-4EE0-B981-1461485C1A11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=اتوبنز وحدت
DefaultDirName={autopf}\\Vahdat-Desktop
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\\dist\\installer
OutputBaseFilename=Vahdat-Desktop-Setup-Win7-to-Win11-v1.6.0-beta
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
MinVersion=6.1sp1
UninstallDisplayIcon={app}\\{#MyExeName}
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
SetupIconFile=assets\\logo.ico
; x86 installer works on both 32-bit Win7 and x64 Win7/8/10/11.
; No firewall rule, port, web server, or network share is installed.

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Dirs]
Name: "{commonappdata}\\VahdatUniversal"; Permissions: users-modify

[Files]
Source: "..\\dist\\VahdatDesktop.exe"; DestDir: "{app}"; Flags: ignoreversion

[Tasks]
Name: "desktopicon"; Description: "ایجاد میانبر روی دسکتاپ"; GroupDescription: "میانبرها:"

[Icons]
Name: "{autoprograms}\\{#MyAppName}"; Filename: "{app}\\{#MyExeName}"
Name: "{autodesktop}\\{#MyAppName}"; Filename: "{app}\\{#MyExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\\{#MyExeName}"; Description: "اجرای اتوبنز وحدت"; Flags: nowait postinstall skipifsilent
'''
INNO.write_text(inno, encoding="utf-8")
print("Universal desktop build transformations applied successfully.")
