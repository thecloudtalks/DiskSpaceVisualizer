@echo off
REM ============================================================
REM  Disk Space Visualizer — per-user install (no admin needed)
REM  Copies the exe to %LocalAppData%\DiskSpaceVisualizer and
REM  creates Start Menu + Desktop shortcuts.
REM  Build the exe first with build_exe.bat.
REM ============================================================
setlocal
cd /d "%~dp0"

if not exist "dist\DiskSpaceVisualizer.exe" (
  echo [ERROR] dist\DiskSpaceVisualizer.exe not found.
  echo         Run build_exe.bat first, then retry.
  pause
  exit /b 1
)

set APPDIR=%LocalAppData%\DiskSpaceVisualizer
mkdir "%APPDIR%" 2>nul
copy /y "dist\DiskSpaceVisualizer.exe" "%APPDIR%\" >nul

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell; " ^
  "$s = $ws.CreateShortcut($env:APPDATA + '\Microsoft\Windows\Start Menu\Programs\Disk Space Visualizer.lnk'); " ^
  "$s.TargetPath = $env:LocalAppData + '\DiskSpaceVisualizer\DiskSpaceVisualizer.exe'; " ^
  "$s.WorkingDirectory = $env:LocalAppData + '\DiskSpaceVisualizer'; " ^
  "$s.IconLocation = $env:LocalAppData + '\DiskSpaceVisualizer\DiskSpaceVisualizer.exe,0'; " ^
  "$s.Save(); " ^
  "$d = $ws.CreateShortcut([IO.Path]::Combine($ws.SpecialFolders('Desktop'), 'Disk Space Visualizer.lnk')); " ^
  "$d.TargetPath = $env:LocalAppData + '\DiskSpaceVisualizer\DiskSpaceVisualizer.exe'; " ^
  "$d.WorkingDirectory = $env:LocalAppData + '\DiskSpaceVisualizer'; " ^
  "$d.Save(); " ^
  "Write-Output 'shortcuts created'"

echo.
echo Installed to %APPDIR%
echo Start Menu + Desktop shortcuts created. Uninstall anytime with uninstall.bat.
pause
