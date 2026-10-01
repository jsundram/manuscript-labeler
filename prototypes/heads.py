# /// script
# dependencies = ["pillow", "numpy", "scipy"]
# ///
"""heads.py PAGE.png CENTER_Y X0 X1 [OUT.png]
Find note-head-like ink blobs and report alto-clef pitch for each."""
import sys
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

page, cy, x0, x1 = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
out = sys.argv[5] if len(sys.argv) > 5 else None
im = Image.open(page).convert('RGB')
a = np.asarray(im).astype(float)
L = a.mean(axis=2)
y0, y1 = cy - 160, cy + 160
# staff lines: brownish rows; detect per local column window for tilt
def lines_at(xa, xb):
    band = L[cy-120:cy+120, xa:xb]
    dark = (band < 175).mean(axis=1)
    idx = np.argsort(dark)[::-1]; pk = []
    for i in idx:
        if all(abs(i - p) > 12 for p in pk): pk.append(i)
        if len(pk) == 5: break
    return sorted(p + cy - 120 for p in pk)
ink = (L[y0:y1, x0:x1] < 95)
er = ndi.binary_opening(ink, structure=np.ones((9, 9)))
lab, n = ndi.label(er)
names = ['A2','B2','C3','D3','E3','F3','G3','A3','B3','C4','D4','E4','F4','G4','A4','B4','C5','D5','E5']
res = []
for i in range(1, n + 1):
    ys, xs = np.where(lab == i)
    if len(ys) < 60: continue
    h, w = ys.max() - ys.min() + 1, xs.max() - xs.min() + 1
    if h > 45 or w > 70: continue   # beams / clumps
    cx, cyy = xs.mean() + x0, ys.mean() + y0
    ln = lines_at(max(0, int(cx) - 60), int(cx) + 60)
    gap = np.median(np.diff(ln)); f3 = ln[-1]
    step = round((f3 - cyy) / (gap / 2))
    name = names[step + 5] if 0 <= step + 5 < len(names) else '?'
    res.append((cx, cyy, name, (f3 - cyy) / (gap / 2) - step))
for cx, cyy, name, err in sorted(res):
    print(f"x={cx:6.0f} y={cyy:6.0f} {name:3s} off={err:+.2f}")
if out:
    crop = im.crop((x0, y0, x1, y1)).resize(((x1-x0)*2, (y1-y0)*2))
    d = ImageDraw.Draw(crop)
    for cx, cyy, name, err in res:
        X, Y = (cx - x0) * 2, (cyy - y0) * 2
        d.ellipse([X-6, Y-6, X+6, Y+6], outline=(255, 0, 0), width=2)
        d.text((X + 8, Y - 30), name, fill=(220, 0, 0))
    crop.save(out)
