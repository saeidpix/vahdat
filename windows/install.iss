#define MyAppName "اتوبنز وحدت"
#define MyAppVersion "1.1.0"
#define MyExeName "VahdatServer.exe"

[Setup]
AppId={{D53496B9-C68D-4AB4-93D0-E6B8FD24B3EF}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Vahdat
DefaultDirName={autopf}\Vahdat
DefaultGroupName=اتوبنز وحدت
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=Vahdat-Setup-Windows-v1.1.0
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\VahdatServer.exe
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
SetupIconFile=assets\logo.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Dirs]
Name: "{commonappdata}\Vahdat"; Permissions: users-modify

[Files]
Source: "..\dist\VahdatServer.exe"; DestDir: "{app}"; Flags: ignoreversion

[Tasks]
Name: "desktopicon"; Description: "ایجاد میانبر روی دسکتاپ"; GroupDescription: "میانبرها:"

[Icons]
Name: "{autoprograms}\اتوبنز وحدت"; Filename: "{app}\{#MyExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\اتوبنز وحدت"; Filename: "{app}\{#MyExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""Vahdat Windows LAN 8765"" dir=in action=allow protocol=TCP localport=8765 remoteip=localsubnet profile=any"; Flags: runhidden
Filename: "{app}\{#MyExeName}"; Description: "اجرای برنامه اتوبنز وحدت"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Vahdat Windows LAN 8765"""; Flags: runhidden
