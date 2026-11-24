; ============================================================
;  Disk Space Visualizer — Inno Setup installer script
;  Requires Inno Setup 6 (https://jrsoftware.org/isinfo.php),
;  then compile with:  iscc installer.iss
;  Output: installer-output\DiskSpaceVisualizer-Setup-1.2.0.exe
;  Build dist\DiskSpaceVisualizer.exe first (build_exe.bat).
; ============================================================

#define MyAppName "Disk Space Visualizer"
#define MyAppVersion "1.2.0"
#define MyAppExe "DiskSpaceVisualizer.exe"

[Setup]
AppId={{8F3C2A1B-4D7E-4A6B-9C0F-2B5D8E7A1C3E}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Disk Space Visualizer
DefaultDirName={autopf}\Disk Space Visualizer
DefaultGroupName={#MyAppName}
OutputDir=installer-output
OutputBaseFilename=DiskSpaceVisualizer-Setup-{#MyAppVersion}
SetupIconFile=app.ico
UninstallDisplayIcon={app}\{#MyAppExe}
Compression=lzma2/max
SolidCompression=yes
PrivilegesRequired=lowest
WizardStyle=modern
DisableProgramGroupPage=yes

[Files]
Source: "dist\{#MyAppExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "Create a &desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
