"""Build DiskSpaceVisualizer-Presentation.pptx from the real app screenshots."""
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE
import os
import tempfile

NAVY = RGBColor(0x0F, 0x17, 0x2A)
ACCENT = RGBColor(0x25, 0x63, 0xEB)
SLATE = RGBColor(0x33, 0x44, 0x55)
MUTED = RGBColor(0x64, 0x74, 0x8B)
LIGHT = RGBColor(0xF1, 0xF5, 0xF9)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GREEN = RGBColor(0x16, 0xA3, 0x4A)
AMBER = RGBColor(0xD9, 0x77, 0x06)
RED = RGBColor(0xDC, 0x26, 0x26)

SHOTS = os.path.join(tempfile.gettempdir(), "dsv_shots")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "DiskSpaceVisualizer-Presentation.pptx")
ICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.png")

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]
FONT = "Segoe UI"


def bg(slide, color):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def textbox(slide, l, t, w, h):
    return slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))


def para(tf, text, size=14, bold=False, color=SLATE, align=None, space_after=Pt(6)):
    p = tf.add_paragraph() if tf.paragraphs else tf.paragraphs[0]
    if tf.paragraphs and not tf.paragraphs[0].text and len(tf.paragraphs) == 1 and not text == "":
        pass
    p.text = ""
    run = p.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = FONT
    if align is not None:
        p.alignment = align
    p.space_after = space_after
    return p


def add_text(slide, l, t, w, h, lines, align=None):
    """lines: [(text, size, bold, color)] — first uses the default paragraph."""
    tb = textbox(slide, l, t, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    first = True
    for text, size, bold, color in lines:
        if first:
            p = tf.paragraphs[0]
            p.text = ""
            run = p.add_run()
            run.text = text
            run.font.size = Pt(size)
            run.font.bold = bold
            run.font.color.rgb = color
            run.font.name = FONT
            if align is not None:
                p.alignment = align
            first = False
        else:
            para(tf, text, size, bold, color, align)
    return tb


def band(slide, title, subtitle):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.5), Inches(0.25),
                                   Inches(12.33), Inches(0.8))
    shape.fill.solid()
    shape.fill.fore_color.rgb = NAVY
    shape.line.fill.background()
    add_text(slide, 0.8, 0.28, 11.8, 0.75,
             [(f"{title}   ", 22, True, WHITE)], align=PP_ALIGN.LEFT)
    add_text(slide, 0.8, 0.62, 11.8, 0.4, [(subtitle, 12, False, RGBColor(0x94, 0xA3, 0xB8))])


def footer(slide, text):
    add_text(slide, 0.5, 7.05, 12.33, 0.3, [(text, 10, False, MUTED)])


def shot_slide(title, subtitle, shotfile, bullets, foot):
    slide = prs.slides.add_slide(BLANK)
    bg(slide, WHITE)
    band(slide, title, subtitle)
    frame = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.47), Inches(1.22),
                                   Inches(8.42), Inches(5.56))
    frame.fill.solid()
    frame.fill.fore_color.rgb = RGBColor(0xE2, 0xE8, 0xF0)
    frame.line.fill.background()
    slide.shapes.add_picture(os.path.join(SHOTS, shotfile),
                             Inches(0.5), Inches(1.25), width=Inches(8.36))
    tb = textbox(slide, 9.15, 1.25, 3.65, 5.4)
    tf = tb.text_frame
    tf.word_wrap = True
    for i, b in enumerate(bullets):
        if i == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()
        p.text = ""
        r = p.add_run()
        r.text = "▸  " + b
        r.font.size = Pt(14)
        r.font.color.rgb = SLATE
        r.font.name = FONT
        p.space_after = Pt(14)
    footer(slide, foot)
    return slide


# ---------------------------------------------------------------- 1. title
s = prs.slides.add_slide(BLANK)
bg(s, NAVY)
s.shapes.add_picture(ICON, Inches(0.9), Inches(1.7), width=Inches(2.2))
add_text(s, 3.5, 1.5, 9.2, 1.4, [("Disk Space Visualizer", 44, True, WHITE)])
add_text(s, 3.5, 2.75, 9.2, 0.8,
         [("See what's eating your drive — and clean it safely.", 20, False, RGBColor(0x94, 0xA3, 0xB8))])
add_text(s, 3.5, 3.9, 9.2, 2.2, [
    ("▸  Windows storage analyzer — visual, honest, free", 16, False, WHITE),
    ("▸  Python + Tkinter • zero runtime dependencies • 100% offline", 16, False, WHITE),
    ("▸  Treemap • Largest files • Types • Age • Duplicates • Cleanup", 16, False, WHITE),
])
bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(7.1), Inches(13.333), Inches(0.4))
bar.fill.solid()
bar.fill.fore_color.rgb = ACCENT
bar.line.fill.background()
add_text(s, 0.9, 6.3, 11.5, 0.5, [("v1.2.0   •   single-file exe or run from source", 13, False, MUTED)])

# ------------------------------------------------------- 2. problem/solution
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
band(s, "The problem", "Disks fill up silently — built-in tools don't show you what matters")
add_text(s, 0.9, 1.6, 11.5, 2.0, [
    ("“My disk is full — but WHERE did 100 GB go?”", 22, True, NAVY),
    ("Explorer shows file sizes one folder at a time — no big picture.", 15, False, SLATE),
    ("Settings → Storage is vague — no biggest-files list, no cleanup guidance.", 15, False, SLATE),
    ("Deleting the wrong thing breaks Windows — people are (rightly) afraid to clean.", 15, False, SLATE),
])
sol = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.5), Inches(4.6),
                         Inches(12.33), Inches(1.15))
sol.fill.solid()
sol.fill.fore_color.rgb = ACCENT
sol.line.fill.background()
add_text(s, 0.9, 4.75, 11.5, 0.9, [
    ("Solution: one scan → a picture of your disk, the biggest offenders ranked, "
     "and a safe-to-delete list that only touches regenerable files.", 16, True, WHITE)])
footer(s, "Disk Space Visualizer 1.2.0 • why it exists")

# ------------------------------------------------------- 3. tour
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
band(s, "One scan, six views", "Every tab below is a live screenshot of the real app")
tours = [
    ("1  Treemap", "Bigger block = more space. Color = what's inside. Click to dive in."),
    ("2  Largest Files & Folders", "Expandable folder tree + sortable top-files table with search."),
    ("3  File Types", "Where is it all going? Video vs photos vs docs at a glance."),
    ("4  Age", "Green = fresh, red = forgotten. Stale files are the safest to reclaim."),
    ("5  Duplicates", "Byte-identical copies grouped with a reclaimable-waste total."),
    ("6  Cleanup", "Safe-to-delete list with Safety badges — Temp, caches, Recycle Bin."),
]
for i, (t, d) in enumerate(tours):
    row, col = divmod(i, 2)
    card = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.5 + col * 6.3),
                              Inches(1.45 + row * 1.85), Inches(6.03), Inches(1.6))
    card.fill.solid()
    card.fill.fore_color.rgb = LIGHT
    card.line.fill.background()
    add_text(s, 0.8 + col * 6.3, 1.6 + row * 1.85, 5.6, 1.35, [(t, 17, True, NAVY), (d, 13, False, SLATE)])
footer(s, "Disk Space Visualizer 1.2.0 • tour")

# ------------------------------------------------------- 4-9. tab slides
shot_slide("🗺  Treemap", "The big picture — dive from drive to folder to file",
           "shot_treemap.png", [
               "Bigger block = more space. Color = what's inside (folders take their dominant type).",
               "Click any folder block to zoom in — subfolders + biggest files, with breadcrumb + ← Back.",
               "Hover any block for path + size; Open or Recycle it right from the treemap.",
           ], "Disk Space Visualizer 1.2.0 • Treemap")
shot_slide("📂  Largest Files & Folders", "The ranked offenders — nothing hides",
           "shot_files.png", [
               "Expandable folder tree (▸) with per-folder size + “Mostly” content type.",
               "Top-files table: sortable columns, filter-as-you-type search.",
               "Double-click to open; right-click any row → Open, Reveal, Recycle.",
           ], "Disk Space Visualizer 1.2.0 • Largest Files & Folders")
shot_slide("🥧  File Types", "What KIND of data owns your disk?",
           "shot_types.png", [
               "Stacked bar + table: Video, Images, Audio, Documents, Archives, more.",
               "Answers “is it my movies or my photos?” in one glance.",
               "Computed from the same single scan — no re-walk.",
           ], "Disk Space Visualizer 1.2.0 • File Types")
shot_slide("⏳  Age", "Forgotten files are the safest to delete",
           "shot_age.png", [
               "Heatmap buckets: 30 days → 2+ years (green fresh, red forgotten).",
               "Threshold picker (6 mo / 1 yr / 2 yrs) lists biggest stale files first.",
               "Size + “untouched for” + date on every row.",
           ], "Disk Space Visualizer 1.2.0 • Age heatmap")
shot_slide("👯  Duplicates", "Same bytes, twice the rent",
           "shot_duplicates.png", [
               "Size → partial-MD5 → full-MD5: fast, and never flags lookalikes.",
               "Groups show per-file size + total reclaimable waste (here: 10 MB).",
               "“Keep newest” auto-select, then Recycle — one copy always survives.",
           ], "Disk Space Visualizer 1.2.0 • Duplicates")
shot_slide("🧹  Cleanup", "Safe to delete — with training wheels",
           "shot_cleanup.png", [
               "Only temp/cache-type locations suggested: Temps, Update cache, browser caches, Bin.",
               "Safety badges on every row — Caution items ask twice before ticking.",
               "Everything goes to the Recycle Bin first. Undoable by design.",
           ], "Disk Space Visualizer 1.2.0 • Cleanup")

# ------------------------------------------------------- 10. safety
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
band(s, "Safety model", "The app is opinionated about what you may delete")
rows = [
    ("🟢  Safe", "Temp files, caches, thumbnail cache, Recycle Bin", "Always fine — the OS and apps regenerate these.", GREEN),
    ("🟡  Caution", "Large files in Downloads, old installers", "Tick only files you recognise — the app asks again.", AMBER),
    ("🔴  Keep", "Windows, Program Files, your documents", "Never auto-touched — listed only as guidance.", RED),
]
for i, (lvl, what, why, color) in enumerate(rows):
    y = 1.6 + i * 1.7
    card = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.5), Inches(y),
                              Inches(12.33), Inches(1.45))
    card.fill.solid()
    card.fill.fore_color.rgb = LIGHT
    card.line.fill.background()
    stripe = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.5), Inches(y),
                                Inches(0.14), Inches(1.45))
    stripe.fill.solid()
    stripe.fill.fore_color.rgb = color
    stripe.line.fill.background()
    add_text(s, 0.95, y + 0.12, 11.6, 1.2, [(lvl, 18, True, NAVY), (f"{what}  —  {why}", 14, False, SLATE)])
add_text(s, 0.5, 6.75, 12.33, 0.4,
         [("Protected paths (Windows, Program Files) trigger an extra “are you REALLY sure?” warning.", 13, False, MUTED)])
footer(s, "Disk Space Visualizer 1.2.0 • safety")

# ------------------------------------------------------- 11. architecture
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
band(s, "Under the hood", "One background scan feeds all six views")
flow = [("Scanner", "os.scandir\nbackground thread"), ("Result", "sizes + top types\n+ age + hashes"),
        ("UI", "6 tabs\ninstant switching")]
for i, (t, d) in enumerate(flow):
    x = 0.5 + i * 4.15
    box = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(1.7),
                             Inches(3.5), Inches(1.9))
    box.fill.solid()
    box.fill.fore_color.rgb = NAVY
    box.line.fill.background()
    add_text(s, x + 0.2, 1.95, 3.1, 1.4, [(t, 20, True, WHITE), (d, 13, False, RGBColor(0x94, 0xA3, 0xB8))],
             align=PP_ALIGN.CENTER)
    if i < 2:
        add_text(s, x + 3.55, 2.35, 0.55, 0.6, [("▶", 26, True, ACCENT)], align=PP_ALIGN.CENTER)
add_text(s, 0.9, 4.1, 11.5, 2.6, [
    ("▸  Python + Tkinter only — zero runtime dependencies, works offline, ~12 MB exe.", 15, False, SLATE),
    ("▸  Junction-safe walk, bottom-up folder rollup; UI never freezes (progress queue + cancel).", 15, False, SLATE),
    ("▸  Deletes go through SHFileOperationW (Recycle Bin, undoable); empty-bin via SHEmptyRecycleBinW.", 15, False, SLATE),
    ("▸  Dev loop: dev.bat live-reloads on save • release via PyInstaller • Setup via Inno Setup.", 15, False, SLATE),
])
footer(s, "Disk Space Visualizer 1.2.0 • architecture")

# ------------------------------------------------------- 12. get it
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
band(s, "Get it", "Portable, installable, or from source — your choice")
table_shape = s.shapes.add_table(5, 3, Inches(0.5), Inches(1.6), Inches(12.33), Inches(4.4))
table = table_shape.table
table.columns[0].width = Inches(3.3)
table.columns[1].width = Inches(5.0)
table.columns[2].width = Inches(4.03)
heads = ["Method", "How", "Best for"]
data = [
    ("Run from source", "python main.py  (needs Python 3.10+)", "Trying it / contributing"),
    ("Live preview", "dev.bat — auto-restarts on every save", "UI iteration & demos"),
    ("Portable exe", "build_exe.bat → dist\\DiskSpaceVisualizer.exe", "Sharing / USB stick"),
    ("Install", "install.bat (no admin) or Setup exe via Inno", "Daily-driver PCs"),
]
for j, h in enumerate(heads):
    cell = table.cell(0, j)
    cell.text = ""
    r = cell.text_frame.paragraphs[0].add_run()
    r.text = h
    r.font.size = Pt(15)
    r.font.bold = True
    r.font.color.rgb = WHITE
    r.font.name = FONT
    cell.fill.solid()
    cell.fill.fore_color.rgb = NAVY
for i, row in enumerate(data):
    for j, val in enumerate(row):
        cell = table.cell(i + 1, j)
        cell.text = ""
        r = cell.text_frame.paragraphs[0].add_run()
        r.text = val
        r.font.size = Pt(13)
        r.font.color.rgb = SLATE
        r.font.name = FONT
        cell.fill.solid()
        cell.fill.fore_color.rgb = LIGHT if i % 2 == 0 else WHITE
footer(s, "Disk Space Visualizer 1.2.0 • distribution")

# ------------------------------------------------------- 13. thanks
s = prs.slides.add_slide(BLANK)
bg(s, NAVY)
s.shapes.add_picture(ICON, Inches(5.9), Inches(0.9), width=Inches(1.5))
add_text(s, 1.5, 2.6, 10.33, 1.0, [("Thank you!", 40, True, WHITE)], align=PP_ALIGN.CENTER)
add_text(s, 2.5, 3.7, 8.33, 2.0, [
    ("Roadmap: scheduled auto-clean  •  HTML storage reports  •  duplicate auto-purge rules", 15, False,
     RGBColor(0x94, 0xA3, 0xB8)),
    ("MIT — do what you like. When in doubt, back up first.", 15, False, RGBColor(0x94, 0xA3, 0xB8)),
], align=PP_ALIGN.CENTER)
bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(7.1), Inches(13.333), Inches(0.4))
bar.fill.solid()
bar.fill.fore_color.rgb = ACCENT
bar.line.fill.background()

prs.save(OUT)
print(f"saved {OUT} ({os.path.getsize(OUT)} bytes, {len(prs.slides.__iter__.__self__._sldIdLst)} slides)")
