"""Analysis: file-type breakdown + cleanup recommendations."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

from utils import file_category, get_drives


@dataclass
class TypeStat:
    category: str
    size: int
    count: int


def breakdown_by_type(files) -> list[TypeStat]:
    acc: dict[str, list[int]] = {}
    for f in files:
        cat = file_category(f.ext or f.path)
        slot = acc.setdefault(cat, [0, 0])
        slot[0] += f.size
        slot[1] += 1
    stats = [TypeStat(cat, size, cnt) for cat, (size, cnt) in acc.items()]
    return sorted(stats, key=lambda s: s.size, reverse=True)


# ---------------------------------------------------------------- cleanup

@dataclass
class CleanupItem:
    key: str
    title: str
    detail: str
    size: int
    safety: str        # "Safe" | "Caution" | "Keep"
    paths: list[str]   # concrete files/folders to delete (or special tokens)
    kind: str = "files"


def _dir_size(path: str, cap_files: int = 60_000) -> tuple[int, list[str]]:
    """Return (bytes, [top-level children]) without following junctions."""
    total = 0
    kids: list[str] = []
    try:
        with os.scandir(path) as it:
            for entry in it:
                p = entry.path
                if entry.is_symlink():
                    continue
                try:
                    if entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                        kids.append(p)
                    elif entry.is_dir(follow_symlinks=False):
                        sub, _ = _dir_size(p, cap_files)
                        total += sub
                        kids.append(p)
                except OSError:
                    continue
                if len(kids) > cap_files:
                    break
    except OSError:
        pass
    return total, kids


def _browser_caches() -> list[tuple[str, str]]:
    local = os.environ.get("LOCALAPPDATA", "")
    roaming = os.environ.get("APPDATA", "")
    candidates = [
        ("Chrome cache",   os.path.join(local, "Google", "Chrome", "User Data", "Default", "Cache")),
        ("Chrome code cache", os.path.join(local, "Google", "Chrome", "User Data", "Default", "Code Cache")),
        ("Edge cache",     os.path.join(local, "Microsoft", "Edge", "User Data", "Default", "Cache")),
        ("Firefox cache",  os.path.join(local, "Mozilla", "Firefox")),
        ("Brave cache",    os.path.join(local, "BraveSoftware", "Brave-Browser", "User Data", "Default", "Cache")),
        ("Opera cache",    os.path.join(roaming, "Opera Software", "Opera Stable", "Cache")),
    ]
    return [(t, p) for t, p in candidates if os.path.isdir(p)]


def _old_large_downloads(min_size: int = 100 * 1024 * 1024, max_items: int = 25):
    dl = os.path.join(os.path.expanduser("~"), "Downloads")
    found = []
    if not os.path.isdir(dl):
        return found, 0
    total = 0
    try:
        with os.scandir(dl) as it:
            for entry in it:
                try:
                    if entry.is_file(follow_symlinks=False):
                        st = entry.stat(follow_symlinks=False)
                        if st.st_size >= min_size:
                            found.append((entry.path, st.st_size, st.st_mtime))
                            total += st.st_size
                except OSError:
                    continue
    except OSError:
        pass
    found.sort(key=lambda t: t[1], reverse=True)
    return found[:max_items], total


def collect_cleanup(scan_root: str | None = None) -> list[CleanupItem]:
    """Build the Safe-to-delete recommendation list (fast, no deep walks except caches)."""
    from utils import SAFE_CLEAN_TARGETS

    items: list[CleanupItem] = []

    # 1. well-known temp locations
    for title, path in SAFE_CLEAN_TARGETS:
        if path == "$RECYCLE.BIN":
            continue
        if os.path.isdir(path):
            size, kids = _dir_size(path)
            if size > 0 or kids:
                items.append(CleanupItem(
                    key=f"dir:{path}", title=title,
                    detail=f"{path} — temporary files Windows & apps can recreate.",
                    size=size, safety="Safe", paths=[path], kind="folder-contents",
                ))

    # 2. user temp (same as above but explicit label if different)
    user_temp = os.environ.get("TEMP") or os.path.expandvars(r"%USERPROFILE%\AppData\Local\Temp")
    if user_temp and os.path.isdir(user_temp) and not any(i.key == f"dir:{user_temp}" for i in items):
        size, _ = _dir_size(user_temp)
        if size:
            items.append(CleanupItem(f"dir:{user_temp}", "User temp files",
                                     f"{user_temp}", size, "Safe", [user_temp], "folder-contents"))

    # 3. browser caches
    for title, path in _browser_caches():
        size, _ = _dir_size(path)
        if size:
            items.append(CleanupItem(f"dir:{path}", title, path, size, "Safe", [path], "folder-contents"))

    # 4. recycle bin (size queried separately by the GUI via cleaner module)
    items.append(CleanupItem("recycle-bin", "Recycle Bin",
                             "Files already deleted, still occupying disk space.",
                             0, "Safe", ["$RECYCLE.BIN"], kind="recycle-bin"))

    # 5. big old installers / downloads the user may have forgotten
    big, big_total = _old_large_downloads()
    if big:
        items.append(CleanupItem(
            "big-downloads", "Large files in Downloads",
            f"{len(big)} file(s) over 100 MB in your Downloads folder. Review before deleting.",
            big_total, "Caution", [p for p, _, _ in big], kind="files"))

    # 6. stale thumbnails / icon cache (safe, regenerates)
    local = os.environ.get("LOCALAPPDATA", "")
    thumb = os.path.join(local, "Microsoft", "Windows", "Explorer")
    if os.path.isdir(thumb):
        size, kids = _dir_size(thumb)
        thumbs = [k for k in kids if os.path.basename(k).lower().startswith("thumbcache") or "iconcache" in os.path.basename(k).lower()]
        if thumbs:
            items.append(CleanupItem("thumbcache", "Thumbnail & icon cache",
                                     "Windows rebuilds these automatically.", size, "Safe", thumbs, kind="files"))
    return sorted(items, key=lambda i: i.size, reverse=True)


def safety_advice() -> list[tuple[str, str, str]]:
    """Static 'never delete' guidance shown at the bottom of the Cleanup tab."""
    windir = os.environ.get("WINDIR", r"C:\Windows")
    return [
        ("Keep", f"{windir}", "Windows itself. Never delete files here by hand — use the Safe items above."),
        ("Keep", "Program Files", "Your installed apps. Uninstall via Settings → Apps instead of deleting folders."),
        ("Caution", "Downloads / Documents", "Only delete files you recognise. When in doubt, move them to an external drive first."),
        ("Safe", "Temp / Cache / Recycle Bin", "These are regenerated automatically and are always safe to clear."),
    ]


# ---------------------------------------------------------------- age heatmap

import time as _time


@dataclass
class AgeStat:
    label: str
    days_min: int
    days_max: int | None   # None = open-ended (oldest bucket)
    color: str
    size: int = 0
    count: int = 0


AGE_BUCKETS: list[tuple[str, int, int | None, str]] = [
    ("Last 30 days",       0,    30, "#22c55e"),
    ("1–6 months",        30,   180, "#84cc16"),
    ("6–12 months",      180,   365, "#f59e0b"),
    ("1–2 years",        365,   730, "#f97316"),
    ("Older than 2 years", 730, None, "#dc2626"),
]


def age_breakdown(files, now: float | None = None) -> list[AgeStat]:
    """Bucket scanned files by last-modified age (fresh → stale)."""
    now = now if now is not None else _time.time()
    stats = [AgeStat(label, dmin, dmax, color) for label, dmin, dmax, color in AGE_BUCKETS]
    unknown = AgeStat("Unknown date", -1, -1, "#64748b")
    for f in files:
        try:
            age_days = (now - f.mtime) / 86400.0
        except (OverflowError, OSError, TypeError):
            unknown.size += f.size
            unknown.count += 1
            continue
        if age_days < 0:
            age_days = 0
        for s in stats:
            if age_days >= s.days_min and (s.days_max is None or age_days < s.days_max):
                s.size += f.size
                s.count += 1
                break
    out = [s for s in stats if s.count] + ([unknown] if unknown.count else [])
    return out


def stale_files(files, older_than_days: int = 365, limit: int = 500):
    """Biggest files not modified in ``older_than_days`` (most-likely-forgotten first)."""
    now = _time.time()
    cutoff = now - older_than_days * 86400.0
    stale = [f for f in files if f.mtime <= cutoff]
    stale.sort(key=lambda f: f.size, reverse=True)
    return stale[:limit]
