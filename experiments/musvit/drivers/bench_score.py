"""Score every model's readings of the public test staves the same way: symbol edits over the reference's
length, as written and on the symbols our labels have (tokens they never contain dropped from both sides);
readings cut at twice the reference's length, which removes runaways."""
import json
from collections import Counter
from pathlib import Path
S = Path(__file__).parent
B = S / "bench"
C = Path.home() / ".cache/manuscript-labeler/zeus"
ours = set()
for d in ("dataL", "dataM", "dataT"):
    for f in (C / d).rglob("*.lmx"):
        ours.update(f.read_text().split())

def edits(a, b):
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]

MODELS = [("stock Zeus", "ayce-2026-08-03.model"), ("Zeus J", "J-lr1e5-e8@2026-10-16"),
          ("MuSViT stage 1 (E2-tf8)", "E2-tf8"), ("musvit-D1", "D1-tf8-M"), ("musvit-D3", "D3-tf8-all")]
rows = []
for test in ("dolores", "omniomr"):
    lines = (B / f"{test}-test.txt").read_text().split()
    refs = {l: (B / test / l).with_suffix(".lmx").read_text().split() for l in lines}
    for name, key in MODELS:
        f = B / f"{test}-{key}.json"
        if not f.exists():
            continue
        got = {k: v.split() for k, v in json.loads(f.read_text()).items()}
        e = eo = ex = exo = n = no = 0
        for l in lines:
            r, g = refs[l], got[l][: 2 * len(refs[l])]
            ro, go = [t for t in r if t in ours], [t for t in g if t in ours]
            d, do = edits(g, r), edits(go, ro)
            e, eo, n, no = e + d, eo + do, n + len(r), no + len(ro)
            ex, exo = ex + (d == 0), exo + (do == 0)
        rows.append((test, name, e / n, ex, eo / no, exo, len(lines)))
out = ["| test | model | symbol errors, as written | exact staves | on our symbols | exact staves |", "|---|---|---:|---:|---:|---:|"]
for test, name, s, ex, so, exo, n in rows:
    out.append(f"| {test} ({n}) | {name} | {100 * s:.1f}% | {ex} | {100 * so:.1f}% | {exo} |")
(B / "public-table.md").write_text("\n".join(out) + "\n")
print("\n".join(out))
