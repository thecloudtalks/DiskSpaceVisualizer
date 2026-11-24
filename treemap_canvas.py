"""Treemap canvas widget (squarified treemap, stdlib + tkinter only)."""
from __future__ import annotations

import os
import tkinter as tk


def _squarify(sizes: list[float], x: float, y: float, w: float, h: float):
    """Yield (index, x, y, w, h) using the squarified treemap algorithm."""
    if not sizes or w <= 0 or h <= 0:
        return
    total = sum(sizes)
    if total <= 0:
        return
    # normalize to the available area
    scale = (w * h) / total
    sizes = [s * scale for s in sizes]
    items = list(enumerate(sizes))
    cx, cy, cw, ch = x, y, w, h

    def worst(row, side):
        s = sum(r[1] for r in row)
        if s <= 0 or side <= 0:
            return float("inf")
        mx = max(r[1] for r in row)
        mn = min(r[1] for r in row)
        return max((side * side * mx) / (s * s), (s * s) / (side * side * mn))

    i = 0
    n = len(items)
    while i < n:
        side = min(cw, ch)
        row = [items[i]]
        i += 1
        while i < n and worst(row + [items[i]], side) <= worst(row, side):
            row.append(items[i])
            i += 1
        s = sum(r[1] for r in row)
        if cw >= ch:  # vertical strip
            strip_w = s / ch if ch else 0
            ry = cy
            for idx, area in row:
                rh = area / strip_w if strip_w else 0
                yield idx, cx, ry, strip_w, rh
                ry += rh
            cx += strip_w
            cw -= strip_w
        else:  # horizontal strip
            strip_h = s / cw if cw else 0
            rx = cx
            for idx, area in row:
                rw = area / strip_h if strip_h else 0
                yield idx, rx, cy, rw, strip_h
                rx += rw
            cy += strip_h
            ch -= strip_h


class TreemapCanvas(tk.Canvas):
    """Canvas that draws clickable / hoverable treemap rectangles."""

    def __init__(self, master, *, on_select=None, **kwargs):
        super().__init__(master, highlightthickness=0, **kwargs)
        self._items: list[dict] = []
        self._rects: list[tuple[int, tuple[float, float, float, float]]] = []
        self._hover: int | None = None
        self.on_select = on_select
        self.empty_message = "Scan a drive to see its treemap.\nEach block = one folder or file, sized by disk usage."
        self._redraw_after: str | None = None
        self.bind("<Configure>", lambda _e: self._schedule_redraw())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", lambda _e: self._set_hover(None))
        self.bind("<Unmap>", lambda _e: self._hide_tip())
        self.bind("<Button-1>", self._on_click)
        self._tooltip: tk.Toplevel | None = None
        self._tip_label: tk.Label | None = None
        self._tip_font = ("Segoe UI", 10)

    # -- data -------------------------------------------------------------
    def set_data(self, items: list[dict]):
        # items: [{label, path, size, color}]
        self._items = sorted(items, key=lambda d: d.get("size", 0), reverse=True)[:400]
        self._hover = None
        self._hide_tip()
        self.redraw()

    def _schedule_redraw(self):
        """Coalesce rapid <Configure> bursts (e.g. tab switches) into one redraw."""
        if self._redraw_after is not None:
            try:
                self.after_cancel(self._redraw_after)
            except tk.TclError:
                pass
            self._redraw_after = None
        self._redraw_after = self.after(40, self._do_redraw)

    def _do_redraw(self):
        self._redraw_after = None
        try:
            if not self.winfo_ismapped():
                return
        except tk.TclError:
            return
        self.redraw()

    def hide_tip(self):
        self._hide_tip()

    def redraw(self):
        self.delete("all")
        self._rects = []
        W = self.winfo_width()
        H = self.winfo_height()
        if W < 50 or H < 50 or not self._items:
            if not self._items:
                self.create_text(28, 24, anchor="nw", fill="#94a3b8",
                                 font=("Segoe UI", 12), text=self.empty_message)
            return
        pad = 6
        sizes = [max(float(d.get("size", 0)), 1.0) for d in self._items]
        for idx, x, y, w, h in _squarify(sizes, pad, pad, W - pad * 2, H - pad * 2):
            if w < 4 or h < 4:
                continue
            d = self._items[idx]
            color = d.get("color", "#38bdf8")
            outline = "#0f172a" if self.cget("bg") == "#0f172a" else "white"
            width = 3 if idx == self._hover else 1
            rid = self.create_rectangle(x, y, x + w, y + h, fill=color,
                                        outline=outline, width=width)
            # soft top-light gloss so blocks feel less flat
            if h > 34 and w > 30:
                gloss_h = min(12, h * 0.28)
                self.create_rectangle(x + 2, y + 2, x + w - 2, y + gloss_h,
                                      fill="white", outline="", stipple="gray25")
            self._rects.append((rid, (x, y, w, h)))
            if w > 70 and h > 30:
                name = os.path.basename(d.get("label") or d.get("path", "")) or d.get("path", "")
                if d.get("is_dir"):
                    name = "📁 " + name
                max_chars = max(5, int((w - 12) / 7.5))
                if len(name) > max_chars:
                    name = name[:max(0, max_chars - 1)] + "…"
                self.create_text(x + 6, y + 5, anchor="nw", text=name,
                                 font=("Segoe UI", 10, "bold"), fill="white")
                if w > 120 and h > 54:
                    from utils import format_bytes
                    self.create_text(x + 6, y + 25, anchor="nw",
                                     text=format_bytes(d.get("size", 0)),
                                     font=("Segoe UI", 10), fill="white")

    # -- interaction ------------------------------------------------------
    def _hit(self, x, y) -> int | None:
        for pos, (rid, (rx, ry, rw, rh)) in enumerate(self._rects):
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                # map back to item index: rects are in layout order of sorted items
                return pos
        return None

    def _set_hover(self, pos: int | None):
        if pos == self._hover:
            return
        # outline-only highlight: no full redraw, so hovering stays buttery smooth
        if self._hover is not None and self._hover < len(self._rects):
            try:
                self.itemconfig(self._rects[self._hover][0], width=1)
            except tk.TclError:
                pass
        self._hover = pos
        if pos is None:
            self._hide_tip()
        elif pos < len(self._rects):
            try:
                self.itemconfig(self._rects[pos][0], width=3)
            except tk.TclError:
                pass

    def _on_motion(self, event):
        pos = self._hit(event.x, event.y)
        if pos != self._hover:
            self._set_hover(pos)
        if pos is not None:
            rid, _ = self._rects[pos]
            # rect order matches item order of the drawn subset
            item = self._items[pos] if pos < len(self._items) else None
            if item:
                self._show_tip(event.x_root + 14, event.y_root + 10, item)

    def _on_click(self, event):
        pos = self._hit(event.x, event.y)
        if pos is not None and self.on_select and pos < len(self._items):
            self.on_select(self._items[pos])

    # -- tooltip ----------------------------------------------------------
    def _show_tip(self, x, y, item):
        from utils import format_bytes
        if self._tooltip is None:
            self._tooltip = tk.Toplevel(self)
            self._tooltip.wm_overrideredirect(True)
            self._tip_label = tk.Label(self._tooltip, justify="left",
                                       background="#0f172a", foreground="white",
                                       font=self._tip_font, padx=8, pady=6)
            self._tip_label.pack()
        text = f"{os.path.basename(item.get('path',''))}\n{format_bytes(item.get('size',0))}\n{item.get('path','')}"
        self._tip_label.config(text=text, font=self._tip_font)
        self._tooltip.wm_geometry(f"+{x}+{y}")
        self._tooltip.deiconify()

    def _hide_tip(self):
        if self._tooltip is not None:
            try:
                self._tooltip.withdraw()
            except tk.TclError:
                pass
