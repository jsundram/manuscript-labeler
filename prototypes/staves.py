# /// script
# dependencies = ["pillow", "numpy"]
# ///
import sys
from PIL import Image
import numpy as np
for path in sys.argv[1:]:
    im = np.asarray(Image.open(path).convert('L')).astype(float)
    h, w = im.shape
    band = im[:, int(w*0.25):int(w*0.75)]
    dark = (band < 150).mean(axis=1)
    rows = np.where(dark > 0.30)[0]
    groups = []
    for r in rows:
        if groups and r - groups[-1][-1] <= 25: groups[-1].append(r)
        else: groups.append([r])
    print(path.split('/')[-1], [(g[0], g[-1]) for g in groups if g[-1]-g[0] > 25])
