# /// script
# requires-python = ">=3.11"
# dependencies = ["torch", "transformers", "peft", "pillow", "numpy"]
# ///
"""Score readers on held-out staves (dataset.py's lists), bar by bar, as
the clean test is scored: notes and rhythm apart from markings.

    uv run experiments/musvit/held_out.py SAMPLES... --runs D3S-h96 D5-B6k [--device mps]

For each reader: the share of bars exact in notes and rhythm (pitches,
rests, durations, dots, chords, graces, tuplets: what compare.py compares
on the clean test), in rhythm alone and in pitch alone; the staves read
with a bar too many or too few (their bars count as wrong); the same
share on the staves every reader counts right; and, apart, the errors in
markings (beams, slurs, ties, articulations), where pairing's labels
follow the encoding, not the copyist. proto.py's score (every token, a
staff exact or not) mixes them: on Dresden's Mus.3403 it read Boccherini
6k as much better than D4 for its beams alone
(reports/2026-10-22-boccherini-6k). Readings are kept in
~/.cache/manuscript-labeler/musvit/held-out/.
"""

import argparse
import difflib
import json
import re
from collections import Counter
from pathlib import Path

import proto

OUT = Path.home() / ".cache/manuscript-labeler/musvit/held-out"
PITCH = re.compile(r"[A-G]-?\d$")
TUPLET = re.compile(r"\d+in\d+$")
DURATIONS = {"breve", "whole", "half", "quarter", "eighth", "16th", "32nd", "64th"}
MARKS = {"beam": lambda t: t.startswith("beam:"), "slur": lambda t: t.startswith("slur:"),
         "tie": lambda t: t.startswith("tied:"),
         "articulation": lambda t: t in ("staccato", "staccatissimo", "accent", "tenuto", "fermata", "trill-mark",
                                         "turn", "mordent", "strong-accent")}


def notes(bar: str) -> list[str]:
    """A bar's notes and rhythm, as the clean test compares them."""
    return [t for t in bar.split() if PITCH.match(t) or t in DURATIONS or TUPLET.match(t)
            or t in ("dot", "rest", "chord", "grace")]


def bars(lmx: str) -> list[str]:
    return lmx.split("measure")[1:]


def readings(run: str, items: list, device: str, name: str) -> dict[str, str]:
    f = OUT / f"{name}-{run}.json"
    if f.exists():
        return json.loads(f.read_text())
    got = proto.read_crops(run, "reader.pt", {str(p): p.read_bytes() for p, _ in items}, device)
    OUT.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(got))
    return got


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("samples", nargs="+", type=Path)
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--device", default="mps")
    a = ap.parse_args()
    items = proto.staves(a.samples)
    name = "+".join(s.stem.removeprefix("samples.") for s in a.samples)
    labels = {str(p): " ".join(t) for p, t in items}
    got = {run: readings(run, items, a.device, name) for run in a.runs}
    counted = [k for k in labels if all(len(bars(got[r][k])) == len(bars(labels[k])) for r in a.runs)]
    n_bars = sum(len(bars(labels[k])) for k in labels)
    print(f"{name}: {len(labels)} staves, {n_bars} bars; {len(counted)} staves every reader counts right")
    print(f"{'reader':22} {'bars exact':>10} {'rhythm':>7} {'pitch':>6} {'miscounted':>10} {'exact, counted':>14}  "
          + "  ".join(f"{m} errors" for m in MARKS))
    for run in a.runs:
        exact = rhythm = pitch = exact_counted = n_counted = miscounted = 0
        marks = Counter()
        for k, want in labels.items():
            bw, bg = bars(want), bars(got[run][k])
            if len(bw) != len(bg):
                miscounted += 1
            else:
                for x, y in zip(bw, bg):
                    a_, b_ = notes(x), notes(y)
                    exact += a_ == b_
                    rhythm += [t for t in a_ if not PITCH.match(t)] == [t for t in b_ if not PITCH.match(t)]
                    pitch += [t for t in a_ if PITCH.match(t)] == [t for t in b_ if PITCH.match(t)]
                if k in counted:
                    n_counted += len(bw)
                    exact_counted += sum(notes(x) == notes(y) for x, y in zip(bw, bg))
            for m, is_m in MARKS.items():  # edits between the marking tokens alone, staff by staff
                w, g = [t for t in want.split() if is_m(t)], [t for t in got[run][k].split() if is_m(t)]
                sm = difflib.SequenceMatcher(None, w, g, autojunk=False)
                marks[m] += sum(max(i2 - i1, j2 - j1) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal")
        print(f"{run:22} {exact / n_bars:10.1%} {rhythm / n_bars:7.1%} {pitch / n_bars:6.1%} {miscounted:10} "
              f"{exact_counted / max(n_counted, 1):14.1%}  " + "  ".join(f"{marks[m]:>{len(m) + 7}}" for m in MARKS))


if __name__ == "__main__":
    main()
