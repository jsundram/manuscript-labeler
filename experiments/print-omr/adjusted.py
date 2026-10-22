"""Agreement accuracy after looking at the print (adjudication.json): an
agreed bar the scorer counts wrong is still right when the print has what
the readers wrote (verdict "edition"). For the D4 + OSSQ pair, only a random
sample of its wrong bars outside the three-way set was looked at; the rest
are counted at the sample's rate.

    python3 experiments/print-omr/adjusted.py
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
score = json.loads((HERE / "results" / "score.json").read_text())["agreement"]
bars = json.loads((HERE / "results" / "bars.json").read_text())["agreed_wrong"]
adj = json.loads((HERE / "adjudication.json").read_text())
key = lambda r: (r["G"], r["part"], r["page"], r["staff"], r["m"])
three = {key(r): r["verdict"] for r in adj["three"]}
pairs = {(tuple(r["pair"]),) + key(r): r["verdict"] for r in adj["pairs"]}

for name, t in score.items():
    names = tuple(name.split(" + "))
    wrong = [r for r in bars if tuple(r["pair"]) == names]
    omr = looked = unseen = 0
    for r in wrong:
        v = three.get(key(r)) if len(names) == 3 or key(r) in three else pairs.get((names,) + key(r))
        if v is None:
            unseen += 1
            continue
        looked += 1
        omr += v == "omr"
    sampled = [v for k, v in pairs.items() if k[0] == names and k[1:] not in three]
    rate = sum(v == "omr" for v in sampled) / len(sampled) if sampled else 1.0
    est = omr + unseen * rate
    n = t["agreed"]
    print(f"{name}: agreed {n} ({n / t['encoded bars']:.1%} of encoded bars); scorer right {t['agreed and right'] / n:.1%}; "
          f"after the print: {1 - est / n:.1%} ({len(wrong)} counted wrong: {looked} looked at, {omr} OMR errors"
          + (f"; {unseen} not looked at, counted at the sample's {rate:.0%})" if unseen else ")"))
