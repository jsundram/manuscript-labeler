# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Do OSSQ-OMR's period labels give the clef the scan draws? (clef-check.md)

OSSQ's labels are cut from OpenScore encodings of the work, not
transcriptions of the scan: a viola or cello passage the print sets in
treble or tenor clef may stay in the part's own clef in the label. This
measures how often, by part (vn1 vn2 va vc are the staff id's last number,
the encoding's part order: ossq_modal.py writes <page>-<system>-<part>).

    modal run experiments/ossq/clef_check.py::fetch     # every period label -> $TMPDIR/ossq-period-labels.json
    modal run experiments/ossq/clef_check.py::sheet --spec sheets.json   # {out.png: [[key, caption], ...]}
    uv run experiments/ossq/clef_check.py analyze       # the tables (clef-check.json)
    uv run experiments/ossq/clef_check.py sheets DIR    # DIR/sheets.json: which staves to look at

Modal: CPU only (fetching labels, drawing sheets); nothing is written to
the volume. musvit-D4's readings are the 1,050 in period-pairing.json.
"""

import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = "/staves/ossq-period"
TMP = Path(os.environ.get("TMPDIR", "/tmp"))
LABELS = TMP / "ossq-period-labels.json"     # re-fetchable, so not kept in the repo
ZEUS = Path.home() / ".cache/manuscript-labeler/zeus"
EDITION_LABELS = HERE.parent.parent / "data/boccherini-opus-48/sources"
PART = {"1": "vn1", "2": "vn2", "3": "va", "4": "vc"}
USUAL = {"vn1": "G2", "vn2": "G2", "va": "C3", "vc": "F4"}
NAME = {"G2": "treble", "C3": "alto", "C4": "tenor", "F4": "bass", "F3": "baritone", "C1": "soprano",
        "C2": "mezzo", "G1": "French violin"}
MIDDLE = {"G2": "B4", "F4": "D3", "C3": "C4", "C4": "A3", "C1": "G4", "C2": "E4", "F3": "F3", "G1": "D5"}
FAR = 9  # steps from the middle line (past 2 ledger lines): where a print might change clef (violins: 13)

try:
    import modal
except ImportError:  # the analysis needs no Modal
    modal = None

if modal is not None:
    app = modal.App("ossq-clef-check")
    image = modal.Image.debian_slim(python_version="3.12").uv_pip_install("pillow")
    staves = modal.Volume.from_name("musvit-staves")

    @app.function(image=image, volumes={"/staves": staves}, timeout=1800)
    def all_labels() -> dict:
        from concurrent.futures import ThreadPoolExecutor
        keys = (Path(OUT) / "samples.ossq-period.txt").read_text().split()
        with ThreadPoolExecutor(64) as ex:
            return dict(zip(keys, ex.map(lambda k: (Path(OUT) / f"{k}.lmx").read_text().strip(), keys)))

    @app.function(image=image, volumes={"/staves": staves}, timeout=900)
    def compose(keys: list[str], captions: list[str], width: int = 1800, h: int = 120) -> bytes:
        """Rows of staves, each h px high, cut (not squeezed) to width, captioned."""
        import io
        from PIL import Image, ImageDraw
        rows = []
        for k, cap in zip(keys, captions):
            im = Image.open(f"{OUT}/{k}.jpg").convert("L")
            im = im.resize((max(1, round(im.width * h / im.height)), h), Image.LANCZOS).crop((0, 0, width, h))
            row = Image.new("RGB", (width, h + 18), "white")
            row.paste(im, (0, 18))
            ImageDraw.Draw(row).text((4, 3), cap, fill=(200, 0, 0))
            rows.append(row)
        sheet = Image.new("RGB", (width, sum(r.height + 4 for r in rows)), (90, 90, 90))
        y = 0
        for r in rows:
            sheet.paste(r, (0, y))
            y += r.height + 4
        buf = io.BytesIO()
        sheet.save(buf, "PNG")
        return buf.getvalue()

    @app.local_entrypoint()
    def fetch(out: str = ""):
        labs = all_labels.remote()
        Path(out or LABELS).write_text(json.dumps(labs))
        print(len(labs), "labels ->", out or LABELS)

    @app.local_entrypoint()
    def sheet(spec: str):
        """Contact sheets from a JSON file {out.png: [[key, caption], ...]}."""
        for out, rows in json.loads(Path(spec).read_text()).items():
            Path(out).write_bytes(compose.remote([k for k, _ in rows], [c for _, c in rows]))
            print(out)


# ---------------------------------------------------------------- reading LMX

STEP = "CDEFGAB"


def idx(p: str) -> int:
    return int(p[1]) * 7 + STEP.index(p[0])


def parse(lmx: str):
    """(clef sequence (consecutive repeats merged), [(measure no, clef, pitch)] per note)."""
    clefs, notes, clef, m = [], [], None, -1
    for t in lmx.split():
        if t == "measure":
            m += 1
        elif t.startswith("clef:"):
            clef = t[5:]
            if not clefs or clefs[-1] != clef:
                clefs.append(clef)
        elif len(t) == 2 and t[0] in STEP and t[1].isdigit():
            notes.append((max(m, 0), clef, t))
    return clefs, notes


def far(notes, limit=FAR) -> list:
    """Notes more than `limit` steps from the middle line of the clef they're in."""
    return [(m, c, p, idx(p) - idx(MIDDLE[c])) for m, c, p in notes
            if c in MIDDLE and abs(idx(p) - idx(MIDDLE[c])) > limit]


def bars(lmx: str) -> list[list[str]]:
    """Each measure's pitches."""
    out = []
    for t in lmx.split():
        if t == "measure":
            out.append([])
        elif len(t) == 2 and t[0] in STEP and t[1].isdigit():
            (out[-1] if out else out.append([]) or out[-1]).append(t)
    return out


def shift(a: list[str], b: list[str]):
    """The step shift taking a bar's pitches to b's, if all agree on one (None if not)."""
    if not a or len(a) != len(b):
        return None
    d = {idx(y) - idx(x) for x, y in zip(a, b)}
    return d.pop() if len(d) == 1 else None


# ---------------------------------------------------------------- the baseline

def baseline() -> dict:
    """Our Boccherini staves by part: dataL2 (hand-labelled, the manuscript's
    clefs, changes included) and dataM (paired; one clef per staff, the one
    autopair chose from the reading)."""
    pmap = {}
    for f in EDITION_LABELS.glob("*/*.labels.json"):
        d = json.loads(f.read_text())
        pmap[f.name.split(".labels")[0]] = {int(k): v.get("part") for k, v in d["pages"].items()}
    for f in (HERE.parent / "zeus/auto").glob("*.json"):
        d = json.loads(f.read_text())
        pmap.setdefault(d["source"], {int(k): v.get("part") for k, v in d["pages"].items()})
    out = {}
    for ds in ("dataL2", "dataM"):
        rows = []
        for f in sorted((ZEUS / ds).glob("*/*.lmx")):
            src = f.parent.name.removesuffix("-noslur")
            if f.parent.name.endswith("-noslur"):
                continue  # the same staves as F-Pn_Vma-ms-1067-3
            mm = re.match(r"p(\d+)", f.stem)
            part = pmap.get(src, {}).get(int(mm.group(1))) if mm else None
            if part not in USUAL:
                continue  # score-form sources: no part per page
            clefs, notes = parse(f.read_text())
            rows.append({"key": f"{src}/{f.stem}", "part": part, "clefs": clefs, "far": len(far(notes))})
        out[ds] = rows
    return out


# ---------------------------------------------------------------- the analysis

def tally(rows):
    """By part: staves, with a clef change inside, with any clef not the part's
    usual one, with notes far off the staff in the label's clef."""
    t = defaultdict(Counter)
    for r in rows:
        c = t[r["part"]]
        c["staves"] += 1
        c["change"] += len(r["clefs"]) > 1
        c["unusual"] += any(x != USUAL[r["part"]] for x in r["clefs"])
        c["far"] += r["far"] > 0
    return {p: dict(t[p]) for p in ("vn1", "vn2", "va", "vc") if p in t}


def analyze():
    labs = json.loads(LABELS.read_text())
    period = []
    for k, lmx in labs.items():
        clefs, notes = parse(lmx)
        part = PART[k.rsplit("-", 1)[1]]
        fn = far(notes, FAR if part in ("va", "vc") else 13)
        period.append({"key": k, "part": part, "clefs": clefs, "far": len(fn), "far_notes": fn[:6]})
    base = baseline()
    res = {"period": tally(period), "dataL2": tally(base["dataL2"]), "dataM": tally(base["dataM"])}
    res["period_clef_sequences"] = {p: Counter("-".join(r["clefs"]) for r in period if r["part"] == p).most_common(12)
                                    for p in ("vn1", "vn2", "va", "vc")}
    res["dataL2_clef_sequences"] = {p: Counter("-".join(r["clefs"]) for r in base["dataL2"] if r["part"] == p).most_common(8)
                                    for p in ("vn1", "vn2", "va", "vc")}
    # per score, the share of va/vc staves with far notes (a score whose encoding drops clef changes)
    per = defaultdict(Counter)
    for r in period:
        if r["part"] in ("va", "vc"):
            s = r["key"].split("/")[0]
            per[(s, r["part"])]["n"] += 1
            per[(s, r["part"])]["far"] += r["far"] > 0
            per[(s, r["part"])]["change"] += len(r["clefs"]) > 1
    res["per_score"] = {f"{s} {p}": dict(c) for (s, p), c in sorted(per.items())}

    # musvit-D4's readings of the 1,050 check staves against their labels
    reads = {r["key"]: r["read"] for r in json.loads((HERE / "period-pairing.json").read_text())["staves"]}
    cmp = []
    for k, got in reads.items():
        part = PART[k.rsplit("-", 1)[1]]
        lc, ln = parse(labs[k])
        rc, rn = parse(got)
        lb, rb = bars(labs[k]), bars(got)
        shifts = Counter(shift(a, b) for a, b in zip(lb, rb))
        fn = far(ln, FAR if part in ("va", "vc") else 13)
        cmp.append({"key": k, "part": part, "set": "check", "label_clefs": lc,
                    "read_clefs": rc, "agree": lc == rc, "label_far": len(fn),
                    "read_far": len(far(rn, FAR if part in ("va", "vc") else 13)),
                    "bars_same": shifts.get(0, 0), "bars_shifted": {str(s): n for s, n in shifts.items()
                                                                    if s not in (0, None)},
                    "bars": len(lb)})
    by = defaultdict(Counter)
    for c in cmp:
        b = by[(c["set"], c["part"])]
        b["staves"] += 1
        b["clefs_differ"] += not c["agree"]
        b["label_change"] += len(c["label_clefs"]) > 1
        b["read_change"] += len(c["read_clefs"]) > 1
        b["label_far"] += c["label_far"] > 0
        b["read_far"] += c["read_far"] > 0
        b["label_far_and_read_not"] += c["label_far"] > 0 and c["read_far"] == 0
        b["shifted_bar"] += any(abs(int(s)) >= 5 for s in c["bars_shifted"])
    res["reads"] = {f"{s} {p}": dict(by[(s, p)]) for s, p in sorted(by)}
    res["disagree"] = [c for c in cmp if not c["agree"]]
    res["far_examples"] = [c for c in cmp if c["label_far"] and c["part"] in ("va", "vc")]
    (HERE / "clef-check.json").write_text(json.dumps(res, indent=1, default=list))
    for k in ("period", "dataL2", "dataM"):
        print(k)
        for p, c in res[k].items():
            n = c["staves"]
            print(f"  {p:4} {n:6}  change {c.get('change', 0):4} ({c.get('change', 0) / n:.1%})  "
                  f"unusual {c.get('unusual', 0):4} ({c.get('unusual', 0) / n:.1%})  far {c.get('far', 0):4} ({c.get('far', 0) / n:.1%})")
    for p, seqs in res["period_clef_sequences"].items():
        print("period", p, seqs)
    for p, seqs in res["dataL2_clef_sequences"].items():
        print("dataL2", p, seqs)
    print("reads")
    for k, c in res["reads"].items():
        print(" ", k, c)


def caption(k: str, lmx: str, read: str | None) -> str:
    """The key, the label's clefs with the measure each starts in, its far notes, and the reading's."""
    part = PART[k.rsplit("-", 1)[1]]
    _, ln = parse(lmx)
    starts, prev = [], None
    for m, c, _ in ln:
        if c != prev:
            starts.append(f"m{m + 1} {NAME.get(c, c)}")
            prev = c
    s = f"{k} {part} | LABEL {' > '.join(starts)}"
    fn = far(ln, FAR if part in ("va", "vc") else 13)
    if fn:
        s += " | far: " + ", ".join(f"m{m + 1} {p} ({d:+d})" for m, _, p, d in fn[:4])
    if read is not None:
        rc, _ = parse(read)
        sh = [f"m{i + 1} {shift(a, b):+d}" for i, (a, b) in enumerate(zip(bars(lmx), bars(read)))
              if shift(a, b) not in (0, None)]
        s += f" | D4 {' > '.join(NAME.get(c, c) for c in rc)}" + (f", bars shifted {' '.join(sh)}" if sh else "")
    return s


def sheets(out_dir: str, seed: int = 0):
    """sheets.json for `sheet`: the readings that disagree with the label,
    the read staves with far notes, far-note staves from the scores with the
    most, staves whose label changes clef, and agreeing cello staves."""
    import random
    rng = random.Random(seed)
    labs = json.loads(LABELS.read_text())
    reads = {r["key"]: r["read"] for r in json.loads((HERE / "period-pairing.json").read_text())["staves"]}
    res = json.loads((HERE / "clef-check.json").read_text())
    vv = lambda k: PART[k.rsplit("-", 1)[1]] in ("va", "vc")
    info = {k: parse(v) for k, v in labs.items()}
    nfar = {k: len(far(info[k][1], FAR if vv(k) else 13)) for k in labs}
    groups = {
        "disagree": [c["key"] for c in res["disagree"]],
        "read-far": [c["key"] for c in res["far_examples"]],
        "change": rng.sample(sorted(k for k in labs if vv(k) and len(info[k][0]) > 1), 12),
        "agree-vc": rng.sample(sorted(k for k in reads if k.endswith("-4") and len(info[k][0]) == 1 and not nfar[k]
                                      and parse(reads[k])[0] == info[k][0]), 24),
    }
    groups["va-far"] = sorted(k for k in labs if k.endswith("-3") and nfar[k])
    groups["vc-starts-treble"] = rng.sample(sorted(k for k in labs if k.endswith("-4") and info[k][0][:1] == ["G2"]), 12)
    worst = sorted(res["per_score"], key=lambda s: -res["per_score"][s]["far"])[:8]
    groups["far-unread"] = []
    for sp in worst:
        sq, p = sp.split()
        pool = sorted(k for k in labs if k.startswith(sq) and PART[k[-1]] == p and nfar[k] and k not in reads)
        groups["far-unread"] += rng.sample(pool, min(3, len(pool)))
    spec = {}
    only = os.environ.get("SHEETS", "")
    for g, keys in groups.items():
        if only and g not in only.split(","):
            continue
        for i in range(0, len(keys), 12):
            spec[f"{out_dir}/{g}-{i // 12}.png"] = [[k, caption(k, labs[k], reads.get(k))] for k in keys[i:i + 12]]
    Path(out_dir, "sheets.json").write_text(json.dumps(spec, indent=1))
    print(sum(len(v) for v in spec.values()), "staves in", len(spec), "sheets ->", Path(out_dir, "sheets.json"))


if __name__ == "__main__" and len(sys.argv) > 1:
    {"analyze": lambda: analyze(), "sheets": lambda: sheets(*sys.argv[2:3] or [str(TMP)])}[sys.argv[1]]()
