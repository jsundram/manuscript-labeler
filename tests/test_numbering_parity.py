"""The editor numbers bars live in JS; the server writes the export in Python.
Both must agree. Runs the JS numberBars under node (skipped without node)."""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
import labels  # noqa: E402
from test_labels import bl, doc, page, system  # noqa: E402

DOC = doc({
    "1": page(None, [], kind="title"),
    "2": page("va", [
        system("p2s2", 0.5, [bl("c", 0.3), bl("d", 0.6, ends_movement=True)]),
        system("p2s1", 0.1, [bl("a", 0.6), bl("p", 0.2, bar_count=0), bl("b", 0.3)]),
    ]),
    "3": page("vc", [system("p3s1", 0.1, [bl("x", 0.5)], role="cue"),
                     system("p3s2", 0.3, [bl("y", 0.5, bar_count=3)])]),
    "10": page("va", [system("p10s1", 0.1, [bl("e", 0.4, bar_count=2), bl("f", 0.8)])]),
})


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_js_and_python_number_bars_the_same():
    src = (ROOT / "static" / "app.js").read_text()
    pick = lambda pat: re.search(pat, src, re.S).group(0)
    js = "\n".join([
        pick(r"const ROMAN = .*?;"),
        pick(r"const mid = .*?;"),
        pick(r"const roman = .*?;"),
        pick(r"function numberBars\(doc\) \{.*?\n\}"),
        f"const out = numberBars({json.dumps(DOC)});",
        "console.log(JSON.stringify(out.map(b => [b.right.id, b.part, b.movement, b.bar, b.count, b.page])));",
    ])
    got = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
    want = [[b["right"]["id"], b["part"], b["movement"], b["bar"], b["count"], b["page"]]
            for b in labels.number_bars(DOC)]
    assert got == want


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_js_and_python_find_the_same_clefs():
    from test_labels import clef_mark
    pg = page("vc", [
        system("l1", 0.1, [bl("a", 0.3), bl("b", 0.6)]),
        system("cue", 0.2, [bl("q", 0.5)], role="cue"),
        system("l2", 0.3, [bl("d", 0.5)]),
    ])
    pg["clef"] = "bass"
    pg["marks"] = [clef_mark("m1", 0.45, 0.115, "tenor"), clef_mark("m2", 0.07, 0.215, "treble"),
                   clef_mark("m3", 0.07, 0.315, "bass"), clef_mark("m4", 0.4, 0.315, "alto"),
                   clef_mark("m5", 0.615, 0.115, "alto")]  # at the start of l1's bar after b
    spans = [("l1", None, 0.3), ("l1", 0.3, 0.6), ("l2", None, 0.5), ("l2", 0.35, 0.5), ("l1", 0.6, 0.95)]
    src = (ROOT / "static" / "app.js").read_text()
    pick = lambda pat: re.search(pat, src, re.S).group(0)
    js = "\n".join([
        pick(r"const CLEFS = .*?;"),
        pick(r"const clamp = .*?;"),
        pick(r"const mid = .*?;"),
        pick(r"function bendAt\(s, x\) \{.*?\n\}"),
        pick(r"function clefStaff\(page, m\) \{.*?\n\}"),
        pick(r"function clefMarks\(page.*?\n\}"),
        pick(r"function clefsBetween\(page, system, x0, x1\) \{.*?\n\}"),
        f"const page = {json.dumps(pg)}; const by = (id) => page.systems.find((s) => s.id === id);",
        f"console.log(JSON.stringify({json.dumps(spans)}.map(([s, a, b]) => clefsBetween(page, by(s), a, b))));",
    ])
    got = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
    by = {s["id"]: s for s in pg["systems"]}
    want = [labels.clefs_between(pg, by[s], a, b) for s, a, b in spans]
    assert got == want
    assert want == [["bass"], ["bass", "tenor"], ["bass", "alto"], ["bass", "alto"], ["alto"]]
