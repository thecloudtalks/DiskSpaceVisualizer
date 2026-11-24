"""Duplicate-file finder — size pre-filter, then partial hash, then full hash.

Runs on top of a finished ScanResult (no re-walk needed) in a daemon thread,
reporting progress through a queue so the Tk UI never freezes. Stdlib only.
"""
from __future__ import annotations

import hashlib
import os
import queue
import threading
from dataclasses import dataclass, field


@dataclass
class DuplicateGroup:
    size: int                       # bytes per file
    files: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.files)

    @property
    def waste(self) -> int:
        """Bytes reclaimable by keeping just one copy."""
        return self.size * (len(self.files) - 1) if len(self.files) > 1 else 0


def _hash_prefix(path: str, num_bytes: int = 256 * 1024) -> str | None:
    """Hash the first ``num_bytes`` — cheap way to split same-size files."""
    try:
        h = hashlib.md5()
        with open(path, "rb") as fh:
            remaining = num_bytes
            while remaining > 0:
                chunk = fh.read(min(65536, remaining))
                if not chunk:
                    break
                h.update(chunk)
                remaining -= len(chunk)
        return h.hexdigest()
    except (OSError, PermissionError):
        return None


def _hash_full(path: str, cancel: threading.Event | None = None) -> str | None:
    try:
        h = hashlib.md5()
        with open(path, "rb") as fh:
            while True:
                if cancel is not None and cancel.is_set():
                    return None
                chunk = fh.read(1024 * 1024)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except (OSError, PermissionError):
        return None


class DuplicateFinder(threading.Thread):
    """Background worker. Puts ``dup-progress`` / ``dup-done`` dicts on ``events``."""

    def __init__(
        self,
        files: list,
        events: "queue.Queue[dict]",
        cancel: threading.Event,
        *,
        min_size: int = 1024 * 1024,
    ) -> None:
        super().__init__(daemon=True)
        self.files = files
        self.events = events
        self.cancel = cancel
        self.min_size = min_size

    def run(self) -> None:  # noqa: C901
        def emit(**kw):
            self.events.put({"type": "dup-progress", **kw})

        # 1. group by exact file size (cheap, no I/O)
        by_size: dict[int, list[str]] = {}
        for f in self.files:
            if self.cancel.is_set():
                self.events.put({"type": "dup-done", "groups": [], "cancelled": True})
                return
            size = f.size if hasattr(f, "size") else f[1]
            path = f.path if hasattr(f, "path") else f[0]
            if size < self.min_size:
                continue
            by_size.setdefault(size, []).append(path)
        candidates = {s: ps for s, ps in by_size.items() if len(ps) > 1}
        emit(stage="grouping", groups=len(candidates))

        # 2. partial hash to weed out same-size-but-different files
        groups: list[DuplicateGroup] = []
        total_steps = sum(len(ps) for ps in candidates.values()) or 1
        done = 0
        for size, paths in sorted(candidates.items(), key=lambda kv: -kv[0]):
            if self.cancel.is_set():
                break
            by_prefix: dict[str, list[str]] = {}
            for p in paths:
                if self.cancel.is_set():
                    break
                digest = _hash_prefix(p)
                done += 1
                if digest:
                    by_prefix.setdefault(digest, []).append(p)
                if done % 20 == 0:
                    emit(stage="hashing", done=done, total=total_steps)
            # 3. full hash only within matching prefixes
            for prefix_paths in by_prefix.values():
                if len(prefix_paths) < 2:
                    continue
                by_full: dict[str, list[str]] = {}
                for p in prefix_paths:
                    if self.cancel.is_set():
                        break
                    digest = _hash_full(p, self.cancel)
                    if digest:
                        by_full.setdefault(digest, []).append(p)
                for same in by_full.values():
                    if len(same) > 1:
                        groups.append(DuplicateGroup(size=size, files=sorted(same)))

        groups.sort(key=lambda g: g.waste, reverse=True)
        self.events.put({
            "type": "dup-done",
            "groups": groups,
            "cancelled": self.cancel.is_set(),
        })


def start_duplicate_search(files: list, events: "queue.Queue[dict]",
                           cancel: threading.Event, **kwargs) -> DuplicateFinder:
    finder = DuplicateFinder(files, events, cancel, **kwargs)
    finder.start()
    return finder
