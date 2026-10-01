"""Automatic first guesses for a manuscript page: staves and bar lines.

Everything here is a *proposal*. The labeler UI shows it, the editor fixes it,
and only what the editor saves is authoritative.

Coordinates returned are normalized to the page: x and y in 0..1, so labels
don't depend on the resolution the page was rendered at.
"""

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
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


def _staff_gap(P: np.ndarray, h: int) -> float | None:
    """Staff-line spacing in pixels, from strip profiles P (rows x strips).

    In a narrow strip a staff line darkens most of the row, notes much less.
    The most common distance between neighbouring line-like rows is the
    staff space. (Autocorrelation was fooled by thick ink at small lags.)
    """
    diffs = []
    for k in range(P.shape[1]):
        # a line is 2-6 px thick: one run of dark rows, counted at its centre
        on = np.concatenate([[False], P[:, k] > 0.5, [False]])
        edges = np.flatnonzero(on[1:] != on[:-1])
        rows = [(a + b - 1) / 2 for a, b in zip(edges[::2], edges[1::2])]
        diffs += [int(round(b - a)) for a, b in zip(rows, rows[1:]) if 4 <= b - a <= h // 40]
    if not diffs:
        return None
    counts = np.bincount(diffs)
    # smooth the histogram by one so 15/16/17 vote together
    sm = np.convolve(counts, [1, 1, 1], mode="same")
    mode = int(np.argmax(sm))
    lo, hi = max(0, mode - 1), mode + 2
    return float(np.average(np.arange(lo, hi), weights=counts[lo:hi] + 1e-9))


def find_staves(g: np.ndarray, strips: int = 24) -> list[dict]:
    """Five-line staves, top to bottom: [{top, bottom, gap, lines, path, score}] in pixels.

    Hand-ruled lines on a curled page are wavy, so no single tilt lines them
    up across the page. Instead the page is cut into narrow vertical strips;
    in each strip every row gets a "staff here" score (five dark rows a staff
    space apart, with lighter rows between them), and a staff is traced
    across the strips allowing a little drift from one strip to the next.

    `top`, `bottom` and `lines` are y at the page's horizontal centre; `path`
    is [(x, y_top_line)] at each strip where the staff was clearly seen.
    """
    h, w = g.shape
    x_lo, x_hi = int(w * 0.08), int(w * 0.92)
    edges = np.linspace(x_lo, x_hi, strips + 1).astype(int)
    xc = (edges[:-1] + edges[1:]) / 2
    dark = g < 175
    P = np.stack([dark[:, edges[k]:edges[k + 1]].mean(axis=1) for k in range(strips)], axis=1)
    # scanner border / page edge: rows dark across the whole page, and the
    # outer margins. (Not per strip: there a thick staff line is near-solid.)
    P[P.mean(axis=1) > 0.9] = 0
    m = int(h * 0.02)
    P[:m] = 0
    P[h - m:] = 0

    gap = _staff_gap(P, h)
    if not gap:
        return []
    n = h - int(round(4.5 * gap)) - 3
    if n <= 0:
        return []
    # allow +-2 px of wobble per line: running max over 5 rows
    Pm = sliding_window_view(np.pad(P, ((2, 2), (0, 0))), 5, axis=0).max(axis=-1)
    on = np.mean([Pm[int(round(i * gap)):][:n] for i in range(5)], axis=0)
    off = np.mean([P[int(round((i + 0.5) * gap)):][:n] for i in range(4)], axis=0)
    S = on - off  # (n, strips)

    # best path through the strips ending at each row, drifting <= D rows per strip
    D = max(1, int(gap * 0.4))
    A = S[:, 0].copy()
    back = []
    for k in range(1, strips):
        win = sliding_window_view(np.pad(A, D, constant_values=-np.inf), 2 * D + 1)
        arg = win.argmax(axis=1)
        back.append(arg - D)
        A = S[:, k] + win[np.arange(n), arg]
    score = A / strips

    staves = []
    for end in _peaks(score, threshold=0.35, min_sep=int(gap * 5)):
        ys = [end]
        for k in range(strips - 1, 0, -1):
            ys.append(ys[-1] + int(back[k - 1][ys[-1]]))
        ys = np.array(ys[::-1])
        seen = S[ys, np.arange(strips)]
        good = seen > max(0.15, 0.5 * float(np.median(seen)))
        if good.sum() < 3:
            continue
        path = [(float(x), float(y)) for x, y, ok in zip(xc, ys, good) if ok]
        top = int(round(np.interp(w / 2, [p[0] for p in path], [p[1] for p in path])))
        lines = [top + int(round(i * gap)) for i in range(5)]
        staves.append({"top": lines[0], "bottom": lines[-1], "gap": gap, "lines": lines,
                       "path": path, "score": float(score[end])})

    # two ends can trace back onto one staff: keep the stronger
    staves.sort(key=lambda s: -s["score"])
    kept: list[dict] = []
    for s in staves:
        if all(abs(s["top"] - k["top"]) > 3 * gap for k in kept):
            kept.append(s)
    return sorted(kept, key=lambda s: s["top"])


def straighten(g: np.ndarray, staff: dict, pad_gaps: float = 4.0) -> tuple[np.ndarray, int]:
    """A horizontal band around one staff, with its waviness taken out.

    Returns (band, y_offset): band row r is page row y_offset + r at the
    page's horizontal centre, and follows the staff elsewhere.
    """
    h, w = g.shape
    pad = int(staff["gap"] * pad_gaps)
    y0 = staff["top"] - pad
    rows = np.arange(y0, staff["bottom"] + pad + 1)
    px, py = zip(*staff["path"])
    shift = np.round(np.interp(np.arange(w), px, py) - staff["top"]).astype(int)
    ys = np.clip(rows[:, None] + shift[None, :], 0, h - 1)
    return g[ys, np.arange(w)[None, :]], y0


def staff_extent(g: np.ndarray, staff: dict) -> tuple[int, int]:
    """Left and right x of the ruled staff lines (pixels).

    A column belongs to the staff when most of its five line rows are dark
    and the spaces between them are not: that rejects dark page edges and
    scanner borders, which are dark everywhere.
    """
    h, w = g.shape
    ink = g < 175
    lines = [min(h - 1, max(0, y)) for y in staff["lines"]]
    on = np.stack([ink[max(0, y - 1): y + 2].any(axis=0) for y in lines]).mean(axis=0)
    mids = [(a + b) // 2 for a, b in zip(lines, lines[1:])]
    off = ink[mids].mean(axis=0)
    col = (on >= 0.8) & (off <= 0.5)
    # notes and clefs hide the lines locally; judge by windows of 4 spaces
    k = max(3, int(staff["gap"] * 4))
    cover = np.convolve(col.astype(float), np.ones(k) / k, mode="same")
    xs = np.flatnonzero(cover >= 0.35)
    if len(xs) == 0:
        return 0, w
    return int(max(0, xs[0] - k // 2)), int(min(w, xs[-1] + k // 2))


def note_ink(g: np.ndarray, staff: dict, left: int, right: int) -> float:
    """Fraction of dark pixels around a staff, staff lines excluded.
    Empty ruled staves are near 0; written ones are a few percent or more."""
    lines = staff["lines"]
    pad = int(staff["gap"] * 2.5)
    y0 = max(0, lines[0] - pad)
    zone = g[y0: lines[-1] + pad, left:right]
    keep = np.ones(zone.shape[0], bool)
    for y in lines:
        keep[max(0, y - y0 - 3): y - y0 + 4] = False
    return float((zone[keep] < 120).mean()) if keep.any() and zone.size else 0.0


def music_start(g: np.ndarray, staff: dict, left: int, right: int) -> tuple[int, int]:
    """(clef x, music start x), a guess for the editor to adjust.

    The first heavy ink in the staff's spaces is the clef, unless it is a
    thin stroke with clear paper after it: that's the system's opening line.
    The music starts after the clef and key signature, at the first clear
    stretch of about a staff space.
    """
    gap = staff["gap"]
    lines = staff["lines"]
    mids = [(a + b) // 2 for a, b in zip(lines, lines[1:])]
    ink = (g[mids, left:right] < 120).mean(axis=0)
    heavy = np.flatnonzero(ink >= 0.5)
    clef = 0
    if len(heavy) and heavy[0] < gap * 6:
        clef = int(heavy[0])
        end = clef
        while end < len(ink) and ink[end] >= 0.25:
            end += 1
        after = ink[end:end + int(gap * 0.6)]
        if end - clef < gap * 0.4 and len(after) and after.max() < 0.25:
            later = heavy[heavy > end]
            if len(later) and later[0] < end + gap * 4:
                clef = int(later[0])
    clear = int(gap)
    lo, hi = clef + int(gap * 2.5), min(right - left, clef + int(gap * 9))
    start = clef + int(gap * 5)
    for x in range(lo, hi - clear):
        if ink[x:x + clear].max() < 0.25:
            start = x
            break
    return left + clef, left + start


def find_barlines(g: np.ndarray, staff: dict, left: int, right: int, skip_to: int | None = None) -> list[dict]:
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

    # clef + key signature at the start of each line
    clef_skip = (skip_to - left) if skip_to is not None else int(gap * 4)
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


def find_page_corners(img: Image.Image) -> list[list[float]]:
    """The paper's four corners, TL TR BR BL, as page fractions.

    The paper is the bright region against the darker scanner bed, felt or
    binding (an Otsu threshold on a small copy). Its corners are the
    extreme points along the diagonals, which also follows a page
    photographed at a slight angle.
    """
    small = img.convert("L").copy()
    small.thumbnail((400, 400))
    lum = np.asarray(small, dtype=np.float32)
    h, w = lum.shape
    hist, edges = np.histogram(lum, bins=64, range=(0, 255))
    best, thr = -1.0, 128.0
    for i in range(1, 64):
        w0, w1 = hist[:i].sum(), hist[i:].sum()
        if not w0 or not w1:
            continue
        m0 = (hist[:i] * edges[:i]).sum() / w0
        m1 = (hist[i:] * edges[i:-1]).sum() / w1
        v = w0 * w1 * (m0 - m1) ** 2
        if v > best:
            best, thr = v, float(edges[i])
    ys, xs = np.nonzero(lum > thr)
    if len(xs) < 0.3 * h * w:  # no clear paper: the whole image
        return [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
    pick = [np.argmin(xs + ys), np.argmax(xs - ys), np.argmax(xs + ys), np.argmin(xs - ys)]
    return [[float(xs[i] + 0.5) / w, float(ys[i] + 0.5) / h] for i in pick]


def detect_page(img: Image.Image) -> list[dict]:
    """Proposed systems for one page, normalized coordinates."""
    g = _gray(img)
    h, w = g.shape
    found = []
    for st in find_staves(g):
        band, y0 = straighten(g, st)
        local = {**st, "top": st["top"] - y0, "bottom": st["bottom"] - y0,
                 "lines": [y - y0 for y in st["lines"]]}
        left, right = staff_extent(band, local)
        if note_ink(band, local, left, right) < 0.01:
            continue  # an empty ruled staff
        clef, start = music_start(band, local, left, right)
        found.append((st, band, local, left, right, clef, start))

    # Where the clef guess failed, the start sits at the staff's edge. Clef
    # and key take about the same room on every staff of a page: borrow it.
    widths = [(s - c) / st["gap"] for st, _, _, _, _, c, s in found if s - c >= 2 * st["gap"]]
    typical = float(np.median(widths)) if widths else 4.0

    systems = []
    for st, band, local, left, right, clef, start in found:
        if start - clef < 2 * st["gap"]:
            clef = left
            start = min(right, left + int(typical * st["gap"]))
        bars = find_barlines(band, local, left, right, skip_to=start)
        # End the staff just after its last bar line when the ruled lines
        # beyond it are blank. Music there (a missed bar line, a bar that
        # runs on to the next line) keeps the full length.
        if bars:
            last = int(max(max(b["x0"], b["x1"]) for b in bars))
            tail = last + int(st["gap"] * 0.5)
            if right - tail > st["gap"] * 1.5 and note_ink(band, local, tail, right) < 0.01:
                right = tail
        # how the staff rises and falls along its length (see labels.bend_at)
        px, py = zip(*st["path"])
        xs = np.linspace(left, right, 5)
        bend = [(float(np.interp(x, px, py)) - st["top"]) / h for x in xs]
        systems.append({
            "top": st["top"] / h,
            "bottom": st["bottom"] / h,
            "left": max(left, clef - int(st["gap"])) / w,
            "right": right / w,
            # where the music starts, after clef and key signature (a guess)
            "start": start / w,
            "bend": bend,
            "barlines": [
                {"x0": b["x0"] / w, "x1": b["x1"] / w, "kind": b["kind"]} for b in bars
            ],
        })
    return systems
