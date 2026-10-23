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
upbeat): with --json, those bars are listed under "split"; a note
abbreviated with stem strokes (c2.:8, six eighths written as a dotted
half) carries "tremolo", the value it stands for repeated; and the key
(in fifths) and time in force from each bar where they change, under
"key_time".

encoding() runs it once for each set of inputs (cache_key: Philhar's
files for the quartet, this script, the edition's events.py, the part,
the movement, LilyPond) and keeps its --json output in CACHE.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

# va2: a quintet's second viola (M. Haydn's MH 411, in experiments/philhar-mss/adapt.py's layout)
FILES = {"vn1": "01-V1", "vn2": "02-V2", "va": "03-A", "vc": "04-Vc", "va2": "05-A2"}
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"]
CACHE = Path.home() / ".cache" / "manuscript-labeler" / "zeus" / "philhar"

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
    ; a note abbreviated with stem strokes (c2.:8): where, and the value it stands for repeated (8: eighths)
    (listeners
     ((tremolo-event engraver ev)
      (let ((m (ly:context-property context 'measurePosition)))
        (format splits "TR ~a ~a ~a ~a~%%" (ly:context-property context 'currentBarNumber 1)
                (ly:moment-main m) (ly:moment-grace m) (ly:event-property ev 'tremolo-type 0)))))
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


def read(edition: Path, quartet_dir: Path, part: str, mvt: str) -> tuple[dict, set[int], dict, dict]:
    """({bar: events.Bar}, bars a bar line falls inside, {bar: (key in fifths, time)}
    where the key or time changes, as in force from that bar, {(bar, position, grace):
    the value a note abbreviated with stem strokes stands for, repeated (8: eighths)})."""
    events = events_module(edition)
    m = measure(quartet_dir, mvt)
    dump, splits = run(events, quartet_dir, part, mvt)
    split, changes, tremolo = set(), {}, {}
    for line in splits.splitlines():
        f = line.split()
        if f[0] == "TR":
            bar, pos, grace = int(f[1]), Fraction(f[2]), Fraction(f[3])
            if pos < 0:              # a pickup, as events.parse places it
                bar, pos = bar - 1, pos + m
            tremolo[(bar, pos, grace)] = int(f[4])
            continue
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
    return events.parse(dump, m), split, changes, tremolo


VALUES = {"breve": Fraction(2), "whole": Fraction(1), "half": Fraction(1, 2), "quarter": Fraction(1, 4),
          "8th": Fraction(1, 8), "16th": Fraction(1, 16), "32nd": Fraction(1, 32), "64th": Fraction(1, 64)}  # events.py's names
NAMES = {4: "quarter", 8: "8th", 16: "16th", 32: "32nd", 64: "64th"}


def written_out(cols: list[dict]) -> list[dict]:
    """A bar's events (--json's) with each note abbreviated by stem strokes
    ("tremolo") written out as the notes it stands for: a dotted half with
    :8, six eighths of its pitches, beamed together. Its slur, marks and
    text go on the first, its tie on the last."""
    out = []
    for k, c in enumerate(cols):
        t = c.get("tremolo")
        if not t or c["kind"] != "note" or t not in NAMES:
            out.append(c)
            continue
        dur = c["dur"] or ""
        length = VALUES[dur.rstrip(".")] * (2 - Fraction(1, 2 ** dur.count(".")))
        n = int(length * t)
        # in a tuplet the note lasts less than it's written: its notes share its span (to the next in its voice)
        nxt = next((Fraction(x["pos"]) for x in cols[k + 1:] if x["voice"] == c["voice"] and x["grace"] == "0"), None)
        step = (nxt - Fraction(c["pos"])) / n if nxt is not None else Fraction(1, t)
        for i in range(n):
            e = {k: v for k, v in c.items() if k != "tremolo"}
            e.update(label=f"{c['label']}.{i}", pos=str(Fraction(c["pos"]) + i * step), dur=NAMES[t],
                     beam=(["start"] if i == 0 else []) + (["stop"] if i == n - 1 else []),
                     tup=c["tup"] if i == 0 else [])  # (a "stop" closes the group before its event, a "start" opens one)
            if i:
                e.update(slur=[], slur_to=[], dyn=None, hair=[], text=None, art=[])
            if i < n - 1:
                e.update(tie=False, tie_to=None)
            out.append(e)
    return out


def cache_key(edition: Path, quartet_dir: Path, part: str, mvt: str) -> str:
    """A hash of everything a part's movement is read from: every file in
    Philhar's quartet folder, this script, the edition's events.py (and the
    facsimile.py it imports), the part and movement, and LilyPond (its path
    and when it was installed)."""
    h = hashlib.sha256(f"{part} {mvt}".encode())
    lily = shutil.which("lilypond")
    h.update(f"{lily} {Path(lily).resolve().stat().st_mtime if lily else ''}".encode())
    scripts = edition / "scripts"
    for f in [Path(__file__), scripts / "events.py", scripts / "facsimile.py",
              *sorted(f for f in quartet_dir.rglob("*") if f.is_file())]:
        h.update(f.name.encode() + b"\0" + (f.read_bytes() if f.exists() else b""))
    return h.hexdigest()[:20]


def encoding(edition: Path, lily: Path, quartet: str, part: str, mvt: str) -> dict:
    """This script's --json output for a part's movement: from CACHE where
    its inputs haven't changed (cache_key), else read with LilyPond (in its
    own environment) and kept."""
    f = CACHE / f"{quartet}.{part}.{mvt}.{cache_key(edition, lily / quartet, part, mvt)}.json"
    if f.exists():
        return json.loads(f.read_text())
    r = subprocess.run(["uv", "run", str(Path(__file__).resolve()), str(edition), str(lily), quartet, part, mvt, "--json"],
                       capture_output=True, text=True, check=True,
                       env={k: v for k, v in os.environ.items() if k != "UV_PYTHON_INSTALL_DIR"})
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(f".{os.getpid()}.tmp")  # two runs may write the same one at once
    tmp.write_text(r.stdout)
    tmp.replace(f)
    return json.loads(r.stdout)


def main():
    if len(sys.argv) < 6:
        sys.exit(__doc__)
    edition, lily = Path(sys.argv[1]), Path(sys.argv[2])
    quartet, part, mvt = sys.argv[3], sys.argv[4].lower(), sys.argv[5]
    bars, split, changes, tremolo = read(edition, lily / quartet, part, mvt)
    if "--json" in sys.argv[6:]:
        events = events_module(edition)
        out = events.to_json(bars)
        for (bar, pos, grace), t in tremolo.items():  # on the note it abbreviates: "tremolo", the value repeated
            for c in out.get(str(bar), []):
                if c["kind"] == "note" and Fraction(c["pos"]) == pos and Fraction(c["grace"]) == grace:
                    c["tremolo"] = t
        print(json.dumps({"bars": out, "split": sorted(split),
                          "key_time": {str(b): list(kt) for b, kt in sorted(changes.items())}}, indent=1))
        return
    for num in sorted(bars):
        print(bars[num].describe())
    print("split:", sorted(split))
    print("key, time from bar:", changes)


if __name__ == "__main__":
    main()
