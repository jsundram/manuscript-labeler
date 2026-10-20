# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "verovio==6.3.0", "resvg-py==0.5.0", "opencv-python-headless==4.10.0.84", "numpy", "lxml", "pillow",
#   "linearized-musicxml==1.0.0",
# ]
# ///
"""Synthetic staves that change clef inside the staff, as Boccherini's copyists write it (dataS4).

Real quartet staves (OpenScore String Quartets, cut by score_to_lmx.py: osq-all.txt) with a stretch moved
to the clef a copyist would write it in where it sits high: cello bass to tenor or treble and back, viola
alto to treble and back. Mostly at a bar line, some inside a bar. The pitches are kept; only the clef, and
so where the notes sit, changes. The clef tokens go where our labels put them (dataL2's cello staves):
after `measure` (and any key and time) at a bar line, else right before the next note. Also staves that
open in a clef that isn't the part's usual one, the OSQ staves that already change clef as they are, and
plain violin staves for balance. Drawn by copyist.py with changes=True, in a random hand.

    uv run experiments/synth/gen_clefs.py OUT GROUP [--n 4000] [--jobs 6] [--seed 48] [--plan-only] [--limit N]

Writes OUT/GROUP/<id>.jpg and .lmx, samples.GROUP.txt, hands.GROUP.json and kinds.GROUP.json (each staff's
kind, source and clefs).
"""
import argparse, contextlib, json, random, re, sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from gen import DENSITY, HANDS, MAX_ASPECT, events  # noqa: E402

SYNTH = Path.home() / "Data/manuscript-labeler/experiments/synth"
OSQ_LIST, OSQ_DIR = SYNTH / "osq-all.txt", SYNTH / "osq-lmx"
VOCAB = Path.home() / ".cache/manuscript-labeler/models/musvit/musvit-D4@2026-10-20/vocab.json"
PITCH = re.compile(r"^([A-G])(\d)$")
STEPS = "CDEFGAB"
ATTR = re.compile(r"^(key:|time$|beats:|beat-type:|clef:)")
EVENT_START = re.compile(r"^([A-G]\d|rest|grace|grace:slash|chord|print-object:no)$")

# how many of each kind, per 1000 staves
KINDS = {
    "vc-treble": 280,   # cello: bass to treble inside the staff (mostly back again)
    "vc-tenor": 220,    # cello: bass to tenor
    "vc-open": 120,     # cello: opens in tenor or treble, mostly back to bass
    "va-treble": 170,   # viola: alto to treble
    "va-open": 50,      # viola: opens in treble
    "osq-real": 60,     # OSQ staves that already change clef or open unusually, as they are
    "vn-plain": 100,    # violins, unchanged, for balance
}
USUAL = {"vc": "F4", "va": "C3", "vn": "G2"}
# where each new clef fits a stretch (diatonic steps, C4 = 28): its lowest and highest note, and how high
# the stretch must reach in the part's usual clef for a copyist to bother (its highest note at least)
FIT = {
    ("vc", "G2"): dict(lo=26, hi=45, reach=30),   # treble: A3 up; reaches E4 (two ledger lines over bass)
    ("vc", "C4"): dict(lo=21, hi=33, reach=27),   # tenor: C3 to A4; reaches B3 (over the bass staff)
    ("va", "G2"): dict(lo=27, hi=45, reach=34),   # treble: B3 up; reaches B4 (a ledger line over alto)
}
MID_BAR = 0.18  # chance each change is inside a bar (where a stretch allows it)


def step(tok: str) -> int | None:
    m = PITCH.match(tok)
    return STEPS.index(m.group(1)) + 7 * int(m.group(2)) if m else None


def parse(toks: list[str]):
    """Boundaries where a clef may go: [(token index to insert at, at a bar line?)], and the notes:
    [(token index, diatonic step)]. Inside a bar only between beamed groups and tuplets, never before
    a grace or chord note, nor in bars with a second voice."""
    bounds, notes = [], []
    i, n = 0, len(toks)
    bar_starts = [k for k, t in enumerate(toks) if t == "measure"]
    for b, s in enumerate(bar_starts):
        e = bar_starts[b + 1] if b + 1 < len(bar_starts) else n
        j = s + 1
        while j < e and ATTR.match(toks[j]):
            j += 1
        bounds.append((j, True))
        bar = toks[s:e]
        two_voices = "backup" in bar or "forward" in bar
        depth = tup = 0
        prev_grace = False
        first = True
        k = j
        while k < e:
            t = toks[k]
            if EVENT_START.match(t):
                # an event: its prefix tokens, then pitch or rest
                start = k
                prefix = []
                while k < e and toks[k] in ("grace", "grace:slash", "chord", "print-object:no"):
                    prefix.append(toks[k])
                    k += 1
                if k < e and (step(toks[k]) is not None):
                    notes.append((start, step(toks[k])))
                ok = (not first and not two_voices and depth == 0 and tup == 0 and not prev_grace
                      and "grace" not in prefix and "chord" not in prefix)
                if ok:
                    bounds.append((start, False))
                if "chord" not in prefix:
                    prev_grace = "grace" in prefix
                first = False
                k += 1
                continue
            if t == "beam:begin":
                depth += 1
            elif t == "beam:end":
                depth -= 1
            elif t == "tuplet:start":
                tup += 1
            elif t == "tuplet:stop":
                tup -= 1
            elif ATTR.match(t) and t.startswith("clef:"):
                return None  # already changes clef: not for shifting
            k += 1
    return bounds, notes


def shift(lmx: str, part: str, new: str, opening: bool, rng: random.Random):
    """lmx with a stretch moved to clef `new` (and back to the usual clef after it, unless it runs to the
    end), or None if no stretch fits. opening: the stretch starts the staff."""
    toks = lmx.split()
    clefs = [t for t in toks if t.startswith("clef:")]
    if clefs != [f"clef:{USUAL[part]}"]:
        return None
    got = parse(toks)
    if got is None:
        return None
    bounds, notes = got
    fit = FIT[(part, new)]
    end = (len(toks), True)
    cands = []
    starts = [0] if opening else range(1, len(bounds))
    for ai in starts:
        a = bounds[ai]
        for bi in range(ai + 1, len(bounds) + 1):
            b = bounds[bi] if bi < len(bounds) else end
            ps = [p for k, p in notes if a[0] <= k < b[0]]
            if len(ps) < 3:
                continue
            if min(ps) < fit["lo"] or max(ps) > fit["hi"]:
                break  # longer stretches only add notes
            if max(ps) < fit["reach"]:
                continue
            if not opening and ai == 0:
                continue
            w = (1 + len(ps) ** 0.5) * (0.6 if bi == len(bounds) else 1.0)  # mostly back to the usual clef
            cands.append((w, ai, bi))
    if not cands:
        return None
    # each end's kind first (inside a bar with chance MID_BAR, where there is such a stretch), then a stretch
    mid_a, mid_b = rng.random() < MID_BAR, rng.random() < MID_BAR
    is_mid = lambda i: i < len(bounds) and not bounds[i][1]
    pool = []
    for strict_a, strict_b in ((True, True), (True, False), (False, True), (False, False)):
        pool = [c for c in cands if (opening or not strict_a or is_mid(c[1]) == mid_a)
                and (not strict_b or c[2] == len(bounds) or is_mid(c[2]) == mid_b)]
        if pool:
            break
        if rng.random() < 0.7:
            return None  # mostly try another staff rather than settle for the other kind of boundary
    w, ai, bi = rng.choices(pool, weights=[c[0] for c in pool])[0]
    ins = {}
    if opening:
        ci = toks.index(f"clef:{USUAL[part]}")
        toks[ci] = f"clef:{new}"
    else:
        ins[bounds[ai][0]] = f"clef:{new}"
    if bi < len(bounds):
        ins[bounds[bi][0]] = f"clef:{USUAL[part]}"
    out = []
    for k, t in enumerate(toks):
        if k in ins:
            out.append(ins[k])
        out.append(t)
    return " ".join(out)


MIDDLE = {"G2": 34, "C3": 28, "C4": 26, "F4": 22, "C1": 32, "C2": 30}  # each clef's middle line: C1 G4, C2 E4


def far_notes(lmx: str, limit: int = 10) -> int:
    """Notes more than `limit` steps from the middle line in the clef in force: past four ledger lines,
    where the crop cuts them off and where a copyist would have changed clef."""
    mid, n = None, 0
    for t in lmx.split():
        if t.startswith("clef:"):
            mid = MIDDLE.get(t[5:], mid)
        p = step(t)
        if p is not None and mid is not None and abs(p - mid) > limit:
            n += 1
    return n


def part_of(path: Path) -> str:
    return {"p0": "vn", "p1": "vn", "p2": "va", "p3": "vc"}[path.name.split("-")[0]]


def sources() -> list[Path]:
    """The OSQ staves (osq-all.txt, whose paths name an old scratch folder: re-rooted at osq-lmx)."""
    out = []
    for line in OSQ_LIST.read_text().split():
        p = Path(line)
        out.append(OSQ_DIR / p.parent.name / p.name)
    # OSQ's one Boccherini is G. 213 (Op. 39), not Op. 48: nothing of the clean test's work is drawn
    assert not [p for p in out if "Boccherini" in p.parent.name and "G_213" not in p.parent.name]
    return out


def plan(n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    srcs = sources()
    text = {s: s.read_text().strip() for s in srcs}
    by_part = {"vn": [], "va": [], "vc": []}
    real = []
    for s in srcs:
        part = part_of(s)
        toks = text[s].split()
        clefs = [t for t in toks if t.startswith("clef:")]
        if part in ("va", "vc") and (len(clefs) > 1 or clefs[:1] != [f"clef:{USUAL[part]}"]):
            real.append(s)
        else:
            by_part[part].append(s)
    for v in by_part.values():
        rng.shuffle(v)
    rng.shuffle(real)
    dens = {s: events(text[s]) for s in srcs}
    used = Counter()  # a cello staff high enough for treble is scarce (about 7%): it may be drawn twice
    jobs = []
    for kind, per in KINDS.items():
        want = round(n * per / 1000)
        got = 0
        part = kind[:2]
        if kind == "osq-real":
            real = [s for s in real if not far_notes(text[s])]  # a clef that doesn't fit its notes
            for s in real[:want]:
                hand = rng.choice(HANDS)
                if hand == "parisB" and text[s].split("clef:")[1][:2] != USUAL[part_of(s)]:
                    hand = "parisA"  # parisB leaves the opening clef off: an unusual one couldn't be known
                jobs.append(dict(kind=kind, src=str(s), lmx=text[s], hand=hand))
            continue
        pool = by_part[part]
        tries = 0
        while got < want and tries < want * 60:
            tries += 1
            hand = rng.choice([h for h in HANDS if not (kind.endswith("open") and h == "parisB")])
            # parisB leaves the opening clef off: an unusual one couldn't be known from the part
            lo, hi = DENSITY.get(hand, (0, 10 ** 6))
            s = pool[rng.randrange(len(pool))]
            if used[s] >= (2 if part == "vc" else 1) or not lo <= dens[s] <= hi:
                continue
            if kind == "vn-plain":
                new_lmx = text[s]
            else:
                new = rng.choice(["G2", "C4"]) if kind == "vc-open" else "C4" if kind == "vc-tenor" else "G2"
                new_lmx = shift(text[s], part, new, kind.endswith("open"), rng)
                if new_lmx is None or far_notes(new_lmx):
                    continue  # no stretch fits, or a high passage is left in the usual clef
            used[s] += 1
            jobs.append(dict(kind=kind, src=str(s), lmx=new_lmx, hand=hand))
            got += 1
        print(f"{kind}: {got} of {want} planned ({tries} tries)", flush=True)
    rng.shuffle(jobs)
    vocab = set(json.loads(VOCAB.read_text()))
    bad = [j for j in jobs if set(j["lmx"].split()) - vocab]
    assert not bad, f"{len(bad)} staves have tokens outside the reader's vocabulary: {bad[0]['src']}"
    return jobs


def one(job):
    import cv2
    import copyist
    try:
        img = copyist.draw(job["lmx"], job["hand"], seed=job["seed"], changes=True)
        if img.shape[1] / img.shape[0] > MAX_ASPECT:
            return "skipped: longer than the reader takes"
        cv2.imwrite(str(Path(job["dst"]).with_suffix(".jpg")), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        Path(job["dst"]).with_suffix(".lmx").write_text(job["lmx"] + "\n")
        return "ok"
    except ValueError as e:
        return "skipped: " + str(e).split(",")[0][:40]
    except Exception as e:
        return f"failed: {type(e).__name__}: {str(e)[:60]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("group")
    ap.add_argument("--n", type=int, default=4000)
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--seed", type=int, default=48)
    ap.add_argument("--plan-only", action="store_true")
    ap.add_argument("--limit", type=int, help="draw only the first LIMIT planned staves (a trial)")
    a = ap.parse_args()
    jobs = plan(a.n, a.seed)
    d = a.out / a.group
    for i, j in enumerate(jobs):
        j["name"] = f"s{i:05d}-0"
        j["dst"] = str(d / j["name"])
        j["seed"] = a.seed * 1_000_003 + i * 31
        j["clefs"] = [t for t in j["lmx"].split() if t.startswith("clef:")]
    jobs = jobs[: a.limit]
    print(Counter(j["kind"] for j in jobs), flush=True)
    if a.plan_only:
        return
    d.mkdir(parents=True, exist_ok=True)
    tally, kept, hands, kinds = Counter(), [], {}, {}
    ex = ProcessPoolExecutor(a.jobs) if a.jobs > 1 else None
    with ex or contextlib.nullcontext():  # --jobs 1: in this process (the sandbox denies a pool's semaphores)
        for n, (j, res) in enumerate(zip(jobs, ex.map(one, jobs, chunksize=8) if ex else map(one, jobs))):
            tally[res] += 1
            if res == "ok":
                key = f"{a.group}/{j['name']}"
                kept.append(key)
                hands[key] = j["hand"]
                kinds[key] = dict(kind=j["kind"], src=str(Path(j["src"]).relative_to(OSQ_DIR)), clefs=j["clefs"])
                tally[j["kind"]] += 1
            if n % 500 == 0:
                print(n, dict(tally.most_common(8)), flush=True)
    (a.out / f"samples.{a.group}.txt").write_text("\n".join(kept) + "\n")
    (a.out / f"hands.{a.group}.json").write_text(json.dumps(hands, indent=0))
    (a.out / f"kinds.{a.group}.json").write_text(json.dumps(kinds, indent=0))
    print(f"{a.group}: {len(kept)} of {len(jobs)} drawn", dict(tally.most_common()), flush=True)


if __name__ == "__main__":
    main()
