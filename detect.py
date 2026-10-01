"""Automatic first guesses for a manuscript page: staves and bar lines.

Everything here is a *proposal*. The labeler UI shows it, the editor fixes it,
and only what the editor saves is authoritative.

Coordinates returned are normalized to the page: x and y in 0..1, so labels
don't depend on the resolution the page was rendered at.
"""

import numpy as np
from PIL import Image


def _gray(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("L"), dtype=np.float32)


def _peaks(profile: np.ndarray, threshold: float, min_sep: int) -> list[int]:
    """Indices of local maxima above threshold, at least min_sep apart (strongest wins)."""
    cand = np.where(profile > threshold)[0]
    cand = sorted(cand, key=lambda i: -profile[i])
    chosen: list[int] = []
    for i in cand:
        if all(abs(i - j) >= min_sep for j in chosen):
            chosen.append(int(i))
    return sorted(chosen)


def _staff_gap(profile: np.ndarray, h: int) -> float:
    """Staff-line spacing in pixels: the strongest period in the row profile."""
    p = profile - profile.mean()
    lo, hi = max(4, h // 400), max(10, h // 40)
    ac = np.array([np.dot(p[:-k], p[k:]) for k in range(lo, hi)])
    return float(lo + int(np.argmax(ac)))


def find_staves(g: np.ndarray) -> list[dict]:
    """Five-line staves: returns [{top, bottom, gap, lines}] in pixels, top to bottom."""
    h, w = g.shape
    band = g[:, int(w * 0.2): int(w * 0.8)]
    profile = (band < 175).mean(axis=1)
    # scanner border / page edge: near-solid rows and the outer margins
    profile[profile > 0.95] = 0
    m = int(h * 0.02)
    profile[:m] = 0
    profile[h - m:] = 0
    # smooth a little so a 2-3 px thick line is one peak
    profile = np.convolve(profile, np.ones(3) / 3, mode="same")
    # staff lines reach ~0.7 of the band; note heads between lines ~0.3
    gap0 = _staff_gap(profile, h)
    peaks = _peaks(profile, threshold=0.45, min_sep=int(gap0 * 0.6))

    staves = []
    i = 0
    while i + 4 < len(peaks):
        group = peaks[i:i + 5]
        gaps = np.diff(group)
        gap = float(np.median(gaps))
        if gap > 0 and gaps.max() < gap * 1.35 and gaps.min() > gap * 0.65 and gap < h / 25:
            staves.append({"top": group[0], "bottom": group[-1], "gap": gap, "lines": group})
            i += 5
        else:
            i += 1
    return staves


def staff_extent(g: np.ndarray, staff: dict) -> tuple[int, int]:
    """Left and right x of the staff lines (pixels)."""
    h, w = g.shape
    rows = g[staff["top"]: staff["bottom"] + 1, :]
    cover = (rows < 175).mean(axis=0)
    xs = np.where(cover > 0.25)[0]
    if len(xs) == 0:
        return 0, w
    # ignore stray ink far from the main run: take the span of columns with lines
    return int(np.percentile(xs, 1)), int(np.percentile(xs, 99))


def find_barlines(g: np.ndarray, staff: dict, left: int, right: int) -> list[dict]:
    """Near-vertical strokes that span the whole staff and don't continue far beyond it.

    Handwritten bar lines lean, so each column is tested along several slants.
    Returns [{x0, x1}] in pixels: x at the top and bottom staff line.
    """
    top, bottom, gap = staff["top"], staff["bottom"], staff["gap"]
    height = bottom - top
    ink = g < 120
    pad = int(gap * 1.6)
    y0, y1 = max(0, top - pad), min(g.shape[0], bottom + pad)
    best_cover = np.zeros(right - left)
    best_slope = np.zeros(right - left)
    for slope in np.linspace(-0.18, 0.18, 13):  # dx per dy
        ys = np.arange(top, bottom + 1)
        shifts = np.round((ys - (top + bottom) / 2) * slope).astype(int)
        acc = np.zeros(right - left)
        for y, s in zip(ys, shifts):
            lo, hi = left + s, right + s
            if lo < 0 or hi > g.shape[1]:
                continue
            row = ink[y, lo:hi]
            # allow 1 px wobble: dilate horizontally
            r = row.copy()
            r[1:] |= row[:-1]
            r[:-1] |= row[1:]
            acc += r
        cover = acc / (height + 1)
        better = cover > best_cover
        best_cover[better] = cover[better]
        best_slope[better] = slope

    clef_skip = int(gap * 4)  # clef + key signature at the start of each line
    cands = [i for i in np.where(best_cover > 0.88)[0] if i > clef_skip]
    # group adjacent columns into strokes
    strokes: list[list[int]] = []
    for i in cands:
        if strokes and i - strokes[-1][-1] <= 3:
            strokes[-1].append(i)
        else:
            strokes.append([i])

    found = []
    for s in strokes:
        if len(s) > gap * 0.6:  # too wide: a beam or a smudge, not a line
            continue
        i = int(np.mean(s))
        slope = best_slope[i]
        x_mid = left + i
        # reject note stems: ink continuing well above or below the staff
        def ink_beyond(y_from, y_to):
            ys = np.arange(y_from, y_to)
            xs = (x_mid + (ys - (top + bottom) / 2) * slope).astype(int)
            ok = (xs >= 0) & (xs < g.shape[1])
            return ink[ys[ok], xs[ok]].mean() if ok.any() else 0.0
        above = ink_beyond(y0, top - int(gap * 0.6))
        below = ink_beyond(bottom + int(gap * 0.6), y1)
        if max(above, below) > 0.5:
            continue
        found.append({
            "x0": x_mid + (top - (top + bottom) / 2) * slope,
            "x1": x_mid + (bottom - (top + bottom) / 2) * slope,
        })

    # merge strokes closer than ~a staff space: double bars / repeat signs
    merged: list[dict] = []
    for b in found:
        if merged and b["x0"] - merged[-1]["x0"] < gap * 1.2:
            merged[-1]["kind"] = "double"
            continue
        merged.append({**b, "kind": "single"})
    return merged


def detect_page(img: Image.Image) -> list[dict]:
    """Proposed systems for one page, normalized coordinates."""
    g = _gray(img)
    h, w = g.shape
    systems = []
    for n, st in enumerate(find_staves(g)):
        left, right = staff_extent(g, st)
        bars = find_barlines(g, st, left, right)
        systems.append({
            "top": st["top"] / h,
            "bottom": st["bottom"] / h,
            "left": left / w,
            "right": right / w,
            "barlines": [
                {"x0": b["x0"] / w, "x1": b["x1"] / w, "kind": b["kind"]} for b in bars
            ],
        })
    return systems
