# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow"]
# ///
"""Are two copies of a print pulls from the same plates? Page by page and
staff by staff, by their staves' ink: each detected staff (cut as Zeus reads
it) becomes a column profile (how much ink in each column, between its
detected ends), and two staves are as alike as the best correlation of
their profiles over a small stretch and shift (the scans differ in scale
and the detected ends by a little). Same plates: every page has one twin,
and on it every staff's twin is the staff at its place.

    uv run experiments/zeus/g213/twins.py G213-DB-Pleyel G213-Sibley [--out twins.json]

Prints the page-to-page matrix's best match for each page of the first
source and its staff-by-staff correlations; writes the staff twins (first
source's staff id -> second's, with the correlation) to --out.
"""

import argparse
import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ZEUS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ZEUS))
import compare  # noqa: E402

N = 600  # profile length


def profiles(source: str) -> dict[int, list[tuple[str, np.ndarray]]]:
    auto = json.loads((ZEUS / "auto" / f"{source}.json").read_text())
    pdf = Path(auto["pdf"])
    out = {}
    for n, p in sorted(auto["pages"].items(), key=lambda kv: int(kv[0])):
        g = compare.page_image(pdf, int(n))
        rows = []
        for k, s in enumerate(sorted(p["systems"], key=lambda s: s["top"])):
            im = np.asarray(Image.open(io.BytesIO(compare.staff_crop(g, s))).convert("L"), np.float32)
            h = im.shape[0]
            band = im[int(h * 0.2):int(h * 0.8)]  # the staff and a little around it
            prof = (255 - band).mean(axis=0)
            x = np.linspace(0, len(prof) - 1, N)
            prof = np.interp(x, np.arange(len(prof)), prof)
            rows.append((f"p{n}-{k}", prof))
        out[int(n)] = rows
    return out


XS = np.arange(N)
SRC = np.array([(XS - sh) / s for s in np.arange(0.90, 1.101, 0.01) for sh in range(-48, 49, 2)])
OK = (SRC >= 0) & (SRC <= N - 1)
SRC, OK = SRC[OK.sum(axis=1) >= N * 0.7], OK[OK.sum(axis=1) >= N * 0.7]
_variants: dict[int, np.ndarray] = {}


def alike(a: np.ndarray, b: np.ndarray) -> float:
    """Best Pearson correlation of a against b stretched by 0.9-1.1 and shifted by up to 8%."""
    if id(b) not in _variants:
        _variants[id(b)] = np.where(OK, np.interp(SRC, XS, b), np.nan)
    bv = _variants[id(b)]
    av = np.where(OK, a[None, :], np.nan)
    am = av - np.nanmean(av, axis=1, keepdims=True)
    bm = bv - np.nanmean(bv, axis=1, keepdims=True)
    c = np.nansum(am * bm, axis=1) / np.sqrt(np.nansum(am ** 2, axis=1) * np.nansum(bm ** 2, axis=1))
    return float(np.nanmax(c))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("first")
    ap.add_argument("second")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    A, B = profiles(a.first), profiles(a.second)
    twins = {}
    for pa, rows_a in A.items():
        scores = {}
        for pb, rows_b in B.items():
            k = min(len(rows_a), len(rows_b))
            # quick page score: each staff against the staff at its place
            scores[pb] = np.mean([alike(rows_a[i][1], rows_b[i][1]) for i in range(k)]) if k else -1
        order = sorted(scores, key=scores.get, reverse=True)
        pb = order[0]
        rows_b = B[pb]
        line = f"{a.first} p{pa} ({len(rows_a)} staves) -> {a.second} p{pb} ({len(rows_b)} staves): {scores[pb]:.2f}, next p{order[1]} {scores[order[1]]:.2f}"
        print(line)
        # each staff's twin on that page: the best of its staves
        for i, (sid, prof) in enumerate(rows_a):
            cs = [alike(prof, q) for _, q in rows_b]
            j = int(np.argmax(cs))
            runner = sorted(cs)[-2] if len(cs) > 1 else -1
            twins[sid] = {"twin": rows_b[j][0], "corr": round(cs[j], 3), "next": round(runner, 3), "at_place": j == i}
            flag = "" if j == i else "  <- NOT AT ITS PLACE"
            print(f"   {sid} -> {rows_b[j][0]} {cs[j]:.2f} (next {runner:.2f}){flag}")
    if a.out:
        a.out.write_text(json.dumps(twins, indent=1))


if __name__ == "__main__":
    main()
