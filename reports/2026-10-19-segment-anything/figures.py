# /// script
# requires-python = ">=3.11"
# dependencies = ["torch==2.14.1", "torchvision", "transformers==5.20.1", "pillow", "numpy"]
# ///
"""Figures for README.md: what the training windows look like, and what each decoder traces on Berlin.

    uv run reports/2026-10-19-segment-anything/figures.py SAM_DIR [OUT_DIR]

SAM_DIR is ~/Data/manuscript-labeler/experiments/sam: train2/, test2/, testR-copyist/, testR-plain/, the run folders'
decoder.pt, and real-vs-synth.png (sam_apply.py's sheets for run2-real and run3-synth, cut to one staff). OUT_DIR
defaults to this folder. Writes small JPEGs.
"""
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageDraw, ImageFont
from transformers import Sam2Model

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments" / "synth"))
import sam_train  # noqa: E402

S = Path(sys.argv[1]).expanduser()
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parent
# the Smashcima report's colours: heads red, stems blue, beams green, accidentals and flags orange, rests purple
COL = {"head": (220, 30, 30), "stem": (20, 110, 240), "beam": (0, 160, 60), "dot": (230, 0, 230),
       "flag": (240, 140, 0), "rest": (130, 60, 200), "slur": (0, 170, 170), "barline": (120, 120, 120),
       "accidental": (240, 140, 0), "trill": (200, 0, 120), "tuplet": (90, 90, 0)}
FONT = ImageFont.load_default(size=17)
SMALL = ImageFont.load_default(size=14)


def base(k):
    return k.split("-")[0]


def raw(f):
    z = np.load(f)
    img = z["image"]
    h, w = img.shape
    n = len(z["kinds"])
    m = np.unpackbits(z["masks"], axis=-1)[..., :w].reshape(n, h, w).astype(bool)
    return img, m, [str(k) for k in z["kinds"]], z["prompts"]


def overlay(img, masks, kinds):
    rgb = np.stack([img] * 3, -1).astype(float)
    for k, m in zip(kinds, masks):
        c = COL.get(base(k))
        if c:
            rgb[m] = 0.3 * rgb[m] + 0.7 * np.array(c)
    return rgb.astype(np.uint8)


def scaled(a, h):
    im = Image.fromarray(a)
    return im.resize((int(im.width * h / im.height), h), Image.LANCZOS)


def stack(rows, labels, gap=6, lw=200):
    W = lw + max(r.width for r in rows)
    sheet = Image.new("RGB", (W, sum(r.height + gap for r in rows)), "white")
    d = ImageDraw.Draw(sheet)
    y = 0
    for r, t in zip(rows, labels):
        sheet.paste(r, (lw, y))
        d.multiline_text((6, y + r.height // 2 - 10 * (t.count("\n") + 1)), t, fill=(40, 40, 40), font=FONT)
        y += r.height + gap
    return sheet


def save(im, name, width=1400):
    if im.width > width:
        im = im.resize((width, int(im.height * width / im.width)), Image.LANCZOS)
    im.save(OUT / name, quality=82, optimize=True)
    print(OUT / name, im.size, (OUT / name).stat().st_size // 1024, "KB")


def iou(a, b):
    return (a & b).sum() / max(1, (a | b).sum())


# -- the decoders --------------------------------------------------------------------------------------------------
dev = "mps" if torch.backends.mps.is_available() else "cpu"
model = Sam2Model.from_pretrained("facebook/sam2.1-hiera-small").to(dev).eval()
own = {k: v.clone() for k, v in model.state_dict().items() if k.startswith(("mask_decoder", "prompt_encoder"))}
DECS = {"untrained": own,
        "real labels": torch.load(S / "run2-real/decoder.pt", map_location="cpu"),
        "copyist renders": torch.load(S / "run3-synth/decoder.pt", map_location="cpu"),
        "renders, then real": torch.load(S / "run5-synth-real/decoder.pt", map_location="cpu")}


def predict_all(f):
    """Every decoder's masks for every symbol of window f, at the window's own size (as sam_eval scores them,
    but upsampled from the 256 x 256 low-resolution mask instead of downsampling the label)."""
    img = raw(f)[0]
    h, w = img.shape
    ex = sam_train.load(f)
    s = ex["s"]
    top, left = (s - h) // 2, (s - w) // 2
    out = {}
    with torch.no_grad():
        emb = model.get_image_embeddings(sam_train.pixels(ex["image"], dev))
        for name, wts in DECS.items():
            model.load_state_dict(wts, strict=False)
            m = np.zeros((len(ex["kinds"]), h, w), bool)
            for kind in ("point", "box"):
                idx = np.array([i for i, k in enumerate(ex["kinds"]) if (k in sam_train.POINT_KINDS) == (kind == "point")])
                if len(idx) == 0:
                    continue
                lo = sam_train.predict(model, emb, ex, idx, dev, kind)
                up = F.interpolate(lo[None].float(), size=(s, s), mode="bilinear", align_corners=False)[0] > 0
                m[idx] = up[:, top:top + h, left:left + w].cpu().numpy()
            out[name] = m
    return out


# -- 1. the training windows: real labels against exact rendered masks --------------------------------------------
rows, labs = [], []
for f, lab in [(S / "train2/D-B_KHM-602_p7s7_w2.npz", "Berlin, KHM 602\n(training page)"),
               (sorted((S / "testR-copyist").glob("*.npz"))[60], "copyist render"),
               (sorted((S / "testR-plain").glob("*.npz"))[60], "plain render")]:
    img, m, k, _ = raw(f)
    rows += [scaled(np.stack([img] * 3, -1), 150), scaled(overlay(img, m, k), 150)]
    labs += [lab, "  its masks"]
save(stack(rows, labs), "training-windows.jpg")

# -- 2. one Berlin test window, traced by each decoder ------------------------------------------------------------
f = S / "test2/D-B_KHM-603_p17s5_w3.npz"
img, m, k, _ = raw(f)
P = predict_all(f)
rows = [scaled(np.stack([img] * 3, -1), 150), scaled(overlay(img, m, k), 150)]
labs = ["KHM 603\n(held out)", "our label"]
for name in DECS:
    p = P[name]
    hi = np.mean([iou(a, b) for a, b, kk in zip(p, m, k) if kk == "head"])
    si = np.mean([iou(a, b) for a, b, kk in zip(p, m, k) if kk == "stem"])
    bi = np.mean([iou(a, b) for a, b, kk in zip(p, m, k) if kk == "beam"])
    rows.append(scaled(overlay(img, p, k), 150))
    labs.append(f"{name}\nheads {hi:.2f}, stems {si:.2f}\nbeams {bi:.2f}")
save(stack(rows, labs), "tracings.jpg")

# -- 3. notes close up: Berlin heads and stems, and rendered ones -------------------------------------------------
CW, CH = 2.6, 6.4  # cell size in staff spaces (a staff space taken as a tenth of the window's height)
Z = 3  # zoom


def notes(f, n, step):
    """Up to n (head index, stem index) pairs of window f whose stem is found and whose cell fits the window."""
    img, m, k, pr = raw(f)
    h, w = img.shape
    ss = h / 10
    out = []
    heads = [i for i, kk in enumerate(k) if kk == "head"]
    for i in heads[::step]:
        x, y = int(pr[i][0]), int(pr[i][1])
        cand = [(abs(pr[j][0] - x), j) for j, kk in enumerate(k) if kk == "stem"
                and abs(pr[j][0] - x) < 1.2 * ss and abs(pr[j][1] - y) < 3.5 * ss]
        if not cand:
            continue
        j = min(cand)[1]
        sy = int(pr[j][1])
        cy = (y + sy) // 2
        x0, y0 = int(x - CW / 2 * ss), int(cy - CH / 2 * ss)
        if x0 < 0 or y0 < 0 or x0 + int(CW * ss) > w or y0 + int(CH * ss) > h:
            continue
        out.append((i, j, x0, y0, int(CW * ss), int(CH * ss)))
        if len(out) == n:
            break
    return out


cols = []  # (window, prediction dict, (i, j, x0, y0, cw, ch))
for f, n, step in [(S / "test2/D-B_KHM-603_p17s5_w3.npz", 4, 3), (S / "test2/D-B_KHM-603_p11s6_w4.npz", 3, 4),
                   (sorted((S / "testR-copyist").glob("*.npz"))[60], 3, 2)]:
    preds = predict_all(f)
    cols += [(f, preds, c) for c in notes(f, n, step)]
order = ["our label", "untrained", "real labels", "copyist renders"]
cw = max(c[2][4] for c in cols) * Z
ch = max(c[2][5] for c in cols) * Z
LW, G = 150, 6
sheet = Image.new("RGB", (LW + len(cols) * (cw + G), 26 + len(order) * (ch + G)), "white")
d = ImageDraw.Draw(sheet)
nb = sum(1 for c in cols if "test2" in str(c[0]))
d.text((LW + 4, 4), "Berlin, KHM 603 (held out)", fill=(40, 40, 40), font=FONT)
d.text((LW + nb * (cw + G) + 4, 4), "copyist render", fill=(40, 40, 40), font=FONT)
for r, name in enumerate(order):
    d.text((6, 26 + r * (ch + G) + ch // 2 - 8), name, fill=(40, 40, 40), font=FONT)
    for c, (f, preds, (i, j, x0, y0, w_, h_)) in enumerate(cols):
        img, m, k, _ = raw(f)
        mm = m if name == "our label" else preds[name]
        sl = (slice(y0, y0 + h_), slice(x0, x0 + w_))
        a = overlay(img[sl], [mm[i][sl], mm[j][sl]], ["head", "stem"])
        t = Image.fromarray(a).resize((w_ * Z, h_ * Z), Image.NEAREST)
        if name != "our label":
            dt = ImageDraw.Draw(t)
            dt.rectangle((0, h_ * Z - 36, w_ * Z, h_ * Z), fill=(255, 255, 255))
            dt.text((3, h_ * Z - 35), f"head {iou(mm[i], m[i]):.2f}", fill=(180, 20, 20), font=SMALL)
            dt.text((3, h_ * Z - 18), f"stem {iou(mm[j], m[j]):.2f}", fill=(10, 80, 200), font=SMALL)
        sheet.paste(t, (LW + c * (cw + G), 26 + r * (ch + G)))
save(sheet, "close-up.jpg")

# -- 4. whole staves, as sam_apply.py draws them --------------------------------------------------------------------
save(Image.open(S / "real-vs-synth.png").convert("RGB"), "whole-staff.jpg", width=1200)
