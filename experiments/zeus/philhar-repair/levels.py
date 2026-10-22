# /// script
# dependencies = ["numpy", "pillow"]
# ///
"""A microfilm's grey paper to white: each page rendered at 2800 px and mapped through levels
(black at LO, white at HI), saved as a PDF of images."""
import subprocess, sys, tempfile
from pathlib import Path
import numpy as np
from PIL import Image
src, dest, lo, hi = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
n = int(next(l for l in subprocess.run(["pdfinfo", src], capture_output=True, text=True).stdout.splitlines()
             if l.startswith("Pages:")).split()[1])
pages = []
with tempfile.TemporaryDirectory() as tmp:
    for k in range(1, n + 1):
        out = f"{tmp}/p{k}"
        subprocess.run(["pdftoppm", "-f", str(k), "-l", str(k), "-scale-to", "2800", "-gray", "-png", "-singlefile", src, out], check=True)
        g = np.asarray(Image.open(out + ".png").convert("L")).astype(np.float32)
        pages.append(Image.fromarray(np.clip((g - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8)))
pages[0].save(dest, save_all=True, append_images=pages[1:], resolution=300)
print("wrote", dest, n, "pages")
