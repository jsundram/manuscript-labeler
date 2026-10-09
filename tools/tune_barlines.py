# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow"]
# ///
"""Re-fit detect.py's bar-line thresholds to every page you've reviewed.

    uv run tools/tune_barlines.py <edition-repo or pdf>... [--false-weight 2]

Finds each source's labels file (labels.labels_path), renders its reviewed music pages,
and treats their bar lines as the truth. Only reviewed pages: on a page
still being edited, untouched proposals would count as confirmed and pull
the tuning toward whatever detect.py does now. Then it adjusts one threshold at a time, keeping any change that
scores better, until nothing improves (coordinate descent). Score = bar
lines found - false-weight x false ones: a false bar line costs more to
fix by hand (find it, delete it) than a missed one (hold b, click).

It prints how each threshold moves the result and the best settings, per
source and overall. It does not edit detect.py: read the table, change the
constants, then re-freeze tests/fixtures and the limits in
tests/test_detect.py together.
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import detect  # noqa: E402
from labels import labels_path  # noqa: E402
from score_barlines import render, score_page, truth_systems  # noqa: E402

# the thresholds tried, each with the values to try (current value added)
GRID = {
    "COVER": [0.8, 0.84, 0.88, 0.92],
    "LEAN": [0.18, 0.24, 0.3, 0.36],
    "ATTACH_WIDTH": [0.7, 0.85, 1.0],
    "ATTACH_ROWS": [0.15, 0.25, 0.35, 0.5],
    "MIN_BAR": [3.0, 3.5, 4.0, 5.0],
    "END_SLACK": [0.0, 0.25],
    "FAINT": [0.6, 0.7, 0.8],
    "WIDE_GAP": [1.4, 1.6, 1.8, 2.2],
}


def find_sources(paths: list[str]) -> list[Path]:
    pdfs = []
    for p in map(Path, paths):
        pdfs += sorted(p.glob("sources/**/*.pdf")) if p.is_dir() else [p]
    return [p for p in pdfs if labels_path(p).exists()]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--false-weight", type=float, default=2.0)
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        pages = []  # (source name, image, truth)
        for pdf in find_sources(args.paths):
            labels = json.loads(labels_path(pdf).read_text())
            for n, p in sorted(labels["pages"].items(), key=lambda kp: int(kp[0])):
                if p["status"] == "reviewed" and p["kind"] == "music":
                    pages.append((pdf.stem, render(pdf, int(n), Path(tmp)), truth_systems(p)))
        if not pages:
            sys.exit("no reviewed music pages found")
        sources = sorted({s for s, _, _ in pages})
        print(f"{len(pages)} pages from {', '.join(sources)}; "
              f"{sum(len(s['xs']) for _, _, t in pages for s in t)} bar lines\n")

        def evaluate() -> dict:
            per = {s: [0, 0, 0] for s in sources}
            for src, img, truth in pages:
                per[src] = [a + b for a, b in zip(per[src], score_page(truth, detect.detect_page(img)))]
            total = [sum(v[i] for v in per.values()) for i in range(3)]
            return {"per": per, "total": total, "score": total[0] - args.false_weight * total[1]}

        def show(r):
            f, fp, m = r["total"]
            return f"found {f} ({f / max(1, f + m):.0%}), false {fp}, missed {m}"

        current = {k: getattr(detect, k) for k in GRID}
        best = evaluate()
        print(f"now:  {show(best)}  {current}\n")
        improved = True
        while improved:
            improved = False
            for name, values in GRID.items():
                tried = []
                for v in sorted(set(values) | {current[name]}):
                    setattr(detect, name, v)
                    r = evaluate()
                    tried.append((v, r))
                    if r["score"] > best["score"]:
                        best, current[name], improved = r, v, True
                setattr(detect, name, current[name])
                print(f"{name:13s}" + "  ".join(
                    f"{v:g}{'*' if v == current[name] else ''}: {r['total'][0]}/{r['total'][1]}" for v, r in tried))
            print()

        print(f"best: {show(best)}")
        for src, (f, fp, m) in best["per"].items():
            print(f"  {src}: found {f} of {f + m}, false {fp}")
        print("\nIn detect.py:")
        for name, v in current.items():
            print(f"  {name} = {v:g}")


if __name__ == "__main__":
    main()
