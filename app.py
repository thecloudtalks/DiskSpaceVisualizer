"""Disk Space Visualizer — main Tkinter application (Windows)."""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from analyzer import age_breakdown, breakdown_by_type, collect_cleanup, safety_advice, stale_files
from cleaner import clear_folder_contents, delete_permanent, empty_recycle_bin, recycle_bin_size, recycle_delete
from duplicates import DuplicateGroup, start_duplicate_search
from scanner import ScanResult, start_scan
from treemap_canvas import TreemapCanvas
from utils import CATEGORY_COLORS, __version__, category_color, file_category, format_bytes, format_date, get_drives, short_path

ACCENT = "#2563eb"
BG = "#f1f5f9"
SAFETY_COLORS = {"Safe": "#16a34a", "Caution": "#d97706", "Keep": "#dc2626"}


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"Disk Space Visualizer {__version__}")
        self.geometry("1220x780")
        self.minsize(1000, 640)
        try:
            base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
            png = os.path.join(base, "app.png")
            if os.path.exists(png):
                _img = tk.PhotoImage(file=png)
                self.iconphoto(True, _img)
                self._icon_img = _img  # keep a reference
            else:
                ico = os.path.join(base, "app.ico")
                if os.path.exists(ico):
                    self.iconbitmap(ico)
        except tk.TclError:
            pass

        self.events: queue.Queue[dict] = queue.Queue()
        self.cancel = threading.Event()
        self.result: ScanResult | None = None
        self.cleanup_items: list = []
        self._sort = {"col": "size", "rev": True}
        self._folder_sort_rev = True
        self._map_stack: list[str] = []          # treemap drill-down trail
        self._dir_children: dict[str, list[str]] = {}
        self._files_by_dir: dict[str, list] = {}
        self._draw_after: dict[str, str] = {}      # debounced canvas redraw handles

        self._build_style()
        self._build_layout()
        self._refresh_drives()
        self.after(120, self._poll_events)

    # ------------------------------------------------------------------ UI
    def _schedule_draw(self, key: str, fn, delay_ms: int = 40):
        """Coalesce rapid <Configure> bursts into a single chart redraw."""
        handle = self._draw_after.get(key)
        if handle is not None:
            try:
                self.after_cancel(handle)
            except tk.TclError:
                pass
        def _fire():
            self._draw_after.pop(key, None)
            try:
                fn()
            except tk.TclError:
                pass
        self._draw_after[key] = self.after(delay_ms, _fire)

    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background="white", relief="flat")
        style.configure("TLabel", background=BG, font=("Segoe UI", 11))
        style.configure("Card.TLabel", background="white", font=("Segoe UI", 11))
        style.configure("Title.TLabel", background=BG, font=("Segoe UI", 19, "bold"))
        style.configure("Sub.TLabel", background=BG, foreground="#475569", font=("Segoe UI", 10))
        style.configure("Accent.TButton", background=ACCENT, foreground="white",
                        font=("Segoe UI", 11, "bold"), padding=(14, 8), relief="flat")
        style.map("Accent.TButton", background=[("active", "#3b82f6"),
                                                        ("pressed", "#1d4ed8"),
                                                        ("disabled", "#94a3b3")])
        style.configure("TButton", font=("Segoe UI", 10), padding=(10, 6), relief="flat")
        style.map("TButton",
                  background=[("active", "#e2e8f0"), ("pressed", "#cbd5e1")],
                  relief=[("pressed", "flat"), ("!disabled", "flat")])
        style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(4, 6, 4, 0))
        # soft pill tabs: flat, no sunken "pressed" edge — selected = white + blue text
        style.configure("TNotebook.Tab",
                        font=("Segoe UI", 11, "bold"), padding=(16, 10),
                        background="#e2e8f0", foreground="#64748b",
                        borderwidth=0, focuscolor="",
                        lightcolor="#e2e8f0", darkcolor="#e2e8f0", bordercolor="#e2e8f0")
        style.map("TNotebook.Tab",
                  background=[("selected", "white"), ("active", "#cbd5e1")],
                  foreground=[("selected", ACCENT), ("active", "#0f172a")],
                  lightcolor=[("selected", "white")],
                  darkcolor=[("selected", "white")],
                  # keep selected/unselected geometry identical — no dip on click
                  padding=[("selected", (16, 10)), ("!selected", (16, 10))])
        style.configure("Treeview", font=("Segoe UI", 11), rowheight=32)
        style.configure("Treeview.Heading", font=("Segoe UI", 11, "bold"),
                        relief="flat", background="#f1f5f9")
        # soft selection: pale blue + dark text instead of the harsh dark-blue block
        style.map("Treeview",
                  background=[("selected", "#dbeafe")],
                  foreground=[("selected", "#0f172a")])
        style.map("Treeview.Heading", background=[("active", "#e2e8f0")])

    def _build_layout(self):
        # ---- header -----------------------------------------------------
        header = ttk.Frame(self, padding=(16, 12, 16, 6))
        header.pack(fill="x")
        ttk.Label(header, text="💾  Disk Space Visualizer", style="Title.TLabel").pack(side="left")

        right = ttk.Frame(header)
        right.pack(side="right")
        ttk.Label(right, text="Drive:").pack(side="left", padx=(0, 6))
        self.drive_var = tk.StringVar()
        self.drive_combo = ttk.Combobox(right, textvariable=self.drive_var, width=44, state="readonly")
        self.drive_combo.pack(side="left", padx=(0, 8))
        self.drive_combo.bind("<<ComboboxSelected>>", lambda _e: self._drive_selected())
        self.scan_btn = ttk.Button(right, text="🔍  Scan", style="Accent.TButton", command=self.start_scan)
        self.scan_btn.pack(side="left", padx=(0, 6))
        self.stop_btn = ttk.Button(right, text="⏹ Stop", command=self.stop_scan, state="disabled")
        self.stop_btn.pack(side="left", padx=(0, 6))
        ttk.Button(right, text="📁 Folder…", command=self.scan_custom_folder).pack(side="left")

        # ---- drive usage bar + progress ---------------------------------
        bar_row = ttk.Frame(self, padding=(16, 0, 16, 4))
        bar_row.pack(fill="x")
        self.usage_label = ttk.Label(bar_row, text="", style="Sub.TLabel")
        self.usage_label.pack(side="left")
        self.status_label = ttk.Label(bar_row, text="Pick a drive and press Scan.", style="Sub.TLabel")
        self.status_label.pack(side="right")

        prog_row = ttk.Frame(self, padding=(16, 0, 16, 8))
        prog_row.pack(fill="x")
        self.progress = ttk.Progressbar(prog_row, mode="indeterminate")
        self.progress.pack(fill="x")
        self.disk_bar = tk.Canvas(prog_row, height=10, highlightthickness=0, bg=BG)
        self.disk_bar.pack(fill="x", pady=(6, 0))
        self.disk_bar.bind("<Configure>", lambda _e: self._draw_disk_bar())

        # ---- tabs --------------------------------------------------------
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        # clean switching: never leave a stray tooltip floating over the new tab
        self.tabs.bind("<<NotebookTabChanged>>", lambda _e: self.treemap.hide_tip())

        self.tab_map = ttk.Frame(self.tabs)
        self.tab_files = ttk.Frame(self.tabs)
        self.tab_types = ttk.Frame(self.tabs)
        self.tab_age = ttk.Frame(self.tabs)
        self.tab_dup = ttk.Frame(self.tabs)
        self.tab_clean = ttk.Frame(self.tabs)
        self.tabs.add(self.tab_map, text="  🗺 Treemap  ")
        self.tabs.add(self.tab_files, text="  📂 Largest Files & Folders  ")
        self.tabs.add(self.tab_types, text="  🥧 File Types  ")
        self.tabs.add(self.tab_age, text="  ⏳ Age  ")
        self.tabs.add(self.tab_dup, text="  👯 Duplicates  ")
        self.tabs.add(self.tab_clean, text="  🧹 Cleanup  ")

        self._build_map_tab()
        self._build_files_tab()
        self._build_types_tab()
        self._build_age_tab()
        self._build_dup_tab()
        self._build_clean_tab()

    # -- treemap tab ------------------------------------------------------
    def _build_map_tab(self):
        top = ttk.Frame(self.tab_map, padding=10)
        top.pack(fill="x")
        self.map_info = ttk.Label(
            top,
            text="Bigger block = more space. Block color = what's inside. Click a folder to dive in.",
            style="Sub.TLabel")
        self.map_info.pack(side="left")
        legend = ttk.Frame(top)
        legend.pack(side="right")
        for cat, color in list(CATEGORY_COLORS.items())[:7]:
            dot = tk.Label(legend, text="●", fg=color, bg=BG, font=("Segoe UI", 13))
            dot.pack(side="left")
            tk.Label(legend, text=cat, bg=BG, font=("Segoe UI", 10)).pack(side="left", padx=(0, 8))

        crumbs = ttk.Frame(self.tab_map, padding=(10, 0, 10, 4))
        crumbs.pack(fill="x")
        self.map_back_btn = ttk.Button(crumbs, text="← Back", width=10,
                                       command=self._map_go_back, state="disabled")
        self.map_back_btn.pack(side="left", padx=(0, 8))
        self.map_crumb = ttk.Label(crumbs, text="", font=("Segoe UI", 11, "bold"))
        self.map_crumb.pack(side="left")
        ttk.Button(crumbs, text="Top level", command=self._map_go_top).pack(side="right")

        self.treemap = TreemapCanvas(self.tab_map, bg="#0f172a", on_select=self._treemap_selected)
        self.treemap.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        actions = ttk.Frame(self.tab_map, padding=(10, 0, 10, 10))
        actions.pack(fill="x")
        self.sel_label = ttk.Label(actions, text="Nothing selected.", style="Sub.TLabel")
        self.sel_label.pack(side="left")
        ttk.Button(actions, text="📂 Open", command=self._open_selected).pack(side="right", padx=4)
        ttk.Button(actions, text="♻ Delete (to Recycle Bin)", command=self._delete_selected).pack(side="right", padx=4)
        self._selected_path: str | None = None

    # -- files tab ---------------------------------------------------------
    def _build_files_tab(self):
        paned = ttk.Panedwindow(self.tab_files, orient="vertical")
        paned.pack(fill="both", expand=True, padx=10, pady=10)

        # folders (expandable tree — click ▸ to open subfolders)
        fbox = ttk.LabelFrame(paned, text=" Biggest folders (click ▸ to expand subfolders, double-click to open) ")
        paned.add(fbox, weight=1)
        self.folder_tree = ttk.Treeview(fbox, columns=("size", "content", "path"),
                                        show="tree headings", height=8)
        self.folder_tree.heading("#0", text="Folder")
        self.folder_tree.heading("size", text="Size  ▼")
        self.folder_tree.heading("content", text="Mostly")
        self.folder_tree.heading("path", text="Full path")
        self.folder_tree.column("#0", width=280, anchor="w")
        self.folder_tree.column("size", width=120, anchor="e")
        self.folder_tree.column("content", width=110, anchor="w")
        self.folder_tree.column("path", width=560, anchor="w")
        self.folder_tree.pack(side="left", fill="both", expand=True)
        fsb = ttk.Scrollbar(fbox, orient="vertical", command=self.folder_tree.yview)
        fsb.pack(side="right", fill="y")
        self.folder_tree.configure(yscrollcommand=fsb.set)
        self.folder_tree.heading("size", command=self._toggle_folder_sort)
        self.folder_tree.bind("<Double-1>", lambda _e: self._open_path(self._focused(self.folder_tree, 2)))
        self._bind_menu(self.folder_tree, col_path=2)

        # files
        lbox = ttk.LabelFrame(paned, text=" Biggest files (double-click to open) ")
        paned.add(lbox, weight=2)
        toolbar = ttk.Frame(lbox)
        toolbar.pack(fill="x", padx=6, pady=4)
        ttk.Label(toolbar, text="Filter:").pack(side="left")
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_: self._render_files())
        ttk.Entry(toolbar, textvariable=self.filter_var, width=36).pack(side="left", padx=6)
        self.files_count = ttk.Label(toolbar, text="", style="Sub.TLabel")
        self.files_count.pack(side="right")

        self.file_tree = ttk.Treeview(lbox, columns=("size", "name", "type", "modified", "path"),
                                      show="headings", height=14)
        for cid, title, w, anchor in (
                ("size", "Size", 110, "e"), ("name", "Name", 260, "w"),
                ("type", "Type", 110, "w"), ("modified", "Modified", 110, "w"),
                ("path", "Location", 480, "w")):
            self.file_tree.heading(cid, text=title, command=lambda c=cid: self._sort_files(c))
            self.file_tree.column(cid, width=w, anchor=anchor)
        self.file_tree.pack(side="left", fill="both", expand=True)
        vsb = ttk.Scrollbar(lbox, orient="vertical", command=self.file_tree.yview)
        vsb.pack(side="right", fill="y")
        self.file_tree.configure(yscrollcommand=vsb.set)
        self.file_tree.bind("<Double-1>", lambda _e: self._open_path(self._focused(self.file_tree, 4)))
        self._bind_menu(self.file_tree, col_path=4)

    def _bind_menu(self, tree: ttk.Treeview, col_path: int):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="📂 Open", command=lambda: self._open_path(self._focused(tree, col_path)))
        menu.add_command(label="📁 Show in Explorer", command=lambda: self._reveal(self._focused(tree, col_path)))
        menu.add_separator()
        menu.add_command(label="♻ Move to Recycle Bin", command=lambda: self._recycle(self._focused(tree, col_path)))
        tree.bind("<Button-3>", lambda e: (tree.identify_row(e.y) and tree.selection_set(tree.identify_row(e.y)),
                                           menu.tk_popup(e.x_root, e.y_root)))

    # -- types tab ----------------------------------------------------------
    def _build_types_tab(self):
        wrap = ttk.Frame(self.tab_types, padding=12)
        wrap.pack(fill="both", expand=True)
        ttk.Label(wrap, text="Where is your space going? Breakdown by file kind.",
                  style="Sub.TLabel").pack(anchor="w", pady=(0, 8))
        self.type_canvas = tk.Canvas(wrap, height=380, bg="white", highlightthickness=1,
                                     highlightbackground="#e2e8f0")
        self.type_canvas.pack(fill="x")
        self.type_canvas.bind("<Configure>", lambda _e: self._schedule_draw("types", self._draw_types))
        self.type_tree = ttk.Treeview(wrap, columns=("size", "count", "share"), show="headings", height=10)
        self.type_tree.heading("size", text="Size")
        self.type_tree.heading("count", text="Files")
        self.type_tree.heading("share", text="Share")
        self.type_tree.column("size", width=140, anchor="e")
        self.type_tree.column("count", width=120, anchor="e")
        self.type_tree.column("share", width=120, anchor="e")
        self.type_tree.pack(fill="both", expand=True, pady=(10, 0))
        self._type_stats: list = []

    # -- age tab ------------------------------------------------------------
    def _build_age_tab(self):
        wrap = ttk.Frame(self.tab_age, padding=12)
        wrap.pack(fill="both", expand=True)
        ttk.Label(wrap, text="When was it last touched? Stale files (untouched for years) "
                             "are the safest space to reclaim.",
                  style="Sub.TLabel").pack(anchor="w", pady=(0, 8))
        bar = ttk.Frame(wrap)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Label(bar, text="Stale means untouched for:").pack(side="left")
        self.age_limit_var = tk.StringVar(value="1 year")
        cb = ttk.Combobox(bar, textvariable=self.age_limit_var, width=10, state="readonly",
                          values=["6 months", "1 year", "2 years"])
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda _e: self._render_age())
        self.age_total = ttk.Label(bar, text="", style="Sub.TLabel")
        self.age_total.pack(side="right")

        self.age_canvas = tk.Canvas(wrap, height=250, bg="white", highlightthickness=1,
                                    highlightbackground="#e2e8f0")
        self.age_canvas.pack(fill="x")
        self.age_canvas.bind("<Configure>", lambda _e: self._schedule_draw("age", self._draw_age))
        self._age_stats: list = []

        self.age_tree = ttk.Treeview(wrap, columns=("size", "age", "modified", "path"),
                                     show="headings", height=12)
        self.age_tree.heading("size", text="Size")
        self.age_tree.heading("age", text="Untouched for")
        self.age_tree.heading("modified", text="Last modified")
        self.age_tree.heading("path", text="Stale file (biggest first)")
        self.age_tree.column("size", width=110, anchor="e")
        self.age_tree.column("age", width=120, anchor="w")
        self.age_tree.column("modified", width=110, anchor="w")
        self.age_tree.column("path", width=730, anchor="w")
        self.age_tree.pack(side="left", fill="both", expand=True, pady=(10, 0))
        asb = ttk.Scrollbar(wrap, orient="vertical", command=self.age_tree.yview)
        asb.pack(side="right", fill="y", pady=(10, 0))
        self.age_tree.configure(yscrollcommand=asb.set)
        self.age_tree.bind("<Double-1>", lambda _e: self._open_path(self._age_focused()))
        self._bind_menu(self.age_tree, col_path=3)

    def _age_limit_days(self) -> int:
        return {"6 months": 180, "1 year": 365, "2 years": 730}.get(self.age_limit_var.get(), 365)

    def _render_age(self):
        self.age_tree.delete(*self.age_tree.get_children())
        if not self.result:
            return
        import time as _t
        self._age_stats = age_breakdown(self.result.files)
        stale = stale_files(self.result.files, self._age_limit_days())
        stale_bytes = sum(f.size for f in stale)
        lim = self.age_limit_var.get()
        self.age_total.config(
            text=f"{len(stale)} file(s) untouched for {lim} — {format_bytes(stale_bytes)} stale")
        now = _t.time()
        for f in stale:
            days = max(0, int((now - f.mtime) / 86400))
            age_txt = f"{days // 365}y {days % 365 // 30}m" if days >= 365 else (
                f"{days // 30}m" if days >= 60 else f"{days}d")
            self.age_tree.insert("", "end", values=(
                format_bytes(f.size), age_txt, format_date(f.mtime), f.path))
        self._draw_age()

    def _draw_age(self):
        c = self.age_canvas
        if c.winfo_width() < 50:  # tab hidden — wait for the debounced Configure
            return
        c.delete("all")
        stats = getattr(self, "_age_stats", [])
        if not stats:
            c.create_text(16, 16, anchor="nw", fill="#64748b",
                          text="Scan a drive to see the age heatmap (green = fresh, red = forgotten).")
            return
        W = c.winfo_width() or 900
        H = c.winfo_height() or 170
        total = sum(s.size for s in stats) or 1
        x = 16
        bar_w = W - 32
        for s in stats:
            w = bar_w * s.size / total
            if w < 1:
                continue
            c.create_rectangle(x, 16, x + w, 56, fill=s.color, outline="white", width=2)
            x += w
        y = 76
        for s in stats:
            c.create_rectangle(16, y, 32, y + 14, fill=s.color, outline="")
            c.create_text(40, y, anchor="nw", fill="#0f172a",
                          font=("Segoe UI", 12, "bold"),
                          text=f"{s.label} — {format_bytes(s.size)}  "
                               f"({s.size / total * 100:.1f}%, {s.count:,} files)")
            y += 26

    def _age_focused(self) -> str | None:
        sel = self.age_tree.selection() or ((self.age_tree.focus(),) if self.age_tree.focus() else ())
        if not sel:
            return None
        return self.age_tree.item(sel[0], "values")[3]

    # -- duplicates tab ----------------------------------------------------
    def _build_dup_tab(self):
        wrap = ttk.Frame(self.tab_dup, padding=12)
        wrap.pack(fill="both", expand=True)
        ttk.Label(wrap, text="Find byte-identical copies (size + MD5 hash). "
                             "Keep one copy per group, recycle the rest.",
                  style="Sub.TLabel", wraplength=1000).pack(anchor="w", pady=(0, 8))

        bar = ttk.Frame(wrap)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Label(bar, text="Min size:").pack(side="left")
        self.dup_min_var = tk.StringVar(value="1 MB")
        ttk.Combobox(bar, textvariable=self.dup_min_var, width=10, state="readonly",
                     values=["100 KB", "1 MB", "10 MB", "100 MB"]).pack(side="left", padx=6)
        self.dup_btn = ttk.Button(bar, text="🔎 Find duplicates", style="Accent.TButton",
                                  command=self._start_dup_search)
        self.dup_btn.pack(side="left", padx=6)
        ttk.Button(bar, text="Select all but newest (per group)",
                   command=lambda: self._dup_autoselect("newest")).pack(side="left", padx=4)
        ttk.Button(bar, text="♻ Recycle selected",
                   command=self._dup_recycle_selected).pack(side="left", padx=4)
        self.dup_status = ttk.Label(bar, text="Scan a drive first.", style="Sub.TLabel")
        self.dup_status.pack(side="right")

        self.dup_tree = ttk.Treeview(wrap, columns=("check", "size", "waste", "path"),
                                     show="headings", height=18)
        self.dup_tree.heading("check", text="✓")
        self.dup_tree.heading("size", text="Size each")
        self.dup_tree.heading("waste", text="Group waste")
        self.dup_tree.heading("path", text="File (grouped by identical content)")
        self.dup_tree.column("check", width=40, anchor="center")
        self.dup_tree.column("size", width=110, anchor="e")
        self.dup_tree.column("waste", width=110, anchor="e")
        self.dup_tree.column("path", width=760, anchor="w")
        self.dup_tree.pack(side="left", fill="both", expand=True)
        dsb = ttk.Scrollbar(wrap, orient="vertical", command=self.dup_tree.yview)
        dsb.pack(side="right", fill="y")
        self.dup_tree.configure(yscrollcommand=dsb.set)
        self.dup_tree.bind("<Button-1>", self._dup_toggle)
        self.dup_tree.bind("<Double-1>", lambda _e: self._open_path(self._dup_focused()))
        self._dup_groups: list[DuplicateGroup] = []
        self._dup_checked: set[str] = set()

    def _dup_min_bytes(self) -> int:
        return {"100 KB": 100 * 1024, "1 MB": 1024 * 1024,
                "10 MB": 10 * 1024 * 1024, "100 MB": 100 * 1024 * 1024}.get(
                    self.dup_min_var.get(), 1024 * 1024)

    def _start_dup_search(self):
        if not self.result or not self.result.files:
            messagebox.showinfo("Duplicates", "Scan a drive or folder first.")
            return
        if hasattr(self, "_dup_worker") and self._dup_worker.is_alive():
            self._dup_cancel.set()
            self.dup_status.config(text="Stopping…")
            return
        self._dup_cancel = threading.Event()
        self._dup_groups = []
        self._dup_checked = set()
        self.dup_tree.delete(*self.dup_tree.get_children())
        self.dup_btn.config(text="⏹ Stop")
        self.dup_status.config(text="Grouping by size, then hashing…")
        self._dup_worker = start_duplicate_search(
            self.result.files, self.events, self._dup_cancel,
            min_size=self._dup_min_bytes())

    def _render_dup_groups(self):
        self.dup_tree.delete(*self.dup_tree.get_children())
        total_waste = sum(g.waste for g in self._dup_groups)
        n_files = sum(g.count for g in self._dup_groups)
        if not self._dup_groups:
            self.dup_status.config(text="No duplicates found — nice and tidy. 🎉")
            return
        self.dup_status.config(
            text=f"{len(self._dup_groups)} groups • {n_files} files • "
                 f"{format_bytes(total_waste)} reclaimable")
        for gi, g in enumerate(self._dup_groups):
            gid = f"group-{gi}"
            self.dup_tree.insert("", "end", iid=gid, values=(
                "", format_bytes(g.size), format_bytes(g.waste),
                f"━━ {g.count} identical files ({format_bytes(g.size)} each) ━━"),
                tags=("grouphdr",))
            for p in g.files:
                mark = "☑" if p in self._dup_checked else "☐"
                self.dup_tree.insert(gid, "end", values=(mark, format_bytes(g.size), "", p))
            self.dup_tree.item(gid, open=True)
        self.dup_tree.tag_configure("grouphdr", foreground="#1d4ed8")

    def _dup_toggle(self, event):
        row = self.dup_tree.identify_row(event.y)
        if not row or row.startswith("group-") or self.dup_tree.identify_column(event.x) != "#1":
            return
        vals = list(self.dup_tree.item(row, "values"))
        path = vals[3]
        if path in self._dup_checked:
            self._dup_checked.discard(path)
        else:
            self._dup_checked.add(path)
        vals[0] = "☑" if path in self._dup_checked else "☐"
        self.dup_tree.item(row, values=vals)

    def _dup_focused(self) -> str | None:
        sel = self.dup_tree.selection() or ((self.dup_tree.focus(),) if self.dup_tree.focus() else ())
        if not sel or sel[0].startswith("group-"):
            return None
        return self.dup_tree.item(sel[0], "values")[3]

    def _dup_autoselect(self, keep: str = "newest"):
        """Tick every copy except one keeper per group (newest by mtime)."""
        self._dup_checked = set()
        for g in self._dup_groups:
            try:
                ranked = sorted(g.files, key=lambda p: os.path.getmtime(p),
                                reverse=(keep == "newest"))
            except OSError:
                ranked = g.files
            for p in ranked[1:]:
                self._dup_checked.add(p)
        self._render_dup_groups()
        # re-apply checks (render clears them)
        for g in self._dup_groups:
            for p in g.files:
                if p in self._dup_checked:
                    for child in self.dup_tree.get_children(f"group-{self._dup_groups.index(g)}"):
                        vals = list(self.dup_tree.item(child, "values"))
                        if vals[3] == p:
                            vals[0] = "☑"
                            self.dup_tree.item(child, values=vals)

    def _dup_recycle_selected(self):
        chosen = [p for p in self._dup_checked if os.path.exists(p)]
        if not chosen:
            messagebox.showinfo("Duplicates", "Tick some files first (click the ✓ column).")
            return
        freed = sum(os.path.getsize(p) for p in chosen if os.path.isfile(p))
        if not messagebox.askyesno("Recycle duplicates",
                                    f"Move {len(chosen)} duplicate file(s) to the Recycle Bin?\n\n"
                                    f"This frees ≈ {format_bytes(freed)}.\n"
                                    "One copy of each group is kept (your unticked files)."):
            return
        ok, fail = 0, 0
        for p in chosen:
            if recycle_delete(p):
                ok += 1
            else:
                fail += 1
        messagebox.showinfo("Done", f"Recycled {ok} file(s)." + (f" {fail} failed." if fail else ""))
        self._dup_checked = set()
        if self.result:
            gone = set(chosen)
            self.result.files = [f for f in self.result.files if f.path not in gone]
            self._render_files()
        self._start_dup_search()  # re-run to refresh groups

    # -- cleanup tab ---------------------------------------------------------
    def _build_clean_tab(self):
        wrap = ttk.Frame(self.tab_clean, padding=12)
        wrap.pack(fill="both", expand=True)
        ttk.Label(wrap, text="Safe to delete — the app only suggests temp/cache-type files. "
                             "Tick items and press Clean. Everything goes to the Recycle Bin first.",
                  style="Sub.TLabel", wraplength=1000).pack(anchor="w", pady=(0, 8))

        btns = ttk.Frame(wrap)
        btns.pack(fill="x", pady=(0, 8))
        ttk.Button(btns, text="🧹 Clean selected", style="Accent.TButton",
                   command=self._clean_selected).pack(side="left")
        ttk.Button(btns, text="↻ Re-check", command=self._load_cleanup).pack(side="left", padx=8)
        self.clean_total = ttk.Label(btns, text="", style="Sub.TLabel")
        self.clean_total.pack(side="right")

        self.clean_tree = ttk.Treeview(wrap, columns=("check", "size", "safety", "detail"),
                                       show="headings", height=12)
        self.clean_tree.heading("check", text="✓")
        self.clean_tree.heading("size", text="Size")
        self.clean_tree.heading("safety", text="Safety")
        self.clean_tree.heading("detail", text="What is this?")
        self.clean_tree.column("check", width=40, anchor="center")
        self.clean_tree.column("size", width=110, anchor="e")
        self.clean_tree.column("safety", width=90, anchor="center")
        self.clean_tree.column("detail", width=750, anchor="w")
        self.clean_tree.pack(fill="both", expand=True)
        self.clean_tree.bind("<Button-1>", self._toggle_check)
        self._checked: set[str] = set()

        ttk.Label(wrap, text="Safety guide — what you should never delete by hand:",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 4))
        self.advice_box = tk.Text(wrap, height=6, font=("Segoe UI", 11), bg="#f8fafc",
                                  relief="flat", padx=8, pady=6)
        self.advice_box.pack(fill="x")
        for level, where, why in safety_advice():
            self.advice_box.insert("end", f"[{level}] {where} — {why}\n")
        self.advice_box.config(state="disabled")

    # ---------------------------------------------------------------- drives
    def _refresh_drives(self):
        self.drives = get_drives()
        values = [d.display for d in self.drives]
        self.drive_combo["values"] = values
        if values:
            # default to the system drive (usually C:)
            idx = next((i for i, d in enumerate(self.drives)
                        if os.path.normcase(d.letter).startswith("c:")), 0)
            self.drive_combo.current(idx)
            self._drive_selected()

    def _selected_drive(self):
        i = self.drive_combo.current()
        return self.drives[i] if 0 <= i < len(self.drives) else None

    def _drive_selected(self):
        self._draw_disk_bar()

    def _draw_disk_bar(self):
        c = self.disk_bar
        c.delete("all")
        d = self._selected_drive()
        if not d:
            return
        W = c.winfo_width() or 800
        pct = d.pct_used / 100.0
        c.create_rectangle(0, 0, W, 10, fill="#e2e8f0", outline="")
        color = "#dc2626" if pct > 0.9 else "#f59e0b" if pct > 0.75 else ACCENT
        c.create_rectangle(0, 0, W * pct, 10, fill=color, outline="")
        self.usage_label.config(
            text=f"{d.letter}  {format_bytes(d.used)} used  •  {format_bytes(d.free)} free  •  {d.pct_used:.0f}% full")

    # ---------------------------------------------------------------- scan
    def start_scan(self):
        if hasattr(self, "_scanner") and self._scanner.is_alive():
            return
        d = self._selected_drive()
        root = d.letter if d else "C:\\"
        self._begin_scan(root)

    def scan_custom_folder(self):
        folder = filedialog.askdirectory(title="Choose a folder to analyse")
        if folder:
            self._begin_scan(folder)

    def _begin_scan(self, root: str):
        self.cancel.clear()
        while not self.events.empty():
            self.events.get_nowait()
        self.result = None
        self._dup_groups = getattr(self, "_dup_groups", [])
        self._dup_groups = []
        self._dup_checked = set()
        if hasattr(self, "dup_tree"):
            self.dup_tree.delete(*self.dup_tree.get_children())
            self.dup_status.config(text="Scan finished — press “Find duplicates”.")
        self.scan_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.progress.start(12)
        self.status_label.config(text=f"Scanning {root} …")
        self._scanner_root = root
        self._scanner = start_scan(root, self.events, self.cancel)

    def stop_scan(self):
        self.cancel.set()
        self.status_label.config(text="Stopping…")

    def _poll_events(self):
        try:
            while True:
                ev = self.events.get_nowait()
                if ev["type"] == "progress":
                    cur = short_path(ev.get("current", ""), 70)
                    self.status_label.config(
                        text=f"Scanning… {ev['files']:,} files • {format_bytes(ev['bytes'])} • {cur}")
                elif ev["type"] == "done":
                    self._finish_scan(ev["result"])
                elif ev["type"] == "dup-progress":
                    if ev.get("stage") == "hashing":
                        self.dup_status.config(
                            text=f"Hashing… {ev.get('done', 0):,} / {ev.get('total', 0):,} files")
                    else:
                        self.dup_status.config(
                            text=f"{ev.get('groups', 0)} candidate groups by size — hashing…")
                elif ev["type"] == "dup-done":
                    self.dup_btn.config(text="🔎 Find duplicates")
                    if ev.get("cancelled"):
                        self.dup_status.config(text="Stopped.")
                    else:
                        self._dup_groups = ev.get("groups", [])
                        self._render_dup_groups()
        except queue.Empty:
            pass
        self.after(150, self._poll_events)

    def _finish_scan(self, result: ScanResult):
        self.result = result
        self.progress.stop()
        self.scan_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        tag = "(stopped)" if result.cancelled else f"in {result.elapsed:.1f}s"
        self.status_label.config(
            text=f"Done {tag}: {result.file_count:,} files • {format_bytes(result.total_size)} • "
                 f"{result.dir_count:,} folders" + (f" • {result.errors} denied" if result.errors else ""))
        self.map_info.config(text=f"{result.root} — {format_bytes(result.total_size)} in "
                                  f"{result.file_count:,} files {tag}")
        self._render_all()

    # ---------------------------------------------------------------- render
    def _render_all(self):
        if not self.result:
            return
        r = self.result
        # lookups for treemap drill-down: immediate children + direct files per folder
        self._dir_children = {}
        for p in r.dir_sizes:
            if os.path.normpath(p) == os.path.normpath(r.root):
                continue
            parent = os.path.normcase(os.path.normpath(os.path.dirname(p)))
            self._dir_children.setdefault(parent, []).append(p)
        self._files_by_dir = {}
        for f in r.files:  # already biggest-first, so per-folder lists stay biggest-first
            key = os.path.normcase(os.path.normpath(os.path.dirname(f.path)))
            bucket = self._files_by_dir.get(key)
            if bucket is None:
                self._files_by_dir[key] = [f]
            elif len(bucket) < 300:
                bucket.append(f)
        self._map_stack = []
        self._render_treemap()
        self._render_files()
        self._render_folders()
        self._render_types()
        self._render_age()
        self._load_cleanup()

    @staticmethod
    def _norm(p: str) -> str:
        return os.path.normcase(os.path.normpath(p))

    def _map_current(self) -> str:
        return self._map_stack[-1] if self._map_stack else (self.result.root if self.result else "")

    def _dir_block(self, path: str, size: int) -> dict:
        cat = (self.result.dir_topcat.get(path, "Other") if self.result else "Other")
        return {"label": path, "path": path, "size": size,
                "color": category_color(cat), "is_dir": True}

    def _file_block(self, f) -> dict:
        return {"label": f.path, "path": f.path, "size": f.size,
                "color": category_color(file_category(f.ext or f.path)),
                "is_dir": False}

    def _render_treemap(self):
        if not self.result:
            return
        r = self.result
        cur = self._map_current()
        if not self._map_stack:
            blocks = [self._dir_block(p, s) for p, s in r.top_dirs(120)]
            blocks += [self._file_block(f) for f in r.top_files(180)]
            blocks.sort(key=lambda d: d["size"], reverse=True)
            self.treemap.empty_message = (
                "Scan a drive to see its treemap.\nEach block = one folder or file, sized by disk usage.")
            self.map_crumb.config(text=r.root)
        else:
            kids = sorted(self._dir_children.get(self._norm(cur), []),
                          key=lambda p: r.dir_sizes.get(p, 0), reverse=True)[:150]
            blocks = [self._dir_block(p, r.dir_sizes.get(p, 0)) for p in kids]
            blocks += [self._file_block(f)
                       for f in self._files_by_dir.get(self._norm(cur), [])[:80]]
            blocks.sort(key=lambda d: d["size"], reverse=True)
            self.treemap.empty_message = f'"{os.path.basename(cur) or cur}" is empty.'
            trail = "  ▸  ".join(
                [r.root] + [os.path.basename(p.rstrip("\\/")) or p for p in self._map_stack])
            self.map_crumb.config(text=trail)
        self.treemap.set_data(blocks[:350])
        self.map_back_btn.config(state="normal" if self._map_stack else "disabled")

    def _map_go_back(self):
        if self._map_stack:
            self._map_stack.pop()
            self._render_treemap()

    def _map_go_top(self):
        if self._map_stack:
            self._map_stack = []
            self._render_treemap()

    def _render_folders(self):
        self.folder_tree.delete(*self.folder_tree.get_children())
        if not self.result:
            return
        r = self.result
        items = [(p, s) for p, s in r.dir_sizes.items()
                 if os.path.normpath(p) != os.path.normpath(r.root) and s > 0]
        items.sort(key=lambda kv: kv[1], reverse=True)
        items = items[:500]
        # shallowest first so parents exist before children; biggest first per level
        items.sort(key=lambda kv: (kv[0].count(os.sep), -kv[1] if self._folder_sort_rev else kv[1]))

        def norm(p: str) -> str:
            return os.path.normcase(os.path.normpath(p))

        iid_of: dict[str, str] = {}
        root_norm = norm(r.root)
        root_size = r.dir_sizes.get(r.root, r.total_size)
        root_iid = self.folder_tree.insert(
            "", "end", text=os.path.basename(r.root.rstrip("\\/")) or r.root, open=True,
            values=(format_bytes(root_size),
                    r.dir_topcat.get(r.root, "Other"), r.root))
        iid_of[root_norm] = root_iid
        for path, size in items:
            # nearest ancestor already in the tree (else hang off the root)
            parent_iid = root_iid
            probe = os.path.dirname(path)
            for _ in range(12):
                n = norm(probe)
                if n in iid_of:
                    parent_iid = iid_of[n]
                    break
                if n == root_norm:
                    break
                nxt = os.path.dirname(probe)
                if nxt == probe:
                    break
                probe = nxt
            iid = self.folder_tree.insert(
                parent_iid, "end", text=os.path.basename(path) or path, open=False,
                values=(format_bytes(size),
                        r.dir_topcat.get(path, "Other"), path))
            iid_of[norm(path)] = iid
        arrow = " ▼" if self._folder_sort_rev else " ▲"
        self.folder_tree.heading("size", text=f"Size{arrow}")

    def _toggle_folder_sort(self):
        self._folder_sort_rev = not self._folder_sort_rev
        self._render_folders()

    def _render_files(self):
        self.file_tree.delete(*self.file_tree.get_children())
        if not self.result:
            return
        q = self.filter_var.get().strip().lower()
        shown = 0
        for f in self.result.files:
            if q and q not in f.path.lower():
                continue
            self.file_tree.insert("", "end", values=(
                format_bytes(f.size), os.path.basename(f.path) or f.path,
                file_category(f.ext or f.path) + (f" ({f.ext})" if f.ext else ""),
                format_date(f.mtime), f.path))
            shown += 1
            if shown >= 2000:
                break
        total = len(self.result.files)
        self.files_count.config(text=f"showing {shown:,} of {total:,} files")

    def _sort_files(self, col: str):
        rev = not self._sort["rev"] if self._sort["col"] == col else (col == "size")
        self._sort = {"col": col, "rev": rev}
        if self.result:
            key = {"size": lambda f: f.size,
                   "name": lambda f: os.path.basename(f.path).lower(),
                   "type": lambda f: (f.ext or "").lower(),
                   "modified": lambda f: f.mtime,
                   "path": lambda f: f.path.lower()}[col]
            self.result.files.sort(key=key, reverse=rev)
            arrow = " ▼" if rev else " ▲"
            for cid, title in (("size", "Size"), ("name", "Name"), ("type", "Type"),
                               ("modified", "Modified"), ("path", "Location")):
                self.file_tree.heading(cid, text=title + (arrow if cid == col else ""))
            self._render_files()

    def _render_types(self):
        self.type_tree.delete(*self.type_tree.get_children())
        if not self.result:
            return
        self._type_stats = breakdown_by_type(self.result.files)
        total = self.result.total_size or 1
        for s in self._type_stats:
            self.type_tree.insert("", "end", text=s.category, values=(
                format_bytes(s.size), f"{s.count:,}", f"{s.size / total * 100:.1f}%"))
        self._draw_types()

    def _draw_types(self):
        c = self.type_canvas
        if c.winfo_width() < 50:  # tab hidden — wait for the debounced Configure
            return
        c.delete("all")
        stats = getattr(self, "_type_stats", [])
        if not stats:
            c.create_text(16, 16, anchor="nw", fill="#64748b",
                          text="Scan a drive to see the breakdown.")
            return
        W = c.winfo_width() or 900
        H = c.winfo_height() or 300
        total = sum(s.size for s in stats) or 1
        x = 16
        bar_w = W - 32
        # horizontal stacked bar
        for s in stats:
            w = bar_w * s.size / total
            if w < 1:
                continue
            c.create_rectangle(x, 20, x + w, 60, fill=category_color(s.category), outline="white", width=2)
            x += w
        # legend rows
        y = 90
        for s in stats[:10]:
            c.create_rectangle(16, y, 32, y + 14, fill=category_color(s.category), outline="")
            c.create_text(40, y, anchor="nw", fill="#0f172a",
                          font=("Segoe UI", 12, "bold"),
                          text=f"{s.category} — {format_bytes(s.size)}  ({s.size / total * 100:.1f}%, {s.count:,} files)")
            y += 26

    # ---------------------------------------------------------------- cleanup
    def _load_cleanup(self):
        self.clean_tree.delete(*self.clean_tree.get_children())
        self.cleanup_items = collect_cleanup(getattr(self, "_scanner_root", None))
        # refresh recycle bin size live
        for item in self.cleanup_items:
            if item.key == "recycle-bin":
                item.size = recycle_bin_size()
                item.detail = (f"{format_bytes(item.size)} sitting in the Recycle Bin. "
                               "Emptying reclaims it immediately.")
        self._checked = {i.key for i in self.cleanup_items if i.safety == "Safe" and i.size > 0}
        for item in self.cleanup_items:
            mark = "☑" if item.key in self._checked else "☐"
            self.clean_tree.insert("", "end", iid=item.key, values=(
                mark, format_bytes(item.size), item.safety,
                f"{item.title} — {item.detail}"))
            tag = f"sf-{item.safety}"
            self.clean_tree.tag_configure("sf-Safe", foreground="#16a34a")
            self.clean_tree.tag_configure("sf-Caution", foreground="#b45309")
            self.clean_tree.tag_configure("sf-Keep", foreground="#dc2626")
            self.clean_tree.item(item.key, tags=(tag,))
        total = sum(i.size for i in self.cleanup_items if i.key in self._checked)
        self.clean_total.config(text=f"Selected will free ≈ {format_bytes(total)}")

    def _toggle_check(self, event):
        row = self.clean_tree.identify_row(event.y)
        if not row or self.clean_tree.identify_column(event.x) != "#1":
            return
        if row in self._checked:
            self._checked.discard(row)
        else:
            item = next((i for i in self.cleanup_items if i.key == row), None)
            if item and item.safety != "Safe":
                if not messagebox.askyesno(
                        "Needs your judgement",
                        f"“{item.title}” is marked Caution.\n\n{item.detail}\n\n"
                        "Only tick this if you recognise these files. Continue?"):
                    return
            self._checked.add(row)
        mark = "☑" if row in self._checked else "☐"
        vals = list(self.clean_tree.item(row, "values"))
        vals[0] = mark
        self.clean_tree.item(row, values=vals)
        total = sum(i.size for i in self.cleanup_items if i.key in self._checked)
        self.clean_total.config(text=f"Selected will free ≈ {format_bytes(total)}")

    def _clean_selected(self):
        chosen = [i for i in self.cleanup_items if i.key in self._checked]
        if not chosen:
            messagebox.showinfo("Nothing selected", "Tick at least one item first.")
            return
        total = sum(i.size for i in chosen)
        if not messagebox.askyesno("Confirm cleanup",
                                    f"Clean {len(chosen)} item(s) and free ≈ {format_bytes(total)}?\n\n"
                                    "Files go to the Recycle Bin where possible, so you can undo."):
            return
        freed, failed = 0, 0
        for item in chosen:
            try:
                if item.kind == "recycle-bin":
                    ok, _msg = empty_recycle_bin()
                    if ok:
                        freed += item.size
                    else:
                        failed += 1
                elif item.kind == "folder-contents":
                    for folder in item.paths:
                        f, _n, fail = clear_folder_contents(folder, recycle=True)
                        freed += f
                        failed += fail
                else:  # individual files
                    for p in item.paths:
                        try:
                            freed += os.path.getsize(p) if os.path.isfile(p) else 0
                        except OSError:
                            pass
                        if not recycle_delete(p):
                            if not delete_permanent(p):
                                failed += 1
            except Exception:
                failed += 1
        messagebox.showinfo("Cleanup finished",
                            f"Freed ≈ {format_bytes(freed)}." +
                            (f" {failed} item(s) could not be removed (in use or access denied)."
                             if failed else ""))
        self._refresh_drives()
        self._load_cleanup()

    # ---------------------------------------------------------------- actions
    def _focused(self, tree: ttk.Treeview, col: int) -> str | None:
        sel = tree.selection()
        if not sel:
            focus = tree.focus()
            sel = (focus,) if focus else ()
        if not sel:
            return None
        vals = tree.item(sel[0], "values")
        return vals[col] if len(vals) > col else None

    def _treemap_selected(self, item: dict):
        self._selected_path = item.get("path")
        from utils import format_bytes as fb
        kind = "📁 Folder" if item.get("is_dir") else "📄 File"
        self.sel_label.config(
            text=f"{kind}: {item.get('path')}  •  {fb(item.get('size', 0))}")
        if item.get("is_dir") and item.get("path"):
            self._map_stack.append(item["path"])
            self._render_treemap()

    def _open_selected(self):
        if self._selected_path:
            self._open_path(self._selected_path)
        else:
            messagebox.showinfo("Treemap", "Click a block first to select a file or folder.")

    def _delete_selected(self):
        if self._selected_path:
            self._recycle(self._selected_path)
        else:
            messagebox.showinfo("Treemap", "Click a block first to select a file or folder.")

    def _open_path(self, path: str | None):
        if not path:
            return
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception as exc:
            messagebox.showerror("Cannot open", f"{path}\n\n{exc}")

    def _reveal(self, path: str | None):
        if not path:
            return
        try:
            target = path if os.path.isdir(path) else os.path.dirname(path)
            subprocess.Popen(["explorer", target])
        except Exception as exc:
            messagebox.showerror("Cannot open Explorer", str(exc))

    def _recycle(self, path: str | None):
        if not path or not os.path.exists(path):
            return
        from utils import is_protected
        if is_protected(path):
            if not messagebox.askyesno("⚠ Protected location",
                                        f"{path}\n\nThis is inside Windows or Program Files. "
                                        "Deleting here can break your PC.\n\nAre you REALLY sure?"):
                return
        else:
            if not messagebox.askyesno("Move to Recycle Bin",
                                        f"Move this to the Recycle Bin?\n\n{path}"):
                return
        if recycle_delete(path):
            messagebox.showinfo("Done", "Moved to the Recycle Bin.")
            self._remove_path_from_results(path)
        else:
            messagebox.showerror("Failed", "Could not delete. The file may be in use or you may need admin rights.")

    def _remove_path_from_results(self, path: str):
        if self.result:
            self.result.files = [f for f in self.result.files
                                 if not (f.path == path or f.path.startswith(path + os.sep))]
            self._render_all()
