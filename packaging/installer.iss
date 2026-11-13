; delta — Inno Setup 6 kurulum betiği
; Doğrudan değil, packaging\build.ps1 üzerinden derleyin (önce PyInstaller çıktısı gerekir).
; Yönetici izni istemez: varsayılan olarak %LOCALAPPDATA%\Programs\delta klasörüne kurulur.
; Kullanıcı verileri (%LOCALAPPDATA%\delta: notlar, tercihler) kaldırmada SİLİNMEZ.

#include "version.iss"
#define AppName "delta"
#define AppExe "delta.exe"
#define AppUserModelID "delta.whiteboard"

[Setup]
AppId={{274E63FA-2C5A-402B-BC02-3F663C51EDA8}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppName}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\build\installer
OutputBaseFilename=delta-setup-{#AppVersion}
SetupIconFile=..\deltaapp\assets\logo.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
LicenseFile=..\LICENSE
VersionInfoDescription={#AppName} kurulumu
VersionInfoProductName={#AppName}
VersionInfoVersion={#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
; delta tepside çalışır; kapatma işini aşağıda "delta.exe --quit" ile kendimiz yapıyoruz
CloseApplications=no
RestartApplications=no

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
turkish.StartGroup=Başlangıç:
english.StartGroup=Startup:
turkish.TaskAutostart=Windows ile başlat (tepside sessizce bekler, kısayollar hep hazır)
english.TaskAutostart=Start with Windows (waits quietly in the tray, shortcuts always ready)
turkish.Desc=Toplantıda anlatmak için çizim tahtası, ekran alıntısı ve ekran videosu
english.Desc=Whiteboard, screen snip and screen recording for explaining things in meetings
turkish.LaunchApp=delta'yı aç
english.LaunchApp=Open delta

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "{cm:TaskAutostart}"; GroupDescription: "{cm:StartGroup}"

[Files]
Source: "..\build\dist\delta\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; güncellemede eski sürümden kalan Python / Qt dosyaları karışmasın
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; Comment: "{cm:Desc}"; AppUserModelID: "{#AppUserModelID}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Comment: "{cm:Desc}"; AppUserModelID: "{#AppUserModelID}"; Tasks: desktopicon

[Registry]
; "Windows ile başlat" — uygulamanın Seçenekler'deki anahtarıyla aynı kayıt (HKCU Run → delta)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "delta"; ValueData: """{app}\{#AppExe}"" --tray"; Tasks: autostart; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "delta"; ValueType: none; Flags: deletevalue uninsdeletevalue; Tasks: not autostart
Root: HKA; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\{#AppExe}"; ValueType: string; ValueData: "{app}\{#AppExe}"; Flags: uninsdeletekey

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent

[Code]
// /NOQUIT parametresi: test kurulumu çalışan delta'ya dokunmasın
function ShouldQuitRunning(): Boolean;
begin
  Result := ExpandConstant('{param:NOQUIT|0}') = '0';
end;

// Çalışan delta'yı notlarını kaydettirerek kapat ("delta.exe --quit"); 1,5 sn'de kapanmazsa zorla
procedure QuitRunningDelta(Exe: String);
var
  Code: Integer;
begin
  if not ShouldQuitRunning() then Exit;
  if FileExists(Exe) then
  begin
    Exec(Exe, '--quit', '', SW_HIDE, ewWaitUntilTerminated, Code);
    Sleep(1500);
  end;
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM {#AppExe} /F', '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  QuitRunningDelta(ExpandConstant('{app}\{#AppExe}'));
  Result := '';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    QuitRunningDelta(ExpandConstant('{app}\{#AppExe}'));
end;
