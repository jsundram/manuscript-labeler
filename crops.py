"""Learned crop edges: how far each staff's bar images reach above and
below it, learned from the editor's reviewed crops.

What a crop should hold (the editor, 2026-10-09): first, everything a
reader (or a model) needs to understand the music on this staff, and
nothing that could confuse it, such as a stray dynamic or another staff's
markings; then, as little as possible, for the synoptic score.
detect.crop_margins reaches for a staff's own ink with fixed rules; this
model chooses among candidate edges the way the editor does.

Each side of a staff (above, below) is looked at outward from its outer
line, in a band straightened along the staff (its bend), from its music
start to its last bar line. Candidate edges every quarter space (the
editor's grid), from MIN_EDGE out to the neighbouring staff (or an empty
ruled staff, which detection doesn't keep, or the page's edge). Each
candidate is described by the ink it would keep and cut, and whose ink
it is: with the ruled lines taken out (where nothing crosses them), a
blob reaching into this staff is its own (notes, stems, slurs from
them), one reaching into the neighbour is the neighbour's, and a
floating one (a dynamic, text, an ornament) goes to the staff whose ink
is nearer it. Also: today's rule's edge (crop_margins), which the editor
often accepted. A gradient-boosted model learns how far each candidate is
from the editor's edge, and a side's crop is its nearest.

Which crops to learn from: the editor's standard tightened over time, and
crops accepted as proposed in early sources often reach into an empty
staff or over a movement title. OLDER_CROPS lists those sources (PDF
names without .pdf): there only the crops the editor changed are learned
from.
Every other source's crops count NEW_WEIGHT times.

Measured (experiments/crops, leaving each source out in turn; 507
reviewed staves), within half a staff space of the editor's edge: on the
newest pages (the 8 held-out test pages) above 64% -> 66%, below 72% ->
84%; on all, above 70% -> 72%, below 68% -> 77%. What it still misses is
mostly above the staff: a floating dynamic that belongs to the staff
above, or a movement's title, which the newest crops leave out and older
ones kept.
"""

import hashlib
import json
import pickle
from pathlib import Path

import numpy as np

import detect
import labels

VERSION = 1         # bump when the features or the training data change
BAND = 12           # staff spaces looked at beyond each outer line
ROWS_PER_SPACE = 8  # the band's rows per staff space
SUB = 4             # page rows sampled per band row (a space is ~15-30 px), so thin strokes stay
INK = 120           # gray below this is ink (detect.py's threshold)
MIN_EDGE = 0.5      # the closest candidate edge, in staff spaces
STEP = 0.25         # between candidates: the editor's grid
LINE = 0.2          # staff spaces either side of a ruled line taken out
RULED = 0.4         # a row this inked across is a ruled line (or the scan's edge)
NEW_WEIGHT = 3.0    # a crop from a source not listed as older, against an older one the editor changed
# Sources labelled before the editor's crop standard settled (the editor's list)
OLDER_CROPS = frozenset({"D-B_KHM-602", "D-B_KHM-603", "F-Po_RES-507-14", "F-Pn_Vma-ms-1067-1"})

R = ROWS_PER_SPACE
Q0 = (BAND + 4) * R  # the outer line's row in an oriented band
FEATURES = ["t", "room", "t_frac", "room_left", "ink_win", "ink_win_min", "ink_row",
            "own_kept", "own_cut", "nb_kept", "nb_cut", "float_kept", "float_cut", "floatnb_kept", "floatnb_cut",
            "t-allreach90", "t-allreach98", "t-allreachmax", "both_kept", "both_cut",
            "cols_own_beyond", "t-reach90", "t-reach98", "t-reachmax", "cols_nb_inside",
            "nb0-t", "nb2-t", "nb10-t", "has_nb", "is_above", "t-today", "|t-today|", "empty_staff"]


# -- the band around a staff ---------------------------------------------------

def extent(s: dict) -> tuple[float, float]:
    """The columns a staff's bars are cut from: its music start to its last
    bar line (page fractions)."""
    x0 = s.get("start", s["left"])
    last = max(((b["x0"] + b["x1"]) / 2 for b in s.get("barlines", [])), default=s["right"])
    return x0, max(last, x0 + 0.01)


def band(g: np.ndarray, s: dict) -> np.ndarray:
    """The staff's band, straightened along its bend, as ink: row r is
    r / ROWS_PER_SPACE - BAND staff spaces from its top line."""
    h, w = g.shape
    x0, x1 = extent(s)
    sp = (s["bottom"] - s["top"]) / 4
    xs = np.arange(int(x0 * w), max(int(x0 * w) + 1, int(x1 * w)))
    offs = np.array([labels.bend_at(s, x / w) for x in xs])
    rows = np.arange((4 + 2 * BAND) * R + 1) / R - BAND
    out = np.zeros((len(rows), len(xs)), bool)
    xi = np.clip(xs, 0, w - 1)[None, :]
    for k in range(SUB):  # every page row a band row spans
        ys = (s["top"] + offs[None, :] + (rows[:, None] + (k / SUB - 0.5) / R) * sp) * h
        yi = np.clip(np.round(ys).astype(int), 0, h - 1)
        out |= (g[yi, xi] < INK) & (ys >= 0) & (ys <= h - 1)
    return out


def rooms(systems: list[dict], s: dict) -> tuple[float, float]:
    """(above, below): staff spaces from the staff's outer line to the
    nearest staff's outer line facing it, over the same columns, else to
    the page's edge if it's within the band; NaN without either."""
    x0, x1 = extent(s)
    xm = (x0 + x1) / 2
    sp = (s["bottom"] - s["top"]) / 4
    top = s["top"] + labels.bend_at(s, xm)
    up = down = np.nan
    for o in systems:
        if o is s or o["right"] < x0 or o["left"] > x1:
            continue
        ot, ob = o["top"] + labels.bend_at(o, xm), o["bottom"] + labels.bend_at(o, xm)
        if ob <= top:
            up = np.nanmin([up, (top - ob) / sp])
        elif ot >= top + 4 * sp:
            down = np.nanmin([down, (ot - top) / sp - 4])
    if not np.isfinite(up) and top / sp < BAND:
        up = top / sp
    if not np.isfinite(down) and (1 - top) / sp - 4 < BAND:
        down = (1 - top) / sp - 4
    return up, down


# -- candidate edges -------------------------------------------------------------

def oriented(b: np.ndarray, side: str) -> np.ndarray:
    """The band with outward as increasing rows: the side's outer line at
    row Q0, the staff's lines at Q0 - 4R .. Q0."""
    return b[::-1] if side == "above" else b


def ruled(o: np.ndarray, limit: float) -> float:
    """Spaces from the outer line to the nearest ruled line beyond it, before
    `limit`, of a staff with no music (detection drops empty staves) or a
    scan's edge: a row inked most of the way across with another a space
    further. NaN without one."""
    frac = o.mean(axis=1)
    hi = min(len(frac) - 1, Q0 + int(limit * R))
    for q in range(Q0 + int(1.5 * R), hi):
        if frac[q] > RULED and frac[q] >= frac[max(0, q - 1):q + 2].max():
            nxt = frac[q + int(0.7 * R): q + int(1.3 * R) + 1]
            if len(nxt) and nxt.max() > RULED:
                return (q - Q0) / R
    return np.nan


def candidates(b: np.ndarray, nb: float, side: str, today: float) -> tuple[np.ndarray, np.ndarray]:
    """(candidate edges in staff spaces beyond the outer line, their
    FEATURES). `nb`: staff spaces to the neighbouring staff (rooms), NaN
    for none; `today`: crop_margins' edge."""
    from scipy import ndimage

    o = oriented(b, side).copy()
    n_rows, w = o.shape
    u = (np.arange(n_rows) - Q0) / R  # spaces beyond the outer line (negative: inside the staff)
    empty = ruled(o, nb if np.isfinite(nb) else BAND)
    if np.isfinite(empty):
        nb = empty  # an empty staff (or the scan's edge) bounds the crop like a neighbour
    lines = [Q0 - k * R for k in range(5)]
    if np.isfinite(nb):
        lines += [Q0 + int(round((nb + k) * R)) for k in range(5)]
    for q in lines:  # taken out, except where a stroke crosses it (a stem, a slur)
        lo, hi = max(0, q - int(LINE * R)), min(n_rows, q + int(LINE * R) + 1)
        if lo == 0 or hi >= n_rows:
            o[lo:hi] = False
            continue
        o[lo:hi] &= (o[lo - 1] & o[hi])[None, :]
    lab, n = ndimage.label(o, structure=np.ones((3, 3), bool))
    rr = np.arange(n_rows)[:, None]
    # each blob's kind: 1 own, 2 the neighbour's, 4 both (a slur or stem
    # across), and floating ones 5 nearer this staff, 6 nearer the neighbour
    kind = np.zeros(n + 1, int)
    boxes = ndimage.find_objects(lab)
    for j, sl in enumerate(boxes):
        rs = sl[0]
        own = rs.start <= Q0 - 0.5 * R  # reaches into the staff, past its outer space
        theirs = np.isfinite(nb) and rs.stop - 1 >= Q0 + (nb + 0.5) * R
        kind[j + 1] = 4 if own and theirs else 1 if own else 2 if theirs else 3
    K = kind[lab]
    own_edge = np.where(K == 1, rr, Q0).max(axis=0)
    nb_line = Q0 + nb * R if np.isfinite(nb) else n_rows
    nb_edge = np.minimum(np.where(K == 2, rr, n_rows).min(axis=0).astype(float), nb_line)
    for j, sl in enumerate(boxes):
        if kind[j + 1] == 3:
            rs, cs = sl
            d_own = rs.start - np.median(own_edge[cs])
            d_nb = np.median(nb_edge[cs]) - (rs.stop - 1)
            kind[j + 1] = 5 if d_own <= d_nb else 6
    K = kind[lab]

    per_row = lambda k: (K == k).sum(axis=1) / max(w, 1)
    own_r, nb_r, both_r, fl_r, flnb_r = (per_row(k) for k in (1, 2, 4, 5, 6))
    all_r = o.sum(axis=1) / max(w, 1)
    beyond = u > 0
    cum = lambda r: np.cumsum(np.where(beyond, r, 0))  # from the outer line out to each row
    c_own, c_nb, c_fl, c_flnb, c_both, c_all = (cum(r) for r in (own_r, nb_r, fl_r, flnb_r, both_r, all_r))
    farthest = lambda k: np.where((K == k).any(axis=0), u[np.where(K == k, rr, 0).max(axis=0)], 0.0)
    reach, fl_reach = farthest(1), farthest(5)  # per column, how far own ink reaches out
    has_nb = (K == 2).any(axis=0)
    first_nb = np.where(has_nb, u[np.argmax(K == 2, axis=0)], np.nan)
    q = lambda a, p: float(np.nanpercentile(a, p)) if np.isfinite(a).any() else np.nan
    reach_q = [q(reach, p) for p in (90, 98, 100)]
    all_q = [q(np.maximum(reach, fl_reach), p) for p in (90, 98, 100)]
    nb_q = [q(first_nb, p) for p in (0, 2, 10)]
    room = nb if np.isfinite(nb) else BAND - 0.5
    cands = np.arange(MIN_EDGE, min(BAND - 0.5, room * 1.1) + 1e-9, STEP)
    feats = []
    for t in cands:
        qi = min(n_rows - 1, Q0 + int(round(t * R)))
        win = slice(max(0, qi - R // 4), qi + R // 4 + 1)
        cut = lambda c: c[-1] - c[qi]
        feats.append([
            t, room, t / room, room - t,
            all_r[win].mean(), all_r[win].min(), all_r[qi],
            c_own[qi], cut(c_own), c_nb[qi], cut(c_nb), c_fl[qi], cut(c_fl), c_flnb[qi], cut(c_flnb),
            t - all_q[0], t - all_q[1], t - all_q[2], c_both[qi], cut(c_both),
            np.mean(reach > t), t - reach_q[0], t - reach_q[1], t - reach_q[2],
            np.mean(first_nb < t) if has_nb.any() else 0.0,
            *[v - t if np.isfinite(v) else 99.0 for v in nb_q],
            float(np.isfinite(nb)), float(side == "above"), t - today, abs(t - today), float(np.isfinite(empty)),
        ])
    return cands, np.array(feats, float).reshape(len(cands), len(FEATURES))


def sides(g: np.ndarray, systems: list[dict], todays: dict) -> list[tuple[dict, str, np.ndarray, np.ndarray]]:
    """(staff, side, candidates, features) for each side of each staff.
    `todays`: id(staff) -> crop_margins' (above, below)."""
    out = []
    for s in systems:
        b = band(g, s)
        up, down = rooms(systems, s)
        for side, nb, today in (("above", up, todays[id(s)][0]), ("below", down, todays[id(s)][1])):
            c, X = candidates(b, nb, side, today)
            out.append((s, side, c, X))
    return out


def todays_crops(g: np.ndarray, systems: list[dict]) -> dict:
    """id(staff) -> what detect.crop_margins proposes for it, on these staves."""
    h, w = g.shape
    ss = sorted(systems, key=lambda s: s["top"])
    crops = []
    for s in ss:
        b = labels.bend_at(s, (s["left"] + s["right"]) / 2)
        crops.append({"gap": (s["bottom"] - s["top"]) / 4 * h, "top_px": int((s["top"] + b) * h),
                      "bottom_px": int((s["bottom"] + b) * h), "x_left": s["left"] * w, "x_right": s["right"] * w})
    return {id(s): m for s, m in zip(ss, detect.crop_margins(g, crops))}


# -- proposing -------------------------------------------------------------------

def propose(g: np.ndarray, systems: list[dict], model: dict) -> None:
    """Set each detected staff's `above` and `below` (staff spaces) from the
    model, in place. `systems` as detect.detect_page gives them, with
    crop_margins' crops, which the model weighs."""
    todays = {id(s): (s.get("above", 2.5), s.get("below", 2.5)) for s in systems}
    for s, side, c, X in sides(g, systems, todays):
        if len(c):
            s[side] = choose(model, c, X)


# -- training --------------------------------------------------------------------

def reviewed_pages(edition: Path, data: Path = labels.DATA) -> list[tuple[Path, int, dict]]:
    """(pdf, page number, labels page) for every reviewed music page with a
    staff whose crop the editor set."""
    out = []
    for lp, pdf in labels.labels_files(edition, data):
        try:
            doc = labels.migrate(json.loads(lp.read_text()))
        except (ValueError, OSError, labels.NewerSchema):
            continue
        for n, p in labels.sorted_pages(doc):
            if p.get("status") == "reviewed" and p.get("kind") == "music" and \
                    any("above" in s and "below" in s for s in p.get("systems", [])):
                out.append((pdf, n, p))
    return out


def truth(p: dict) -> list:
    """What the model learns from on one page: its staves and their crops."""
    return [(s.get("top"), s.get("bottom"), s.get("above"), s.get("below"), s.get("start"), s.get("bend"),
             [(b.get("x0"), b.get("x1")) for b in s.get("barlines", [])]) for s in p.get("systems", [])]


def key(pages: list, older: set) -> str:
    h = hashlib.sha1(f"v{VERSION}:{FEATURES}:{sorted(older)}".encode())
    for pdf, n, p in pages:
        h.update(f"{pdf.name}:{n}:{truth(p)}".encode())
    return h.hexdigest()[:16]


def examples(g: np.ndarray, page: dict, old: bool) -> list[dict]:
    """Each side of each staff on a reviewed page whose crop the editor set:
    its candidates, features, the editor's edge, today's, and whether and
    how much the model learns from it. On an older source (OLDER_CROPS)
    only the sides the editor changed from today's rule are learned from;
    elsewhere every one, weighing NEW_WEIGHT. "Accepted as proposed" is
    today's rule recomputed on the editor's staves, which detection ran on
    its own staves: close, not exact, so a few accepted crops are learned
    from anyway (and the rule's edge as a feature differs as little)."""
    systems = page.get("systems", [])
    todays = todays_crops(g, systems)
    out = []
    for s, side, c, F in sides(g, systems, todays):
        if "above" not in s or "below" not in s or not len(c):
            continue
        today = todays[id(s)][0 if side == "above" else 1]
        out.append({"staff": s["id"], "side": side, "cands": c, "X": F, "truth": s[side], "today": today,
                    # an older source's crop accepted as proposed, before the standard settled: not learned
                    "learn": not (old and s[side] == today), "weight": 1.0 if old else NEW_WEIGHT})
    return out


def fit(ex: list[dict]) -> dict:
    """The model from examples (those to learn from): how far each candidate
    is from the editor's edge (capped at 3 spaces)."""
    from sklearn.ensemble import HistGradientBoostingRegressor

    ex = [e for e in ex if e["learn"]]
    if not ex:
        raise ValueError("no reviewed crops to learn from")
    X = np.concatenate([e["X"] for e in ex])
    y = np.concatenate([np.minimum(np.abs(e["cands"] - e["truth"]), 3.0) for e in ex])
    wt = np.concatenate([np.full(len(e["cands"]), e["weight"]) for e in ex])
    reg = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, max_leaf_nodes=15, random_state=0)
    return {"reg": reg.fit(X, y, sample_weight=wt), "sides": len(ex), "version": VERSION}


def choose(model: dict, cands: np.ndarray, X: np.ndarray) -> float:
    """The candidate edge the model puts nearest the editor's."""
    return float(cands[int(np.argmin(model["reg"].predict(X)))])


def train(pages: list, gray, older: set) -> dict:
    """A model from (pdf, page, labels) pages; gray(pdf, n) gives the page as
    a gray array (as detection reads it)."""
    ex = [e for pdf, n, p in pages for e in examples(gray(pdf, n), p, pdf.stem in older)]
    return {**fit(ex), "pages": len(pages)}


def load_or_train(edition: Path, cache: Path, gray, data: Path = labels.DATA) -> dict | None:
    """The model for this edition's reviewed crops, from the cache if they
    haven't changed, else trained now. None if there's nothing to learn from."""
    pages = reviewed_pages(edition, data)
    if not pages:
        return None
    older = OLDER_CROPS
    path = cache / "models" / f"crops-{key(pages, older)}.pkl"
    if path.exists():
        try:
            return pickle.loads(path.read_bytes())
        except Exception:
            pass
    model = train(pages, gray, older)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(pickle.dumps(model))
    tmp.replace(path)
    for old in path.parent.glob("crops-*.pkl"):
        if old != path:
            old.unlink()
    return model
