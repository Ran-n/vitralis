; Vitralis's Windows installer (Inno Setup 6). `uv run build` compiles it after PyInstaller and passes:
;   /DAppVersion=1.4.0  /DAppGuid=<GUID, no braces>  /DSourceExe=<built exe>  /DIconFile=<.ico>
;   /DLicenseFile=<LICENSE>  /DOutputDir=<dist>
; It installs for the current user only, in %LOCALAPPDATA%\Programs\Vitralis: no admin prompt, and the folder
; stays writable, which the in-app updater needs to swap Vitralis.exe in place. Settings, drawings and the
; licence live in %APPDATA%\Vitralis and are kept on uninstall, so a reinstall needs no new key.

#ifndef AppVersion
  #error AppVersion is not defined: build with `uv run build`
#endif

#define AppName "Vitralis"
#define AppExe "Vitralis.exe"

[Setup]
AppId={{{#AppGuid}}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Ran#
AppPublisherURL=https://github.com/Ran-n/vitralis
AppSupportURL=https://github.com/Ran-n/vitralis/issues
AppUpdatesURL=https://github.com/Ran-n/vitralis/releases
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoDescription={#AppName} installer
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile={#LicenseFile}
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
OutputDir={#OutputDir}
OutputBaseFilename=vitralis-{#AppVersion}-setup
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=auto

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "pt"; MessagesFile: "compiler:Languages\Portuguese.isl"
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"
Name: "de"; MessagesFile: "compiler:Languages\German.isl"

[CustomMessages]
en.StartWithWindows=Start Vitralis when I sign in to Windows
es.StartWithWindows=Iniciar Vitralis al iniciar sesión en Windows
pt.StartWithWindows=Iniciar o Vitralis ao entrar no Windows
fr.StartWithWindows=Lancer Vitralis à l'ouverture de la session Windows
de.StartWithWindows=Vitralis bei der Windows-Anmeldung starten

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startup"; Description: "{cm:StartWithWindows}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceExe}"; DestDir: "{app}"; DestName: "{#AppExe}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "ran.vitralis"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "ran.vitralis"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: startup

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; left by the in-app updater: the previous exe until the next start, and its write probe
Type: files; Name: "{app}\{#AppExe}.old"
Type: files; Name: "{app}\.vitralis-update-test"
