"""Each candidate's reading of BA 2676, as one list per part of staves in
reading order (PDF page, then top to bottom), each staff a list of
measures, each measure a list of events as compare.py compares them, at the
pitches the reader wrote (its own clefs): {part: [{"page", "staff", "measures"}]}.

- MuSViT readers (musvit-D4 and the OSSQ reader): experiments/zeus/answers/
  BA2676-<part>-auto-musvit-<run>.json, LMX per detected staff (read_auto.py),
  staves ordered as auto/BA2676-<part>.json has them.
- MusicXML readers (Audiveris, ...): one MusicXML file per page,
  <dir>/<part>/p<NN>.musicxml (or .mxl), each a single part; staves split at
  <print new-system>.
"""

import io
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
ZEUS = HERE.parent / "zeus"
sys.path.insert(0, str(ZEUS))
import compare  # noqa: E402

PARTS = ("vn1", "vn2", "va", "vc")
TYPES = {"breve": "breve", "whole": "whole", "half": "half", "quarter": "quarter", "eighth": "8th",
         "16th": "16th", "32nd": "32nd", "64th": "64th"}


def ev(e: dict, end=None) -> dict:
    out = {"kind": e["kind"], "pitches": tuple(e["pitches"]), "dur": e["dur"], "dots": e["dots"],
           "grace": bool(e["grace"]), "acc": tuple(e["acc"])}
    if end is not None:
        out["end"] = end  # where it ends in its measure, as a fraction of a whole note
    return out


def lmx_end(e: dict):
    if e["grace"] or e.get("bar_rest"):
        return None
    return e["onset"] + compare.length(e["dur_raw"], e["dots"], e["tuplet"])


def musvit(run: str, source_prefix: str = "BA2676") -> dict:
    out = {}
    for part in PARTS:
        src = f"{source_prefix}-{part}"
        auto = json.loads((ZEUS / "auto" / f"{src}.json").read_text())
        ans = json.loads((ZEUS / "answers" / f"{src}-auto-musvit-{run}.json").read_text())
        by_staff = {k.split(":")[0]: v for k, v in ans.items()}
        staves = []
        for n, p in sorted(auto["pages"].items(), key=lambda kv: int(kv[0])):
            for k, _ in enumerate(sorted(p["systems"], key=lambda s: s["top"])):
                lmx = by_staff.get(f"p{n}-{k}")
                if lmx is None:
                    continue
                measures, _ = compare.parse(lmx)
                ms = [[ev(compare.zeus_event(e, e["zclef"] if e["zclef"] in compare.MIDDLE else "G2"), lmx_end(e))
                       for e in m] for m in measures]
                staves.append({"page": int(n), "staff": k, "measures": ms})
        out[part] = staves
    return out


def _root(path: Path) -> ET.Element:
    if path.suffix == ".mxl":
        z = zipfile.ZipFile(path)
        name = next(n for n in z.namelist() if n.endswith((".xml", ".musicxml")) and not n.startswith("META-INF"))
        return ET.parse(io.BytesIO(z.read(name))).getroot()
    return ET.parse(path).getroot()


def mxl_staves(path: Path) -> list[list[list[dict]]]:
    """A one-part MusicXML page as staves of measures of events (as compared),
    at the pitches written. A score with several parts (a reader that split
    the staves into parts) is read part by part, top part first per system."""
    root = _root(path)
    parts = root.findall("part")
    systems: list[list[list[dict]]] = []
    for pi, part in enumerate(parts):
        div, si = 1, -1
        for m in part.findall("measure"):
            p = m.find("print")
            if si < 0 or (p is not None and (p.get("new-system") == "yes" or p.get("new-page") == "yes")):
                si += 1
                if pi == 0:
                    systems.append([])
            t, events, last = Fraction(0), [], None
            for el in m:
                if el.tag == "attributes" and el.findtext("divisions"):
                    div = int(el.findtext("divisions"))
                elif el.tag in ("backup", "forward"):
                    d = Fraction(int(el.findtext("duration", "0") or 0), div)
                    t += -d if el.tag == "backup" else d
                elif el.tag == "note":
                    dur = Fraction(int(el.findtext("duration", "0") or 0), div)
                    if el.find("chord") is not None and last is not None:
                        if el.find("pitch") is not None:
                            last["pitches"].append(el.findtext("pitch/step") + el.findtext("pitch/octave"))
                            if el.findtext("accidental"):
                                last["acc"].append(el.findtext("accidental"))
                        continue
                    if el.get("print-object") == "no" or el.find("cue") is not None:
                        t += dur
                        last = None
                        continue
                    grace = el.find("grace") is not None
                    rest = el.find("rest")
                    kind = el.findtext("type")
                    dots = len(el.findall("dot"))
                    if rest is not None:
                        bar_rest = rest.get("measure") == "yes" or kind in (None, "whole")
                        e = {"kind": "rest", "pitches": [], "dur": "bar" if bar_rest else TYPES.get(kind),
                             "dots": 0 if bar_rest else dots, "grace": False, "acc": []}
                    elif el.find("pitch") is not None:
                        e = {"kind": "note", "pitches": [el.findtext("pitch/step") + el.findtext("pitch/octave")],
                             "dur": TYPES.get(kind), "dots": dots, "grace": grace,
                             "acc": [el.findtext("accidental")] if el.findtext("accidental") else []}
                    else:  # unpitched
                        continue
                    e.update(onset=t, voice=el.findtext("voice", "1"),
                             end=None if grace or e["dur"] == "bar" else t + dur)
                    events.append(e)
                    last = e
                    if not grace:
                        t += dur
            for e in events:
                e["pitches"] = tuple(sorted(e["pitches"]))
                e["acc"] = tuple(sorted(e["acc"]))
            if si < len(systems):
                if pi == 0:
                    systems[si].append([ev(e, e["end"]) for e in compare.merge(events)])
    return systems


def _order(f: Path):
    """p-02.mxl, p-02.mvt2.mxl ... -> (2, 2): page, then movement (Audiveris
    writes one file per movement it finds on a page)."""
    m = re.match(r"p-?(\d+)(?:\.mvt(\d+))?", f.name)
    return int(m.group(1)), int(m.group(2) or 0)


def musicxml_dir(root: Path) -> dict:
    out = {}
    for part in PARTS:
        staves = []
        files = sorted((f for f in (root / part).glob("p*") if f.suffix in (".mxl", ".musicxml", ".xml")
                        and re.match(r"p-?\d+", f.name)), key=_order)
        k = Counter()
        for f in files:
            page = _order(f)[0]
            try:
                systems = mxl_staves(f)
            except (ET.ParseError, StopIteration, zipfile.BadZipFile):
                continue
            for ms in systems:
                staves.append({"page": page, "staff": k[page], "measures": ms})
                k[page] += 1
        out[part] = staves
    return out
