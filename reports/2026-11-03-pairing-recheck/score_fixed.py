# /// script
# requires-python = ">=3.11"
# ///
# The pairing's staves against the editor's fixed pages outside Op. 48: per staff, the
# measures as the editor's bar lines make them (each bar line's count, and a last piece where the
# staff runs on) against the pairing's boxes (each box's count, "continues" for a run-on piece).
#   uv run reports/2026-11-03-pairing-recheck/score_fixed.py <old results dir> [name=result-suffix ...]
# The number of measures is compared (a bar split across a line break is marked on either staff, by
# the editor and by the pairing, so the counts in each measure are not).
import json, sys, glob
from pathlib import Path
ROOT = Path.home() / "Dropbox/Code/manuscript-labeler"
sys.path.insert(0, str(ROOT))
import pairing
Z = ROOT / "experiments/zeus"
OLD = Path(sys.argv[1])
SUFFIX = {"default": "any-count-neighbours-paired-short-ends-long-ends-head-box-musvit-D3S-h96|"
          "any-count-neighbours-paired-short-ends-long-ends-musvit-D3S-h96",
          "G213-KHM587": "any-count-neighbours-short-ends-musvit-D3S-h96"}
for a in sys.argv[2:]:
    k, v = a.split("="); SUFFIX[k] = v
X = lambda b: (b["x0"] + b["x1"]) / 2


def result(d: Path, name: str):
    for suf in SUFFIX.get(name, SUFFIX["default"]).split("|"):
        f = d / f"autopair-{name}-{suf}.json"
        if f.exists():
            return json.loads(f.read_text())
    return None


def truth(s):
    out = [max(0, b.get("bar_count", 1)) for b in sorted(s["barlines"], key=X) if X(b) > s.get("start", s["left"])]
    return out + (["on"] if s.get("runs_on") else [])


def pieces(rec):
    out = []
    for bx in rec.get("boxes", []):
        out.append("on" if bx.get("continues") else bx["count"])
    return out


src = pairing.sources()
tot = {}
rows = []
for f in sorted(glob.glob(str(ROOT / "data/**/*.labels.json"), recursive=True)):
    if "opus-48" in f:
        continue
    lab = json.load(open(f))
    pages = {int(n): p for n, p in lab["pages"].items() if p.get("status") in ("edited", "reviewed")}
    if not pages:
        continue
    pdf = next((p for p in src if p.stem == Path(f).name.replace(".labels.json", "")), None)
    for name in src.get(pdf, []):
        auto = json.loads((Z / "auto" / f"{name}.json").read_text())
        res = {"old": result(OLD, name), "new": result(Z / "results", name)}
        if not res["old"] or not res["new"]:
            print("no results for", name); continue
        recs = {k: ({x["staff"]: ("kept", x) for x in r["kept"]} | {x["staff"]: ("not kept", x) for x in r.get("not kept", [])})
                for k, r in res.items()}
        for n, page in sorted(pages.items()):
            if str(n) not in auto["pages"]:
                continue
            det = sorted(auto["pages"][str(n)]["systems"], key=lambda s: s["top"])
            for s in page["systems"]:
                k = min(range(len(det)), key=lambda i: abs(det[i]["top"] - s["top"]), default=None)
                if k is None or abs(det[k]["top"] - s["top"]) > 0.015:
                    continue
                staff = f"p{n}-{k}"
                want = truth(s)
                for which in ("old", "new"):
                    st, rec = recs[which].get(staff, ("absent", {}))
                    got = pieces(rec)
                    ok = len(got) == len(want)
                    key = (which, st, ok)
                    tot[key] = tot.get(key, 0) + 1
                    if which == "new" and (st == "kept" and not ok or len(sys.argv) > 2 and False):
                        rows.append(f"  kept but measures differ: {name} {staff} yours {want} pairing {got} {[b[-1] for b in rec.get('bars', [])]}")
                if recs["old"].get(staff, ("absent",))[0] != recs["new"].get(staff, ("absent",))[0]:
                    o, nw = recs["old"].get(staff, ("absent", {})), recs["new"].get(staff, ("absent", {}))
                    rows.append(f"  changed: {name} {staff}: {o[0]} -> {nw[0]}; measures right? old {len(pieces(o[1])) == len(want)}, new {len(pieces(nw[1])) == len(want)}"
                                + (f"; now out: {nw[1].get('why', [''])[0]}" if nw[0] == 'not kept' else ""))
for which in ("old", "new"):
    k_ok, k_bad = tot.get((which, "kept", True), 0), tot.get((which, "kept", False), 0)
    n_ok, n_bad = tot.get((which, "not kept", True), 0), tot.get((which, "not kept", False), 0)
    print(f"{which}: kept {k_ok + k_bad} (measures right {k_ok}, wrong {k_bad}); not kept {n_ok + n_bad} (measures right {n_ok}, wrong {n_bad}); absent {sum(v for (w, s, _), v in tot.items() if w == which and s == 'absent')}")
print("\n".join(rows))
