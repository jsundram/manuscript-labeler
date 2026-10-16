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
    "4": page(None, [], kind="title"),  # the cello stops on page 3: its movement ends there
    "10": page("va", [system("p10s1", 0.1, [bl("e", 0.4, bar_count=2), bl("f", 0.8)])]),
    "11": page("va", [system("p11s1", 0.1, [bl("g", 0.5)])]),
    "12": page(None, [], kind="other"),
    "13": page("vn1", [system("p13s1", 0.1, [bl("h", 0.5)])]),
})


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_js_and_python_number_bars_the_same():
    src = (ROOT / "static" / "app.js").read_text()
    pick = lambda pat: re.search(pat, src, re.S).group(0)
    js = "\n".join([
        pick(r"const ROMAN = .*?;"),
        pick(r"const mid = .*?;"),
        pick(r"const roman = .*?;"),
        pick(r"function partEnds\(doc\) \{.*?\n\}"),
        pick(r"function numberBars\(doc[^)]*\) \{.*?\n\}"),
        f"const out = numberBars({json.dumps(DOC)});",
        "console.log(JSON.stringify(out.map(b => [b.right.id, b.part, b.movement, b.bar, b.count, b.page, b.ends])));",
    ])
    got = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
    want = [[b["right"]["id"], b["part"], b["movement"], b["bar"], b["count"], b["page"], b["ends"]]
            for b in labels.number_bars(DOC)]
    assert got == want
    assert {b[0] for b in got if b[6]} == {"d", "y", "g"}  # marked; the cello before a title; the viola past a chart


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_js_and_python_find_the_same_clefs():
    from test_labels import clef_mark
    pg = page("vc", [
        system("l1", 0.1, [bl("a", 0.3), bl("b", 0.6)]),
        system("cue", 0.2, [bl("q", 0.5)], role="cue"),
        system("l2", 0.3, [bl("d", 0.5)]),
    ])
    pg["clef"] = "bass"
    pg["systems"][2]["clef"] = "bass"  # l2's own clef, written at its start
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
        pick(r"const sigValid = .*?;\n"),
        pick(r"function markStaff\(page, m\) \{.*?\n\}"),
        pick(r"function sigChanges\(page.*?\n\}"),
        pick(r"const clefMarks = .*?;"),
        pick(r"function clefsBetween\(page, system, x0, x1\) \{.*?\n\}"),
        f"const page = {json.dumps(pg)}; const by = (id) => page.systems.find((s) => s.id === id);",
        f"console.log(JSON.stringify({json.dumps(spans)}.map(([s, a, b]) => clefsBetween(page, by(s), a, b))));",
    ])
    got = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
    by = {s["id"]: s for s in pg["systems"]}
    want = [labels.clefs_between(pg, by[s], a, b) for s, a, b in spans]
    assert got == want
    assert want == [["bass"], ["bass", "tenor"], ["bass", "alto"], ["bass", "alto"], ["alto"]]


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_a_staff_ends_at_its_last_bar_line():
    # the editor's staff-end rule (app.js): bar line edits move an end out of
    # the band back to the last bar line; an end left out of it is flagged
    # unless the staff runs on; cues are left alone
    src = (ROOT / "static" / "app.js").read_text()
    pick = lambda pat: re.search(pat, src, re.S).group(0)
    js = "\n".join([
        "const S = { W: 1000, H: 1000, page: 1, step: null };",
        pick(r"const mid = .*?;"), pick(r"const clamp = .*?;"), pick(r"const space = .*?;"), pick(r"const pg = .*?;"),
        pick(r"function bendAt\(s, x\) \{.*?\n\}"), pick(r"function setExtent\(s, left, right\) \{.*?\n\}"),
        pick(r"const lastBarlineX = .*?;\n"), pick(r"const endAtLast = .*?;\n"),
        pick(r"function trimToLastBarline\(s\) \{.*?\n\}"), pick(r"const END_SLACK = .*?;"),
        pick(r"function endOutside\(s\) \{.*?\n\}"), pick(r"const endOff = .*?;\n"),
        pick(r"function stepStart\(\) \{.*?\n\}"),
        pick(r"function followLastBarlines\(\) \{.*?\n\}"),
        # staff spaces of 0.01: half a space past the last bar line is +0.005
        "const s = { id: 's', top: 0.1, bottom: 0.14, left: 0.1, right: 0.9, bend: [0, 0.01, 0.02], barlines: [{ x0: 0.5, x1: 0.5 }, { x0: 0.7, x1: 0.7 }] };",
        "const cue = { id: 'c', role: 'cue', top: 0.3, bottom: 0.34, left: 0.1, right: 0.9, barlines: [{ x0: 0.5, x1: 0.5 }] };",
        "S.doc = { pages: { 1: { systems: [s, cue] } } };",
        "const r = (v) => Math.round(v * 1e4) / 1e4, out = {};",
        "const edit = (fn) => { stepStart(); fn(); followLastBarlines(); };",
        "out.flagged = r(endOff(s));",                                   # as saved, 20 spaces past: flagged
        "edit(() => s.barlines.push({ x0: 0.8, x1: 0.8 })); out.added = r(s.right);",
        # the bend carries on along its last segment when the end moves out
        "edit(() => { s.barlines[2].x0 = s.barlines[2].x1 = 0.95; }); out.extended = r(s.right); out.bend_end = r(s.bend[2]);",
        "edit(() => { s.barlines[2].x0 = s.barlines[2].x1 = 0.951; }); out.in_band = r(s.right);",   # a nudge within the band: no move
        "edit(() => s.barlines.pop()); out.deleted = r(s.right);",
        "edit(() => { s.barlines[0].x0 = 0.52; }); out.other_moved = r(s.right);",
        # placed and taken back in one step (snapped onto a bar line already there): the end is as it was
        "s.right = 0.71; s.auto = true; edit(() => { s.barlines.push({ x0: 0.9, x1: 0.9 }); followLastBarlines(); s.barlines.pop(); });",
        "out.net_none = [r(s.right), s.auto];",
        "s.right = 0.99; out.dragged = r(endOff(s));",                 # an end dragged by hand stays, flagged
        "s.right = 0.696; out.just_short = r(endOff(s));",             # 0.4 space short: the bar line is outside
        "s.right = 0.99; s.runs_on = true; out.runs_on = r(endOff(s)); s.right = 0.696;",  # runs on: past is not flagged
        "edit(() => { s.barlines[1].x0 = s.barlines[1].x1 = 0.6; }); out.runs_on_kept = r(s.right);",
        "edit(() => { cue.barlines[0].x0 = cue.barlines[0].x1 = 0.4; }); out.cue_kept = r(cue.right); out.cue_flag = endOff(cue);",
        "const d = { id: 'd', top: 0.5, bottom: 0.54, left: 0.1, right: 0.9, barlines: [{ x0: 0.6, x1: 0.6 }], auto: true };",
        # detection's own end, with music past its last bar line, stays and is flagged
        "S.doc.pages[1].systems.push(d); out.detected = [r(d.right), r(endOff(d))];",
        # re-detection replacing its bar lines (taking the step again after) keeps it
        "stepStart(); d.barlines = [{ x0: 0.61, x1: 0.61 }]; stepStart(); followLastBarlines(); out.redetected = [r(d.right), d.auto];",
        # the editor nudging that bar line, or snapping it, doesn't cut it; adding the missed final one does
        "edit(() => { d.barlines[0].x0 = d.barlines[0].x1 = 0.612; }); out.nudged = r(d.right);",
        "edit(() => d.barlines.push({ x0: 0.85, x1: 0.85 })); out.final_added = [r(d.right), d.auto];",
        # a runs-on staff whose last bar line lies past its end is flagged short
        "const ro = { id: 'r', top: 0.6, bottom: 0.64, left: 0.1, right: 0.7, runs_on: true, barlines: [{ x0: 0.75, x1: 0.75 }] };",
        "out.runs_on_short = r(endOff(ro));",
        "console.log(JSON.stringify(out));",
    ])
    got = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
    assert got == {"flagged": 20.0, "added": 0.805, "extended": 0.955, "bend_end": 0.0214, "in_band": 0.955,
                   "deleted": 0.705, "other_moved": 0.705, "net_none": [0.71, True], "dragged": 29.0,
                   "just_short": -0.4, "runs_on": 0, "runs_on_kept": 0.696, "cue_kept": 0.9, "cue_flag": 0,
                   "detected": [0.9, 30.0], "redetected": [0.9, True], "nudged": 0.9,
                   "final_added": [0.855, False], "runs_on_short": -5.0}
