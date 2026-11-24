"""Rebuild app.ico from app.png (the canonical icon source).

app.png may be any Pillow-readable format (it was originally a WebP with a
.png extension). This script normalises app.png to genuine PNG data and writes
a multi-size app.ico (256/48/32/16) for the window + exe.

Requires Pillow — build-time only (`pip install Pillow`); the app itself
remains standard-library-only.
"""
from PIL import Image

SRC = "app.png"
DST = "app.ico"
SIZES = [(256, 256), (48, 48), (32, 32), (16, 16)]

img = Image.open(SRC)
print(f"source: format={img.format} size={img.size} mode={img.mode}")
img = img.convert("RGBA")

# normalise app.png to real PNG bytes so Tk PhotoImage can read it
img.save(SRC, "PNG")
print(f"normalised {SRC} to genuine PNG")

img.save(DST, sizes=SIZES)
print(f"wrote {DST} with sizes {SIZES}")
