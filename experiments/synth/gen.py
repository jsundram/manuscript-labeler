# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "verovio==6.3.0", "resvg-py==0.5.0", "opencv-python-headless==4.10.0.84", "numpy", "lxml", "pillow",
#   # the LMX reader (Delinearizer); score_to_lmx.py writes LMX with Zeus's pinned encoder
#   "linearized-musicxml==1.0.0",
# ]
# ///
"""Synthetic training staves: LMX files drawn by copyist.py in a random hand, written as
dataset.py's folders are (GROUP/<id>.jpg and .lmx, samples.GROUP.txt).

    uv run experiments/synth/gen.py OUT GROUP LMX_LIST [--jobs 8] [--per 1] [--real-width] [--seed 0]

LMX_LIST: a text file of LMX paths, or of samples files (lines SOURCE/STAFF, beside them).
--real-width: an LMX beside a real staff's JPEG is drawn at that staff's length.
--per: drawings per LMX (each in its own hand and seed).
--match-density: hands in their usual proportions, each given music as dense as its real staves.
Writes hands.GROUP.json too: each drawn staff's hand.
"""
import argparse, json, random, re, sys, traceback
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import cv2
sys.path.insert(0, str(Path(__file__).parent))
import copyist

MAX_ASPECT = 2688 / 128  # proto.py's MAXW / H: wider staves are squeezed
HANDS = ["berlin"] * 25 + ["parisA"] * 20 + ["parisB"] * 20 + ["vma"] * 20 + ["generic"] * 15


# the middle half of each hand's real staves' notes and rests (explainer.py's measurement of dataL2)
DENSITY = {"berlin": (26, 43), "parisA": (26, 48), "parisB": (24, 35), "vma": (15, 26)}
EVENT = re.compile(r"^([A-G]\d|rest)$")


def events(lmx: str) -> int:
    toks = lmx.split()
    return sum(1 for t in toks if EVENT.match(t)) - toks.count("chord")


def by_density(srcs: list[Path], n: int, rng: random.Random) -> list[tuple[Path, str]]:
    """n staves with hands in HANDS' proportions, each hand's music as dense as its real staves (generic: any)."""
    pool = list(srcs)
    rng.shuffle(pool)
    dens = {s: events(s.read_text()) for s in pool}
    out, used = [], set()
    for hand in sorted(set(HANDS)):
        want = round(n * HANDS.count(hand) / len(HANDS))
        lo, hi = DENSITY.get(hand, (0, 10 ** 6))
        got = [s for s in pool if s not in used and lo <= dens[s] <= hi][:want]
        used.update(got)
        out += [(s, hand) for s in got]
    rng.shuffle(out)
    return out


def one(job):
    src, dst, seed, real_width, hand = job
    rng = random.Random(seed)
    hand = hand or rng.choice(HANDS)
    try:
        lmx = Path(src).read_text().strip()
        width = None
        jpg = Path(src).with_suffix(".jpg")
        if real_width and jpg.exists():
            h, w = cv2.imread(str(jpg), cv2.IMREAD_GRAYSCALE).shape
            width = w / h * 9 - 2
        img = copyist.draw(lmx, hand, seed=seed, width=width)
        if img.shape[1] / img.shape[0] > MAX_ASPECT:
            return hand, "skipped: longer than the reader takes"
        cv2.imwrite(str(dst.with_suffix(".jpg")), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        dst.with_suffix(".lmx").write_text(lmx + "\n")
        return hand, "ok"
    except ValueError as e:
        return hand, "skipped: " + str(e).split(",")[0][:40]
    except Exception as e:
        return hand, f"failed: {type(e).__name__}: {str(e)[:60]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("group")
    ap.add_argument("lists", nargs="+", type=Path)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--per", type=int, default=1)
    ap.add_argument("--real-width", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--match-density", action="store_true",
                    help="give each hand music as dense as its real staves (for new music; with --limit)")
    a = ap.parse_args()
    srcs = []
    for lst in a.lists:
        if lst.name.startswith("samples."):
            srcs += [lst.parent / f"{l}.lmx" for l in lst.read_text().split()]
        else:
            srcs += [Path(l) for l in lst.read_text().split()]
    rng = random.Random(a.seed)
    if a.match_density:
        picked = by_density(srcs, a.limit or len(srcs), rng)
    else:
        rng.shuffle(srcs)
        picked = [(s, None) for s in srcs[: a.limit]]
    d = a.out / a.group
    d.mkdir(parents=True, exist_ok=True)
    jobs, names = [], []
    for i, (s, hand) in enumerate(picked):
        for k in range(a.per):
            name = f"s{i:05d}-{k}"
            jobs.append((str(s), d / name, a.seed * 1_000_003 + i * 31 + k, a.real_width, hand))
            names.append(name)
    tally = Counter()
    kept, hands = [], {}
    with ProcessPoolExecutor(a.jobs) as ex:
        for n, (name, (hand, res)) in enumerate(zip(names, ex.map(one, jobs, chunksize=8))):
            tally[res] += 1
            if res == "ok":
                kept.append(f"{a.group}/{name}")
                hands[f"{a.group}/{name}"] = hand
                tally[hand] += 1
            if n % 2000 == 0:
                print(n, dict(tally.most_common(6)), flush=True)
    (a.out / f"samples.{a.group}.txt").write_text("\n".join(kept) + "\n")
    (a.out / f"hands.{a.group}.json").write_text(json.dumps(hands, indent=0))  # each staff's hand
    print(f"{a.group}: {len(kept)} of {len(jobs)} drawn", dict(tally.most_common()), flush=True)


if __name__ == "__main__":
    main()
