"""Numbers for the cheap runs: SER on Madrid, Op. 32, Dolores, OmniOMR (per staff, paired bootstrap over staves
against a baseline), and the clean test's bars exact (paired bootstrap over bars).

    python analyze.py BASE RUN [RUN ...]
"""
import json, random, sys
from pathlib import Path

HERE = Path(__file__).parent
S = HERE.parent
B = S / "bench"
C = Path.home() / ".cache/manuscript-labeler/zeus"
R = Path("/Users/jsundram/Dropbox/Code/manuscript-labeler/experiments/zeus/results")


def edits(a, b):
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def refs(test):
    if test == "madrid":
        out = {}
        for i, f in enumerate(sorted((C / "dataT").glob("samples.*.txt"))):
            out |= {(i, l): (f.parent / l).with_suffix(".lmx").read_text().split() for l in f.read_text().split()}
        return out
    if test == "op32":
        f = C / "dataM" / "samples.Op32-G201-206.txt"
        return {l: (f.parent / l).with_suffix(".lmx").read_text().split() for l in f.read_text().split()}
    return {l: (B / test / l).with_suffix(".lmx").read_text().split() for l in (B / f"{test}-test.txt").read_text().split()}


def readings(test, run):
    if test == "madrid":
        out = {}
        for f in sorted(HERE.glob(f"madrid*-{run}.json")):
            i = int(f.name.split("-")[0][len("madrid"):])
            out |= {(i, k): v.split() for k, v in json.loads(f.read_text()).items()}
        return out
    f = HERE / f"{test}-{run}.json"
    return {k: v.split() for k, v in json.loads(f.read_text()).items()} if f.exists() else None


def per_staff(test, run, ref):
    got = readings(test, run)
    if not got:
        return None
    return {k: (edits(got[k][: 2 * len(r)], r), len(r)) for k, r in ref.items()}


def boot(a, b, keys, stat, n=2000):
    rng = random.Random(0)
    ds = []
    for _ in range(n):
        s = [rng.choice(keys) for _ in keys]
        ds.append(stat(b, s) - stat(a, s))
    ds.sort()
    return ds[int(.025 * n)], ds[int(.975 * n)]


def ser(d, keys):
    return sum(d[k][0] for k in keys) / sum(d[k][1] for k in keys)


def bars(run):
    f = R / f"D-B_KHM-603-I-musvit-{run}-best.json"
    if not f.exists():
        return None
    return {(b["part"], b["movement"], b["bar"]): b["exact"] for b in json.loads(f.read_text())["bars"]}


def exact(d, keys):
    return sum(d[k] for k in keys)


base, runs = sys.argv[1], sys.argv[2:]
rows = []
for test in ("madrid", "op32", "dolores", "omniomr"):
    ref = refs(test)
    a = per_staff(test, base, ref)
    if a is None:
        continue
    keys = list(ref)
    rows.append(f"| {test} SER ({len(keys)} staves) | {100 * ser(a, keys):.1f}% | "
                + " | ".join(
                    (lambda d: f"{100 * ser(d, keys):.1f}% ({100 * (ser(d, keys) - ser(a, keys)):+.1f}; "
                     + "{:+.1f} to {:+.1f})".format(*(100 * x for x in boot(a, d, keys, ser))))(per_staff(test, r, ref))
                    if readings(test, r) else "–" for r in runs) + " |")
a = bars(base)
if a:
    keys = list(a)
    cells = []
    for r in runs:
        d = bars(r)
        if not d:
            cells.append("–"); continue
        k = [x for x in keys if x in d]
        lo, hi = boot(a, d, k, exact)
        cells.append(f"{exact(d, k)} ({exact(d, k) - exact(a, k):+d}; {100 * lo / len(k):+.1f} to {100 * hi / len(k):+.1f} pts)")
    rows.append(f"| clean test, bars exact (/{len(keys)}) | {exact(a, keys)} | " + " | ".join(cells) + " |")
print(f"| | {base} | " + " | ".join(runs) + " |")
print("|---|---:|" + "---:|" * len(runs))
print("\n".join(rows))
