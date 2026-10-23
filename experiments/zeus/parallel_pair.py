# /// script
# requires-python = ">=3.11"
# ///
"""The parallel pairer: autopair.py again on every paired source, each with
the options it was first paired with, one source per core. Pairing is CPU
work in one process each, so it maps the sources' runs onto the cores and
then runs the merges that wait on them.

    uv run experiments/zeus/parallel_pair.py [--jobs N] [--groups M W G] [SOURCE ...]

The groups, and the recipes they repeat:
  M  philhar-repair/sources.txt: Philhar's quartet encodings, read by
     musvit-D3S-h96; a source in musvit-D4's training (a "before" set, not
     a -score) also by musvit-C4-bocch-tf8-L-best, then both.py
     (philhar-repair/build.sh).
  W  wayback-print-pairs/sources.txt: Philhar's other works (W), or the
     print's reading (P), with --head-box (wayback-print-pairs/build.sh).
  G  G. 213's three copies against its MusicXML score, then g213/merge.py
     (g213/README.md).

The readings must be cached (answers/), as `--model /nonexistent/<reader>`
reads none; experiments/musvit/read_auto.py reads a source first. Each
run's output goes to LOGS/<source>[-<reader>].log. A full re-pair takes
about 6 minutes on the Mac mini (M1) with six at a time and Philhar's
encodings cached (philhar.encoding), about 45 one at a time.
"""

import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOME = Path.home()
EDITION = HOME / "Dropbox/Code/boccherini-opus-48"
QUARTET_LILY = HOME / "Dropbox/Code/boccherini-quartet-data/lilypond"
SITE_LILY = HOME / "Data/manuscript-labeler/philhar-site/lily"
PRINT = HERE.parents[1] / "experiments/print-omr/G223/BA2676-G223.json"
G213_XML = HOME / "Data/manuscript-labeler/zeus/g213/sq8454356_cleaned.musicxml"
LOGS = HOME / ".cache/manuscript-labeler/zeus/pair-logs"
D4, C4 = "musvit-D3S-h96", "musvit-C4-bocch-tf8-L-best"
FULL = ["--any-count", "--neighbours", "--neighbours-paired", "--short-ends", "--long-ends"]
# G. 213's merges (g213/README.md): Berlin print pages to Sibley's, and the staves checked by eye
G213_PAGES = "11:1,12:2,13:3,15:4,16:5,29:6,30:7,31:8,32:9,43:10,44:11,45:12,46:13,57:14,58:15,59:16,60:17"
EYED_DB, EYED_SIB = "p43-5,p43-6,p44-2,p44-11,p30-10", "p1-11,p2-1,p13-12,p15-12"


def rows(path: Path) -> list[list[str]]:
    return [line.split() for line in path.read_text().splitlines() if line.strip() and not line.startswith("#")]


def autopair(source: str, reader: str, *opts: str) -> list[str]:
    return ["uv", "run", "--python-preference", "only-managed", "autopair.py", str(EDITION), "--source", source,
            *opts, "--model", f"/nonexistent/{reader}"]


def jobs(groups: set[str], only: set[str]) -> tuple[list[tuple[str, list[str]]], list[list[str]]]:
    """(name, autopair command) for every run, and the merges to run after them, in order."""
    runs, after = [], []
    want = lambda s: not only or s in only
    if "M" in groups:
        old = []
        for s, quartets, before in rows(HERE / "philhar-repair" / "sources.txt"):
            if not want(s):
                continue
            readers = [D4] + ([C4] if before != "-" and not s.endswith("-score") else [])
            old += [s] if len(readers) > 1 else []
            for r in readers:
                runs.append((f"{s}-{r}", autopair(s, r, "--philhar", str(QUARTET_LILY), "--quartets", quartets, *FULL)))
        if old:
            after.append(["uv", "run", "philhar-repair/both.py", *old])
    if "W" in groups:
        for g, s, _pages, quartets, _pdf in rows(HERE / "wayback-print-pairs" / "sources.txt"):
            if want(s):
                enc = ["--philhar", str(SITE_LILY), "--quartets", quartets] if g == "W" else ["--print-bars", str(PRINT)]
                runs.append((s, autopair(s, D4, *enc, *FULL, "--head-box")))
    if "G" in groups:
        g213 = [s for s in ("G213-Sibley", "G213-DB-Pleyel", "G213-KHM587") if want(s)]
        for s in g213:
            runs.append((s, autopair(s, D4, "--musicxml", str(G213_XML), "--any-count", "--neighbours", "--short-ends")))
        if g213:
            back = ",".join(":".join(p.split(":")[::-1]) for p in G213_PAGES.split(","))
            after += [["uv", "run", "g213/merge.py", "G213-DB-Pleyel", "G213-Sibley", "--pages", G213_PAGES,
                       "--eyed", EYED_DB, "--twin-eyed", EYED_SIB],
                      ["uv", "run", "g213/merge.py", "G213-Sibley", "G213-DB-Pleyel", "--pages", back,
                       "--eyed", EYED_SIB, "--twin-eyed", EYED_DB],
                      ["uv", "run", "g213/merge.py", "G213-KHM587", "-"]]
    return runs, after


def run(name: str, cmd: list[str]) -> bool:
    env = {**os.environ, "UV_PYTHON_INSTALL_DIR": str(HOME / ".cache/manuscript-labeler/zeus/py")}
    with open(LOGS / f"{name}.log", "w") as log:
        ok = subprocess.run(cmd, cwd=HERE, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log).returncode == 0
    print(f"{name}: {('merged' if name.startswith('merge-') else 'paired') if ok else f'FAILED (see {LOGS / name}.log)'}",
          flush=True)
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sources", nargs="*", help="only these sources (default: every one in the groups)")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2), help="runs at once (default: cores - 2)")
    ap.add_argument("--groups", nargs="+", default=["M", "W", "G"], choices=["M", "W", "G"])
    a = ap.parse_args()
    runs, after = jobs(set(a.groups), set(a.sources))
    if not runs:
        sys.exit("no source matched")
    LOGS.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(a.jobs) as pool:  # each run is its own process: threads only wait on them
        ok = all(list(pool.map(lambda r: run(*r), runs)))
    for cmd in after:  # the merges read the runs' results
        name = "merge-" + "-".join(x for x in cmd[2:4] if x != "-").replace("/", "-").replace(".py", "")
        ok = run(name, cmd) and ok
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
