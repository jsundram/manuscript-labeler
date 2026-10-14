# /// script
# requires-python = "==3.10.*"
# dependencies = [
#   "zeus @ git+https://github.com/OmniOMR/zeus.git@main",
#   "tensorflow-macos==2.12.0; sys_platform == 'darwin' and platform_machine == 'arm64'",
#   "numpy", "pillow",
# ]
# [tool.uv]
# override-dependencies = ["tensorflow; sys_platform != 'darwin' or platform_machine != 'arm64'"]
# ///
"""Zeus (untouched, and fine-tuned) on the OSSQ manuscripts, against OSSQ's
encoding, bar by bar.

    uv run experiments/zeus/ossq/score.py <name> <musicxml> [--model M ...]

Inputs and outputs live in ~/.cache/manuscript-labeler/ossq/ (README.md):
auto-OSSQ-<name>.json in, answers/ (each model's readings, cached) and
result-<name>.json out.

Detection's staves (auto-OSSQ-<name>.json, every staff of every page) are
grouped into systems of four: by the gaps between staves, a group of 4k
staves cut into k. Each staff is read by every model. The detected
systems are lined up with the encoding's systems (OSSQ keeps the
manuscript's line breaks) by dynamic programming, on how many bars every
model's reading of the four staves gets right in rhythm: one line-up for
all models. On each lined-up staff, Zeus's measures are paired with the
encoded bars (the most exact bars in order, skips free), pitches read in the
encoding's clef. A bar whose clef changes inside isn't compared. A bar on
a system no detected system lined up with counts as wrong.
"""

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import compare  # noqa: E402
import mxl  # noqa: E402

DATA = Path.home() / ".cache/manuscript-labeler/ossq"
SWEEP = Path.home() / ".cache/manuscript-labeler/models/zeus/sweep"
MODELS = [compare.MODEL, SWEEP / "G-lr1e5-e8.model"]


def groups(staves: list[dict]) -> list[list[dict]]:
    staves = sorted(staves, key=lambda s: s["top"])
    if len(staves) < 4:
        return []
    gaps = [b["top"] - a["bottom"] for a, b in zip(staves, staves[1:])]
    cut = 1.6 * sorted(gaps)[len(gaps) // 2]
    out = [[staves[0]]]
    for g, s in zip(gaps, staves[1:]):
        if g > cut:
            out.append([])
        out[-1].append(s)
    fours = []
    for g in out:
        if len(g) % 4 == 0:
            fours += [g[k:k + 4] for k in range(0, len(g), 4)]
    return fours


def lcs(a: list, b: list, match) -> int:
    n, m = len(a), len(b)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n):
        for j in range(m):
            d[i + 1][j + 1] = max(d[i][j + 1], d[i + 1][j], d[i][j] + match(i, j))
    return d[n][m]


def rhythm(evs):
    return [(e["kind"], e["dur"], e["dots"], e["grace"]) for e in evs]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("musicxml", type=Path)
    ap.add_argument("--model", type=Path, nargs="+", default=MODELS)
    a = ap.parse_args()
    auto = json.loads((DATA / f"auto-OSSQ-{a.name}.json").read_text())
    pdf = Path(auto["pdf"])

    # detected systems, in reading order
    det = []
    for n, p in sorted(auto["pages"].items(), key=lambda kv: int(kv[0])):
        for k, g in enumerate(groups(p["systems"])):
            det.append({"page": int(n), "k": k, "staves": g})
    print(f"{a.name}: {len(det)} detected systems of 4 staves on {len({d['page'] for d in det})} pages", flush=True)

    # readings
    crops, keys = {}, {}
    page, g = None, None
    for d in det:
        if d["page"] != page:
            g, page = compare.page_image(pdf, d["page"]), d["page"]
        for i, s in enumerate(d["staves"]):
            sid = f"p{d['page']}-{d['k']}-{i}"
            crops[sid] = compare.staff_crop(g, s)
            keys[sid] = f"{sid}:{hashlib.sha1(crops[sid]).hexdigest()[:10]}"
    readings = {}
    for m in a.model:
        cf = DATA / "answers" / f"{a.name}-{m.name}.json"
        cache = json.loads(cf.read_text()) if cf.exists() else {}
        todo = [sid for sid in crops if keys[sid] not in cache]
        if todo:
            from zeus import InferenceOptions, Zeus
            model = Zeus.load(m)
            print(f"{m.name} reads {len(todo)} staves ...", flush=True)
            for sid, lmx in zip(todo, model.predict([crops[sid] for sid in todo], InferenceOptions(batch_size=8))):
                cache[keys[sid]] = lmx
            cf.parent.mkdir(parents=True, exist_ok=True)
            cf.write_text(json.dumps(cache, indent=1, sort_keys=True))
        readings[m.name] = {sid: compare.parse(cache[keys[sid]])[0] for sid in crops}

    enc = mxl.systems(a.musicxml)
    E = len(enc)
    D = len(det)

    def zm(model, d, i):
        return readings[model][f"p{d['page']}-{d['k']}-{i}"]

    # line up detected systems with the encoding's: bars right in rhythm, every model
    sim = [[0] * E for _ in range(D)]
    for x, d in enumerate(det):
        for y, e in enumerate(enc):
            t = 0
            for i, part in enumerate(mxl.PARTS):
                eb = [rhythm(b["events"]) for b in e[part]]
                for m in readings:
                    zb = [rhythm([compare.zeus_event(ev, "treble") for ev in ms]) for ms in zm(m, d, i)]
                    t += lcs(zb, eb, lambda p, q: zb[p] == eb[q] and len(eb[q]) > 1)
            sim[x][y] = t
    best = [[0] * (E + 1) for _ in range(D + 1)]
    for x in range(D):
        for y in range(E):
            best[x + 1][y + 1] = max(best[x][y + 1], best[x + 1][y], best[x][y] + sim[x][y])
    pairs, x, y = [], D, E
    while x and y:
        if best[x][y] == best[x - 1][y]:
            x -= 1
        elif best[x][y] == best[x][y - 1]:
            y -= 1
        else:
            if sim[x - 1][y - 1] > 0:
                pairs.append((x - 1, y - 1))
            x, y = x - 1, y - 1
    pairs.reverse()

    # score
    lined = {y: x for x, y in pairs}
    out = {"name": a.name, "detected systems": D, "encoded systems": E, "lined up": len(pairs), "models": {},
           "pairs": [[f"p{det[x]['page']}-{det[x]['k']}", y, sim[x][y]] for x, y in pairs]}
    for m in readings:
        t = Counter()
        for y, e in enumerate(enc):
            for i, part in enumerate(mxl.PARTS):
                bars = [b for b in e[part] if not b["clef_change"]]
                t["bars"] += len(bars)
                t["not compared (clef change)"] += len(e[part]) - len(bars)
                t[f"{part} bars"] += len(bars)
                if y not in lined:
                    continue
                t["bars on lined-up systems"] += len(bars)
                zs = zm(m, det[lined[y]], i)
                ex = lambda p, q: [compare.zeus_event(ev, bars[q]["clef"]) for ev in zs[p]]
                same = lambda p, q: (lambda z, b: len(z) == len(b) and all(map(compare.same, b, z)))(ex(p, q), bars[q]["events"])
                t["bars exact"] += lcs(zs, bars, same)
                t["bars right in rhythm"] += lcs(zs, bars, lambda p, q: rhythm(ex(p, q)) == rhythm(bars[q]["events"]))
                t[f"{part} exact"] += lcs(zs, bars, same)
        out["models"][m] = dict(t)
        pct = lambda k, of: f"{100 * t[k] / max(t[of], 1):.0f}%"
        print(f"{a.name} {m}: exact {t['bars exact']}/{t['bars']} ({pct('bars exact', 'bars')}; "
              f"{pct('bars exact', 'bars on lined-up systems')} on lined-up systems), "
              f"rhythm {pct('bars right in rhythm', 'bars')}; "
              + " ".join(f"{p} {pct(p + ' exact', p + ' bars')}" for p in mxl.PARTS), flush=True)
    print(f"  systems: {D} detected, {E} encoded, {len(pairs)} lined up")
    (DATA / f"result-{a.name}.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
