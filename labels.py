"""The labels file: schema, migration, validation, bar numbering, bar export.

Everything here is pure data in, data out, so it can be tested without the
server or a browser. The front end has its own copy of the numbering rules
(`static/app.js`, `numberBars`) for live display; this module is the
authority for what gets written to disk.
"""

import re
from pathlib import Path

SCHEMA = 1

PARTS = ["vn1", "vn2", "va", "vc", "score"]
CLEFS = ["treble", "alto", "tenor", "bass"]
DEFAULT_CLEF = {"vn1": "treble", "vn2": "treble", "va": "alto", "vc": "bass", "score": "treble"}
PAGE_KINDS = ["music", "title", "blank", "other"]
PAGE_STATUSES = ["auto", "edited", "reviewed"]
BARLINE_KINDS = ["single", "double", "repeat_start", "repeat_end", "repeat_both", "final"]
MARK_KINDS = ["text", "tempo", "dynamic", "stray", "unclear", "other"]
SYSTEM_ROLES = ["part", "cue"]  # a cue staff is drawn but not counted

# Vertical margin of a bar's crop, in staff spaces above and below the staff.
QUAD_MARGIN = 2.5


class SchemaError(ValueError):
    pass


class NewerSchema(SchemaError):
    """The file was written by a newer version of this tool. Never overwrite it."""


# from_version -> function(doc) -> doc at from_version + 1
MIGRATIONS: dict = {}


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

    # A mark belongs to the bar whose crop holds its centre. A tempo outside
    # every crop (written above the music) belongs to the first bar of the
    # nearest staff below it; any other mark outside every crop ("Da capo
    # il Minuetto" under the last line, "Segue il Trio") to the last bar of
    # the nearest staff that its text reaches.
    quads = [bar_quad(nb["system"], nb["left"], nb["right"]) for nb in numbered]
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
                below = [i for i in idx if numbered[i]["system"]["top"] > cy]
                if m.get("kind") == "tempo" and below:
                    owner[m["id"]] = min(below, key=lambda i: (numbered[i]["system"]["top"], i))
                elif m.get("kind") != "tempo":
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
        bars.append({
            "part": nb["part"], "movement": nb["movement"], "bar": nb["bar"],
            "count": nb["count"], "page": nb["page"], "system": s["id"],
            "barline": nb["right"]["id"],
            "quad": quad,
            "staff": {"top": s["top"], "bottom": s["bottom"]},
            "reviewed": page.get("status") == "reviewed",
            "marks": marks,
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
        "schema": SCHEMA,
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
    r"|(?P<partial>\\partial\s+[\d.]+(?:\*\d+(?:/\d+)?)?)"
    r"|(?P<open>\{)|(?P<close>\})"
    r"|(?P<spacer>(?<![\\\w])s(?:\d+\.*)?(?:\*(?P<n>\d+)(?:/\d+)?)?(?![\w]))"
)


def parse_structure(text: str) -> dict[str, dict]:
    """Expected bars per movement from a `Structure.ily` skeleton.

    Returns {"I": {"total": 130, "pickup": False, "segments": [
    {"bars": 48, "repeat": True}, ...]}}. A spacer right after `\\partial`
    is a pickup and isn't counted, matching `bar_count` 0 in the labels.
    """
    text = re.sub(r"%[^\n]*", "", text)
    out: dict[str, dict] = {}
    for m in re.finditer(r"\\tag\s+#'mvt(\w+)\s*\{", text):
        name = m.group(1)
        depth, i = 1, m.end()
        segments: list[dict] = []
        stack: list[bool] = []  # is this brace a repeat?
        current = None  # the open segment
        pickup_next, pickup = False, False

        def seg(repeat: bool):
            nonlocal current
            if current is None or current["repeat"] != repeat or repeat:
                current = {"bars": 0, "repeat": repeat}
                segments.append(current)
            return current

        end = len(text)
        for t in _TOKEN.finditer(text, i):
            if t.group("repeat"):
                depth += 1
                stack.append(True)
                current = None
                seg(True)
            elif t.group("open"):
                depth += 1
                stack.append(False)
            elif t.group("close"):
                depth -= 1
                if depth == 0:
                    end = t.start()
                    break
                if stack.pop():
                    current = None
            elif t.group("partial"):
                pickup_next = True
            elif t.group("spacer"):
                if pickup_next:
                    pickup_next = False
                    pickup = True
                    continue
                in_repeat = any(stack)
                s = current if current is not None else seg(in_repeat)
                s["bars"] += int(t.group("n") or 1)
        segments = [s for s in segments if s["bars"]]
        out[name] = {"total": sum(s["bars"] for s in segments),
                     "pickup": pickup, "segments": segments,
                     "tempos": re.findall(r'\\tempo\s+"([^"]*)"', text[m.end():end])}
    return out
