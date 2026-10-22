# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow", "scipy"]
# ///
"""BA 2676's page scans, cleaned for print OMR: the scanner's black surround
(everything dark that touches the image's edge) made white, the image
cropped to the paper. Audiveris stalls on the uncleaned scans (its BEAMS and
HEADS steps run past any timeout on the black blobs).

    uv run experiments/print-omr/clean_pages.py

Reads ~/Data/manuscript-labeler/experiments/print-omr/pages/<part>/p-NN.png
(pdftoppm -r 300 -gray -png -f 2), writes clean/<part>/p-NN.png beside it.
"""

from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path.home() / "Data/manuscript-labeler/experiments/print-omr"


def clean(g: np.ndarray) -> np.ndarray:
    dark = g < 128
    lab, n = ndimage.label(dark)
    edge = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    edge = edge[edge > 0]
    out = g.copy()
    out[np.isin(lab, edge)] = 255
    # crop to the paper: rows and columns that were not surround
    sur = np.isin(lab, edge)
    rows = np.where(sur.mean(axis=1) < 0.5)[0]
    cols = np.where(sur.mean(axis=0) < 0.5)[0]
    if len(rows) and len(cols):
        out = out[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
    return out


def main():
    for f in sorted((ROOT / "pages").glob("*/p-*.png")):
        dest = ROOT / "clean" / f.parent.name / f.name
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        g = np.asarray(Image.open(f).convert("L"))
        Image.fromarray(clean(g)).save(dest)
    print("cleaned", len(list((ROOT / "clean").glob("*/p-*.png"))), "pages")


if __name__ == "__main__":
    main()
