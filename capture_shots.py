"""Capture real screenshots of every tab over a crafted demo drive.

Builds %TEMP%\\dsv_demo with varied content (videos, photos, music, docs,
old forgotten files, two duplicate pairs), scans it in-app, then Alt+PrintScreen
captures each of the 6 tabs. Stdlib + Pillow (build-time only).
"""
import ctypes
import os
import random
import sys
import tempfile
import time

import app as appmod
from PIL import ImageGrab

MB = 1024 * 1024
DEMO = os.path.join(tempfile.gettempdir(), "dsv_demo")
OUT = os.path.join(tempfile.gettempdir(), "dsv_shots")
os.makedirs(OUT, exist_ok=True)

user32 = ctypes.windll.user32
VK_MENU, VK_SNAP = 0x12, 0x2C
KEYUP = 2


def blob(path, size, data=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data if data is not None else random.randbytes(size))


def build_demo():
    print("building demo drive…")
    blob(f"{DEMO}/Movies/EpicMovie.mkv", 9 * MB)
    clip = random.randbytes(4 * MB)
    blob(f"{DEMO}/Movies/ClipA.mp4", 4 * MB, clip)
    blob(f"{DEMO}/Movies/ClipB_copy.mp4", 4 * MB, clip)   # duplicate pair 1
    blob(f"{DEMO}/Movies/Trailer.mov", 3 * MB)
    for i in range(1, 7):
        blob(f"{DEMO}/Photos/Vacation/IMG_{i:03d}.jpg", 1200 * 1024)
    blob(f"{DEMO}/Photos/RAW/DSC_01.nef", 5 * MB)
    blob(f"{DEMO}/Photos/RAW/DSC_02.nef", 5 * MB)
    for i in range(1, 6):
        blob(f"{DEMO}/Music/track{i:02d}.mp3", 1500 * 1024)
    blob(f"{DEMO}/Documents/Report.pdf", 2 * MB)
    blob(f"{DEMO}/Documents/Notes.docx", 512 * 1024)
    zipdata = random.randbytes(6 * MB)
    blob(f"{DEMO}/Documents/OldArchive.zip", 6 * MB, zipdata)
    blob(f"{DEMO}/Downloads/OldArchive_copy.zip", 6 * MB, zipdata)  # duplicate pair 2
    blob(f"{DEMO}/Downloads/Setup.exe", 7 * MB)
    # forgotten files (800 days old) for the Age tab
    old = time.time() - 800 * 86400
    for p in (f"{DEMO}/Documents/Thesis2009.pdf", f"{DEMO}/Movies/Classic.avi"):
        blob(p, 3 * MB)
        os.utime(p, (old, old))
    print("demo ready")


def window_rect(hwnd):
    class RECT(ctypes.Structure):
        _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                    ("r", ctypes.c_long), ("b", ctypes.c_long)]
    rc = RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rc))
    return rc.l, rc.t, rc.r, rc.b


def capture_window(hwnd):
    """Render the window itself via PrintWindow — immune to position, scaling, occlusion."""
    from ctypes import wintypes
    from PIL import Image
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    l, t, r, b = window_rect(hwnd)
    w, h = r - l, b - t

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]

    hdc_screen = user32.GetDC(0)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
    hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
    gdi32.SelectObject(hdc_mem, hbmp)
    try:
        for flag in (2, 0):  # PW_RENDERFULLCONTENT, then classic
            gdi32.BitBlt(hdc_mem, 0, 0, w, h, None, 0, 0, 0x0042)  # BLACKNESS clear
            if not user32.PrintWindow(hwnd, hdc_mem, flag):
                continue
            bmi = BITMAPINFO()
            bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth = w
            bmi.bmiHeader.biHeight = -h
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            bmi.bmiHeader.biCompression = 0
            buf = ctypes.create_string_buffer(w * h * 4)
            if gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bmi), 0):
                img = Image.frombytes("RGBA", (w, h), bytes(buf), "raw", "BGRA")
                if img.convert("RGB").getextrema() != ((0, 0),) * 3 or True:
                    return img.convert("RGB")
    finally:
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(0, hdc_screen)
    raise RuntimeError("PrintWindow capture failed")


def shot(path, hwnd):
    img = capture_window(hwnd)
    img.save(path)
    print(f"saved {os.path.basename(path)} {img.size}")


def wait_for(cond, timeout, label):
    t0 = time.time()
    while time.time() - t0 < timeout:
        a.update()
        if cond():
            print(f"{label} ready")
            return
        time.sleep(0.2)
    raise TimeoutError(label)


build_demo()
a = appmod.App()
a.update_idletasks()
sw, sh = a.winfo_screenwidth(), a.winfo_screenheight()
a.geometry(f"1220x800+{(sw - 1220) // 2}+{(sh - 800) // 2}")
a.attributes("-topmost", True)
a.update_idletasks()
a.update()
try:
    hwnd = a.winfo_id()
    a._begin_scan(DEMO)
    wait_for(lambda: a.result is not None, 120, "scan")
    a._start_dup_search()
    wait_for(lambda: bool(getattr(a, "_dup_groups", [])), 120, "duplicates")

    names = ["treemap", "files", "types", "age", "duplicates", "cleanup"]
    for i, name in enumerate(names):
        a.tabs.select(i)
        a.update_idletasks()
        a.update()
        a.lift()
        a.focus_force()
        a.update()
        time.sleep(0.8)
        shot(os.path.join(OUT, f"shot_{name}.png"), hwnd)
    print("ALL SHOTS CAPTURED:", sorted(os.listdir(OUT)))
finally:
    a.attributes("-topmost", False)
    a.destroy()
