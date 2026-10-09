"""The labels file: schema, migration, validation, bar numbering, bar export.

Everything here is pure data in, data out, so it can be tested without the
server or a browser. The front end has its own copy of the numbering rules
(`static/app.js`, `numberBars`) for live display; this module is the
authority for what gets written to disk.
"""

import math
import re
from fractions import Fraction
from pathlib import Path

SCHEMA = 4         # of the labels file
EXPORT_SCHEMA = 1  # of the bar export (the edition's build checks it): additive changes keep it

PARTS = ["vn1", "vn2", "va", "vc", "score"]
CLEFS = ["treble", "alto", "tenor", "bass"]
DEFAULT_CLEF = {"vn1": "treble", "vn2": "treble", "va": "alto", "vc": "bass", "score": "treble"}
PAGE_KINDS = ["music", "title", "blank", "other"]
PAGE_STATUSES = ["auto", "edited", "reviewed"]
BARLINE_KINDS = ["single", "double", "repeat_start", "repeat_end", "repeat_both", "final"]
MARK_KINDS = ["text", "tempo", "title", "dynamic", "stray", "unclear", "other", "signature"]  # title: a movement's ("Trio")
# what a staff's start, or a signature mark, records as written: a clef, a key
# signature (sharps > 0, flats < 0; its mode isn't written) and a time signature
SIG_FIELDS = ("clef", "key", "time")
TIME_SIGNATURE = re.compile(r"\d+/\d+|C|C/")  # 2/4 ... and the common- and cut-time signs
SYSTEM_ROLES = ["part", "cue"]  # a cue staff is drawn but not counted

# Vertical margin of a bar's crop, in staff spaces above and below the staff.
QUAD_MARGIN = 2.5


class SchemaError(ValueError):
    pass


class NewerSchema(SchemaError):
    """The file was written by a newer version of this tool. Never overwrite it."""


# from_version -> function(doc) -> doc at from_version + 1
def _to_3(doc: dict) -> dict:
    """3: clef marks become signature marks, which may also hold a key and
    time; nothing else changes (each box, at a line's start or mid-line,
    keeps its place and id)."""
    for p in doc.get("pages", {}).values():
        for m in p.get("marks", []) if isinstance(p, dict) else []:
            if isinstance(m, dict) and m.get("kind") == "clef":
                m["kind"] = "signature"
    return doc


MIGRATIONS: dict = {
    # 2 adds clef marks (kind "clef", with a `clef`); nothing to change in
    # older files, but a tool that knows only 1 must refuse them, not drop them
    1: lambda doc: doc,
    2: _to_3,
    # 4 adds movement-title marks (kind "title"); nothing to change in older
    # files, but a tool that knows only 3 must refuse them, not reject them
    3: lambda doc: doc,
}


def migrate(doc: dict) -> dict:
    v = doc.get("schema")
    if not isinstance(v, int) or v < 1:
        raise SchemaError(f"missing or bad schema version: {v!r}")
    if v > SCHEMA:
        raise NewerSchema(f"file is schema {v}; this tool only knows up to {SCHEMA}")
    while v < SCHEMA:
        doc = MIGRATIONS[v](doc)
        v += 1
        doc["schema"] = v
    return doc


def new_doc(source: dict) -> dict:
    return {"schema": SCHEMA, "source": source, "pages": {}}


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def validate(doc) -> list[str]:
    """Problems that would make the file unsafe to write. Empty list = OK."""
    errs: list[str] = []
    if not isinstance(doc, dict):
        return ["document is not an object"]
    if doc.get("schema") != SCHEMA:
        errs.append(f"schema must be {SCHEMA}")
    if not isinstance(doc.get("source"), dict):
        errs.append("source must be an object")
    pages = doc.get("pages")
    if not isinstance(pages, dict):
        return errs + ["pages must be an object"]
    ids: set[str] = set()

    def unique(i, where):
        if not isinstance(i, str) or not i:
            errs.append(f"{where}: missing id")
        elif i in ids:
            errs.append(f"{where}: duplicate id {i}")
        ids.add(i)

    for key, p in pages.items():
        w = f"page {key}"
        if not key.isdigit() or int(key) < 1:
            errs.append(f"{w}: page keys are page numbers from 1")
        if not isinstance(p, dict):
            errs.append(f"{w}: not an object")
            continue
        if p.get("status") not in PAGE_STATUSES:
            errs.append(f"{w}: bad status {p.get('status')!r}")
        if p.get("kind") not in PAGE_KINDS:
            errs.append(f"{w}: bad kind {p.get('kind')!r}")
        if p.get("part") not in PARTS + [None]:
            errs.append(f"{w}: bad part {p.get('part')!r}")
        if p.get("clef") not in CLEFS + [None]:
            errs.append(f"{w}: bad clef {p.get('clef')!r}")
        c = p.get("corners")
        if c is not None:
            pts = c.get("points") if isinstance(c, dict) else None
            if not (isinstance(pts, list) and len(pts) == 4
                    and all(isinstance(q, list) and len(q) == 2 and all(_num(v) for v in q) for q in pts)):
                errs.append(f"{w}: corners.points must be 4 [x, y] pairs")
        rs = p.get("rejected_staves", [])
        if not (isinstance(rs, list) and all(_num(v) for v in rs)):
            errs.append(f"{w}: rejected_staves must be a list of numbers")
        for s in p.get("systems", []):
            ws = f"{w} system {s.get('id')}"
            unique(s.get("id"), ws)
            for f in ("top", "bottom", "left", "right"):
                if not _num(s.get(f)):
                    errs.append(f"{ws}: {f} must be a number")
            bend = s.get("bend")
            if bend is not None and not (isinstance(bend, list) and len(bend) >= 2 and all(_num(v) for v in bend)):
                errs.append(f"{ws}: bend must be a list of numbers")
            rej = s.get("rejected", [])
            if not (isinstance(rej, list) and all(_num(v) for v in rej)):
                errs.append(f"{ws}: rejected must be a list of numbers")
            for f in ("above", "below", "start"):
                if f in s and not _num(s[f]):
                    errs.append(f"{ws}: {f} must be a number")
            if s.get("role", "part") not in SYSTEM_ROLES:
                errs.append(f"{ws}: bad role")
            errs += [f"{ws}: bad {f} {s[f]!r}" for f in SIG_FIELDS if f in s and not sig_valid(f, s[f])]
            for b in s.get("barlines", []):
                wb = f"{ws} barline {b.get('id')}"
                unique(b.get("id"), wb)
                if not (_num(b.get("x0")) and _num(b.get("x1"))):
                    errs.append(f"{wb}: x0 and x1 must be numbers")
                if b.get("kind") not in BARLINE_KINDS:
                    errs.append(f"{wb}: bad kind {b.get('kind')!r}")
                for f in ("above", "below"):
                    if f in b and not _num(b[f]):
                        errs.append(f"{wb}: {f} must be a number")
                c = b.get("bar_count", 1)
                if not isinstance(c, int) or isinstance(c, bool) or c < 0:
                    errs.append(f"{wb}: bar_count must be a whole number >= 0")
        for m in p.get("marks", []):
            wm = f"{w} mark {m.get('id')}"
            unique(m.get("id"), wm)
            if not all(_num(m.get(f)) for f in ("x", "y", "w", "h")):
                errs.append(f"{wm}: x, y, w, h must be numbers")
            if m.get("kind") not in MARK_KINDS:
                errs.append(f"{wm}: bad kind {m.get('kind')!r}")
            if not isinstance(m.get("text_auto", False), bool):
                errs.append(f"{wm}: text_auto must be true or false")
            if m.get("kind") == "signature":
                if not any(f in m for f in SIG_FIELDS):
                    errs.append(f"{wm}: a signature mark needs a clef, key or time")
                errs += [f"{wm}: bad {f} {m[f]!r}" for f in SIG_FIELDS if f in m and not sig_valid(f, m[f])]
    return errs


def round_floats(x, places: int = 4):
    """Keep the file diff-friendly: 1e-4 of a page is well under a pixel."""
    if isinstance(x, float):
        return round(x, places)
    if isinstance(x, dict):
        return {k: round_floats(v, places) for k, v in x.items()}
    if isinstance(x, list):
        return [round_floats(v, places) for v in x]
    return x


# ---------------------------------------------------------------- numbering

ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]


def roman(n: int) -> str:
    return ROMAN[n - 1] if 1 <= n <= len(ROMAN) else str(n)


def _mid(b: dict) -> float:
    return (b["x0"] + b["x1"]) / 2


def sorted_pages(doc: dict) -> list[tuple[int, dict]]:
    return sorted(((int(k), p) for k, p in doc["pages"].items()), key=lambda kp: kp[0])


def counted_systems(page: dict) -> list[dict]:
    return sorted((s for s in page.get("systems", []) if s.get("role", "part") == "part"),
                  key=lambda s: s["top"])


def number_bars(doc: dict) -> list[dict]:
    """Every bar in reading order, with its derived part, movement and number.

    A bar runs from the previous bar line (or the system's music start) to a
    bar line. Numbers run on through a part's pages and restart after a bar
    line marked `ends_movement`. `bar_count` 0 is a pickup: it shares the
    number before it (0 at the start of a movement) and doesn't advance.
    """
    state: dict[str, dict] = {}
    out = []
    for n, page in sorted_pages(doc):
        part = page.get("part")
        if page.get("kind") != "music" or not part:
            continue
        st = state.setdefault(part, {"mvt": 1, "bar": 1})
        for s in counted_systems(page):
            prev = None
            for b in sorted(s.get("barlines", []), key=_mid):
                count = b.get("bar_count", 1)
                out.append({
                    "part": part,
                    "movement": roman(st["mvt"]),
                    "bar": st["bar"] if count else st["bar"] - 1,
                    "count": count,
                    "page": n,
                    "system": s,
                    "left": prev,
                    "right": b,
                })
                st["bar"] += count
                if b.get("ends_movement"):
                    st["mvt"] += 1
                    st["bar"] = 1
                prev = b
    return out


def bend_at(system: dict, x: float) -> float:
    """Vertical offset of the staff at x (page fraction).

    `bend` is optional: offsets of the staff at 5 evenly spaced points from
    `left` to `right`, linearly interpolated (flat beyond the ends). It
    follows staves that slant or curl with the paper. `top` and `bottom`
    are the staff without the offset.
    """
    bend = system.get("bend")
    if not bend:
        return 0.0
    left, right = system["left"], system["right"]
    if right <= left:
        return bend[0]
    t = (x - left) / (right - left) * (len(bend) - 1)
    t = min(max(t, 0.0), len(bend) - 1.0)
    i = min(int(t), len(bend) - 2)
    return bend[i] + (bend[i + 1] - bend[i]) * (t - i)


def sig_valid(field: str, v) -> bool:
    if field == "clef":
        return v in CLEFS
    if field == "key":
        return isinstance(v, int) and not isinstance(v, bool) and -7 <= v <= 7
    return isinstance(v, str) and bool(TIME_SIGNATURE.fullmatch(v))


def mark_staff(page: dict, m: dict) -> dict | None:
    """The staff a mark's box is on: the nearest to its centre, bend and all."""
    systems = page.get("systems", [])
    if not systems:
        return None
    cx, cy = m["x"] + m["w"] / 2, m["y"] + m["h"] / 2

    def dist(s):
        d = bend_at(s, cx)
        return max(s["top"] + d - cy, 0.0, cy - s["bottom"] - d)
    return min(systems, key=lambda s: (dist(s), s["top"]))


def sig_changes(page: dict, field: str) -> list[tuple[dict, float, object]]:
    """Where a counted staff's clef, key or time (`field`) is written on the
    page, in reading order: (staff, x, value). A staff's own `field` is
    written at its start (x -inf); a signature mark's on the staff nearest
    its centre (one on a cue staff changes only the cue), at its centre,
    or at the bar line its box starts at (its left edge within its own
    width after it, or half that before): a change written at the start of
    a bar governs the whole bar."""
    out = []
    for s in page.get("systems", []):
        if s.get("role", "part") == "part" and sig_valid(field, s.get(field)):
            out.append((s, -math.inf, s[field]))
    for m in page.get("marks", []):
        if m.get("kind") != "signature" or not sig_valid(field, m.get(field)):
            continue
        s = mark_staff(page, m)
        if s is None or s.get("role", "part") != "part":
            continue
        at = [_mid(b) for b in s.get("barlines", []) if _mid(b) - m["w"] / 2 <= m["x"] <= _mid(b) + m["w"]]
        out.append((s, min(at, key=lambda b: abs(m["x"] - b)) if at else m["x"] + m["w"] / 2, m[field]))
    return sorted(out, key=lambda e: (e[0]["top"], e[1]))


def clef_marks(page: dict) -> list[tuple[dict, float, str]]:
    """Where a counted staff's clef changes on the page (sig_changes)."""
    return sig_changes(page, "clef")


def clefs_between(page: dict, system: dict, x0: float | None, x1: float, marks: list | None = None) -> list[str]:
    """The clefs in force on a counted staff from x0 to x1: the one at x0,
    then any it changes to before x1. x0 None means the line's first bar,
    which a clef written before the music start (the line's own clef)
    governs from its beginning. The page's `clef` holds from its top until
    a clef mark changes it, and a change holds through later staves until
    the next; a staff's own `clef` is written at its start. On a score
    page, where each staff is its own instrument, a change holds only on
    its own staff. `marks`: clef_marks(page), if at hand."""
    marks = clef_marks(page) if marks is None else marks
    if page.get("part") == "score":
        marks = [e for e in marks if e[0] is system]
    start = system.get("start", system["left"]) if x0 is None else x0
    now = page.get("clef")
    for s, x, clef in marks:
        if (s["top"] < system["top"] and s is not system) or (s is system and x <= start):
            now = clef
    out = [now] if now else []
    for s, x, clef in marks:
        if s is system and start < x < x1 and (not out or out[-1] != clef):
            out.append(clef)
    return out


def bar_quad(system: dict, left: dict | None, right: dict, margin: float = QUAD_MARGIN) -> list:
    """Corners TL, TR, BR, BL in page fractions.

    Each side follows the lean of its bar line and the staff's local height
    (`bend`). The crop reaches `above` / `below` staff spaces beyond the
    staff, so notes and markings outside it are kept: the bar's own values
    (set on the bar line that ends it) if any, else the staff's, else
    `margin`. Neighbouring staves' crops may overlap.
    """
    space = (system["bottom"] - system["top"]) / 4
    above = right.get("above", system.get("above", margin))
    below = right.get("below", system.get("below", margin))

    def side(edge):
        if edge is None:  # first bar of the system: from the music start
            x = system.get("start", system["left"])
            x0 = x1 = x
        else:
            x0, x1 = edge["x0"], edge["x1"]
        d = bend_at(system, (x0 + x1) / 2)
        top, bottom = system["top"] + d, system["bottom"] + d
        yt = max(0.0, top - above * space)
        yb = min(1.0, bottom + below * space)

        def x_at(y):
            return x0 + (x1 - x0) * (y - top) / (bottom - top) if bottom > top else x0
        return [x_at(yt), yt], [x_at(yb), yb]

    lt, lb = side(left)
    rt, rb = side(right)
    return [lt, rt, rb, lb]


def bars_export(doc: dict) -> dict:
    """The flat file the synoptic build reads (`<pdf>.bars.json`)."""
    numbered = number_bars(doc)
    pages = dict(sorted_pages(doc))

    # A mark belongs to the bar whose crop holds its centre; one left of a
    # line's music, within its height, to that line's first bar. A tempo
    # outside every crop (written above the music) belongs to the first bar
    # of the nearest staff below it; any other mark outside every crop ("Da capo
    # il Minuetto" under the last line, "Segue il Trio") to the last bar of
    # the nearest staff that its text reaches.
    quads = [bar_quad(nb["system"], nb["left"], nb["right"]) for nb in numbered]
    clef_changes = {n: clef_marks(p) for n, p in pages.items()}
    owner: dict[str, int] = {}
    for n, page in pages.items():
        idx = [i for i, nb in enumerate(numbered) if nb["page"] == n]
        for m in page.get("marks", []):
            cx, cy = m["x"] + m["w"] / 2, m["y"] + m["h"] / 2
            for i in idx:
                xs = [q[0] for q in quads[i]]
                ys = [q[1] for q in quads[i]]
                if min(xs) <= cx <= max(xs) and min(ys) <= cy <= max(ys):
                    owner.setdefault(m["id"], i)
            if m["id"] not in owner and idx:
                # written wholly left of a line's music, within its height
                # (a "Trio" before the clef): that line's first bar, the
                # nearest staff's where crops overlap
                beside = [i for i in idx if numbered[i]["left"] is None
                          and min(q[1] for q in quads[i]) <= cy <= max(q[1] for q in quads[i])
                          and m["x"] + m["w"] <= min(q[0] for q in quads[i])]
                if beside:
                    def to_staff(i):
                        s = numbered[i]["system"]
                        return abs((s["top"] + s["bottom"]) / 2 - cy)
                    owner[m["id"]] = min(beside, key=to_staff)
                    continue
                below = [i for i in idx if numbered[i]["system"]["top"] > cy]
                if m.get("kind") in ("tempo", "title") and below:
                    owner[m["id"]] = min(below, key=lambda i: (numbered[i]["system"]["top"], i))
                elif m.get("kind") not in ("tempo", "title"):
                    # the staff it's written under (or over), then the last
                    # bar its text reaches: "Da capo" and "Segue" refer to
                    # the end of the music they're written under, wherever
                    # along it the text happens to begin
                    def vdist(i):
                        ys = [q[1] for q in quads[i]]
                        return max(min(ys) - cy, 0, cy - max(ys))
                    staff = numbered[min(idx, key=vdist)]["system"]
                    line = [i for i in idx if numbered[i]["system"] is staff]
                    reached = [i for i in line if min(q[0] for q in quads[i]) <= m["x"] + m["w"]]
                    owner[m["id"]] = reached[-1] if reached else line[0]

    bars = []
    for i, nb in enumerate(numbered):
        s, page = nb["system"], pages[nb["page"]]
        quad = quads[i]
        marks = [m["id"] for m in page.get("marks", []) if owner.get(m["id"]) == i]
        # the clefs in force across the bar (from the staff's left end for its
        # first bar, so the clef at the start of the line counts)
        left = _mid(nb["left"]) if nb["left"] else None
        clefs = clefs_between(page, s, left, _mid(nb["right"]), clef_changes[nb["page"]])
        bars.append({
            "part": nb["part"], "movement": nb["movement"], "bar": nb["bar"],
            "count": nb["count"], "page": nb["page"], "system": s["id"],
            "barline": nb["right"]["id"],
            "quad": quad,
            "staff": {"top": s["top"], "bottom": s["bottom"]},
            "reviewed": page.get("status") == "reviewed",
            "marks": marks,
            "clefs": clefs,
        })

    # A run (part + movement) is complete when every bar is reviewed, it ends
    # with an ends_movement bar line, and no earlier page is unlabeled (an
    # unlabeled page might belong to this part and shift its numbers).
    complete: dict[str, list[str]] = {}
    runs: dict[tuple, list] = {}
    for nb in numbered:
        runs.setdefault((nb["part"], nb["movement"]), []).append(nb)
    for (part, mvt), rs in runs.items():
        complete.setdefault(part, [])
        end = rs[-1]["page"]
        ok = (rs[-1]["right"].get("ends_movement")
              and all(pages[r["page"]].get("status") == "reviewed" for r in rs)
              and all(i in pages for i in range(1, end + 1)))
        if ok:
            complete[part].append(mvt)

    return {
        "schema": EXPORT_SCHEMA,
        "source": doc["source"],
        "complete": complete,
        # the paper's corners on each page, for cropping and straightening it
        "pages": {str(n): {"corners": p["corners"]["points"]}
                  for n, p in pages.items() if p.get("corners")},
        "bars": bars,
    }


# ---------------------------------------------------------------- edition metadata

_LINK = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")


def parse_sources_readme(text: str) -> dict[str, dict]:
    """Rows of the sources table in `sources/README.md`, keyed by pdf path
    relative to the edition root (e.g. `sources/G226/D-B_KHM-602.pdf`)."""
    out: dict[str, dict] = {}
    header: list[str] = []
    quartet = ""
    for line in text.splitlines():
        if not line.startswith("|"):
            header = []
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not header:
            header = [c.lower() for c in cells]
            quartet = ""
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        row = dict(zip(header, cells))
        f = re.search(r"`([^`]+\.pdf)`", row.get("file", ""))
        if not f:
            continue
        if row.get("quartet"):
            quartet = row["quartet"]
        rism = _LINK.search(row.get("rism", ""))
        online = _LINK.search(row.get("online", ""))
        out["sources/" + f.group(1)] = {
            "work": quartet,
            "description": _LINK.sub(r"\1", row.get("source", "")),
            "rism": rism.group(1) if rism else row.get("rism", ""),
            "rism_url": rism.group(2) if rism else "",
            "online": online.group(2) if online else "",
            "online_label": online.group(1) if online else row.get("online", ""),
        }
    return out


def source_info(pdf_rel: str, readme_rows: dict) -> dict:
    """The `source` block for a labels file, plus display-only metadata."""
    stem = Path(pdf_rel).stem
    siglum, _, shelf = stem.partition("_")
    row = readme_rows.get(pdf_rel, {})
    g = re.search(r"G\s*(\d+)", row.get("work", "")) or re.search(r"/G(\d+)/", pdf_rel)
    source = {
        "pdf": pdf_rel,
        "siglum": siglum,
        "shelfmark": shelf.replace("-", " "),
        "rism": row.get("rism", ""),
        "gerard": int(g.group(1)) if g else None,
    }
    return {"source": source, "display": row}


def structure_path(edition: Path, work: str) -> Path | None:
    """`Op. 48/1, G 226` -> `<edition>/Op48-1/Structure.ily`, if it exists."""
    m = re.search(r"Op\.\s*(\d+)\s*/\s*(\d+)", work or "")
    if not m:
        return None
    p = edition / f"Op{m.group(1)}-{m.group(2)}" / "Structure.ily"
    return p if p.exists() else None


_TOKEN = re.compile(
    r"(?P<repeat>\\repeat\s+volta\s+\d+\s*\{)"
    r"|(?P<unfold>\\repeat\s+(?:unfold|percent)\s+(?P<times>\d+)\s*\{)"
    r"|(?P<partial>\\partial\s+(?P<pdur>\d+)(?P<pdots>\.*)(?:\s*\*\s*(?P<pn>\d+)(?:\s*/\s*(?P<pm>\d+))?)?)"
    r"|(?P<time>\\time\s+(?P<tn>\d+)\s*/\s*(?P<td>\d+))"
    r"|(?P<key>\\key\s+(?P<tonic>[a-g][a-z]*)\s*\\(?P<mode>major|minor))"
    r"|(?P<numeric>\\(?P<which>numeric|default)TimeSignature\b)"
    r"|(?P<heading>\\(?:tempo|sectionLabel)\b)"
    r"|(?P<open>\{)|(?P<close>\})"
    r"|(?P<spacer>(?<![\\\w])s(?P<dur>\d+)?(?P<dots>\.*)(?:\s*\*\s*(?P<n>\d+)(?:\s*/\s*(?P<m>\d+))?)?(?![\w]))"
)
_WORD = re.compile(r"\S*")
_COMMAND = re.compile(r"\\[A-Za-z-]+\s*")


_FIFTHS = {"c": 0, "d": 2, "e": 4, "f": -1, "g": 1, "a": 3, "b": 5}


def key_fifths(tonic: str, mode: str) -> int:
    """A LilyPond key (Dutch note names: fis, bes, es, as) as its signature:
    sharps > 0, flats < 0, as the labels record it (d major and b minor: 2)."""
    rest = tonic[1:]  # is, isis (sharps); es, eses, and s, ses, sas after a vowel (as, es, asas, eses)
    flats = rest.count("es") + rest.count("as") + rest.startswith("s")
    n = _FIFTHS[tonic[0]] + 7 * (rest.count("is") - flats)
    return n - 3 if mode == "minor" else n


def written_time(num: int, den: int, numeric: bool = False) -> str:
    """A \\time as the page writes it: 4/4 and 2/2 print as C and ¢ unless numeric."""
    if not numeric and (num, den) in ((4, 4), (2, 2)):
        return "C" if den == 4 else "C/"
    return f"{num}/{den}"


def _duration(dur: str | None, dots: str, n: str | None, m: str | None) -> Fraction | None:
    """A LilyPond duration in whole notes (2. = 3/4, 2*7 = 7/2); None without one."""
    if not dur:
        return None
    base = Fraction(1, int(dur))
    return base * (2 - Fraction(1, 2 ** len(dots or ""))) * int(n or 1) / int(m or 1)


def _blank(text: str) -> str:
    """The skeleton with what isn't music blanked to spaces, every position
    kept: comments (% and %{ %}), the contents of quoted strings, and
    \\markup (its commands and its { } block or word), so a word in a
    marking ("segue s") isn't read as a spacer."""
    out = list(text)
    i, n = 0, len(text)

    def blank(a, b):
        for k in range(a, b):
            if out[k] != "\n":
                out[k] = " "
    while i < n:
        c = text[i]
        if text.startswith("%{", i):
            j = text.find("%}", i + 2)
            j = n if j < 0 else j + 2
            blank(i, j)
            i = j
        elif c == "%":
            j = text.find("\n", i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
        elif c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            blank(i + 1, min(j, n))
            i = j + 1
        elif text.startswith("\\markup", i):
            j = i + len("\\markup")
            while j < n and text[j].isspace():
                j += 1
            while (m := _COMMAND.match(text, j)):  # \bold, \italic, \line ...
                j = m.end()
            if j < n and text[j] == "{":
                depth = 0
                while j < n:
                    if text[j] == '"':  # a string inside: skip it whole
                        j += 1
                        while j < n and text[j] != '"':
                            j += 2 if text[j] == "\\" else 1
                    depth += {"{": 1, "}": -1}.get(text[j], 0) if j < n else 0
                    j += 1
                    if depth == 0:
                        break
            else:
                j = _WORD.match(text, j).end()
            blank(i, j)
            i = j
        else:
            i += 1
    return "".join(out)


class _Bars:
    """Bars as LilyPond numbers them, from spacer rests, \\partial and \\time.

    `pos` is the position in the current bar (past the meter's length when
    a \\partial lengthened the bar); `fresh` that a bar line has been
    reached, so the next music begins a new bar. A \\partial before any
    music is the pickup: bar 0, its length still to fill in `pickup_left`,
    not counted. Without a \\time, every spacer counts as its multiplier in
    bars (and a pickup's spacer as none)."""

    def __init__(self):
        self.bar = None            # bar length in whole notes, once \time is seen
        self.started = False       # any music yet
        self.pos = Fraction(0)
        self.fresh = True
        self.begun = 0             # bars begun (bar 0, the pickup, not counted)
        self.pickup = False
        self.pickup_left = None    # the pickup's length still to fill (None: unknown, the next spacer)

    def time(self, bar: Fraction):
        if not self.fresh and self.bar is not None and self.pos >= bar:
            self.fresh, self.pos = True, Fraction(0)  # the meter changed on what is now a bar line
        self.bar = bar

    def partial(self, length: Fraction | None):
        if not self.started:
            self.pickup, self.pickup_left = True, length
            return
        if self.bar is None or length is None:
            return
        # the current bar's remaining length: on a bar line, a new (short) bar
        if self.fresh:
            self.begun += 1
            self.fresh = False
        self.pos = self.bar - length

    def spacer(self, length: Fraction, n: int):
        self.started = True
        if self.pickup and self.pickup_left is None:  # a pickup of unknown length: this spacer
            self.pickup_left = Fraction(0)
            return
        if self.bar is None:
            if self.pickup_left:
                self.pickup_left = Fraction(0)
            else:
                self.begun += n
            return
        take = min(length, self.pickup_left or Fraction(0))
        if take:
            self.pickup_left -= take
        left = length - take
        if left <= 0:
            return
        if self.fresh:
            self.begun += 1
            self.fresh, self.pos = False, Fraction(0)
        room = self.bar - self.pos
        if left < room:
            self.pos += left
            return
        left -= room
        full, rest = divmod(left, self.bar)
        self.begun += int(full) + (1 if rest else 0)
        self.fresh, self.pos = (False, rest) if rest else (True, Fraction(0))


_HEADING = re.compile(r'\\(tempo|sectionLabel)\s+"')
_STRING = re.compile(r'"((?:[^"\\]|\\.)*)"')


def _headings(text: str, music: str, a: int, b: int) -> dict:
    """A block's \\tempo and \\sectionLabel texts, found in `music` (comments
    blanked, positions kept) and read from `text` (escaped quotes undone):
    {"tempos", "titles", "headings": both, in the order written}."""
    out = {"tempos": [], "titles": [], "headings": []}
    for h in _HEADING.finditer(music, a, b):
        s = _STRING.match(text, h.end() - 1)
        if not s:
            continue
        t = re.sub(r"\\(.)", r"\1", s.group(1))
        out["tempos" if h.group(1) == "tempo" else "titles"].append(t)
        out["headings"].append(t)
    return out


def parse_structure(text: str) -> dict[str, dict]:
    """Expected bars per movement from a `Structure.ily` skeleton.

    Returns {"I": {"total": 130, "pickup": False, "segments": [
    {"bars": 48, "repeat": True, "split": False, "heading": False}, ...],
    "tempos": [...]}}. A segment is `split` when it ends mid-bar (its last
    bar is short: the next section's upbeat completes it), and has a
    `heading` when a \\tempo or \\sectionLabel begins it after the music has
    begun (a Trio's).

    With a \\time, bars are numbered as LilyPond numbers them (_Bars): a
    \\partial before any music is the pickup (bar 0, not counted); a
    \\partial later sets the current bar's remaining length, so on a bar
    line it begins a short bar that counts (a Trio's last two-beat bar,
    `s2.*23 \\partial 2 s2`), and within a bar it shortens or lengthens
    it. A section's short last bar and the next section's upbeat make one
    bar (`\\partial 4 s4 s2.*7 s2 } { s4 s2.*19 s2` is 8 + 20 bars). A
    bare `s` repeats the last duration, multiplier and all. A segment's
    bars are those that begin in it. Without a \\time every spacer counts
    as its multiplier in bars. `bar_count` 0 in the labels matches: the
    pickup, and the upbeat that completes a short bar.
    """
    music = _blank(text)
    out: dict[str, dict] = {}
    for m in re.finditer(r"\\tag\s+#'mvt(\w+)\s*\{", music):
        name = m.group(1)
        b = _Bars()
        last = Fraction(1, 4)   # the duration a bare `s` repeats (LilyPond starts at a quarter)
        depth = 1
        stack: list = []        # per open brace: True (volta repeat), False, or an unfold frame
        marks: list[tuple] = [] # (bars so far, repeat?, on a bar line?) where segments end
        headed: set = set()     # bars so far where a heading begins a section (a Trio's \tempo)
        sig: dict = {}          # the movement's opening key and time
        changes: list = []      # later ones: {"bar": n, "key" or "time": value}
        numeric = False         # \numericTimeSignature in force (4/4 printed as 4/4, not C)
        end = len(music)

        def signature(field, value, mode=None):
            extra = {"mode": mode} if mode else {}  # a key's mode, which its signature doesn't show
            if not b.started:
                sig.update({field: value, **extra})
            elif b.fresh:  # on a bar line: from the next bar
                changes.append({"bar": b.begun + 1, "on_bar_line": True, field: value, **extra})
            else:          # mid-bar: from the rest of this one (a Trio's upbeat, completing the short bar)
                changes.append({"bar": b.begun, "on_bar_line": False, field: value, **extra})

        def emit(ev: tuple):
            """One musical event; a written-out repeat records it to play again."""
            for f in stack:
                if isinstance(f, dict):
                    f["events"].append(ev)
            if ev[0] == "signature":
                signature(*ev[1:])
            else:
                getattr(b, ev[0])(*ev[1:])

        for t in _TOKEN.finditer(music, m.end()):
            if t.group("time"):
                emit(("time", Fraction(int(t.group("tn")), int(t.group("td")))))
                emit(("signature", "time", written_time(int(t.group("tn")), int(t.group("td")), numeric)))
            elif t.group("numeric"):
                numeric = t.group("which") == "numeric"
            elif t.group("heading"):
                if b.started:
                    headed.add(b.begun)
            elif t.group("key"):
                if t.group("tonic")[0] in _FIFTHS:
                    emit(("signature", "key", key_fifths(t.group("tonic"), t.group("mode")), t.group("mode")))
            elif t.group("unfold"):
                depth += 1
                stack.append({"times": int(t.group("times")), "events": []})
            elif t.group("repeat"):
                depth += 1
                stack.append(True)
                marks.append((b.begun, False, b.fresh))  # music before the repeat, if any
            elif t.group("open"):
                depth += 1
                stack.append(False)
            elif t.group("close"):
                depth -= 1
                if depth == 0:
                    end = t.start()
                    break
                frame = stack.pop()
                if isinstance(frame, dict):  # written out N times: play what's inside N - 1 more
                    for _ in range(frame["times"] - 1):
                        for ev in frame["events"]:
                            emit(ev)
                elif frame:
                    marks.append((b.begun, True, b.fresh))
            elif t.group("partial"):
                emit(("partial", _duration(t.group("pdur"), t.group("pdots"), t.group("pn"), t.group("pm"))))
            elif t.group("spacer"):
                n = int(t.group("n") or 1)
                if t.group("dur"):
                    length = _duration(t.group("dur"), t.group("dots"), t.group("n"), t.group("m"))
                    last = length
                else:  # a bare `s` (or `s*2`): the last duration again
                    length = last * n / int(t.group("m") or 1)
                emit(("spacer", length, n))
        marks.append((b.begun, False, b.fresh))

        segments, prev = [], 0
        for v, repeat, fresh in marks:
            nb = v - prev
            if nb > 0:
                segments.append({"bars": nb, "repeat": repeat, "split": not fresh, "heading": prev in headed})
            prev += max(0, nb)
        out[name] = {"total": sum(s["bars"] for s in segments),
                     "pickup": b.pickup, "segments": segments, **sig, "changes": changes,
                     **_headings(text, music, m.end(), end)}
    return out
