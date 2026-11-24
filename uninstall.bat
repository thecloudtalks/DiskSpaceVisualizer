@echo off
REM Disk Space Visualizer — per-user uninstall (pairs with install.bat).
setlocal
rmdir /s /q "%LocalAppData%\DiskSpaceVisualizer" 2>nul
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Disk Space Visualizer.lnk" 2>nul
powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell; " ^
  "$p = [IO.Path]::Combine($ws.SpecialFolders('Desktop'), 'Disk Space Visualizer.lnk'); " ^
  "if (Test-Path $p) { Remove-Item $p -Force }"
echo Uninstalled. Your Recycle Bin / cleaned files are untouched.
pause
