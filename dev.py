"""Dev live-preview: runs main.py and auto-restarts it whenever a .py file changes.

Usage:  python dev.py   (or double-click dev.bat)
Stop with Ctrl+C. Stdlib only — no extra installs.

Why this instead of rebuilding the exe? Running from source shows the exact
same UI (same code, same app.png icon) and restarts in ~2 seconds, versus
minutes for a PyInstaller build. Only rebuild the exe for release testing.
"""
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
POLL = 0.5


def snapshot() -> dict:
    snap = {}
    for f in os.listdir(ROOT):
        if f.endswith(".py"):
            try:
                snap[f] = os.path.getmtime(os.path.join(ROOT, f))
            except OSError:
                pass
    return snap


def launch():
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "main.py")],
                            cwd=ROOT)
    print(f"[dev] running main.py (pid {proc.pid})")
    return proc


def stop(proc: "subprocess.Popen"):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def main() -> None:
    last = snapshot()
    proc = launch()
    print("[dev] edit + save any .py file to auto-restart | Ctrl+C to quit")
    try:
        while True:
            time.sleep(POLL)
            if proc.poll() is not None:
                # app was closed by the user — wait for a code change, then relaunch
                print(f"[dev] app exited (code {proc.returncode}) — waiting for a file change…")
                while snapshot() == last:
                    time.sleep(POLL)
            if snapshot() != last:
                last = snapshot()
                print("[dev] change detected — restarting…")
                stop(proc)
                proc = launch()
    except KeyboardInterrupt:
        print("\n[dev] stopping…")
        stop(proc)


if __name__ == "__main__":
    main()
