#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{B7C1F6A2-5E3D-4C8A-9F21-6A7D2E4B1C90}
AppName=LeFilou Rec
AppVersion={#AppVersion}
AppPublisher=LeFilou2.0
DefaultDirName={autopf}\LeFilouRec
DefaultGroupName=LeFilou Rec
UninstallDisplayIcon={app}\LeFilouRec.exe
SetupIconFile=..\icon.ico
OutputDir=..
OutputBaseFilename=LeFilouRec-Setup-windows
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
WizardStyle=modern
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le bureau"; Flags: unchecked

[Files]
Source: "..\dist\LeFilouRec\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\LeFilou Rec"; Filename: "{app}\LeFilouRec.exe"
Name: "{autodesktop}\LeFilou Rec"; Filename: "{app}\LeFilouRec.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\LeFilouRec.exe"; Description: "Lancer LeFilou Rec"; Flags: nowait postinstall skipifsilent
