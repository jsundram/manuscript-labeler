# Two pairings of one source (D4 and D5 readings, or a base and add_reader.py's), scored on the editor's fixed pages
#   uv run reports/2026-11-04-d5-pairing/compare_readers.py SOURCE FIRST-RESULT SECOND-RESULT [D5 samples list]
import json, sys, glob
from pathlib import Path
ROOT = Path.home() / "Dropbox/Code/manuscript-labeler"; sys.path.insert(0, str(ROOT)); import pairing
Z = ROOT / "experiments/zeus"; X = lambda b: (b["x0"] + b["x1"]) / 2
name, fa, fb = sys.argv[1:4]
R = [json.loads((Z / "results" / f).read_text()) for f in (fa, fb)]
recs = [{x["staff"]: ("kept", x) for x in r["kept"]} | {x["staff"]: ("not kept", x) for x in r.get("not kept", [])} for r in R]
def truth(s):
    return [max(0, b.get("bar_count", 1)) for b in sorted(s["barlines"], key=X) if X(b) > s.get("start", s["left"])] + (["on"] if s.get("runs_on") else [])
pieces = lambda rec: ["on" if b.get("continues") else b["count"] for b in rec.get("boxes", [])]
src = pairing.sources(); pdf = next(p for p, v in src.items() if name in v)
lab = json.loads(next(ROOT.glob(f"data/**/{pdf.stem}.labels.json")).read_text())
auto = json.loads((Z / "auto" / f"{name}.json").read_text())
want = {}
for n, p in lab["pages"].items():
    if p.get("status") not in ("edited", "reviewed") or n not in auto["pages"]: continue
    det = sorted(auto["pages"][n]["systems"], key=lambda s: s["top"])
    for s in p["systems"]:
        k = min(range(len(det)), key=lambda i: abs(det[i]["top"] - s["top"]))
        if abs(det[k]["top"] - s["top"]) <= 0.015: want[f"p{n}-{k}"] = truth(s)
for i, lbl in enumerate(("D4", "D5")):
    kept = [s for s, (st, _) in recs[i].items() if st == "kept"]
    ok = sum(pieces(recs[i][s][1]) == want[s] for s in kept if s in want)
    print(f"{lbl}: kept {len(kept)} of {len(recs[i])}; on fixed pages kept {sum(s in want for s in kept)}, right {ok}")
a = {s for s, (st, _) in recs[0].items() if st == "kept"}; b = {s for s, (st, _) in recs[1].items() if st == "kept"}
for title, ss, j in (("D5 only", b - a, 1), ("D4 only", a - b, 0)):
    right = sum(pieces(recs[j][s][1]) == want.get(s) for s in ss)
    print(f"{title}: {len(ss)} ({sum(s in want for s in ss)} on fixed pages, {right} right)")
both = a & b
print("both:", len(both), "same boxes", sum(pieces(recs[0][s][1]) == pieces(recs[1][s][1]) for s in both))
# staves D5 trained on (sys.argv[4]: its samples list), and the comparison without them
if len(sys.argv) > 4:
    seen = {l.strip().split("/")[-1] for l in open(sys.argv[4]) if l.strip()}
    print("D5 trained on", len(seen), "of this source's staves")
    for title, ss in (("D5 only", b - a), ("D4 only", a - b), ("both", both)):
        print(f"  {title}: {len(ss & seen)} trained on")
    for i, lbl in enumerate(("D4", "D5")):
        kept = [s for s, (st, _) in recs[i].items() if st == "kept" and s not in seen]
        print(f"  unseen, {lbl}: kept {len(kept)} of {len(set(recs[i]) - seen)}, right {sum(pieces(recs[i][s][1]) == want.get(s) for s in kept)}")
