; Vitralis's Windows installer (Inno Setup 6). `uv run build` compiles it after PyInstaller and passes:
;   /DAppVersion=1.4.0  /DAppGuid=<GUID, no braces>  /DSourceExe=<built exe>  /DIconFile=<.ico>
;   /DLicenseFile=<LICENSE>  /DOutputDir=<dist>
; It installs for the current user only, in %LOCALAPPDATA%\Programs\Vitralis: no admin prompt, and the folder
; stays writable, which the in-app updater needs to swap Vitralis.exe in place. Settings, drawings and the
; licence live in %APPDATA%\Vitralis and are kept on uninstall, so a reinstall needs no new key.
; It speaks every language Vitralis does, and saves the one picked (HKCU\Software\Vitralis, Language) so
; Vitralis starts in it until another is picked in Settings (vitralis.installed). Galician and Chinese come
; from installer\languages: Inno Setup ships Galician only as unofficial, and some builds lack Chinese; the
; reintegrated Galician is Vitralis's own.

#ifndef AppVersion
  #error AppVersion is not defined: build with `uv run build`
#endif

#define AppName "Vitralis"
#define AppExe "Vitralis.exe"
; held by Vitralis while it runs (vitralis.single_instance.RUNNING_MUTEX)
#define AppMutex "VitralisRunning"

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
; always: Windows has no locale for Galego reintegrado, so it can only be picked here
ShowLanguageDialog=yes

[Languages]
; Galego before Galego reintegrado: both are Windows's Galician ($0456), and detection takes the first
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "gl"; MessagesFile: "languages\Galician.isl"
Name: "glr"; MessagesFile: "languages\GalicianReintegrated.isl"
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "pt"; MessagesFile: "compiler:Languages\Portuguese.isl"
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "zh"; MessagesFile: "languages\ChineseSimplified.isl"
Name: "ja"; MessagesFile: "compiler:Languages\Japanese.isl"

[CustomMessages]
en.StartWithWindows=Start Vitralis when I sign in to Windows
gl.StartWithWindows=Iniciar Vitralis ao iniciar sesión en Windows
glr.StartWithWindows=Iniciar Vitralis ao iniciar sessom em Windows
es.StartWithWindows=Iniciar Vitralis al iniciar sesión en Windows
pt.StartWithWindows=Iniciar o Vitralis ao entrar no Windows
fr.StartWithWindows=Lancer Vitralis à l'ouverture de la session Windows
de.StartWithWindows=Vitralis bei der Windows-Anmeldung starten
zh.StartWithWindows=登录 Windows 时启动 Vitralis
ja.StartWithWindows=Windows へのサインイン時に Vitralis を起動する
; the language as Vitralis's Settings names it (vitralis.settings.LANGUAGES)
en.AppLanguage=English
gl.AppLanguage=Galego
glr.AppLanguage=Galego reintegrado
es.AppLanguage=Español
pt.AppLanguage=Português
fr.AppLanguage=Français
de.AppLanguage=Deutsch
zh.AppLanguage=中文
ja.AppLanguage=日本語

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startup"; Description: "{cm:StartWithWindows}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceExe}"; DestDir: "{app}"; DestName: "{#AppExe}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "ran.vitralis"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "ran.vitralis"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: startup

[Registry]
Root: HKCU; Subkey: "Software\Vitralis"; ValueType: string; ValueName: "Language"; ValueData: "{cm:AppLanguage}"; Flags: uninsdeletekey

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; left by the in-app updater: the previous exe until the next start, and its write probe
Type: files; Name: "{app}\{#AppExe}.old"
Type: files; Name: "{app}\.vitralis-update-test"

[Code]
// Uninstalling under a running Vitralis can't delete its exe, and would leave it running from a folder that
// is half gone: ask to quit it first, in the installer's own words and language. A silent uninstall stops.
function InitializeUninstall(): Boolean;
begin
  Result := True;
  while CheckForMutexes('{#AppMutex}') do
    if SuppressibleMsgBox(FmtMessage(SetupMessage(msgUninstallAppRunningError), ['{#AppName}']),
                          mbError, MB_OKCANCEL, IDCANCEL) <> IDOK then
    begin
      Result := False;
      Exit;
    end;
end;
