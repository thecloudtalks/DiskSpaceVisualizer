@echo off
REM Live preview: runs the app from source, auto-restarts on every save.
REM Same UI as the exe, ~2 second refresh. Ctrl+C to quit.
cd /d "%~dp0"
python dev.py
pause
