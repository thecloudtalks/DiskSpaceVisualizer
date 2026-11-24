@echo off
REM Fast exe preview build (one-folder, not one-file):
REM much quicker to build and instant to start than the release exe.
REM For release, use build_exe.bat instead.
setlocal
cd /d "%~dp0"

python -m PyInstaller --noconfirm --onedir --noconsole --name DiskSpaceVisualizer-dev --icon app.ico --add-data "app.ico;." --add-data "app.png;." main.py
if errorlevel 1 (
  echo [ERROR] dev build failed.
  pause
  exit /b 1
)

echo.
echo DONE: dist\DiskSpaceVisualizer-dev\DiskSpaceVisualizer-dev.exe
echo (Starts instantly — no unpack step like the one-file release exe.)
pause
