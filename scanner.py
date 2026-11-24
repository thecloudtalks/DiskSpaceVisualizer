"""Background disk scanner — fast os.scandir walk with progress + cancellation.

Design:
* Runs in a daemon thread, never blocks the Tk mainloop.
* Reports progress through a thread-safe callback (the GUI polls a queue).
* Aggregates directory sizes bottom-up so the treemap + folder list are instant.
* Skips reparse points / junctions to avoid infinite loops (AppData loops on Windows).
"""
from __future__ import annotations

import os
import time
import queue
import threading
from dataclasses import dataclass, field

from utils import EXT_TO_CATEGORY


@dataclass
class FileRecord:
    path: str
    size: int
    mtime: float
    ext: str


@dataclass
class ScanResult:
    root: str
    files: list[FileRecord] = field(default_factory=list)
    dir_sizes: dict[str, int] = field(default_factory=dict)   # dir path -> total bytes incl. children
    dir_counts: dict[str, int] = field(default_factory=dict)  # dir path -> file count incl. children
    dir_topcat: dict[str, str] = field(default_factory=dict)  # dir path -> dominant content category
    total_size: int = 0
    file_count: int = 0
    dir_count: int = 0
    skipped: int = 0
    errors: int = 0
    elapsed: float = 0.0
    cancelled: bool = False

    def top_files(self, n: int = 500) -> list[FileRecord]:
        return sorted(self.files, key=lambda f: f.size, reverse=True)[:n]

    def top_dirs(self, n: int = 200) -> list[tuple[str, int]]:
        items = sorted(self.dir_sizes.items(), key=lambda kv: kv[1], reverse=True)
        # hide the root itself and tiny entries for a cleaner list
        items = [(p, s) for p, s in items if os.path.normpath(p) != os.path.normpath(self.root)]
        return items[:n]


class Scanner(threading.Thread):
    """Single background thread that walks ``root``."""

    def __init__(
        self,
        root: str,
        events: "queue.Queue[dict]",
        cancel: threading.Event,
        *,
        min_file_size: int = 0,
        skip_hidden: bool = False,
        max_files_stored: int = 120_000,
    ) -> None:
        super().__init__(daemon=True)
        self.root = os.path.abspath(root)
        self.events = events
        self.cancel = cancel
        self.min_file_size = min_file_size
        self.skip_hidden = skip_hidden
        self.max_files_stored = max_files_stored

    # -- public -----------------------------------------------------------
    def run(self) -> None:  # noqa: C901 - straightforward walk
        import ctypes

        t0 = time.time()
        result = ScanResult(root=self.root)
        # per-directory direct totals so we can roll up bottom-up
        direct_size: dict[str, int] = {}
        direct_count: dict[str, int] = {}
        direct_cat: dict[str, dict[str, int]] = {}  # dir -> {category: bytes} (direct files only)
        children: dict[str, list[str]] = {}
        order: list[str] = []          # discovery order (parents before children)
        stack = [self.root]
        seen_dirs = {os.path.normcase(os.path.abspath(self.root))}

        scanned_files = 0
        scanned_bytes = 0
        last_emit = 0.0

        def is_hidden(path: str, name: str) -> bool:
            if name.startswith("$") or name.startswith("."):
                return True
            try:
                attrs = ctypes.windll.kernel32.GetFileAttributesW(ctypes.c_wchar_p(path))
                if attrs != 0xFFFFFFFF:
                    return bool(attrs & 0x6)  # HIDDEN(2) | SYSTEM(4)
            except Exception:
                pass
            return False

        while stack:
            if self.cancel.is_set():
                result.cancelled = True
                break
            current = stack.pop()
            order.append(current)
            direct_size.setdefault(current, 0)
            direct_count.setdefault(current, 0)
            children.setdefault(current, [])
            try:
                with os.scandir(current) as it:
                    for entry in it:
                        if self.cancel.is_set():
                            break
                        try:
                            p = entry.path
                            if self.skip_hidden and is_hidden(p, entry.name):
                                result.skipped += 1
                                continue
                            if entry.is_symlink():
                                result.skipped += 1
                                continue
                            if entry.is_dir(follow_symlinks=False):
                                norm = os.path.normcase(os.path.abspath(p))
                                if norm in seen_dirs:
                                    result.skipped += 1
                                    continue
                                seen_dirs.add(norm)
                                children[current].append(p)
                                stack.append(p)
                                result.dir_count += 1
                            elif entry.is_file(follow_symlinks=False):
                                try:
                                    st = entry.stat(follow_symlinks=False)
                                except OSError:
                                    result.errors += 1
                                    continue
                                size = st.st_size
                                scanned_files += 1
                                scanned_bytes += size
                                direct_size[current] += size
                                direct_count[current] += size and 1 or 0
                                ext = os.path.splitext(entry.name)[1].lower()
                                cat = EXT_TO_CATEGORY.get(ext, "Other")
                                slot = direct_cat.get(current)
                                if slot is None:
                                    slot = direct_cat[current] = {}
                                slot[cat] = slot.get(cat, 0) + size
                                if size >= self.min_file_size and len(result.files) < self.max_files_stored:
                                    result.files.append(FileRecord(
                                        path=p, size=size,
                                        mtime=st.st_mtime,
                                        ext=ext,
                                    ))
                        except (OSError, PermissionError):
                            result.errors += 1
            except (OSError, PermissionError):
                result.errors += 1
                continue

            now = time.time()
            if now - last_emit > 0.15:
                last_emit = now
                self.events.put({
                    "type": "progress",
                    "files": scanned_files,
                    "bytes": scanned_bytes,
                    "current": current,
                    "dirs": result.dir_count,
                })

        # bottom-up rollup (children first). Child category maps are merged
        # into the parent and freed, so memory stays proportional to the
        # tree frontier rather than dirs x categories.
        total = dict(direct_size)
        counts = dict(direct_count)
        merged: dict[str, dict[str, int]] = {}
        topcat: dict[str, str] = {}
        for parent in reversed(order):
            for child in children.get(parent, []):
                total[parent] = total.get(parent, 0) + total.get(child, 0)
                counts[parent] = counts.get(parent, 0) + counts.get(child, 0)
            m = direct_cat.pop(parent, {})
            for child in children.get(parent, []):
                cm = merged.pop(child, None)
                if not cm:
                    continue
                if len(cm) > len(m):
                    m, cm = cm, m
                for k, v in cm.items():
                    m[k] = m.get(k, 0) + v
            topcat[parent] = max(m.items(), key=lambda kv: kv[1])[0] if m else "Other"
            merged[parent] = m

        result.dir_sizes = total
        result.dir_counts = counts
        result.dir_topcat = topcat
        result.total_size = total.get(self.root, 0)
        result.file_count = scanned_files
        result.elapsed = time.time() - t0
        # biggest-first so the GUI can render instantly
        result.files.sort(key=lambda f: f.size, reverse=True)
        self.events.put({"type": "done", "result": result})


def start_scan(root: str, events: "queue.Queue[dict]", cancel: threading.Event, **kwargs) -> Scanner:
    scanner = Scanner(root, events, cancel, **kwargs)
    scanner.start()
    return scanner
