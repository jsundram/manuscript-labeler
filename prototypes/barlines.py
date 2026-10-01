# /// script
# dependencies = ["pillow", "numpy"]
# ///
"""barlines.py PAGE.png CENTER_Y [CENTER_Y ...]: x positions of bar lines per system."""
import sys
import numpy as np
from PIL import Image
L = np.asarray(Image.open(sys.argv[1]).convert('L')).astype(float)
for c in map(int, sys.argv[2:]):
    band = L[c-120:c+120, :]
    dark = (band < 175).mean(axis=1)
    idx = np.argsort(dark)[::-1]; pk = []
    for i in idx:
        if all(abs(i - p) > 12 for p in pk): pk.append(i)
        if len(pk) == 5: break
    top, bot = min(pk) + c - 120, max(pk) + c - 120
    seg = L[top:bot+1, :] < 110
    cover = seg.mean(axis=0)
    # also require little ink just outside the staff (stems of notes extend; barlines don't much)
    xs = np.where(cover > 0.85)[0]
    groups = []
    for x in xs:
        if groups and x - groups[-1][-1] <= 6: groups[-1].append(x)
        else: groups.append([x])
    cols = [int(np.mean(g)) for g in groups if len(g) <= 14]
    print(c, f"staff {top}-{bot}", len(cols), cols)
