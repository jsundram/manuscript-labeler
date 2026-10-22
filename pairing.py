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


def for_pdf(pdf: Path, cache: Path) -> dict:
    """{"sources": [...], "pages": {n: [staff, ...]}}, each staff
    {top, bottom, left, right, part, status, bars, why, source, id}."""
    names = sources().get(Path(pdf).resolve(), [])
    pages: dict[str, list] = {}
    for name in names:
        auto = _load(ZEUS / "auto" / f"{name}.json")
        res = _load(results_file(name))
        kept = {k["staff"]: k for k in res["kept"]}
        out = {k["staff"]: k for k in res["not kept"]}
        in_set = set()
        for s in SETS:
            f = cache / "zeus" / s / f"samples.{name}.txt"
            if f.exists():
                in_set |= {x.split("/", 1)[1] for x in f.read_text().split() if x.startswith(name + "/")}
        for n, page in auto["pages"].items():
            for k, s in enumerate(sorted(page["systems"], key=lambda s: s["top"])):
                sid = f"p{n}-{k}"
                entry = kept.get(sid) or out.get(sid)
                status = ("set" if sid in in_set else "paired") if sid in kept else "unpaired" if sid in out else "unknown"
                pages.setdefault(n, []).append({
                    "top": s["top"], "bottom": s["bottom"], "left": s["left"], "right": s["right"],
                    "part": s.get("part", page.get("part")), "status": status, "source": name, "id": sid,
                    "bars": bars_text(entry.get("bars") or []) if entry else "",
                    "why": entry.get("why", []) if status == "unpaired" else [],
                })
    return {"sources": names, "pages": pages}


def source_info(rel: str, pdf: Path, names: list[str]) -> dict:
    """labels.source_info for a paired PDF outside the edition and the archive."""
    g = re.search(r"G\.?\s*(\d+)", pdf.stem) or re.search(r"G(\d+)", " ".join(names))
    source = {"pdf": rel, "siglum": "", "shelfmark": pdf.stem, "rism": "", "gerard": int(g.group(1)) if g else None}
    return {"source": source, "display": {"work": "", "description": "paired: " + ", ".join(names)}}
