# /// script
# dependencies = ["pillow", "numpy"]
# ///
"""zoom.py PAGE.png CENTER_Y X0 X1 OUT.png [scale]
Crop a staff region and label alto-clef pitches at each line/space."""
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

page, cy, x0, x1, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
scale = float(sys.argv[6]) if len(sys.argv) > 6 else 2.5
im = Image.open(page).convert('RGB')
g = np.asarray(im.convert('L')).astype(float)
# find the 5 staff lines near cy inside [x0,x1]
y0, y1 = cy - 120, cy + 120
band = g[y0:y1, x0:x1]
dark = (band < 160).mean(axis=1)
# smooth and pick 5 peaks with min separation
idx = np.argsort(dark)[::-1]
peaks = []
for i in idx:
    if all(abs(i - p) > 12 for p in peaks):
        peaks.append(i)
    if len(peaks) == 5:
        break
peaks = sorted(p + y0 for p in peaks)
gap = np.median(np.diff(peaks))
top, bot = int(peaks[0] - 3.2 * gap), int(peaks[-1] + 3.2 * gap)
crop = im.crop((x0, top, x1, bot))
crop = crop.resize((int(crop.width * scale), int(crop.height * scale)), Image.LANCZOS)
W = crop.width + 140
canvas = Image.new('RGB', (W, crop.height), 'white')
canvas.paste(crop, (70, 0))
d = ImageDraw.Draw(canvas)
try:
    font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf', 20)
except Exception:
    font = ImageFont.load_default()
# alto clef: lines bottom->top F3 A3 C4 E4 G4
names = ['C3', 'D3', 'E3', 'F3', 'G3', 'A3', 'B3', 'C4', 'D4', 'E4', 'F4', 'G4', 'A4', 'B4', 'C5', 'D5']
base = peaks[-1]  # F3 line
for k, n in enumerate(names):
    step = k - 3  # F3 is index 3
    y = (base - step * gap / 2 - top) * scale
    if 0 < y < crop.height:
        is_line = step % 2 == 0
        col = (200, 0, 0) if is_line else (0, 90, 200)
        d.text((4, y - 11), n, fill=col, font=font)
        d.text((W - 62, y - 11), n, fill=col, font=font)
        if not is_line:
            for xx in range(70, W - 70, 14):
                d.line([(xx, y), (xx + 5, y)], fill=(0, 120, 255), width=1)
# x ruler every 50 source px
for sx in range(x0 - x0 % 50 + 50, x1, 50):
    xx = 70 + (sx - x0) * scale
    d.line([(xx, crop.height - 18), (xx, crop.height)], fill=(0, 150, 0), width=2)
    d.text((xx + 2, crop.height - 22), str(sx), fill=(0, 150, 0), font=font)
canvas.save(out)
print(out, 'lines at', peaks, 'gap', gap)
