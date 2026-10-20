# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "verovio==6.3.0", "resvg-py==0.5.0", "opencv-python-headless==4.10.0.84", "numpy", "lxml", "pillow",
#   "linearized-musicxml==1.0.0",
# ]
# ///
"""A contact sheet to judge copyist.py by eye: each real staff (SOURCE/STAFF in
a dataset folder) above two drawings of its music at its length, in the hand
named; or, for an LMX file, drawings in each hand.

    uv run experiments/synth/sheet.py OUT.png D-B_KHM-602/p2s3:berlin F-Po_RES-507-17/p10s3:parisB some.lmx
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import copyist  # noqa: E402

H, W = 110, 1800


def fit(img):
    img = cv2.resize(img, None, fx=H / img.shape[0], fy=H / img.shape[0], interpolation=cv2.INTER_AREA)[:, :W]
    return np.hstack([img, np.full((H, W - img.shape[1]), 255, np.uint8)])


def label(img, text):
    cv2.putText(img, text, (W - 220, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, 0, 1, cv2.LINE_AA)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("items", nargs="+", help="SOURCE/STAFF:HAND (a real staff) or an .lmx file")
    ap.add_argument("--data", type=Path, default=copyist.DATA)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    gap, rule = np.full((4, W), 255, np.uint8), np.full((14, W), 200, np.uint8)
    rows = []
    for item in a.items:
        if item.endswith(".lmx"):
            lmx = Path(item).read_text()
            for k, hand in enumerate(sorted(copyist.HANDS)):
                rows += [label(fit(copyist.draw(lmx, hand, seed=a.seed + k)), hand), gap]
        else:
            key, _, hand = item.partition(":")
            real = cv2.imread(str(a.data / f"{key}.jpg"), cv2.IMREAD_GRAYSCALE)
            lmx = (a.data / f"{key}.lmx").read_text()
            width = real.shape[1] / real.shape[0] * 9 - 2
            rows += [label(fit(real), key), gap]
            for k in range(2):
                rows += [label(fit(copyist.draw(lmx, hand or "generic", seed=a.seed + k, width=width)), hand), gap]
        rows.append(rule)
    cv2.imwrite(a.out, np.vstack(rows))
    print(a.out)


if __name__ == "__main__":
    main()
