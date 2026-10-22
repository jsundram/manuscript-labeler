# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""The staves to train on from two pulls of the same plates (G. 213 in
Pleyel's edition, plate 125: the Sibley and Berlin copies), each staff
paired by its own reading (autopair.py --musicxml --any-count --neighbours
--short-ends)
and checked against its twin, the staff at its place on the twin page.

    uv run experiments/zeus/g213/merge.py G213-DB-Pleyel G213-Sibley --pages 11:1,12:2,... [--eyed p13-12,...]

A staff is kept, in results/autopair-<first>-final.json:
- "own": its reading paired it, and something independent of the reading
  agrees: detection's bar boxes are as many as its measures, or its twin's
  reading paired the twin with the same bars;
- "twin": its reading didn't pair it (or nothing confirmed it), but its
  twin's did, confirmed by the twin's bar boxes, every measure one bar; and
  (or by eye, --twin-eyed) the two staves' ends sit at the same place on their pages (within 2% of
  the page's staff width), so the crop holds the same music;
- "own+twin": its reading paired every measure one to one, but a rule put
  it out (the staff beside it began or ended with a measure for two bars);
  its twin, confirmed, holds the same bars;
- "eye": paired by its own reading, unconfirmed, and checked by eye (--eyed).
A kept staff that holds every bar whole (one measure each) and shares a bar
with another kept staff is put out (half a bar on each, at a line break,
one paired as if it held the whole).
Everything else is listed under "not kept" with why.
"""

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path

ZEUS = Path(__file__).resolve().parent.parent


def load(src: str) -> dict:
    return json.loads((ZEUS / "results" / f"autopair-{src}-any-count-neighbours-short-ends-musvit-D3S-h96.json").read_text())


def geometry(src: str) -> dict:
    """Each staff's ends as fractions of its page's staff block (median left to median right)."""
    auto = json.loads((ZEUS / "auto" / f"{src}.json").read_text())
    out = {}
    for n, p in auto["pages"].items():
        ss = sorted(p["systems"], key=lambda s: s["top"])
        L = statistics.median(s["left"] for s in ss)
        R = statistics.median(s["right"] for s in ss)
        for k, s in enumerate(ss):
            out[f"p{n}-{k}"] = ((s["left"] - L) / (R - L), (s["right"] - L) / (R - L))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("first")
    ap.add_argument("second")
    ap.add_argument("--pages", default="", help="first's page:second's page,... (second '-': no twin)")
    ap.add_argument("--eyed", default="", help="first's staves checked by eye (own pairing, unconfirmed)")
    ap.add_argument("--twin-eyed", default="", help="second's staves checked by eye (its --eyed)")
    a = ap.parse_args()
    alone = a.second == "-"  # a source with no twin: its own pairings, no bar on two staves
    pm = {} if alone else {int(x.split(":")[0]): int(x.split(":")[1]) for x in a.pages.split(",")}
    twin = lambda sid: None if alone else (lambda p, i: f"p{pm[int(p)]}-{i}")(*sid[1:].split("-"))
    A = load(a.first)
    B = {"kept": [], "not kept": []} if alone else load(a.second)
    gA = geometry(a.first)
    gB = {} if alone else geometry(a.second)
    Ak = {k["staff"]: k for k in A["kept"]}
    Bk = {k["staff"]: k for k in B["kept"]}
    eyed = set(filter(None, a.eyed.split(",")))
    twin_eyed = set(filter(None, a.twin_eyed.split(",")))
    boxes_ok = lambda k: k["measures"] == k["bar_boxes"]
    kept, not_kept = [], []
    allA = {k["staff"]: k for k in A["kept"] + A["not kept"]}
    for sid, k in allA.items():
        t = twin(sid)
        tk = Bk.get(t)
        same_place = not alone and all(abs(x - y) < 0.02 for x, y in zip(gA[sid], gB[t]))
        if sid in Ak:
            if boxes_ok(k):
                kept.append(dict(k, how="own", confirmed="bar boxes"))
                continue
            if alone:
                kept.append(dict(k, how="own", confirmed="its reading (no twin)"))
                continue
            if tk is not None and tk["bars"] == k["bars"]:
                kept.append(dict(k, how="own", confirmed=f"twin {t}"))
                continue
            if sid in eyed:
                kept.append(dict(k, how="eye", confirmed="by eye"))
                continue
        twin_ok = tk is not None and (boxes_ok(tk) or t in twin_eyed)
        if sid not in Ak and twin_ok and k["bars"] == tk["bars"] and set(k["steps"]) <= {"one", "join"}:
            # its reading paired every measure with the twin's bars, but a rule put it out (a neighbour's)
            kept.append(dict(tk, staff=sid, page=int(sid[1:].split("-")[0]), system=None, how="own+twin",
                             confirmed=f"its reading and twin {t} pair the same bars", twin=t))
            continue
        if twin_ok and tk["plain"] and same_place:
            kept.append(dict(tk, staff=sid, page=int(sid[1:].split("-")[0]), system=None, how="twin",
                             confirmed=f"twin {t} ({'its bar boxes' if boxes_ok(tk) else 'checked by eye'})", twin=t))
            continue
        why = list(k.get("why", [])) if sid not in Ak else ["own pairing unconfirmed (bar boxes differ, twin "
                                                            + ("not kept" if tk is None else "pairs other bars") + ")"]
        if alone:
            pass  # nothing to say about a twin
        elif tk is None:
            why.append(f"twin {t} not kept")
        elif not (boxes_ok(tk) or t in twin_eyed):
            why.append(f"twin {t} unconfirmed")
        elif not tk["plain"]:
            why.append(f"twin {t} not plain")
        elif not same_place:
            why.append(f"twin {t}'s ends elsewhere: {[round(x, 3) for x in gA[sid]]} vs {[round(x, 3) for x in gB[t]]}")
        not_kept.append({"staff": sid, "part": k["part"], "why": why, "bars": k.get("bars", []),
                         "boxes": k.get("boxes", [])})
    # no bar on two staves
    held = Counter((k["part"], tuple(b)) for k in kept for b in k["bars"])
    plain = lambda k: set(k.get("steps", {"one": 1})) <= {"one", "join"}
    # (a bar the line breaks is on two staves by right, each holding a half: neither plain)
    twice = [k for k in kept if plain(k) and any(held[(k["part"], tuple(b))] > 1 for b in k["bars"])]
    for k in twice:
        kept.remove(k)
        shared = [b for b in k["bars"] if held[(k["part"], tuple(b))] > 1]
        not_kept.append({"staff": k["staff"], "part": k["part"], "bars": k["bars"], "boxes": k.get("boxes", []),
                         "why": [f"bar {shared[0]} also on another kept staff (was {k['how']}: {k['confirmed']})"]})
    # a twin-kept staff takes its own detection's staff (system) for the crop
    auto = json.loads((ZEUS / "auto" / f"{a.first}.json").read_text())
    for k in kept:
        if k["system"] is None:
            p, i = k["staff"][1:].split("-")
            k["system"] = sorted(auto["pages"][p]["systems"], key=lambda s: s["top"])[int(i)]
    kept.sort(key=lambda k: tuple(map(int, k["staff"][1:].split("-"))))
    out = {"source": a.first, "twin source": a.second, "kept": kept, "not kept": not_kept}
    dest = ZEUS / "results" / f"autopair-{a.first}-final.json"
    dest.write_text(json.dumps(out, indent=1))
    print(a.first, "kept", len(kept), dict(Counter(k["how"] for k in kept)), "plain", sum(k["plain"] for k in kept),
          "| not kept", len(not_kept), "->", dest.name)
    for k in not_kept:
        print("  not kept", k["staff"], k["part"], "; ".join(k["why"]))
    for k in kept:
        if k["how"] != "own" or not k["confirmed"].startswith(("bar", "twin")):
            print("  ", k["how"], k["staff"], k["confirmed"], k["bars"][0], k["bars"][-1])


if __name__ == "__main__":
    main()
