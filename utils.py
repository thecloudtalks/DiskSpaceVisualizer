"""Shared helpers for Disk Space Visualizer (Windows, stdlib only)."""
from __future__ import annotations

__version__ = "1.2.0"

import ctypes
import os
import shutil
import datetime
from dataclasses import dataclass

# ---------------------------------------------------------------- file categories

CATEGORY_COLORS = {
    "Video":      "#ef4444",
    "Images":     "#f59e0b",
    "Audio":      "#8b5cf6",
    "Documents":  "#3b82f6",
    "Archives":   "#eab308",
    "Code":       "#22c55e",
    "Executables":"#ec4899",
    "Games":      "#14b8a6",
    "System":     "#64748b",
    "Other":      "#94a3b3",
    "Folders":    "#38bdf8",
}

EXT_TO_CATEGORY = {
    # video
    ".mp4": "Video", ".mkv": "Video", ".avi": "Video", ".mov": "Video",
    ".wmv": "Video", ".flv": "Video", ".webm": "Video", ".m4v": "Video", ".ts": "Video",
    # images
    ".jpg": "Images", ".jpeg": "Images", ".png": "Images", ".gif": "Images",
    ".bmp": "Images", ".tiff": "Images", ".webp": "Images", ".heic": "Images",
    ".raw": "Images", ".cr2": "Images", ".nef": "Images", ".svg": "Images", ".ico": "Images",
    # audio
    ".mp3": "Audio", ".wav": "Audio", ".flac": "Audio", ".aac": "Audio",
    ".ogg": "Audio", ".m4a": "Audio", ".wma": "Audio",
    # documents
    ".pdf": "Documents", ".doc": "Documents", ".docx": "Documents", ".xls": "Documents",
    ".xlsx": "Documents", ".ppt": "Documents", ".pptx": "Documents", ".txt": "Documents",
    ".rtf": "Documents", ".odt": "Documents", ".csv": "Documents", ".md": "Documents",
    ".epub": "Documents",
    # archives
    ".zip": "Archives", ".rar": "Archives", ".7z": "Archives", ".tar": "Archives",
    ".gz": "Archives", ".bz2": "Archives", ".iso": "Archives", ".vhd": "Archives",
    ".vhdx": "Archives", ".wim": "Archives",
    # code
    ".py": "Code", ".js": "Code", ".ts": "Code", ".html": "Code", ".css": "Code",
    ".java": "Code", ".c": "Code", ".cpp": "Code", ".cs": "Code", ".go": "Code",
    ".rs": "Code", ".json": "Code", ".xml": "Code", ".yml": "Code", ".yaml": "Code",
    ".sql": "Code",
    # executables
    ".exe": "Executables", ".msi": "Executables", ".dll": "Executables",
    ".bat": "Executables", ".ps1": "Executables", ".sys": "Executables",
}


def file_category(path_or_ext: str) -> str:
    ext = os.path.splitext(path_or_ext)[1].lower() if "." in os.path.basename(path_or_ext) or path_or_ext.startswith(".") else ""
    if not ext and path_or_ext.startswith("."):
        ext = path_or_ext.lower()
    return EXT_TO_CATEGORY.get(ext, "Other")


def category_color(category: str) -> str:
    return CATEGORY_COLORS.get(category, "#94a3b3")


# ---------------------------------------------------------------- formatting

def format_bytes(num: float) -> str:
    num = float(num or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(num)} B"
            return f"{num:.1f} {unit}" if num < 100 else f"{num:.0f} {unit}"
        num /= 1024.0
    return f"{num:.1f} PB"


def format_date(ts: float) -> str:
    try:
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    except (OSError, OverflowError, ValueError):
        return "—"


def short_path(path: str, max_len: int = 60) -> str:
    if len(path) <= max_len:
        return path
    head, tail = os.path.splitdrive(path)
    parts = tail.split(os.sep)
    # keep drive + first folder + ... + last 2 parts
    if len(parts) > 4:
        return f"{head}{os.sep}{parts[1]}{os.sep}…{os.sep}{os.sep.join(parts[-2:])}"
    return "…" + path[-(max_len - 1):]


# ---------------------------------------------------------------- drives

@dataclass
class DriveInfo:
    letter: str          # "C:\\"
    label: str           # volume label or ""
    total: int
    used: int
    free: int

    @property
    def pct_used(self) -> float:
        return (self.used / self.total * 100.0) if self.total else 0.0

    @property
    def display(self) -> str:
        name = f" ({self.label})" if self.label else ""
        return f"{self.letter.rstrip(chr(92))}{name} — {format_bytes(self.free)} free of {format_bytes(self.total)}"


def _volume_label(letter: str) -> str:
    try:
        kernel32 = ctypes.windll.kernel32
        vol = ctypes.create_unicode_buffer(256)
        fs = ctypes.create_unicode_buffer(256)
        serial = ctypes.c_uint32()
        max_comp = ctypes.c_uint32()
        flags = ctypes.c_uint32()
        ok = kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(letter), vol, 256,
            ctypes.byref(serial), ctypes.byref(max_comp),
            ctypes.byref(flags), fs, 256,
        )
        return vol.value if ok else ""
    except Exception:
        return ""


def get_drives() -> list[DriveInfo]:
    """List fixed + removable Windows drives. Falls back gracefully."""
    drives: list[DriveInfo] = []
    try:
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        letters = [f"{chr(65 + i)}:\\" for i in range(26) if bitmask & (1 << i)]
    except Exception:
        letters = [f"{chr(65 + i)}:\\" for i in range(26) if os.path.exists(f"{chr(65 + i)}:\\")]

    for letter in letters:
        try:
            dtype = ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(letter))
        except Exception:
            dtype = 3  # assume fixed
        if dtype not in (2, 3):  # removable or fixed only (skip CD/network/ram)
            continue
        try:
            usage = shutil.disk_usage(letter)
            drives.append(DriveInfo(
                letter=letter,
                label=_volume_label(letter),
                total=usage.total, used=usage.used, free=usage.free,
            ))
        except (OSError, PermissionError):
            continue
    if not drives:  # last-resort fallback
        for letter in ("C:\\",):
            try:
                usage = shutil.disk_usage(letter)
                drives.append(DriveInfo(letter, "", usage.total, usage.used, usage.free))
            except OSError:
                pass
    return drives


# ---------------------------------------------------------------- safety

# Folders the app will NEVER offer to delete / will warn about.
PROTECTED_DIRS = [
    os.environ.get("WINDIR", r"C:\Windows").lower(),
    os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files")).lower(),
    os.path.join(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")).lower(),
]

SAFE_CLEAN_TARGETS = [
    ("Windows Temp",           os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Temp")),
    ("User Temp",              os.path.join(os.environ.get("TEMP", os.path.expandvars(r"%USERPROFILE%\AppData\Local\Temp")))),
    ("Windows Update cache",   os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "SoftwareDistribution", "Download")),
    ("Delivery Optimization",  os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "SoftwareDistribution", "DeliveryOptimization")),
    ("Windows Logs",           os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Logs")),
    ("Prefetch",               os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Prefetch")),
    ("Crash dumps",            os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Minidump")),
    ("Recycle Bin",            "$RECYCLE.BIN"),
]


def is_protected(path: str) -> bool:
    pl = os.path.normpath(path).lower()
    for prot in PROTECTED_DIRS:
        if pl == prot or pl.startswith(prot + os.sep):
            # Deleting *inside* temp-like subfolders is fine; the roots themselves are not.
            return True
    return False


def is_hidden_system(path: str) -> bool:
    try:
        attrs = ctypes.windll.kernel32.GetFileAttributesW(ctypes.c_wchar_p(path))
        if attrs == 0xFFFFFFFF:
            return False
        return bool(attrs & (0x2 | 0x4))  # HIDDEN | SYSTEM
    except Exception:
        name = os.path.basename(path)
        return name.startswith(".") or name.startswith("$")
