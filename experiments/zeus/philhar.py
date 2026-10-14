# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow"]
# ///
"""Each bar's events in Philhar's encodings (boccherini-quartet-data,
lilypond/OpNN-n/), read as the edition's scripts/events.py reads its own.

    uv run experiments/zeus/philhar.py <edition-repo> <lilypond-dir> Op33-1 vn1 I [--json]

Philhar's layout is the one the edition copied: Trame.ily holds the
skeleton (time, key, repeats, spacer bars) under \\tag #'mvtI ..., the
notes are in 0X-{V1,V2,A,Vc}-M.ily, written once, tagged 'partie for the
parts. So events.py's engraver runs on them unchanged, with Trame.ily
for Structure.ily and 'partie for 'part.

It also says where a bar line falls inside a bar (a repeat with an
upbeat): with --json, those bars are listed under "split"; and the key
(in fifths) and time in force from each bar where they change, under
"key_time".
"""

import json
import re
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

FILES = {"vn1": "01-V1", "vn2": "02-V2", "va": "03-A", "vc": "04-Vc"}
ROMAN = ["I", "II", "III", "IV"]

# bar lines drawn where a bar isn't over: a repeat sign inside a bar
SPLITS = r'''
#(define splits (open-output-file "%(splits)s"))
#(define last-kt "")
#(define (split-staff context)
   (make-engraver
    ; at the end of the timestep: a \key or \time at this moment is in force by then
    ((stop-translation-timestep engraver)
     (let* ((alts (ly:context-property context 'keyAlterations '()))
            (fifths (apply + (map (lambda (a) (if (> (cdr a) 0) 1 -1)) alts)))
            (ts (ly:context-property context 'timeSignatureFraction '(4 . 4)))
            (kt (format #f "~a ~a/~a" fifths (car ts) (cdr ts))))
       (if (not (equal? kt last-kt))
           (begin (set! last-kt kt)
                  (format splits "KT ~a ~a ~a~%%" (ly:context-property context 'currentBarNumber 1)
                          (ly:moment-main (ly:context-property context 'measurePosition)) kt)))))
    (acknowledgers
     ((bar-line-interface engraver grob source)
      (let ((pos (ly:context-property context 'measurePosition)))
        (if (> (ly:moment-main pos) 0)
            (format splits "~a ~a~%%" (ly:context-property context 'currentBarNumber 1)
                    (ly:moment-main pos))))))))
'''


def events_module(edition: Path):
    sys.path.insert(0, str(edition / "scripts"))
    import events
    return events


def movements(quartet_dir: Path) -> list[str]:
    nums = sorted({int(m.group(1)) for f in quartet_dir.glob("01-V1-*.ily")
                   if (m := re.fullmatch(r"01-V1-(\d+)\.ily", f.name))})
    return [ROMAN[n - 1] for n in nums]


def measure(quartet_dir: Path, mvt: str) -> Fraction:
    """The bar's length from the movement's first \\time in Trame.ily."""
    text = (quartet_dir / "Trame.ily").read_text(errors="replace")
    block = text[text.index(f"\\tag #'mvt{mvt}"):]
    n, d = re.search(r"\\time\s+(\d+)/(\d+)", block).groups()
    return Fraction(int(n), int(d))


def run(events, quartet_dir: Path, part: str, mvt: str) -> tuple[str, str]:
    file = f"{FILES[part]}-{ROMAN.index(mvt) + 1}.ily"
    ly = (events.LY
          .replace(r"\playOnce ", "")
          .replace('"Structure.ily"', '"Trame.ily"')
          .replace("#'part {", "#'partie {")
          .replace(r"\Staff \consists #encode-staff", r"\Staff \consists #encode-staff \consists #split-staff"))
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        out, splits = tmp / "events.txt", tmp / "splits.txt"
        ly = ly % {"out": out.as_posix(), "mvt": mvt, "file": file}
        ly = ly.replace(r"\score {", SPLITS.replace("%(splits)s", splits.as_posix()).replace("%%", "%")
                        + r"\score {", 1)
        (tmp / "events.ly").write_text(ly)
        r = subprocess.run(["lilypond", "-dbackend=cairo", "-dno-print-pages", "-o", str(tmp / "x"),
                            "-I", str(quartet_dir), str(tmp / "events.ly")], capture_output=True, text=True)
        if r.returncode or not out.exists():
            raise RuntimeError(f"LilyPond failed on {quartet_dir.name}/{file}:\n{r.stderr[-3000:]}")
        return out.read_text(), splits.read_text() if splits.exists() else ""


def read(edition: Path, quartet_dir: Path, part: str, mvt: str) -> tuple[dict, set[int], dict]:
    """({bar: events.Bar}, bars a bar line falls inside, {bar: (key in fifths, time)}
    where the key or time changes, as in force from that bar)."""
    events = events_module(edition)
    m = measure(quartet_dir, mvt)
    dump, splits = run(events, quartet_dir, part, mvt)
    split, changes = set(), {}
    for line in splits.splitlines():
        f = line.split()
        if f[0] == "KT":
            bar, pos = int(f[1]), Fraction(f[2])
            if pos < 0:
                bar -= 1
            elif pos > 0:            # off the bar line: from the next bar
                bar += 1
            changes[bar] = (int(f[3]), f[4])
            continue
        bar, pos = int(f[0]), Fraction(f[1])
        if pos < 0:                  # inside a pickup: LilyPond's bar 1 at a negative position
            bar -= 1
        split.add(bar)
    return events.parse(dump, m), split, changes


def main():
    if len(sys.argv) < 6:
        sys.exit(__doc__)
    edition, lily = Path(sys.argv[1]), Path(sys.argv[2])
    quartet, part, mvt = sys.argv[3], sys.argv[4].lower(), sys.argv[5]
    bars, split, changes = read(edition, lily / quartet, part, mvt)
    if "--json" in sys.argv[6:]:
        events = events_module(edition)
        print(json.dumps({"bars": events.to_json(bars), "split": sorted(split),
                          "key_time": {str(b): list(kt) for b, kt in sorted(changes.items())}}, indent=1))
        return
    for num in sorted(bars):
        print(bars[num].describe())
    print("split:", sorted(split))
    print("key, time from bar:", changes)


if __name__ == "__main__":
    main()
