"""Structure.ily's repeats, upbeats and movement ends, proposed on untouched
bar lines as the labeler numbers bars (static/app.js structureProposer).
Runs the JS under node (skipped without node)."""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
import structure  # noqa: E402
from test_labels import bl, doc, page, system  # noqa: E402

pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node not installed")

# a minuet whose halves begin with an upbeat and end on a short bar, then a
# Trio (a heading: its first repeat sign stands at a line's start); bars
# 0, 1-3 :|: 3-6 :| Trio 6-8 :|: 8-10 :|
MINUET = r"""\tag #'mvtI {
  \time 3/4
  \repeat volta 2 { \partial 4 s4 s2.*2 s2 }
  \repeat volta 2 { s4 s2.*2 s2 }
  \tempo "Trio"
  \repeat volta 2 { s4 s2. s2 }
  \repeat volta 2 { s4 s2.*2 }
}
\tag #'mvtII { \time 2/4 \repeat volta 2 { s2*1 } }
"""
WANT = [  # (bar it ends, count, kind, movement ends)
    (0, 0, "single", False), (1, 1, "single", False), (2, 1, "single", False), (3, 1, "repeat_both", False),
    (3, 0, "single", False), (4, 1, "single", False), (5, 1, "single", False), (6, 1, "repeat_end", False),
    (6, 0, "single", False), (7, 1, "single", False), (8, 1, "repeat_both", False), (8, 0, "single", False),
    (9, 1, "single", False), (10, 1, "repeat_end", True),
]


def lines(n, prefix, **kw):
    """n untouched bar lines, as detection places them"""
    return [bl(f"{prefix}{k}", 0.1 + 0.8 * k / n, auto=True, **kw) for k in range(n)]


def propose(d, text=MINUET, with_doc=False):
    src = (ROOT / "static" / "app.js").read_text()
    pick = lambda pat: re.search(pat, src, re.S).group(0)
    js = "\n".join([
        pick(r"const ROMAN = .*?;"),
        pick(r"const mid = .*?;"),
        pick(r"const roman = .*?;"),
        pick(r"function sectionEnds\(e\) \{.*?\n\}"),
        pick(r"const REPEAT_KINDS = .*?;"),
        pick(r"function structureProposer\(expected, doc\) \{.*?\n\}"),
        pick(r"function numberBars\(doc[^)]*\) \{.*?\n\}"),
        f"const doc = {json.dumps(d)};",
        f"const out = numberBars(doc, structureProposer({json.dumps(structure.expected(text))}, doc));",
        "console.log(JSON.stringify([doc, out.map(b => [b.right.id, b.movement, b.bar, b.count, b.right.kind, b.right.ends_movement])]));",
    ])
    out, bars = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
    return (out, bars) if with_doc else bars


def test_a_minuet_and_trio_are_proposed():
    d = doc({"1": page("va", [system("s1", 0.1, lines(7, "a")), system("s2", 0.3, lines(7, "b")),
                              system("s3", 0.5, lines(2, "c"))])})
    d["pages"]["1"]["status"] = "edited"
    got = propose(d)
    assert [(b, c, k, e) for _, m, b, c, k, e in got if m == "I"] == WANT
    # the next movement is still the template's: nothing proposed
    assert [(m, b, c, k, e) for _, m, b, c, k, e in got if m == "II"] == [
        ("II", 1, 1, "single", False), ("II", 2, 1, "single", False)]


def test_the_editors_bar_lines_and_reviewed_pages_are_left_alone():
    touched = lines(14, "a")
    touched[3].update(auto=False)                          # the editor's: no repeat sign here
    touched[13].update(auto=False, kind="double")
    d = doc({"1": page("va", [system("s1", 0.1, touched)]),
             "2": page("vc", [system("s1", 0.1, lines(14, "c"))])})
    d["pages"]["1"]["status"] = "edited"
    d["pages"]["2"]["status"] = "reviewed"
    got = {i: (b, c, k, e) for i, _, b, c, k, e in propose(d)}
    assert got["a3"] == (3, 1, "single", False) and got["a4"] == (3, 0, "single", False)  # the upbeat after it still is
    assert got["a13"] == (10, 1, "double", False)
    assert all(k == "single" and c == 1 and not e for i, (b, c, k, e) in got.items() if i.startswith("c"))


def test_proposals_follow_a_fix():
    # detection missed bar 2's bar line: the repeat lands a bar late, on a4
    a = lines(14, "a")
    missed = doc({"1": page("va", [system("s1", 0.1, a[:2] + a[3:])])})
    missed["pages"]["1"]["status"] = "edited"
    missed, bars = propose(missed, with_doc=True)
    kinds = lambda bars: {i: (c, k) for i, _, _, c, k, _ in bars}
    assert kinds(bars)["a4"] == (1, "repeat_both") and kinds(bars)["a5"] == (0, "single")
    # the editor adds it: the repeat and its upbeat move back
    missed["pages"]["1"]["systems"][0]["barlines"].append(bl("new", a[2]["x0"]))
    got = kinds(propose(missed))
    assert got["a3"] == (1, "repeat_both") and got["a4"] == (0, "single") and got["a5"] == (1, "single")


def test_a_movement_end_the_editor_marked_later_holds():
    # an extra bar line reaches bar 10 a bar early; the editor marked the end
    a = lines(15, "a")
    a[14].update(auto=False, ends_movement=True)
    d = doc({"1": page("va", [system("s1", 0.1, a)])})
    d["pages"]["1"]["status"] = "edited"
    got = {i: (m, b, e) for i, m, b, _, _, e in propose(d)}
    assert got["a13"] == ("I", 10, False) and got["a14"] == ("I", 11, True)
    # but an end the editor marked a movement later is that movement's
    two = MINUET.replace(r"\repeat volta 2 { s2*1 }", "s2*4")
    b = lines(18, "b")
    b[17].update(auto=False, ends_movement=True)
    d = doc({"1": page("va", [system("s1", 0.1, b)])})
    d["pages"]["1"]["status"] = "edited"
    got = {i: (m, n, e) for i, m, n, _, _, e in propose(d, two)}
    assert got["b13"] == ("I", 10, True) and got["b17"] == ("II", 4, True)


def test_a_proposal_moved_past_the_structure_is_taken_back():
    # the end lands on a13; the editor adds a missed bar line, and a13 is
    # movement II's (still the template's): plain again
    a = lines(14, "a")
    d = doc({"1": page("va", [system("s1", 0.1, a)])})
    d["pages"]["1"]["status"] = "edited"
    d, bars = propose(d, with_doc=True)
    assert {i: (k, e) for i, _, _, _, k, e in bars}["a13"] == ("repeat_end", True)
    d["pages"]["1"]["systems"][0]["barlines"].append(bl("new", (a[1]["x0"] + a[2]["x0"]) / 2))
    got = {i: (m, c, k, e) for i, m, _, c, k, e in propose(d)}
    assert got["a12"] == ("I", 1, "repeat_end", True) and got["a13"] == ("II", 1, "single", False)
