"""The activity log (SPEC.md, Activity): the page's edit descriptions
(static/app.js describeEdit, under node; skipped without it), the server's
log, and activity.py's active time and the Time panel's report."""

import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
import activity  # noqa: E402
import server  # noqa: E402


def describe(a, b):
    src = (ROOT / "static" / "app.js").read_text()
    fn = re.search(r"function describeEdit\(a, b\) \{.*?\n\}", src, re.S).group(0)
    js = f"{fn}\nconsole.log(JSON.stringify(describeEdit({json.dumps(a)}, {json.dumps(b)})));"
    return json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)


def page(barlines, marks=(), status="auto", top=0.1):
    return {"status": status, "kind": "music", "part": "vn1", "clef": None, "notes": "",
            "corners": {"points": [[0, 0], [1, 0], [1, 1], [0, 1]], "auto": True},
            "systems": [{"id": "p1s1", "top": top, "bottom": 0.2, "left": 0.1, "right": 0.9, "auto": True,
                         "barlines": list(barlines)}],
            "marks": list(marks)}


def bl(i, x, auto=True, **kw):
    return {"id": f"p1s1b{i}", "x0": x, "x1": x, "kind": "single", "bar_count": 1, "auto": auto, **kw}


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
def test_describe_edit():
    a = page([bl(1, 0.3), bl(2, 0.5)])
    assert describe(a, page([bl(1, 0.3), bl(2, 0.5), bl(3, 0.7, auto=False)])) == ["bar line added"]
    assert describe(a, page([bl(1, 0.3)])) == ["bar line removed (detected)"]
    assert describe(a, page([bl(1, 0.31, auto=False), bl(2, 0.5)])) == ["bar line moved (detected)"]
    assert describe(a, page([bl(1, 0.3), bl(2, 0.5, bar_count=0)])) == ["bar count (detected)"]
    assert describe(a, page([bl(1, 0.3), bl(2, 0.5)], status="reviewed")) == ["status reviewed"]
    assert describe(a, page([bl(1, 0.3), bl(2, 0.5)], top=0.11)) == ["staff moved (detected)"]
    m = {"id": "p1m1", "kind": "tempo", "x": 0.1, "y": 0.1, "w": 0.1, "h": 0.05, "text": "Allegro", "auto": True}
    with_mark = page([bl(1, 0.3), bl(2, 0.5)], [m])
    assert describe(a, with_mark) == ["mark added"]
    assert describe(with_mark, page([bl(1, 0.3), bl(2, 0.5)], [{**m, "kind": "title"}])) == ["mark kind (detected)"]
    assert describe(a, a) == []
    # marking reviewed writes the movement's key onto the staves: part of reviewing, not a correction
    signed = page([bl(1, 0.3), bl(2, 0.5)], status="reviewed")
    signed["systems"][0]["key"] = -2
    assert describe(a, signed) == ["status reviewed"]


def test_server_log(tmp_path):
    root = tmp_path / "ed"
    (root / "sources").mkdir(parents=True)
    ed = server.Edition(root, tmp_path / "cache", tmp_path / "data")
    t = time.mktime((2026, 10, 16, 9, 0, 0, 0, 0, -1))
    n = ed.log_activity([{"t": t, "src": "labeler", "kind": "open", "file": "sources/G1/X.pdf", "where": "p1"},
                         {"t": t + 60, "src": "labeler", "kind": "edit", "what": "bar line added"}])
    assert n == 2
    f = tmp_path / "data" / "ed" / "activity" / "2026-10.jsonl"
    assert [json.loads(l)["kind"] for l in f.read_text().splitlines()] == ["open", "edit"]
    ed.log_activity([{"t": t + 120, "kind": "key"}])  # appended, not rewritten
    assert len(f.read_text().splitlines()) == 3
    for bad in ({"kind": "x"}, {"t": "now", "kind": "x"}, "x", {"t": float("nan"), "kind": "x"},
                {"t": 1e300, "kind": "x"}):
        with pytest.raises(ValueError):
            ed.log_activity([bad])
    with pytest.raises(ValueError):
        ed.log_activity({"t": t, "kind": "x"})
    assert ed.timed("detect", "sources/G1/X.pdf", 3, lambda: 42) == 42
    last = json.loads(f.read_text().splitlines()[-1])
    assert last["src"] == "labeler-server" and last["kind"] == "detect" and last["where"] == "p3"


def ev(t, kind="active", where="p1", t_end=None, src="labeler", **kw):
    return {"t": t, "t_end": t if t_end is None else t_end, "src": src, "kind": kind,
            "file": "sources/G1/X.pdf", "where": where, "edition": "ed", **kw}


def test_active_time():
    k = ("ed", "sources/G1/X.pdf")
    # one stretch: p1 from 0 to 120, then p2 to its heartbeat's end at 200
    got = activity.attribute([ev(0), ev(120, kind="open", where="p2"), ev(150, where="p2", t_end=200)])
    assert got == {(*k, "p1"): 120, (*k, "p2"): 80}
    # a gap of over ten minutes ends a stretch: each lone event counts a minute
    got = activity.attribute([ev(0), ev(1000)])
    assert got == {(*k, "p1"): 120}
    # time after the page lost focus isn't counted
    got = activity.attribute([ev(0, t_end=30), ev(30, kind="blur"), ev(300, kind="focus"), ev(330, t_end=390)])
    assert got[(*k, "p1")] == 30 + 0 + 30 + 60
    # a heartbeat running on over the keys and edits inside it: each moment counted once
    got = activity.attribute([ev(0, t_end=300), ev(50, kind="key"), ev(100, kind="edit"), ev(200, kind="key")])
    assert got == {(*k, "p1"): 300}
    # the server's events count no person's time
    assert activity.attribute([ev(0, src="labeler-server", kind="detect", t_end=50)]) == {}


def test_report(tmp_path, monkeypatch):
    monkeypatch.setattr(activity, "DATA", tmp_path)
    (tmp_path / "ed" / "sources" / "G1").mkdir(parents=True)
    (tmp_path / "ed" / "sources" / "G1" / "X.labels.json").write_text(json.dumps({"pages": {"1": page(
        [bl(1, 0.3), bl(2, 0.5), bl(3, 0.7, bar_count=0)])}}))
    evs = [ev(0, kind="open"), ev(10, kind="edit", what="bar line added, bar line removed (detected)", n=3),
           ev(20, kind="key", what="d"), ev(25, kind="detect", src="labeler-server", seconds=4.0), ev(600)]
    r = activity.report(evs, activity.GAP, pages=True)
    assert r["active_seconds"] == 600
    src = r["sources"]["ed/sources/G1/X.pdf"]
    assert src["bars"] == 2 and src["edits"] == {"p1": 3}
    assert r["edits"] == {"bar line added": 3} and r["corrections"] == {"bar line removed (detected)": 3}
    assert r["waits"] == {"detect": [1, 4.0]} and r["keys"] == {"d": 1}


def test_source_report():
    """The Time panel: time while it is open (pause to resume) doesn't
    count; a page's time splits at its first marking as reviewed."""
    doc = {"pages": {"1": page([bl(1, 0.3), bl(2, 0.5)]), "2": {**page([bl(1, 0.4)]), "status": "reviewed"}}}
    evs = [ev(0, kind="open"), ev(60, kind="edit", what="bar line moved (detected)"),
           ev(120, kind="edit", what="status reviewed"), ev(150, kind="open", where="p2"),
           ev(200, kind="pause", where="p2"), ev(500, kind="resume", where="p2"), ev(560, where="p2"),
           ev(565, kind="detect", src="labeler-server", where="p2", t_end=569, seconds=4)]
    r = activity.source_report(evs, doc)
    p1, p2 = r["pages"]
    assert (p1["page"], p1["first_pass"], p1["review"], p1["corrections"], p1["edits"]) == (1, 120, 30, 1, 2)
    assert (p2["page"], p2["seconds"]) == (2, 50 + 60 + 0)  # 150-200, then 500-560; the panel's 300 s left out
    assert r["seconds"] == 150 + 110 and r["reviewed"] == 1 and r["bars"] == 3
    (run,) = r["timeline"]
    assert [w for _, _, w in run["pieces"]] == ["p1", "p1", "p1", "p2", "p2"]
    assert run["waits"] == [[565, 569, "detect", "p2"]]
    assert activity.source_report([], doc)["timeline"] == []


def test_undo_and_background():
    """An undone marking as reviewed doesn't split the page's time; Claude's
    read of the next page isn't a wait; undo and machine changes are tallied
    apart from the editor's edits."""
    evs = [ev(0, kind="open"), ev(60, kind="edit", what="status reviewed"), ev(70, kind="undo", what="status edited"),
           ev(100, kind="auto", what="bar line added", by="detection"), ev(200),
           ev(150, kind="read-ahead", src="labeler-server", t_end=160, seconds=10),
           ev(170, kind="read", src="labeler-server", t_end=175, seconds=5)]
    r = activity.source_report(sorted(evs, key=lambda e: e["t"]), {"pages": {"1": page([bl(1, 0.3)])}})
    (p1,) = r["pages"]
    assert p1["reviewed_at"] is None and p1["review"] == 0 and p1["edits"] == 1
    assert r["undone"] == {"undo: status edited": 1} and r["machine"] == {"detection: bar line added": 1}
    assert r["waits"] == {"read": [1, 5.0]} and r["background"] == {"read-ahead": [1, 10.0]}
    assert [w[2] for w in r["timeline"][0]["waits"]] == ["read"]
