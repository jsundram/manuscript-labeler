# /// script
# requires-python = ">=3.11"
# dependencies = ["torch", "transformers", "peft", "pillow", "numpy", "scipy", "scikit-learn"]
# ///
"""Learned crop edges (crops.py) with MuSViT's features added: does what
an encoder sees at a candidate edge (a dynamic, a title, the neighbour's
notes) choose the editor's edge better than the ink features alone?

    uv run experiments/crops/musvit_rows.py <edition-repo> [--encoder d5|musvit] [--dims 16] [--out DIR]

Each reviewed staff's band, straightened along its bend as crops.band
cuts it (12 staff spaces beyond each outer line), is passed through the
frozen encoder at the readers' scale (96 px for 9 staff spaces): musvit-D5's
(adapters folded in), or MuSViT's as pretrained on IMSLP pages. Each patch
row's vectors are averaged over the staff's columns, and reduced to
--dims by PCA (fitted on every row, no labels). A candidate edge gets the
row vectors at the edge, a space inside it and a space beyond it,
interpolated between patch rows, beside crops.FEATURES. Then the same
model (crops.fit) is trained without each source in turn, as
experiments/crops/evaluate.py does, with and without the added features.

The band vectors are cached in --out (default $TMPDIR/crop-rows).
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE), str(ROOT), str(ROOT / "experiments" / "musvit"), str(ROOT / "experiments" / "zeus")]
import crops  # noqa: E402
import evaluate  # noqa: E402
import labels  # noqa: E402

PX = 96 / 9  # the readers' pixels per staff space: 96 px for the staff and 2.5 spaces above and below
SPACES = 4 + 2 * crops.BAND  # the band's height in staff spaces
ROWS = int(round(SPACES * PX / 16)) * 16  # the band's height in pixels, whole patches


def band_image(g: np.ndarray, s: dict) -> np.ndarray:
    """The staff's band in grey (0-1), crops.BAND spaces beyond each outer line, at PX per space."""
    h, w = g.shape
    x0, x1 = crops.extent(s)
    sp = (s["bottom"] - s["top"]) / 4  # page heights
    sp_x = sp * h / w  # a staff space in page widths
    n = max(16, int(round((x1 - x0) / sp_x * PX / 16)) * 16)
    xs = x0 + (np.arange(n) + 0.5) / n * (x1 - x0)
    offs = np.array([labels.bend_at(s, x) for x in xs])
    u = -crops.BAND + (np.arange(ROWS) + 0.5) / ROWS * SPACES  # spaces from the top line
    ys = (s["top"] + offs[None, :] + u[:, None] * sp) * h
    yi = np.clip(np.round(ys).astype(int), 0, h - 1)
    xi = np.clip(np.round(xs * w).astype(int), 0, w - 1)[None, :]
    out = g[yi, xi] / 255.0
    out[(ys < 0) | (ys > h - 1)] = 1.0  # past the page: paper
    return out.astype(np.float32)


def row_vectors(enc, dtype, device, img: np.ndarray) -> np.ndarray:
    """Each patch row's vector, averaged over the band's columns: (ROWS // 16, D)."""
    import torch
    x = torch.from_numpy(img)[None, None].expand(1, 3, *img.shape)
    with torch.no_grad():
        out = enc(pixel_values=x.to(device, dtype), interpolate_pos_encoding=True).last_hidden_state[0, 1:]
    v = out.float().cpu().numpy().reshape(ROWS // 16, -1, out.shape[-1])
    return v.mean(1)


def at(rows: np.ndarray, u: float) -> np.ndarray:
    """Row vectors interpolated at u staff spaces from the top line."""
    k = (u + crops.BAND) / SPACES * len(rows) - 0.5
    k = float(np.clip(k, 0, len(rows) - 1))
    i = min(int(k), len(rows) - 2)
    return rows[i] * (1 - (k - i)) + rows[i + 1] * (k - i)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edition", type=Path)
    ap.add_argument("--encoder", default="d5", choices=("d5", "musvit"))
    ap.add_argument("--dims", type=int, default=16)
    ap.add_argument("--out", type=Path, default=Path(tempfile.gettempdir()) / "crop-rows")
    a = ap.parse_args()
    import torch
    import questions
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    cache = a.out / f"rows-{a.encoder}"
    cache.mkdir(parents=True, exist_ok=True)
    enc = None
    ex, rows = [], {}
    with tempfile.TemporaryDirectory() as tmp:
        for pdf, n, p in crops.reviewed_pages(a.edition):
            g = evaluate.gray(pdf, n, Path(tmp))
            by_id = {s["id"]: s for s in p["systems"]}
            for e in crops.examples(g, p, pdf.stem in crops.OLDER_CROPS):
                key = f"{pdf.stem}-p{n}-{e['staff']}"
                if key not in rows:
                    f = cache / f"{key}.npy"
                    if not f.exists():
                        if enc is None:
                            enc, dtype = questions.encoder(device, a.encoder)
                        np.save(f, row_vectors(enc, dtype, device, band_image(g, by_id[e["staff"]])))
                    rows[key] = np.load(f)
                ex.append({**e, "source": pdf.stem, "key": key})
            print(f"{pdf.stem} p{n}", flush=True)
    from sklearn.decomposition import PCA
    pca = PCA(a.dims, random_state=0).fit(np.concatenate(list(rows.values())))
    small = {k: pca.transform(v) for k, v in rows.items()}
    for e in ex:
        r = small[e["key"]]
        # each candidate: the rows at its edge, a space inside it, and a space beyond it
        out = (lambda t: -t) if e["side"] == "above" else (lambda t: 4 + t)
        sgn = -1 if e["side"] == "above" else 1
        add = np.array([np.concatenate([at(r, out(t)), at(r, out(t) - sgn), at(r, out(t) + sgn)]) for t in e["cands"]])
        e["X_plus"] = np.concatenate([e["X"], add], 1)
    print(f"{len(ex)} sides, {len(rows)} staves; encoder {a.encoder}, {a.dims} dimensions a row")
    for held in sorted({e["source"] for e in ex}):
        train = [e for e in ex if e["source"] != held]
        base = crops.fit(train)
        plus = crops.fit([{**e, "X": e["X_plus"]} for e in train])
        for e in ex:
            if e["source"] == held:
                e["learned"] = crops.choose(base, e["cands"], e["X"])
                e["plus"] = crops.choose(plus, e["cands"], e["X_plus"])
    print("within half a staff space of the editor's edge (too tight, too wide), each source left out")
    for name, grp in [(s, [e for e in ex if e["source"] == s]) for s in sorted({e["source"] for e in ex})] + [("all", ex)]:
        print(f"{name} ({len(grp) // 2} staves)")
        print(evaluate.line("learned", grp, lambda x: x["learned"]))
        print(evaluate.line("+musvit", grp, lambda x: x["plus"]))
    (a.out / f"result-{a.encoder}-{a.dims}.json").write_text(json.dumps(
        [{k: e[k] for k in ("source", "key", "side", "truth", "learned", "plus")} for e in ex]))


if __name__ == "__main__":
    main()
