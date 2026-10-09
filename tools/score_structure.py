# /// script
# requires-python = ">=3.11"
# ///
"""How many of the editor's bar-line labels Structure.ily proposes.

    uv run tools/score_structure.py <edition-repo>

Each reviewed source of a work with a Structure.ily: its bar lines kept
where the editor put them, but made untouched (auto), with what the
proposal decides cleared (kind single, unless double; count 1; no
movement end); multi-bar rests stay the editor's, and aren't scored.
Then the labeler's own numbering with structureProposer (static/app.js,
under node) proposes,
and each field is compared with the editor's: repeat signs, upbeats
(count 0) and movement ends, as the editor's proposed right and the
proposal's the editor didn't make (listed). Needs node.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import labels  # noqa: E402
import structure  # noqa: E402

REPEATS = ("repeat_start", "repeat_end", "repeat_both")


def proposer_js() -> str:
    src = (ROOT / "static" / "app.js").read_text()
    pick = lambda pat: re.search(pat, src, re.S).group(0)
    return "\n".join([
        pick(r"const ROMAN = .*?;"),
        pick(r"const mid = .*?;"),
        pick(r"const roman = .*?;"),
        pick(r"function sectionEnds\(e\) \{.*?\n\}"),
        pick(r"const REPEAT_KINDS = .*?;"),
        pick(r"function structureProposer\(expected, doc\) \{.*?\n\}"),
        pick(r"function numberBars\(doc[^)]*\) \{.*?\n\}"),
        'const {doc, expected} = JSON.parse(require("fs").readFileSync(0, "utf8"));',
        "numberBars(doc, structureProposer(expected, doc));",
        "console.log(JSON.stringify(doc));",
    ])


def fields(b: dict) -> dict:
    """What the proposal decides, as compared: a repeat sign (or False), an upbeat, a movement end."""
    kind = b.get("kind", "single")
    return {"repeat": kind in REPEATS and kind, "upbeat": b.get("bar_count", 1) == 0,
            "end": bool(b.get("ends_movement"))}


def score(doc: dict, expected: dict, js: str) -> tuple[dict, list[str]]:
    """{field: [editor's, proposed right, proposed wrongly]}, and the differences."""
    names = {nb["right"]["id"]: f"p{nb['page']} {nb['part']} {nb['movement']} {nb['bar']}{'u' if nb['count'] == 0 else ''}"
             for nb in labels.number_bars(doc)}
    cleared = json.loads(json.dumps(doc))
    want = {}
    for p in cleared["pages"].values():
        if p.get("status") != "reviewed" or p.get("kind") != "music":
            continue
        p["status"] = "edited"
        for s in p["systems"]:
            if s.get("role", "part") != "part":
                continue
            for b in s["barlines"]:
                if b.get("bar_count", 1) > 1:  # the editor's, not proposed: not scored
                    b["auto"] = False
                    continue
                want[b["id"]] = fields(b)
                b.update(auto=True, kind="double" if b.get("kind") == "double" else "single",
                         bar_count=1, ends_movement=False)
    out = json.loads(subprocess.run(["node", "-e", js], input=json.dumps({"doc": cleared, "expected": expected}),
                                    capture_output=True, text=True, check=True).stdout)
    got = {b["id"]: fields(b) for p in out["pages"].values() for s in p["systems"] for b in s["barlines"]}
    counts = {k: [0, 0, 0] for k in ("repeat", "upbeat", "end")}
    diffs = []
    for bid, w in want.items():
        for k, c in counts.items():
            wv, gv = w[k], got[bid][k]
            if wv:
                c[0] += 1
                c[1] += gv == wv
            if gv and gv != wv:
                c[2] += 1
            if wv != gv:
                diffs.append(f"  {names.get(bid, bid)}: {k} editor {wv}, proposed {gv}")
    return counts, diffs


def line(counts: dict) -> str:
    return "; ".join(f"{k} {r}/{t} right, {x} wrong" for k, (t, r, x) in counts.items())


def main():
    edition = Path(sys.argv[1])
    readme = edition / "sources" / "README.md"
    rows = labels.parse_sources_readme(readme.read_text()) if readme.exists() else {}
    js = proposer_js()
    total = {}
    for lp, pdf in labels.labels_files(edition):
        info = labels.source_info(str(pdf.relative_to(edition)), rows)
        sp = labels.structure_path(edition, info["display"].get("work", ""))
        if not sp:
            continue
        counts, diffs = score(labels.migrate(json.loads(lp.read_text())), structure.expected(sp.read_text()), js)
        print(f"{lp.name}: {line(counts)}")
        print("\n".join(diffs))
        for k, v in counts.items():
            total[k] = [a + b for a, b in zip(total.get(k, [0, 0, 0]), v)]
    print(f"all: {line(total)}")


if __name__ == "__main__":
    main()
