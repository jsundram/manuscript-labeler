"""Notes abbreviated by stem strokes (Philhar's c2.:8): written out where a
copyist wrote the notes out (philhar.written_out), else labelled with their
tremolo strokes (dataset.note_elements)."""

import sys
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "experiments" / "zeus"))
import dataset  # noqa: E402
import philhar  # noqa: E402


def col(label, pos, dur, pitch="D4", **kw):
    return {"label": label, "kind": "note", "pos": pos, "grace": "0", "voice": 1, "dur": dur,
            "notes": [{"pitch": pitch, "acc": None}], "slur": ["("], "slur_to": [], "tie": False, "tie_to": None,
            "beam": [], "dyn": "p", "hair": [], "text": None, "art": ["staccato"], "tup": [], "clef": "treble", **kw}


def test_written_out():
    bar = [col("n1", "0", "half.", tremolo=8, tie=True, tie_to=[2, 1])]
    out = philhar.written_out(bar)
    assert [(e["label"], e["pos"], e["dur"]) for e in out] == [(f"n1.{i}", str(Fraction(i, 8)), "8th") for i in range(6)]
    assert out[0]["beam"] == ["start"] and out[-1]["beam"] == ["stop"] and all(not e["beam"] for e in out[1:-1])
    assert out[0]["slur"] == ["("] and out[0]["art"] == ["staccato"] and all(e["slur"] == [] and e["art"] == [] for e in out[1:])
    assert not out[0]["tie"] and out[-1]["tie"] and out[-1]["tie_to"] == [2, 1]
    assert all("tremolo" not in e for e in out)
    # a bar without abbreviations is as it was
    plain = [col("n1", "0", "quarter"), col("n2", "1/4", "half")]
    assert philhar.written_out(plain) == plain
    # in a tuplet (Op. 32/5 I, vn2, bar 32: a dotted quarter :16 lasting a quarter, triplet sixteenths after):
    # its six sixteenths share the quarter, and the tuplet opens on the first
    bar = [col("n1", "0", "quarter.", tremolo=16, tup=[["start", 3, 2]]), col("n2", "1/4", "16th")]
    out = philhar.written_out(bar)
    assert [e["pos"] for e in out[:6]] == [str(Fraction(i, 24)) for i in range(6)] and out[6]["pos"] == "1/4"
    assert out[0]["tup"] == [["start", 3, 2]] and all(e["tup"] == [] for e in out[1:6])
    # a quarter with :16, four sixteenths
    assert [e["dur"] for e in philhar.written_out([col("n1", "0", "quarter", tremolo=16)])] == ["16th"] * 4


def strokes(e) -> list[tuple]:
    m = ET.Element("measure")
    dataset.note_elements(m, 1, e, {}, Fraction(3, 4))
    return [(t.get("type"), t.text) for t in m.iter("tremolo")]


def test_tremolo_strokes_in_the_label():
    assert strokes(col("n1", "0", "half.", tremolo=8)) == [("single", "1")]   # a dotted half for eighths: one stroke
    assert strokes(col("n1", "0", "quarter", tremolo=16)) == [("single", "2")]
    assert strokes(col("n1", "0", "8th", tremolo=16)) == [("single", "1")]    # its flag counts as one
    assert strokes(col("n1", "0", "half.")) == []
