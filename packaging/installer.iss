; Inno Setup script — wraps the PyInstaller output into a Windows installer
; (the standard next-next-finish wizard).
;   Compile:  iscc /DAppVersion=1.0.0 packaging\installer.iss
; Expects PyInstaller to have produced dist\RSVP Pocket Reader\

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "RSVP Pocket Reader"
#define AppExe "RSVP Pocket Reader.exe"

[Setup]
AppId={{B7E5B1B4-2C5E-4E7A-9C2E-RSVPREADER0001}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Owen Price
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=installer
OutputBaseFilename=RSVP-Pocket-Reader-{#AppVersion}-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "..\dist\{#AppName}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
