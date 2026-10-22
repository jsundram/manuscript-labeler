# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow"]
# ///
"""The known encodings of the test-bed quartets, bar by bar, each bar's
events as compare.py compares them (experiments/zeus/compare.py: a chord as
one event, a rest, a grace note; voices merged).

    uv run experiments/print-omr/truth.py            all four
    uv run experiments/print-omr/truth.py 213 228    some

- G. 213: OSSQ-OMR's corrected encoding (experiments/zeus/ossq/mxl.py);
  every <measure> is a bar, so a bar a repeat splits is two.
- G. 228 (Op48-3): the Op. 48 edition's own encoding (its scripts/events.py),
  both movements.
- G. 159 (Op02-1), G. 189 (Op24-1): Philhar's LilyPond (experiments/zeus/philhar.py).

A multi-bar rest is written out: one bar rest ("R") per bar it spans.

Writes truth/G<n>.json: {part: {movement: [{"bar": label, "events": [...]}]}}.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ZEUS = HERE.parent / "zeus"
sys.path.insert(0, str(ZEUS))
sys.path.insert(0, str(ZEUS / "ossq"))
import compare  # noqa: E402
import mxl  # noqa: E402

EDITION = Path.home() / "Dropbox/Code/boccherini-opus-48"
LILY = Path.home() / "Dropbox/Code/boccherini-quartet-data/lilypond"
OSSQ_G213 = Path.home() / "Data/manuscript-labeler/zeus/g213/sq8454356_cleaned.musicxml"
PARTS = ("vn1", "vn2", "va", "vc")
ROMAN = ["I", "II", "III", "IV"]
PHILHAR = {159: "Op02-1", 189: "Op24-1"}


def clean(e: dict) -> dict:
    return {"kind": e["kind"], "pitches": list(e["pitches"]), "dur": e["dur"], "dots": e["dots"],
            "grace": bool(e["grace"]), "acc": list(e["acc"])}


def from_events_json(bars_json: dict) -> list[dict]:
    """events.py's JSON ({bar: [cols]}) as bars of compare events; the bars
    an mmrest spans, which events.py leaves out after its first, as bar rests."""
    out = []
    nums = [int(n) for n in bars_json]
    rest = {"kind": "rest", "pitches": [], "dur": "bar", "dots": 0, "grace": False, "acc": []}
    for n in range(min(nums), max(nums) + 1):
        cols = bars_json.get(str(n))
        if cols is None:  # inside a multi-bar rest: events.py lists only its first bar
            out.append({"bar": str(n), "events": [dict(rest)]})
            continue
        out.append({"bar": str(n), "events": [clean(e) for e in compare.encoded(cols)]})
    return out


def g213() -> dict:
    mv = mxl.movements(OSSQ_G213)
    out = {}
    for p in PARTS:
        out[p] = {}
        for k, bars in enumerate(mv[p]):
            out[p][ROMAN[k]] = [{"bar": b["number"], "events": [clean(e) for e in b["events"]]} for b in bars]
    return out


def g228() -> dict:
    out = {}
    for p in PARTS:
        out[p] = {}
        for mvt in ("I", "II"):
            r = subprocess.run(["uv", "run", "--offline", str(EDITION / "scripts" / "events.py"), "Op48-3", p, mvt,
                                "--json"], capture_output=True, text=True, check=True, cwd=EDITION)
            out[p][mvt] = from_events_json(json.loads(r.stdout))
    return out


def philhar(g: int) -> dict:
    q = PHILHAR[g]
    out = {}
    env = {k: v for k, v in os.environ.items() if k != "UV_PYTHON_INSTALL_DIR"}
    for p in PARTS:
        out[p] = {}
        for mvt in ("I", "II", "III"):
            r = subprocess.run(["uv", "run", str(ZEUS / "philhar.py"), str(EDITION), str(LILY), q, p, mvt, "--json"],
                               capture_output=True, text=True, check=True, env=env)
            out[p][mvt] = from_events_json(json.loads(r.stdout)["bars"])
    return out


def main():
    which = [int(x) for x in sys.argv[1:]] or [159, 189, 213, 228]
    (HERE / "truth").mkdir(exist_ok=True)
    for g in which:
        d = g213() if g == 213 else g228() if g == 228 else philhar(g)
        (HERE / "truth" / f"G{g}.json").write_text(json.dumps(d))
        print(f"G. {g}:", {p: {m: len(b) for m, b in d[p].items()} for p in d})


if __name__ == "__main__":
    main()
