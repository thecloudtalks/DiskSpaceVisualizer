@echo off
REM ============================================================
REM  Disk Space Visualizer — one-file .exe builder (Windows)
REM  Double-click this file. Output: dist\DiskSpaceVisualizer.exe
REM ============================================================
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found. Install Python 3.10+ from python.org
  echo         (tick "Add python.exe to PATH" during setup), then retry.
  pause
  exit /b 1
)

echo [*] Python: & python --version
echo [*] Installing PyInstaller (once) ...
python -m pip install --upgrade pyinstaller
if errorlevel 1 (
  echo [ERROR] Could not install PyInstaller. Check your internet connection.
  pause
  exit /b 1
)

echo [*] Building one-file exe, this takes 1-3 minutes ...
if exist app.ico (
  set ICONFLAG=--icon app.ico --add-data "app.ico;." --add-data "app.png;."
) else (
  set ICONFLAG=
)

python -m PyInstaller --noconfirm --clean --onefile --noconsole --name DiskSpaceVisualizer %ICONFLAG% main.py
if errorlevel 1 (
  echo [ERROR] Build failed — see the output above.
  pause
  exit /b 1
)

echo.
echo ============================================================
echo  DONE: dist\DiskSpaceVisualizer.exe
echo  Copy it anywhere (no Python needed) and double-click to run.
echo ============================================================

REM Optional: compile the Inno Setup installer if Inno is available.
where iscc >nul 2>nul
if not errorlevel 1 (
  echo [*] Inno Setup found — building installer ...
  iscc installer.iss
  echo [*] Installer built in installer-output\
) else (
  echo [*] Tip: install Inno Setup 6 to also build a Setup wizard,
  echo     or use install.bat for a no-admin portable install.
)
pause
