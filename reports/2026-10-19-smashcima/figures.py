# /// script
# requires-python = ">=3.11"
# dependencies = ["torch==2.14.1", "torchvision", "transformers==5.20.1", "pillow", "numpy"]
# ///
"""Figures for README.md: Smashcima's training windows, Berlin's, and what each decoder draws on Berlin.

    uv run reports/2026-10-19-smashcima/figures.py SAM_DIR   # holds smash1/, test2/, run8-smash/ and run2-real/decoder.pt

Writes PNGs to SAM_DIR/figs (the README's are those, as JPEG).
"""
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageDraw, ImageFont
from transformers import Sam2Model

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments" / "synth"))
import sam_train

S = Path(sys.argv[1])
OUT = S / "figs"
COL = {"head": (220, 30, 30), "stem": (20, 110, 240), "beam": (0, 160, 60), "dot": (230, 0, 230),
       "flag": (240, 140, 0), "rest": (130, 60, 200), "slur": (0, 170, 170), "barline": (120, 120, 120),
       "accidental": (180, 120, 0), "trill": (200, 0, 120), "tuplet": (90, 90, 0)}
H = 200
FONT = ImageFont.load_default(size=18)


def base(k):
    return k.split("-")[0]


def overlay(img, masks, kinds):
    rgb = np.stack([img] * 3, -1).astype(float)
    for k, m in zip(kinds, masks):
        c = COL.get(base(k))
        if c:
            rgb[m] = 0.35 * rgb[m] + 0.65 * np.array(c)
    return rgb.astype(np.uint8)


def scaled(a, h=H):
    im = Image.fromarray(a)
    return im.resize((int(im.width * h / im.height), h), Image.LANCZOS)


def stack(rows, labels, gap=8, lw=170):
    W = lw + max(r.width for r in rows)
    sheet = Image.new("RGB", (W, sum(r.height + gap for r in rows)), "white")
    d = ImageDraw.Draw(sheet)
    y = 0
    for r, t in zip(rows, labels):
        sheet.paste(r, (lw, y))
        d.multiline_text((6, y + r.height // 2 - 12), t, fill=(40, 40, 40), font=FONT)
        y += r.height + gap
    return sheet


def raw(f):
    z = np.load(f)
    img = z["image"]
    h, w = img.shape
    m = np.unpackbits(z["masks"], axis=-1)[..., :w].astype(bool)
    return img, m, [str(k) for k in z["kinds"]]


# 1. what Smashcima draws, and what the copyist draws
sm = sorted((S / "smash1").glob("*.npz"))
picks = [sm[i] for i in (40, 700, 1500, 2600, 3900)]
rows, labs = [], []
for f in picks:
    img, m, k = raw(f)
    rows += [scaled(img), scaled(overlay(img, m, k))]
    labs += ["Smashcima", "  its labels"]
stack(rows, labs).save(OUT / "smashcima-windows.png")

te = sorted((S / "test2").glob("*.npz"))
tpick = [te[i] for i in (30, 31, 32, 120, 170)]
rows, labs = [], []
for f in tpick[:3]:
    img, m, k = raw(f)
    rows += [scaled(img), scaled(overlay(img, m, k))]
    labs += ["Berlin\n(KHM 603)", "  its labels"]
stack(rows, labs).save(OUT / "berlin-windows.png")

# 2. what each decoder draws on Berlin
dev = "mps" if torch.backends.mps.is_available() else "cpu"
model = Sam2Model.from_pretrained("facebook/sam2.1-hiera-small").to(dev).eval()
own = {k: v.clone() for k, v in model.state_dict().items() if k.startswith(("mask_decoder", "prompt_encoder"))}
decs = {"untrained": own,
        "Smashcima": torch.load(S / "run8-smash/decoder.pt", map_location="cpu"),
        "real labels": torch.load(S / "run2-real/decoder.pt", map_location="cpu")}


def masks_for(ex, emb):
    s, h, w = ex["s"], *raw_shape[ex["name"]]
    top, left = (s - h) // 2, (s - w) // 2
    out = np.zeros((len(ex["kinds"]), h, w), bool)
    for kind in ("point", "box"):
        idx = np.array([i for i, k in enumerate(ex["kinds"]) if (k in sam_train.POINT_KINDS) == (kind == "point")])
        if len(idx) == 0:
            continue
        lo = sam_train.predict(model, emb, ex, idx, dev, kind)
        up = F.interpolate(lo[None].float(), size=(s, s), mode="bilinear", align_corners=False)[0] > 0
        out[idx] = up[:, top:top + h, left:left + w].cpu().numpy()
    return out


raw_shape = {}
preds = {}
for f in tpick:
    img, m, k = raw(f)
    raw_shape[f.stem] = img.shape
    ex = sam_train.load(f)
    with torch.no_grad():
        emb = model.get_image_embeddings(sam_train.pixels(ex["image"], dev))
        for name, wts in decs.items():
            model.load_state_dict(wts, strict=False)
            preds[f.stem, name] = masks_for(ex, emb)


def iou(a, b):
    return (a & b).sum() / max(1, (a | b).sum())


for j, f in enumerate(tpick[:3]):
    img, m, k = raw(f)
    rows = [scaled(overlay(img, m, k))]
    labs = ["our label"]
    for name in ("Smashcima", "real labels"):
        p = preds[f.stem, name]
        rows.append(scaled(overlay(img, p, k)))
        hi = [iou(a, b) for a, b, kk in zip(p, m, k) if kk == "head"]
        labs.append(f"{name}\nheads {np.mean(hi):.2f}")
    stack(rows, labs).save(OUT / f"predictions-{j + 1}.png")

# 3. heads close up: label, Smashcima, real labels, with each head's IoU
cells = {"our label": [], "Smashcima": [], "real labels": [], "untrained": []}
n = 0
for f in tpick:
    img, m, k = raw(f)
    h, w = img.shape
    ss = h / 10
    z = np.load(f)
    for i, (kk, pr) in enumerate(zip(k, z["prompts"])):
        if kk != "head" or n >= 10 or i % 3:
            continue
        x, y = int(pr[0]), int(pr[1])
        r = int(1.6 * ss)
        if x - r < 0 or y - r < 0 or x + r > w or y + r > h:
            continue
        sl = (slice(y - r, y + r), slice(x - r, x + r))
        for name in cells:
            mm = m[i] if name == "our label" else preds[f.stem, name][i]
            a = overlay(img[sl], [mm[sl]], ["head"])
            t = Image.fromarray(a).resize((150, 150), Image.NEAREST)
            if name != "our label":
                ImageDraw.Draw(t).text((4, 128), f"{iou(mm, m[i]):.2f}", fill=(0, 0, 0), font=FONT)
            cells[name].append(t)
        n += 1
order = ["our label", "untrained", "Smashcima", "real labels"]
sheet = Image.new("RGB", (170 + 10 * 156, 4 * 156), "white")
d = ImageDraw.Draw(sheet)
for r, name in enumerate(order):
    d.text((6, r * 156 + 64), name, fill=(40, 40, 40), font=FONT)
    for c, t in enumerate(cells[name]):
        sheet.paste(t, (170 + c * 156, r * 156))
sheet.save(OUT / "heads.png")
print("done", n, "heads")
