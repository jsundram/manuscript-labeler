# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow", "numpy"]
# ///
"""Figures for README.md: the pointer's places (run ptrA1) drawn on staves beside the places it was scored against.

    uv run reports/2026-10-19-pointer/figures.py [POS_DIR]   # default ~/Data/manuscript-labeler/experiments/pos

POS_DIR holds pos_data.py's test staves (real603/, test-copyist/, dolores-test/) and runs/ptrA1/predictions-*.json.
Writes berlin.jpg, misses.jpg and dolores.jpg beside this script.

Marks: a ring is the place scored against (the classical map on Berlin, the engraving on rendered staves, the
polygon's centre on Dolores); a dot is the pointer's. A line joins the two when they are more than half a space apart.
Bar lines: a thin line full height is the labels' (or the engraving's); a short tick top and bottom is the pointer's.
Notes red, rests green, bar lines blue.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

POS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "Data/manuscript-labeler/experiments/pos"
OUT = Path(__file__).resolve().parent
COL = {"note": (220, 30, 30), "grace": (220, 30, 30), "rest": (0, 150, 60), "rest_x": (0, 150, 60),
       "barline": (20, 90, 230)}
FONT = ImageFont.load_default(size=20)


def load(kind_dir: str, name: str, run: str = "ptrA1"):
    p = json.loads((POS / kind_dir / f"{name}.pos.json").read_text())
    img = Image.open(POS / kind_dir / f"{name}.jpg").convert("L")
    pred = {}
    f = POS / "runs" / run / f"predictions-{kind_dir}.json"
    if f.exists():
        pred = {t[0]: t for t in json.loads(f.read_text()).get(f"{kind_dir}/{name}", {}).get("points", [])}
    return img, p, pred


def draw(kind_dir: str, name: str, x0: float | None = None, x1: float | None = None, label: bool = True, k: int = 2):
    """The staff from x0 to x1 (image pixels), scaled by k, with its targets and the pointer's places."""
    K = k
    img, p, pred = load(kind_dir, name)
    w, h = img.size
    x0 = 0 if x0 is None else max(0, int(x0))
    x1 = w if x1 is None else min(w, int(x1))
    im = img.crop((x0, 0, x1, h)).resize(((x1 - x0) * K, h * K), Image.LANCZOS).convert("RGB")
    im = Image.blend(im, Image.new("RGB", im.size, "white"), 0.25)  # lighten the ink so the marks read
    d = ImageDraw.Draw(im)
    ss = p["ss"] * K
    r = max(6, 0.4 * ss)

    def at(x, y):
        return (x - x0) * K, y * K

    for tok, kind, tx, ty in p["targets"]:
        c = COL[kind]
        X, Y = at(tx, ty)
        if kind == "barline":
            d.line([(X, 0), (X, h * K)], fill=c, width=2)
        elif kind == "rest_x":
            d.line([(X, Y - 1.5 * ss), (X, Y + 1.5 * ss)], fill=c, width=2)
        else:
            d.ellipse([X - r, Y - r, X + r, Y + r], outline=c, width=3)
        if tok not in pred:
            continue
        _, _, _, _, px, py = pred[tok]
        PX, PY = at(px, py)
        if kind == "barline":
            d.line([(PX, 0), (PX, 0.12 * h * K)], fill=c, width=5)
            d.line([(PX, 0.88 * h * K), (PX, h * K)], fill=c, width=5)
            off = abs(px - tx) / p["ss"]
        elif kind == "rest_x":
            d.ellipse([PX - 5, Y - 5, PX + 5, Y + 5], fill=c)
            off = abs(px - tx) / p["ss"]
            PY = Y
        else:
            d.ellipse([PX - 5, PY - 5, PX + 5, PY + 5], fill=c)
            off = math.hypot(px - tx, py - ty) / p["ss"]
        if off > 0.5:
            d.line([(X, Y if kind != "barline" else h * K / 2), (PX, PY if kind != "barline" else h * K / 2)],
                   fill=(0, 0, 0), width=2)
    if label:
        d.rectangle([0, 0, 8 + 11 * len(name), 26], fill="white")
        d.text((4, 2), name.replace("D-B_", ""), fill=(0, 0, 0), font=FONT)
    return im


def stack(rows, gap=10, width=None):
    W = width or max(r.width for r in rows)
    rows = [r if r.width <= W else r.resize((W, round(r.height * W / r.width)), Image.LANCZOS) for r in rows]
    sheet = Image.new("RGB", (W, sum(r.height + gap for r in rows) - gap), "white")
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.height + gap
    return sheet


def span(kind_dir: str, name: str, pad: float = 3):
    """The stretch of a staff that has note targets, padded by `pad` spaces."""
    p = json.loads((POS / kind_dir / f"{name}.pos.json").read_text())
    xs = [t[2] for t in p["targets"] if t[1] in ("note", "grace", "rest", "rest_x")]
    return min(xs) - pad * p["ss"], max(xs) + pad * p["ss"]


def save(im, name, width=1600):
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    im.save(OUT / name, quality=82, optimize=True)
    print(name, im.size, (OUT / name).stat().st_size // 1024, "KB")


def main():
    # 1. Berlin, KHM 603: the pointer against the classical map, in the map's good bars
    rows = []
    for name in ("D-B_KHM-603_p17s2", "D-B_KHM-603_p5s6", "D-B_KHM-603_p22s4"):
        a, b = span("real603", name)
        rows.append(draw("real603", name, a, b))
    save(stack(rows), "berlin.jpg")

    # 2. Where it goes wrong: a rendered staff (copyist style) of repeated octaves, the worst test staff
    name = "Viotti__String_Quartet_in_E_minor__W_2a_2__sq11246134-p0-044-854"
    img, p, _ = load("test-copyist", name)
    w = img.size[0]
    save(stack([draw("test-copyist", name, 0, w // 2, label=False),
                draw("test-copyist", name, w // 2 - 40, w, label=False)]), "misses.jpg")

    # 3. Dolores: what its targets are (the polygons' centres); no pointer places here (they're on Modal)
    rows = []
    for f in sorted((POS / "dolores-test").glob("*.pos.json"))[:4]:
        nm = f.name[: -len(".pos.json")]
        rows.append(draw("dolores-test", nm, 0, 1100, label=False, k=1))
    save(stack(rows), "dolores.jpg")


if __name__ == "__main__":
    main()
