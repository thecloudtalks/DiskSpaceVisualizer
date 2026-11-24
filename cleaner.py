"""Safe deletion helpers (Recycle Bin aware, Windows-first, stdlib only)."""
from __future__ import annotations

import ctypes
import os
import shutil


# ---------------------------------------------------------------- recycle bin

def recycle_delete(path: str) -> bool:
    """Move a file/folder to the Recycle Bin (undoable). Returns True on success."""
    try:
        SHFileOperationW = ctypes.windll.shell32.SHFileOperationW

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ("hwnd", ctypes.c_void_p),
                ("wFunc", ctypes.c_uint),
                ("pFrom", ctypes.c_wchar_p),
                ("pTo", ctypes.c_wchar_p),
                ("fFlags", ctypes.c_ushort),
                ("fAnyOperationsAborted", ctypes.c_bool),
                ("hNameMappings", ctypes.c_void_p),
                ("lpszProgressTitle", ctypes.c_wchar_p),
            ]

        FO_DELETE = 3
        FOF_ALLOWUNDO = 0x40
        FOF_NOCONFIRMATION = 0x10
        FOF_SILENT = 0x4
        FOF_NOERRORUI = 0x400

        op = SHFILEOPSTRUCTW()
        op.hwnd = None
        op.wFunc = FO_DELETE
        op.pFrom = os.path.abspath(path) + "\0"
        op.pTo = None
        op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
        return SHFileOperationW(ctypes.byref(op)) == 0 and not op.fAnyOperationsAborted
    except Exception:
        return False


def delete_permanent(path: str) -> bool:
    try:
        if os.path.isfile(path) or os.path.islink(path):
            os.remove(path)
        elif os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=False)
        else:
            return False
        return True
    except Exception:
        return False


def empty_recycle_bin() -> tuple[bool, str]:
    try:
        res = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 1 | 2 | 4)  # no confirm/sound/progress
        return (True, "Recycle Bin emptied.") if res == 0 else (False, f"Could not empty Recycle Bin (code {res}).")
    except Exception as exc:
        return False, str(exc)


def recycle_bin_size() -> int:
    """Total bytes in the Recycle Bin across fixed drives (best effort)."""
    try:
        SHQueryRecycleBinW = ctypes.windll.shell32.SHQueryRecycleBinW

        class SHQUERYRBINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_ulong),
                        ("i64Size", ctypes.c_int64),
                        ("i64NumItems", ctypes.c_int64)]

        info = SHQUERYRBINFO()
        info.cbSize = ctypes.sizeof(SHQUERYRBINFO)
        if SHQueryRecycleBinW(None, ctypes.byref(info)) == 0:
            return int(info.i64Size)
    except Exception:
        pass
    # fallback: sum $RECYCLE.BIN folders
    total = 0
    for letter in (f"{chr(c)}:\\$RECYCLE.BIN" for c in range(65, 91)):
        if os.path.isdir(letter):
            for _root, _dirs, files in os.walk(letter):
                for fn in files:
                    try:
                        total += os.path.getsize(os.path.join(_root, fn))
                    except OSError:
                        pass
    return total


# ---------------------------------------------------------------- folder-contents cleaning

def clear_folder_contents(folder: str, *, recycle: bool = True) -> tuple[int, int, int]:
    """Delete everything *inside* folder (never the folder itself).

    Returns (freed_bytes, removed_count, failed_count). Sizes are measured
    before deletion; files that fail are counted, not raised.
    """
    freed, removed, failed = 0, 0, 0
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return 0, 0, 1
    for entry in entries:
        try:
            p = entry.path
            try:
                if entry.is_file(follow_symlinks=False) or entry.is_symlink():
                    freed += os.path.getsize(p)
                elif entry.is_dir(follow_symlinks=False):
                    freed += _tree_size(p)
            except OSError:
                pass
            ok = recycle_delete(p) if recycle else delete_permanent(p)
            if not ok and recycle:
                ok = delete_permanent(p)  # last resort
            removed += 1 if ok else 0
            failed += 0 if ok else 1
        except Exception:
            failed += 1
    return freed, removed, failed


def _tree_size(root: str) -> int:
    total = 0
    try:
        with os.scandir(root) as it:
            for entry in it:
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                    elif entry.is_dir(follow_symlinks=False):
                        total += _tree_size(entry.path)
                except OSError:
                    continue
    except OSError:
        pass
    return total
