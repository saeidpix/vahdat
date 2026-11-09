# -*- coding: utf-8 -*-
"""Build-time transformation: separate, restricted Qaemshahr Windows 7 PILOT.
The upstream Vahdat 1.5.7 source is never modified in GitHub or on the hub.
"""
from pathlib import Path

BASE = Path("Vahdat-1.5.7")
APP = BASE / "windows" / "app.py"
SYNC = BASE / "windows" / "sync_engine.py"
INNO = BASE / "windows" / "install.iss"


def one(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError("{}: expected one match, found {}".format(label, count))
    return text.replace(old, new, 1)


app = APP.read_text(encoding="utf-8")
app = one(app, "PORT = int(os.environ.get('VAHDAT_PORT', '8765'))",
          "PORT = int(os.environ.get('VAHDAT_PORT', '8877'))", "pilot port")
app = one(app, '/ "Vahdat"\n', '/ "VahdatPilotQaemshahr"\n', "isolated data folder")
app = one(app, 'json.dumps(["قائم‌شهر"],ensure_ascii=False)',
          'json.dumps(["تهران"],ensure_ascii=False)', "only allowed destination")
app = one(app, 'version="1.5.6-beta"',
          'version="1.5.7-win7-qaemshahr-pilot"', "health version")
app = one(app, 'id=f"VH-{now}-{uuid.uuid4().hex[:6].upper()}"',
          'id=f"VH-PILOT-{now}-{uuid.uuid4().hex[:6].upper()}"', "pilot waybill identifier")
app = one(app,
    '    c=connect()\n    try:\n        if sync_engine.permitted_destinations(c,sync_engine.load_config(DATA)) is not None:',
    '    if v != ["تهران"]:\n'
    '        return error("در نسخه آزمایشی قائم‌شهر فقط مقصد تهران مجاز است.",409)\n'
    '    c=connect()\n    try:\n        if sync_engine.permitted_destinations(c,sync_engine.load_config(DATA)) is not None:',
    "lock editable destinations")
app = one(app,
    "            if b['destination'] not in allowed:\n",
    '            if b["destination"] != "تهران":\n'
    '                return error("نسخه آزمایشی قائم‌شهر فقط بار به تهران صادر می‌کند.",409)\n'
    '            count=c.execute("SELECT COUNT(*) FROM waybills WHERE origin_here=1").fetchone()[0]\n'
    '            if count >= 30:\n'
    '                return error("سقف ۳۰ بارنامه آزمایشی قائم‌شهر تکمیل شده است.",409)\n'
    "            if b['destination'] not in allowed:\n",
    "enforce outbound limit and route")
app = one(app,
    "lan='--lan' in sys.argv or os.environ.get('VAHDAT_LAN')=='1'",
    "lan=False  # Pilot: do not expose unauthenticated HTTP on Windows 7 LAN.",
    "localhost-only server")
app = one(app, "port=PORT,threads=8)", "port=PORT,threads=4)", "low-RAM thread cap")
APP.write_text(app, encoding="utf-8")

sync = SYNC.read_text(encoding="utf-8")
sync = one(sync,
   "return dict(enabled=False, branch_id='tehran', branch_name='تهران', hub_url='', token='')",
   "return dict(enabled=False, branch_id='qaemshahr', branch_name='قائم‌شهر', hub_url='https://autobenzvahdat.ir', token='')",
   "fixed default identity")
sync = one(sync,"config.setdefault('branch_id', 'tehran')",
           "config.setdefault('branch_id', 'qaemshahr')","default branch ID")
sync = one(sync,"config.setdefault('branch_name', 'تهران')",
           "config.setdefault('branch_name', 'قائم‌شهر')","default branch name")
sync = one(sync,"config.setdefault('hub_url', '')",
           "config.setdefault('hub_url', 'https://autobenzvahdat.ir')","hub default")
sync = one(sync,
  "    return config\n\n\ndef validate_config(cfg):",
  '    if config["branch_id"] != "qaemshahr" or config["branch_name"] != "قائم‌شهر":\n'
  '        raise ValueError("این نسخه آزمایشی فقط برای شعبه قائم‌شهر است.")\n'
  "    return config\n\n\ndef validate_config(cfg):", "fixed branch identity")
sync = one(sync, "version='1.5.6-beta'",
            "version='1.5.7-win7-qaemshahr-pilot'", "heartbeat pilot version")
SYNC.write_text(sync, encoding="utf-8")

inno = INNO.read_text(encoding="utf-8")
inno = one(inno, '#define MyAppName "اتوبنز وحدت"',
           '#define MyAppName "اتوبنز وحدت - تست قائم شهر"', "pilot app title")
inno = one(inno, '#define MyAppVersion "1.5.6"',
           '#define MyAppVersion "1.5.7-pilot"', "pilot app version")
inno = one(inno, 'AppId={{D53496B9-C68D-4AB4-93D0-E6B8FD24B3EF}',
           'AppId={{763A9CA1-52F3-4CD5-A86E-711F062E1C21}', "separate installer identity")
inno = one(inno,'DefaultDirName={autopf}\\Vahdat',
           'DefaultDirName={autopf}\\Vahdat-Win7-Qaemshahr-Pilot', "separate application folder")
inno = one(inno,'DefaultGroupName=اتوبنز وحدت',
           'DefaultGroupName=اتوبنز وحدت - تست قائم شهر', "separate start menu")
inno = one(inno,'OutputBaseFilename=Vahdat-Setup-Windows-v1.5.6-beta',
           'OutputBaseFilename=Vahdat-Setup-Win7-Qaemshahr-PILOT-v1.5.7',
           "installer filename")
inno = one(inno,'Name: "{commonappdata}\\Vahdat"; Permissions: users-modify',
           'Name: "{commonappdata}\\VahdatPilotQaemshahr"; Permissions: users-modify',
           "isolated application data")
# 32-bit installer supports both Windows 7 x86 and Windows 7 x64.
inno = inno.replace('ArchitecturesAllowed=x64\n', '')
inno = inno.replace('ArchitecturesInstallIn64BitMode=x64\n', '')
# This pilot only listens on 127.0.0.1 and never opens the local firewall.
inno = "\n".join(line for line in inno.splitlines()
                 if 'lanmode' not in line and 'netsh.exe' not in line) + "\n"
inno = one(inno,
           'Name: "{autoprograms}\\اتوبنز وحدت"; Filename: "{app}\\{#MyExeName}"',
           'Name: "{autoprograms}\\اتوبنز وحدت - تست قائم شهر"; Filename: "{app}\\{#MyExeName}"',
           "pilot start menu shortcut")
inno = one(inno,
           'Name: "{autodesktop}\\اتوبنز وحدت"; Filename: "{app}\\{#MyExeName}"',
           'Name: "{autodesktop}\\اتوبنز وحدت - تست قائم شهر"; Filename: "{app}\\{#MyExeName}"',
           "pilot desktop shortcut")
INNO.write_text(inno, encoding="utf-8")
print("Pilot transforms applied: Windows 7 / Python 3.8 / Qaemshahr / localhost only.")
