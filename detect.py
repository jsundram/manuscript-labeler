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


def clef_left(g: np.ndarray, staff: dict, clef: int, left: int, bound: int | None = None) -> int:
    """Leftmost ink of the clef found at `clef`, by walking left until a
    clear half staff space. A treble clef's curl reaches well left of its
    heavy middle stroke (and above and below the staff), so the rows looked
    at span two spaces beyond the staff; staff-line rows are skipped. Some
    copyists write the clef partly left of where the ruled lines begin (a
    bass clef's arc reaching well into the margin), so the walk may go up
    to CLEF_REACH spaces past `left`, but never past `bound` (a brace)."""
    gap = staff["gap"]
    lines = staff["lines"]
    y0, y1 = max(0, int(lines[0] - 2 * gap)), min(g.shape[0], int(lines[-1] + 2 * gap))
    rows = np.ones(y1 - y0, bool)
    for y in lines:
        rows[max(0, y - y0 - 2): y - y0 + 3] = False
    ink = (g[y0:y1][rows] < 120).sum(axis=0)
    clear = max(2, int(gap * 0.5))
    x = clef
    stop = max(0, left - int(gap * CLEF_REACH), bound if bound is not None else 0)
    while x - clear > stop and ink[x - clear:x].max() > 1:
        x -= 1
    return x


def crop_margins(g: np.ndarray, staves: list[dict]) -> list[tuple[float, float]]:
    """(above, below) in staff spaces for each staff: how far its own ink
    (notes on ledger lines, slurs, dynamics, text) reaches.

    Going out from the staff, the crop stops at the first clear stretch of
    a staff space, or where the space shared with the next staff is
    emptiest, whichever comes first, plus a little margin. Neighbours
    split the space between them at that emptiest row.
    """
    h = g.shape[0]
    ink = (g < 120)
    out = []
    for i, st in enumerate(staves):
        gap = st["gap"]
        xs = slice(int(st["x_left"]), int(st["x_right"]))
        prof = ink[:, xs].mean(axis=1)
        k = max(1, int(gap * 0.3))
        prof = np.convolve(prof, np.ones(k) / k, mode="same")
        blank = prof < 0.002
        clear = max(2, int(gap))

        def reach(start: int, step: int, limit: int) -> int:
            """Rows from the staff edge to where its ink ends, going `step`."""
            y = start
            while (y + step * clear - limit) * step < 0:
                if blank[min(y, y + step * clear): max(y, y + step * clear)].all():
                    break
                y += step
            return abs(y - start)

        # the emptiest row between this staff and each neighbour
        def split(a: int, b: int) -> int:
            lo, hi = a + int(gap), b - int(gap)
            if hi <= lo:
                return (a + b) // 2
            seg = prof[lo:hi]
            best = np.flatnonzero(seg <= seg.min() + 1e-4)
            mid = (hi - lo) / 2
            return lo + int(best[np.argmin(np.abs(best - mid))])

        top, bottom = st["top_px"], st["bottom_px"]
        up_limit = split(staves[i - 1]["bottom_px"], top) if i > 0 else max(0, int(top - 8 * gap))
        down_limit = split(bottom, staves[i + 1]["top_px"]) if i + 1 < len(staves) else min(h - 1, int(bottom + 8 * gap))
        above = reach(top, -1, up_limit) / gap + CROP_PAD
        below = reach(bottom, 1, down_limit) / gap + CROP_PAD
        out.append((round(max(CROP_MIN, above) * 2) / 2, round(max(CROP_MIN, below) * 2) / 2))
    return out


def ink_around(g: np.ndarray, staff: dict, x_from: int, x_to: int) -> np.ndarray:
    """Per column, whether there's ink from two spaces above the staff to
    one below it, staff-line rows left out. Accidentals of a key signature
    are often written above the staff (a bass clef's B flat on the top
    line or over it), where the staff's own spaces don't see them."""
    gap = staff["gap"]
    lines = staff["lines"]
    y0, y1 = max(0, int(lines[0] - 2 * gap)), min(g.shape[0], int(lines[-1] + gap))
    rows = np.ones(y1 - y0, bool)
    for y in lines:
        rows[max(0, y - y0 - 2): y - y0 + 3] = False
    x_from, x_to = max(0, x_from), min(g.shape[1], x_to)
    return (g[y0:y1][rows][:, x_from:x_to] < 120).sum(axis=0) >= 2


def music_start(g: np.ndarray, staff: dict, left: int, right: int) -> tuple[int, int, int]:
    """(clef x, music start x, brace x), a guess for the editor to adjust.

    The clef is the first heavy ink in the staff's spaces after any thin
    stroke running the staff's full height: a system's opening line or the
    brace joining a cue staff to the part (a part's name, written over the
    ruled lines, sits left of the brace). A bass clef's thin first arc
    isn't full height, so it isn't skipped. Brace x is where such a stroke
    ends (or `left`), so the clef's leftward search stops there.
    The music starts after the clef and key signature, at the first clear
    stretch of about a staff space.
    """
    gap = staff["gap"]
    lines = staff["lines"]
    mids = [(a + b) // 2 for a, b in zip(lines, lines[1:])]
    ink = (g[mids, left:right] < 120).mean(axis=0)
    heavy = np.flatnonzero(ink >= 0.5)
    clef, brace = 0, 0

    def stroke(a: int, b: int) -> tuple[bool, bool, bool]:
        """(thin and full staff height, clear paper after, runs on 3 spaces
        above or below the staff), for the heavy run [a, b)."""
        rows = g[lines[0]:lines[-1] + 1, left + a:left + b] < 120
        full = bool(rows.size) and rows.any(axis=1).mean() >= 0.9 and b - a < gap * 0.5
        clear_after = ink[b:b + int(gap * 0.6)].max(initial=0) < 0.25
        y_lo = max(0, int(lines[0] - 3 * gap))
        y_hi = min(g.shape[0], int(lines[-1] + 3 * gap))
        out = ((g[y_lo:lines[0], left + a:left + b] < 120).any(axis=1).mean() > 0.8
               or (g[lines[-1]:y_hi, left + a:left + b] < 120).any(axis=1).mean() > 0.8)
        return full, clear_after, out

    # heavy runs in the first stretch of the staff, left to right, each
    # widened to the stroke's lighter edges
    runs: list[list[int]] = []
    for x in heavy[heavy < gap * 20]:
        if runs and x - runs[-1][1] <= 1:
            runs[-1][1] = int(x) + 1
        else:
            runs.append([int(x), int(x) + 1])
    for r in runs:
        while r[1] < len(ink) and ink[r[1]] >= 0.25:
            r[1] += 1
    # A brace joining a cue staff to the part runs on to the next staff;
    # the part's name may be written over the ruled lines before it, so
    # look for one first and read the clef only after it.
    for a, b in runs:
        full, _, out = stroke(a, b)
        if full and out:
            brace = b
            break
    for a, b in runs:
        if b <= brace:
            continue
        full, clear_after, out = stroke(a, b)
        # an opening line (clear paper after it) or a brace: not the clef.
        # A treble clef's spine is thin and full height too, but has neither.
        if full and (clear_after or out):
            brace = b
            continue
        if a < brace + gap * 6:
            clef = a
        break
    if not runs or clef < brace:
        clef = brace
    clear = int(gap)
    lo, hi = clef + int(gap * 2.5), min(right - left, clef + int(gap * 9))
    start = clef + int(gap * 5)
    around = ink_around(g, staff, left, right)
    for x in range(lo, hi - clear):
        if not around[x:x + clear].any():
            start = x
            break
    return left + clef, left + start, left + brace


# Bar-line tests, in staff spaces (tuned on D-B KHM 602 pp. 2, 3, 6 against
# the editor's corrections; see SPEC.md).
ATTACH_WIDTH = 0.85   # an ink run this wide crossing the stroke is a note head or beam
ATTACH_ROWS = 0.25    # ... and this many rows of it means the stroke is a stem
TAIL_BLANK = 8.0      # empty staff (spaces) after the last ink that ends a staff early
CLEF_REACH = 4.0      # how far (spaces) a clef may stick out left of the ruled lines
SNAP_REACH = 1.0      # snapping a hand-placed bar line looks this many spaces either side
SNAP_COVER = 0.6      # ...for a stroke covering at least this much of the staff height
CROP_PAD = 1.0        # staff spaces of paper kept beyond a staff's outermost ink
CROP_MIN = 1.5        # never crop closer to the staff than this
MIN_BAR = 4.0         # bars are rarely narrower (about 1 cm in KHM 602)
COVER = 0.88          # share of the staff's height the stroke must cover
BEYOND = 0.9          # ink share past the staff above which a stroke is a stem
LEAN = 0.3            # steepest lean tried, dx per dy
END_SLACK = 0.0       # staff spaces a bar line may stop short of the outer staff lines
FAINT = 0.7           # weaker cover accepted where a gap is too wide for one bar...
WIDE_GAP = 1.6        # ...i.e. wider than this many times the line's typical bar


def attachment(ink: np.ndarray, staff: dict, x_mid: float, slope: float) -> float:
    """How much of a stroke has wide ink across it (note heads, beams), in
    staff spaces of height. A bar line is thin all the way; a stem has a
    head at one end and often beams across it. Staff-line rows are skipped,
    since every stroke crosses those. (Judging width against the stroke's
    own width, to spare thick final bars, let more stems through: worse.)"""
    top, bottom, gap = staff["top"], staff["bottom"], staff["gap"]
    h, w = ink.shape
    c = (top + bottom) / 2
    lines = staff["lines"]
    wide = 0
    cap = int(gap * 2)
    for y in range(max(0, int(top - gap)), min(h, int(bottom + gap) + 1)):
        if any(abs(y - ly) <= 2 for ly in lines):
            continue
        x = int(round(x_mid + (y - c) * slope))
        if not (0 <= x < w):
            continue
        # the ink run through the stroke (allowing a pixel of wobble)
        hit = [xx for xx in (x - 1, x, x + 1) if 0 <= xx < w and ink[y, xx]]
        if not hit:
            continue
        lo = hi = hit[0]
        while lo > 0 and ink[y, lo - 1] and hi - lo < cap:
            lo -= 1
        while hi < w - 1 and ink[y, hi + 1] and hi - lo < cap:
            hi += 1
        if hi - lo + 1 > ATTACH_WIDTH * gap:
            wide += 1
    return wide / gap


def find_barlines(g: np.ndarray, staff: dict, left: int, right: int, skip_to: int | None = None) -> list[dict]:
    """Near-vertical strokes that span the whole staff and don't continue far beyond it.

    Handwritten bar lines lean, so each column is tested along several slants.
    Stems are told apart by what's attached to them (`attachment`), and by
    spacing: bars are wider than MIN_BAR staff spaces, so of strokes closer
    than that, only the cleanest is kept.
    Returns [{x0, x1}] in pixels: x at the top and bottom staff line.
    """
    top, bottom, gap = staff["top"], staff["bottom"], staff["gap"]
    height = bottom - top
    ink = g < 120
    pad = int(gap * 1.6)
    y0, y1 = max(0, top - pad), min(g.shape[0], bottom + pad)
    best_cover = np.zeros(right - left)
    best_slope = np.zeros(right - left)
    slack = int(gap * END_SLACK)
    for slope in np.linspace(-LEAN, LEAN, 2 * int(LEAN / 0.03) + 1):  # dx per dy
        ys = np.arange(top + slack, bottom - slack + 1)
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
        cover = acc / len(ys)
        better = cover > best_cover
        best_cover[better] = cover[better]
        best_slope[better] = slope

    # clef + key signature at the start of each line
    clef_skip = (skip_to - left) if skip_to is not None else int(gap * 4)

    def strokes_over(threshold: float, lo: int = 0, hi: int | None = None) -> list[list[int]]:
        """Runs of adjacent columns covering more than `threshold` of the staff."""
        hi = len(best_cover) if hi is None else hi
        cands = [i for i in np.where(best_cover > threshold)[0] if max(clef_skip, lo) < i < hi]
        out: list[list[int]] = []
        for i in cands:
            if out and i - out[-1][-1] <= 3:
                out[-1].append(i)
            else:
                out.append([i])
        return out

    def test(stroke: list[int]) -> dict | None:
        """The bar line this stroke makes, or None if it's a stem, beam or smudge."""
        if len(stroke) > gap * 0.6:  # too wide: a beam or a smudge, not a line
            return None
        i = int(np.mean(stroke))
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
        if max(above, below) > BEYOND:
            return None
        att = attachment(ink, staff, x_mid, slope)
        if att > ATTACH_ROWS:
            return None
        return {
            "x0": x_mid + (top - (top + bottom) / 2) * slope,
            "x1": x_mid + (bottom - (top + bottom) / 2) * slope,
            "att": att, "cover": float(best_cover[i]),
        }

    found = [b for b in map(test, strokes_over(COVER)) if b]

    # merge strokes closer than ~a staff space: double bars / repeat signs
    merged: list[dict] = []
    for b in found:
        if merged and b["x0"] - merged[-1]["x0"] < gap * 1.2:
            merged[-1]["kind"] = "double"
            merged[-1]["att"] = min(merged[-1]["att"], b["att"])
            continue
        merged.append({**b, "kind": "single"})

    # bars are wider than MIN_BAR: in a tighter cluster keep the cleanest
    # stroke (least attached), cleanest first so it claims its neighbourhood
    kept: list[dict] = []
    for b in sorted(merged, key=lambda b: b["att"]):
        if all(abs(b["x0"] - k["x0"]) >= gap * MIN_BAR for k in kept):
            kept.append(b)
    kept.sort(key=lambda b: b["x0"])

    # Bars on a line are roughly even. A gap much wider than the line's
    # typical bar probably hides a faint or broken bar line: accept a
    # weaker stroke there, the strongest one near the middle of the gap.
    if len(kept) >= 3:
        typical = float(np.median(np.diff([b["x0"] for b in kept])))
        for a, c in zip(list(kept), list(kept)[1:]):
            if c["x0"] - a["x0"] > WIDE_GAP * typical:
                lo = int(a["x0"] - left + gap * MIN_BAR)
                hi = int(c["x0"] - left - gap * MIN_BAR)
                extra = [b for b in map(test, strokes_over(FAINT, lo, hi)) if b]
                if extra:
                    centre = (a["x0"] + c["x0"]) / 2
                    best = max(extra, key=lambda b: b["cover"] - abs(b["x0"] - centre) / (c["x0"] - a["x0"]))
                    kept.append({**best, "kind": "single"})
        kept.sort(key=lambda b: b["x0"])
    return [{k: v for k, v in b.items() if k not in ("att", "cover")} for b in kept]


def snap_barline(g: np.ndarray, top: float, bottom: float, x0: float, x1: float,
                 reach: float = SNAP_REACH) -> dict | None:
    """Fit a bar line the editor placed by hand to the stroke under it.

    Searches `reach` staff spaces either side of where it was put, at every
    lean from upright to steep, for the column of ink covering the most of
    the staff's height, and returns its centre line as {x0, x1, cover}
    (x on the top and bottom staff lines, in pixels). A fine adjustment:
    if nothing covers SNAP_COVER of the staff that close, returns None and
    the line stays where it was put. `top`/`bottom` are the staff's lines
    at this point (bend included).
    """
    h, w = g.shape
    t, b = int(round(top)), int(round(bottom))
    if b - t < 8:
        return None
    gap = (b - t) / 4
    ys = np.arange(t, b + 1)
    yc = (t + b) / 2
    xm = (x0 + x1) / 2
    r = int(np.ceil(reach * gap))
    lean = 0.4  # dx per dy, steeper than any bar line seen so far
    pad = r + int(np.ceil(lean * (b - t) / 2)) + 2
    lo, hi = int(xm) - pad, int(xm) + pad + 1
    if lo < 0 or hi > w:
        return None
    ink = g[t:b + 1, lo:hi] < 135
    # allow a pixel of wobble
    ink = ink | np.roll(ink, 1, axis=1) | np.roll(ink, -1, axis=1)
    offsets = np.arange(-r, r + 1)
    best = None
    for slope in np.linspace(-lean, lean, 81):
        shift = np.round((ys - yc) * slope).astype(int)
        cols = (int(xm) - lo) + offsets[None, :] + shift[:, None]
        cover = ink[np.arange(len(ys))[:, None], cols].mean(axis=0)
        # prefer the nearer of two equally good strokes
        score = cover - 0.1 * np.abs(offsets) / max(1, r)
        i = int(np.argmax(score))
        if best is None or score[i] > best[0]:
            best = (score[i], cover[i], slope, i, cover)
    _, cover, slope, i, covers = best
    if cover < SNAP_COVER:
        return None
    # the stroke is several pixels wide: take the middle of its run
    j, k = i, i
    while j > 0 and covers[j - 1] >= cover - 0.05:
        j -= 1
    while k < len(covers) - 1 and covers[k + 1] >= cover - 0.05:
        k += 1
    xc = int(xm) + offsets[(j + k) // 2] + ((j + k) % 2) * 0.5
    return {"x0": xc + (t - yc) * slope, "x1": xc + (b - yc) * slope, "cover": float(cover)}


def snap_start(g: np.ndarray, top: float, bottom: float, x: float, reach: float = 2.0) -> float | None:
    """The music start nearest x: where a clear stretch (0.8 of a space, no
    ink from two spaces above the staff to one below, see ink_around)
    begins, within `reach` spaces. None if there's none that close.

    For carrying one line's start to the lines below it: the same place on
    the page, snapped to where the clear paper after the key signature is.
    (Backtested on KHM 602/603: beats measuring from each line's left edge.)
    """
    gap = (bottom - top) / 4
    if gap < 2:
        return None
    staff = {"gap": gap, "lines": [int(round(top + i * gap)) for i in range(5)]}
    lo, hi = int(x - reach * gap), int(x + reach * gap)
    around = ink_around(g, staff, lo, hi + int(gap))
    lo = max(0, lo)
    clear = max(2, int(gap * 0.8))
    ok = [not around[i:i + clear].any() for i in range(max(0, len(around) - clear))]
    cands = [lo + i for i, v in enumerate(ok) if v and (i == 0 or not ok[i - 1])]
    return float(min(cands, key=lambda c: abs(c - x))) if cands else None


def find_page_corners(img: Image.Image) -> list[list[float]]:
    """The paper's four corners, TL TR BR BL, as page fractions.

    The paper is the bright region against the darker scanner bed, felt or
    binding (an Otsu threshold on a small copy). A straight line is fitted
    to each of its four edges and the corners are where they meet, so a
    torn or rounded corner doesn't pull the result inward (taking the
    outermost paper pixel did). A page photographed at an angle still works.
    """
    small = img.convert("L").copy()
    small.thumbnail((500, 500))
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
    paper = lum > thr
    whole = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
    if paper.mean() < 0.3:  # no clear paper: the whole image
        return whole

    def edge(mask: np.ndarray, from_end: bool) -> tuple[np.ndarray, np.ndarray]:
        """Per row of `mask`: the first paper pixel from the start (or end).
        Only the middle 80% of rows, away from the corners."""
        n, m = mask.shape
        rows = np.arange(int(n * 0.1), int(n * 0.9))
        sub = mask[rows]
        has = sub.any(axis=1)
        pos = (m - 1 - np.argmax(sub[:, ::-1], axis=1)) if from_end else np.argmax(sub, axis=1)
        return rows[has].astype(float), pos[has].astype(float)

    def fit(t: np.ndarray, p: np.ndarray) -> tuple[float, float]:
        """p = a*t + b, refitted once without the worst outliers (tears, tabs)."""
        a, b = np.polyfit(t, p, 1)
        r = np.abs(p - (a * t + b))
        keep = r <= np.percentile(r, 80)
        return tuple(np.polyfit(t[keep], p[keep], 1)) if keep.sum() > 10 else (a, b)

    lines = {}
    for name, mask, end in (("left", paper, False), ("right", paper, True),
                            ("top", paper.T, False), ("bottom", paper.T, True)):
        t, p = edge(mask, end)
        if len(t) < 20:
            return whole
        lines[name] = fit(t, p)

    def meet(vert: tuple, horiz: tuple) -> list[float]:
        # vertical edge: x = a*y + b; horizontal edge: y = c*x + d
        a, b = vert
        c, d = horiz
        y = (c * b + d) / (1 - a * c)
        x = a * y + b
        return [min(1.0, max(0.0, (x + 0.5) / w)), min(1.0, max(0.0, (y + 0.5) / h))]

    return [meet(lines["left"], lines["top"]), meet(lines["right"], lines["top"]),
            meet(lines["right"], lines["bottom"]), meet(lines["left"], lines["bottom"])]


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
        clef, start, brace = music_start(band, local, left, right)
        found.append((st, band, local, left, right, clef, start, brace))

    # Where the clef guess failed, the start sits at the staff's edge. Clef
    # and key take about the same room on every staff of a page: borrow it.
    widths = [(s - c) / st["gap"] for st, _, _, _, _, c, s, _ in found if s - c >= 2 * st["gap"]]
    typical = float(np.median(widths)) if widths else 4.0

    systems, crops = [], []
    for st, band, local, left, right, clef, start, brace in found:
        if start - clef < 2 * st["gap"]:
            clef = left
            start = min(right, left + int(typical * st["gap"]))
        # search a little past the ruled end: a final bar line often sits on it
        reach = min(band.shape[1], right + int(st["gap"]))
        bars = find_barlines(band, local, left, reach, skip_to=start)
        if bars:
            right = max(right, int(max(max(b["x0"], b["x1"]) for b in bars)) + 2)
        # End the staff just after its last bar line when the ruled lines
        # beyond it are blank. Music there (a missed bar line, a bar that
        # runs on to the next line) keeps the full length.
        if bars:
            last = int(max(max(b["x0"], b["x1"]) for b in bars))
            tail = last + int(st["gap"] * 0.5)
            if right - tail > st["gap"] * 1.5 and note_ink(band, local, tail, right) < 0.01:
                right = tail
            else:
                # Ink between the staff lines that stops for good well before
                # the ruled end (a movement ending mid-line, text such as "da
                # capo" above or below it, a flourish): end the staff there.
                gap = st["gap"]
                mids = [(a + b) // 2 for a, b in zip(local["lines"], local["lines"][1:])]
                inner = (band[mids, tail:right] < 120).any(axis=0)
                on = np.flatnonzero(inner)
                end = tail + (int(on[-1]) + 1 if len(on) else 0)
                # (Limiting this to short tails, for fear of cutting music
                # after a missed bar line, lost most of the gain; the lines
                # it flagged turned out to end there, untrimmed by hand.)
                if right - end >= gap * TAIL_BLANK:
                    right = max(tail, end + int(gap * 0.5))
        # the staff starts half a space before its clef's leftmost ink
        bound = brace if brace > left else None
        left = max(bound or 0, clef_left(band, local, clef, left, bound) - int(st["gap"] * 0.5))
        # how the staff rises and falls along its length (see labels.bend_at)
        px, py = zip(*st["path"])
        xs = np.linspace(left, right, 5)
        bend = [(float(np.interp(x, px, py)) - st["top"]) / h for x in xs]
        crops.append({"gap": st["gap"], "top_px": st["top"], "bottom_px": st["bottom"],
                      "x_left": left, "x_right": right})
        systems.append({
            "top": st["top"] / h,
            "bottom": st["bottom"] / h,
            "left": left / w,
            "right": right / w,
            # where the music starts, after clef and key signature (a guess)
            "start": start / w,
            "bend": bend,
            "barlines": [
                {"x0": b["x0"] / w, "x1": b["x1"] / w, "kind": b["kind"]} for b in bars
            ],
        })
    # how far each staff's own ink reaches above and below it
    for sys_, (above, below) in zip(systems, crop_margins(g, crops)):
        sys_["above"], sys_["below"] = above, below
    return systems
