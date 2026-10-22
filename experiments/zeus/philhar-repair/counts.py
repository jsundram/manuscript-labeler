# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""The counts table for README.md: per source, staves detected, paired, in
the staff set before (dataM/dataT) and now (dataM2), with their bars.

    uv run experiments/zeus/philhar-repair/counts.py > counts.md
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ZEUS = HERE.parent
CACHE = Path.home() / ".cache/manuscript-labeler/zeus"
SUFFIX = "-any-count-neighbours-paired-short-ends-long-ends-musvit-D3S-h96"
OLD = {"dataM": "-any-count-musvit-C4-bocch-tf8-L-best", "dataT": "-any-count-both"}


def listed(path: Path) -> list[str]:
    return [l.split("/")[1] for l in path.read_text().split()] if path.exists() else []


def bars_of(results: Path, staves: list[str]) -> int:
    if not results.exists():
        return 0
    k = {r["staff"]: r for r in json.loads(results.read_text())["kept"]}
    return sum(len(k[s]["bars"]) for s in staves if s in k)


def main():
    rows, tot = [], [0] * 7
    for line in (HERE / "sources.txt").read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        src, _, before = line.split()
        auto = json.loads((ZEUS / "auto" / f"{src}.json").read_text())
        detected = sum(len(p["systems"]) for p in auto["pages"].values())
        both = ZEUS / "results" / f"autopair-{src}-both.json"
        res = both if before != "-" and not src.endswith("-score") else ZEUS / "results" / f"autopair-{src}{SUFFIX}.json"
        paired = len(json.loads(res.read_text())["kept"]) if res.exists() else 0
        now = listed(CACHE / "dataM2" / f"samples.{src}.txt")
        old_set, old_src = before.split("/") if before != "-" else (None, None)
        old = listed(CACHE / old_set / f"samples.{old_src}.txt") if old_set else []
        old_bars = bars_of(ZEUS / "results" / f"autopair-{old_src}{OLD[old_set]}.json", old) if old_set else 0
        row = [detected, paired, len(old), old_bars, len(now), bars_of(res, now)]
        tot = [a + b for a, b in zip(tot, row + [0])]
        rows.append(f"| {src} | " + " | ".join(map(str, row)) + f" | {len(now) - len(old):+d} |")
    print("| source | detected | paired | before: staves | before: bars | dataM2: staves | dataM2: bars | gain |")
    print("|---|--:|--:|--:|--:|--:|--:|--:|")
    print("\n".join(rows))
    print(f"| **all** | {tot[0]} | {tot[1]} | {tot[2]} | {tot[3]} | **{tot[4]}** | {tot[5]} | {tot[4] - tot[2]:+d} |")


if __name__ == "__main__":
    main()
