"""What the automatic pairing made of each staff of a paired manuscript, for
the labeler to show over the page (server.py /api/pairing).

The pairing (experiments/zeus): autodetect.py found the staves
(auto/<source>.json), a reader read them, autopair.py aligned the readings
with an encoding's bars (results/autopair-<source>-*.json: "kept" and "not
kept", each staff named p<page>-<k>, k from the top of the page), and
dataset.py took the staves it trusts into a training set
(<cache>/zeus/<set>/samples.<source>.txt). One PDF can hold several sources
(the Paris parts: Op22-Paris-va and Op22-6-Vmbr153-va).

Each staff gets a status:
- "set": in a training set, with the bars it holds;
- "paired": kept by the pairing, but not taken into a set;
- "unpaired": not kept, with the pairing's reasons;
- "unknown": on a page the pairing read, but in no result.
"""

import json
import re
import time
from pathlib import Path

ZEUS = Path(__file__).resolve().parent / "experiments" / "zeus"
# the newest staff sets (docs/storage.md)
SETS = ("dataM4", "dataW3", "dataP3", "dataG213-3")
# the pairing a set was built from, most final first: G. 213's merge, the
# two readers' merge (the older sources), then one reader's
SOURCES_TTL = 10.0
RESULTS = ("final", "both",
           "any-count-neighbours-paired-short-ends-long-ends-head-box-musvit-D3S-h96",
           "any-count-neighbours-paired-short-ends-long-ends-musvit-D3S-h96")

_cache: dict = {}
_sources: list = [0.0, {}]  # (when, sources()): the server asks on every request


def _load(p: Path):
    """A JSON file, read again only when it changes."""
    key = (str(p), p.stat().st_mtime_ns)
    if key not in _cache:
        _cache[key] = json.loads(p.read_text())
    return _cache[key]


def sources() -> dict[Path, list[str]]:
    """{PDF: its paired sources}, for every detection whose PDF is here
    (under home: a paired: id is a path from it). Looked up again after
    SOURCES_TTL seconds."""
    if time.monotonic() - _sources[0] < SOURCES_TTL:
        return _sources[1]
    out: dict[Path, list[str]] = {}
    for f in sorted(ZEUS.glob("auto/*.json")):
        pdf = _load(f).get("pdf")
        if not pdf or not Path(pdf).is_file() or not results_file(f.stem) \
                or not Path(pdf).resolve().is_relative_to(Path.home()):
            continue
        out.setdefault(Path(pdf).resolve(), []).append(f.stem)
    _sources[:] = [time.monotonic(), out]
    return out


def part_pages(source: str) -> set[str]:
    """The pages the source's detections give a part (vn1 ...): the ones a staff can be tried on."""
    return {n for n, p in _load(ZEUS / "auto" / f"{source}.json")["pages"].items() if p.get("part") != "score"}


def results_file(source: str) -> Path | None:
    for r in RESULTS:
        p = ZEUS / "results" / f"autopair-{source}-{r}.json"
        if p.exists():
            return p
    return None


def bars_text(bars: list) -> str:
    """[["Op32-1", "I", 14], ..., ["Op32-1", "I", 20]] -> "Op32-1 I 15–21":
    the encoding's bars counted from 1, as the labeler counts them (but a
    pickup counts as bar 1 here); a run per movement."""
    runs = []
    for b in bars:
        head, i = tuple(b[:-1]), b[-1]
        if runs and runs[-1][0] == head and i in (runs[-1][2], runs[-1][2] + 1):
            runs[-1][2] = i
        else:
            runs.append([head, i, i])
    return ", ".join(" ".join(map(str, h)) + (f" {a + 1}" if a == b else f" {a + 1}–{b + 1}") for h, a, b in runs)


def _bars_in(text: str) -> str:
    """The pairing's bar references in a reason, counted from 1 as the
    labeler counts: "['Op32-1', 'II', 20]" -> "Op32-1 II 21"."""
    one = re.compile(r"\[((?:'[^']*',\s*)+)(\d+)\]")
    text = one.sub(lambda m: " ".join(re.findall(r"'([^']*)'", m.group(1))) + f" {int(m.group(2)) + 1}", text)
    return re.sub(r"\[([^\[\]']*)\]", r"\1", text)  # a list of them


# the pairing's reasons (autopair.py, g213/merge.py) in the editor's words
REASONS = [
    (r"next staff begins with (extra|two|rests)",
     "The next line starts with part of a bar, or a measure the reading added or merged, so this line's last "
     "bar may be the next line's. A bar crossing the line break puts out both lines."),
    (r"staff before ends with (extra|two|rests)",
     "The line before ends with part of a bar, or a measure the reading added or merged, so this line's first "
     "bar may be the line before's. A bar crossing the line break puts out both lines."),
    (r"an end measure shorter than its bar (.*)",
     r"Its first or last measure reads shorter than bar \1: part of a bar crossing the line break, taken for the whole."),
    (r"an end measure longer than its bar (.*)",
     r"Its first or last measure reads longer than bar \1: part of the next or previous line's bar read into it."),
    (r"(\d+) measures, (\d+) bar boxes.*",
     r"The reading has \1 measures where detection found \2 bars on the line (a bar line missed or extra)."),
    (r"extra at none", "The reading has a measure the score doesn't (a heading, or part of a bar read as a whole)."),
    (r"extra at (.*)", r"The reading has a measure the score doesn't, at \1."),
    (r"two at (.*)", r"One measure of the reading holds two bars, \1: a bar line it missed."),
    (r"unlike (.*)", r"A measure is nothing like bar \1: the alignment may have slipped."),
    (r"beside a missed bar (.*)", r"Bar \1 is on no line: next to it is a line detection or the reading missed, or cut short."),
    (r"mis-measured.*", "The line was measured short, with music past its end."),
    (r"below a mis-measured staff.*", "A line above it on this page was measured short."),
    (r"more bar boxes than measures.*",
     "Detection found more bars than the reading has measures, the first narrow: the reading dropped part of a "
     "bar at the line's start."),
    (r"twin (p\d+-\d+) not (kept|plain)", r"Its copy in the other manuscript (\1) wasn't paired cleanly."),
]
# the set builder's (dataset.py), where they need it
LEFT_OUT = {
    "not plain": "Not every measure pairs with one bar (a bar crossing the line break, or a multi-bar rest): "
                 "a training label can't hold part of a bar yet.",
}


def explain(why: list[str]) -> list[str]:
    """The reasons, without the reader's name, each once, in plain words."""
    out = []
    for w in why:
        w = re.sub(r"^musvit-[\w.-]+: ", "", w)
        for pat, plain in REASONS:
            m = re.fullmatch(pat, w)
            if m:
                w = m.expand(plain)
                break
        w = _bars_in(w)
        if w not in out:
            out.append(w)
    return out


def _left_out(name: str, cache: Path) -> dict:
    """{staff: why the set builder left it out} (dataset.py's left_out.<name>.json)."""
    out = {}
    for s in SETS:
        f = cache / "zeus" / s / f"left_out.{name}.json"
        if f.exists():
            out.update(_load(f))
    return out


def summary(pdf: Path, cache: Path) -> dict:
    """How many of the PDF's staves are in a set, paired, unpaired."""
    n = {"set": 0, "paired": 0, "unpaired": 0}
    for name in sources().get(Path(pdf).resolve(), []):
        res = _load(results_file(name))
        in_set = _in_sets(name, cache)
        n["unpaired"] += len(res["not kept"])
        for k in res["kept"]:
            n["set" if k["staff"] in in_set else "paired"] += 1
    return n


def _in_sets(name: str, cache: Path) -> set:
    out = set()
    for s in SETS:
        f = cache / "zeus" / s / f"samples.{name}.txt"
        if f.exists():
            out |= {x.split("/", 1)[1] for x in f.read_text().split() if x.startswith(name + "/")}
    return out


def for_pdf(pdf: Path, cache: Path) -> dict:
    """{"sources": [...], "pages": {n: [staff, ...]}}, each staff
    {top, bottom, left, right, part, status, bars, why, source, id}: `why`,
    an unpaired staff's reasons, or why a paired one was left out of the sets."""
    names = sources().get(Path(pdf).resolve(), [])
    pages: dict[str, list] = {}
    for name in names:
        auto = _load(ZEUS / "auto" / f"{name}.json")
        res = _load(results_file(name))
        kept = {k["staff"]: k for k in res["kept"]}
        out = {k["staff"]: k for k in res["not kept"]}
        in_set = _in_sets(name, cache)
        left_out = _left_out(name, cache)
        for n, page in auto["pages"].items():
            for k, s in enumerate(sorted(page["systems"], key=lambda s: s["top"])):
                sid = f"p{n}-{k}"
                entry = kept.get(sid) or out.get(sid)
                status = ("set" if sid in in_set else "paired") if sid in kept else "unpaired" if sid in out else "unknown"
                pages.setdefault(n, []).append({
                    "top": s["top"], "bottom": s["bottom"], "left": s["left"], "right": s["right"],
                    "part": s.get("part", page.get("part")), "status": status, "source": name, "id": sid,
                    "bars": bars_text(entry.get("bars") or []) if entry else "",
                    "why": explain(entry.get("why", [])) if status == "unpaired"
                    else [LEFT_OUT.get(left_out[sid], left_out[sid])] if status == "paired" and sid in left_out else [],
                })
    return {"sources": names, "pages": pages}


def source_info(rel: str, pdf: Path, names: list[str]) -> dict:
    """labels.source_info for a paired PDF outside the edition and the archive."""
    g = re.search(r"G\.?\s*(\d+)", pdf.stem) or re.search(r"G(\d+)", " ".join(names))
    source = {"pdf": rel, "siglum": "", "shelfmark": pdf.stem, "rism": "", "gerard": int(g.group(1)) if g else None}
    return {"source": source, "display": {"work": "", "description": "paired: " + ", ".join(names)}}
