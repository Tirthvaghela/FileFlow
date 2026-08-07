; Inno Setup script for the FileFlow Agent installer.
; Build the frozen app first (from the repo root):
;   pyinstaller agent/fileflow_agent.spec
; then compile this script (requires Inno Setup's iscc.exe):
;   iscc agent/installer/fileflow_agent.iss
; Output lands in agent/installer/Output/.

#define AppName "FileFlow Agent"
#define AppVersion "1.0.4"
#define AppPublisher "FileFlow"
#define DistDir "..\..\dist\FileFlowAgent"

[Setup]
AppId={{6F2C8B36-6E4E-4C4B-9F0A-3C6E6E9B7A21}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
; Per-user install, no admin/UAC prompt -- this is a small personal
; utility, not something that needs to touch Program Files or HKLM, and
; it keeps {userstartup} below unambiguously the current user's own.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=FileFlowAgentSetup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\FileFlowAgent.exe
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startup"; Description: "Launch FileFlow Agent when Windows starts"; Flags: checkedonce

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\FileFlowAgent.exe"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{userstartup}\{#AppName}"; Filename: "{app}\FileFlowAgent.exe"; Tasks: startup

[Run]
; Unconditional (not postinstall/skipifsilent) so this also fires on a
; silent auto-update install -- the agent triggers that itself with no
; one watching a wizard, so there's no checkbox to click. A manual
; interactive install launches immediately too now, same as most
; installers, rather than offering an opt-out checkbox.
Filename: "{app}\FileFlowAgent.exe"; Flags: nowait

[UninstallRun]
; A running instance locks FileFlowAgent.exe and its DLLs, which would
; otherwise leave them behind after uninstall (verified directly: without
; this, uninstalling while the tray icon is still running leaves the app
; folder non-empty). Force-closing it first, before file removal, makes
; uninstall reliable even if the user forgot to Quit from the tray menu.
Filename: "{cmd}"; Parameters: "/C taskkill /IM FileFlowAgent.exe /F"; Flags: runhidden; RunOnceId: "KillAgent"

[Code]
// Same problem as [UninstallRun] above, but for install/reinstall: a
// running tray instance locks FileFlowAgent.exe, so overwriting it during
// a manual re-run of this installer fails with "DeleteFile failed; code
// 5. Access is denied." (verified directly -- the tray app has no window
// to close, so it's easy to forget it's still running in the background).
// The auto-updater already exits the process itself before launching a
// silent install, so this is a no-op there; it only matters for a human
// double-clicking the installer while the agent happens to be running.
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssInstall then
    Exec('taskkill.exe', '/IM FileFlowAgent.exe /F', '', SW_HIDE,
      ewWaitUntilTerminated, ResultCode);
end;
