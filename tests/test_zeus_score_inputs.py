"""tools/zeus_score.py's inputs: explicit files, or the Op. 48 edition's
layout; a structure as Structure.ily or JSON. Zeus itself isn't run."""

import importlib.util
import json
import sys
from argparse import Namespace
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("zeus_score_tool", ROOT / "tools" / "zeus_score.py")
zs = importlib.util.module_from_spec(spec)
sys.modules["zeus_score_tool"] = zs
spec.loader.exec_module(zs)

STRUCTURE = r"""
\tag #'mvtI {
  \time 2/4 \key a \major
  \tempo "Andante lento"
  s2*88
  \bar "|."
}
"""


def args(**kw):
    base = dict(pdf=None, bars=None, structure=None, edition=None, source=None)
    return Namespace(**{**base, **kw})


def edition(tmp_path, gerard=227):
    src = tmp_path / "sources" / f"G{gerard}"
    src.mkdir(parents=True)
    (src / "X.pdf").write_bytes(b"%PDF")
    (src / "X.bars.json").write_text(json.dumps({"source": {"gerard": gerard}, "bars": []}))
    q = tmp_path / f"Op48-{gerard - 225}"
    q.mkdir()
    (q / "Structure.ily").write_text(STRUCTURE)
    return tmp_path


def test_movements_json(tmp_path):
    f = tmp_path / "s.json"
    f.write_text(json.dumps({"II": {"time": "3/4", "key": 3, "changes": [{"bar": 28, "on_bar_line": False, "key": 2}]},
                             "I": {"time": "2/4", "key": 3}}))
    m = zs.movements(f)
    assert m["I"]["changes"] == []
    box = {"bar": 28, "count": 0}
    assert zs.compare.in_force(m["II"], "key", box) == 2  # from the upbeat of bar 28
    assert zs.compare.in_force(m["II"], "key", {"bar": 27, "count": 1}) == 3
    f.write_text(json.dumps({"I": {"time": "2/4"}}))
    with pytest.raises(SystemExit, match="key"):
        zs.movements(f)


def test_movements_ily(tmp_path):
    f = tmp_path / "Structure.ily"
    f.write_text(STRUCTURE)
    m = zs.movements(f)
    assert m["I"]["time"] == "2/4" and m["I"]["key"] == 3


def test_inputs_edition(tmp_path):
    ed = edition(tmp_path)
    pdf, export, mvts, source = zs.inputs(args(edition=ed, source="X"))
    assert pdf == ed / "sources" / "G227" / "X.pdf" and source == "X" and "I" in mvts
    with pytest.raises(SystemExit, match="--source"):
        zs.inputs(args(edition=ed))


def test_inputs_explicit(tmp_path):
    ed = edition(tmp_path)
    s = tmp_path / "s.json"
    s.write_text(json.dumps({"I": {"time": "6/8", "key": 1}}))
    pdf, export, mvts, source = zs.inputs(args(pdf=ed / "sources" / "G227" / "X.pdf", structure=s))
    assert source == "X" and mvts["I"]["time"] == "6/8"  # the bar export found beside the PDF
    with pytest.raises(SystemExit, match="--structure"):
        zs.inputs(args(pdf=ed / "sources" / "G227" / "X.pdf"))
    with pytest.raises(SystemExit, match="--pdf"):
        zs.inputs(args(structure=s))
    with pytest.raises(SystemExit, match="bar export"):
        zs.inputs(args(pdf=tmp_path / "nowhere.pdf", structure=s))


def test_movements_json_changes(tmp_path):
    f = tmp_path / "s.json"
    for bad in ({"I": {"time": "3/4", "key": 1, "changes": [{"key": 2}]}},           # no bar
                {"I": {"time": "3/4", "key": 1, "changes": [{"bar": 9}]}},           # nothing changes
                {"I": {"time": "3/4", "key": "A major"}},                            # key not in fifths
                {"I": {"time": "three", "key": 1}}):
        f.write_text(json.dumps(bad))
        with pytest.raises(SystemExit):
            zs.movements(f)


def test_trained():
    on = {"D-B_KHM-603": ["II"], "Op32-G201-206": ["*"]}
    assert zs.trained(on, "D-B_KHM-603", True, "II") is True
    assert zs.trained(on, "D-B_KHM-603", True, "I") is False
    assert zs.trained(on, "Op32-G201-206", False, "III") is True       # every movement
    assert zs.trained(on, "F-Po_RES-507-17", True, "II") is False      # named, not trained on
    assert zs.trained(on, "KHM603-scan", False, "II") is None          # named only by its file: unknown
    assert zs.trained(None, "D-B_KHM-603", True, "II") is None         # a model given by path


def test_render_dir(tmp_path, monkeypatch):
    """Two manuscripts with one name never share renders."""
    monkeypatch.setattr(zs.compare, "RENDERS", tmp_path / "renders")
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    a, b = tmp_path / "a" / "M.pdf", tmp_path / "b" / "M.pdf"
    a.write_bytes(b"%PDF one")
    b.write_bytes(b"%PDF two")
    assert zs.compare.render_dir(a) != zs.compare.render_dir(b)
    assert zs.compare.render_dir(a).name.startswith("M-")
