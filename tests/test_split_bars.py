"""experiments/zeus/dataset.py: which staves autopair.py kept can be
labelled (labellable), and each staff's part of a bar split across a line
break or by a repeat (staff_boxes, box_events)."""

import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "experiments" / "zeus"))
import dataset  # noqa: E402

REPEAT = "a bar a repeat splits"


def ev(pos, dur="8", grace="0"):
    return {"kind": "note", "pos": pos, "dur": dur, "grace": grace}


# bar 0: a one-eighth pickup at 3/8; bar 5: four eighths; bar 7: split by a repeat
EVENTS = {"0": [ev("3/8")], "5": [ev("0"), ev("1/8"), ev("1/4"), ev("3/8")],
          "6": [ev("0", "2")], "7": [ev("0"), ev("1/8"), ev("1/4"), ev("3/8")]}


def measure(b, count=1):
    return {"bars": [["Op1-1", "I", b]], "count": count}


def kept(boxes, plain=False, **kw):
    return {"plain": plain, "clef": "treble", "bars": [["Op1-1", "I", m["bars"][0][2]] for m in boxes],
            "boxes": boxes, **kw}


def test_labellable():
    assert dataset.labellable({"plain": True})
    assert dataset.labellable({"plain": False, "halves": [{}]})
    assert dataset.labellable({"plain": False, "irregular": [REPEAT]})
    # halves beside a bar a repeat splits: both labelled
    assert dataset.labellable({"plain": False, "halves": [{}], "irregular": [REPEAT]})
    assert not dataset.labellable({"plain": False, "halves": [{}], "irregular": [REPEAT, "a multi-bar rest"]})
    assert not dataset.labellable({"plain": False, "irregular": ["a bar a repeat splits, read as one measure"]})
    # a pairing from before autopair.py named its measures: only plain staves
    assert not dataset.labellable({"plain": False})


def test_line_break_halves():
    """The staff ending with bar 5's first half, and the next opening with its second."""
    half = lambda h: {"bar": ["Op1-1", "I", 5], "half": h, "cut": "1/4", "fit": 0.1}
    end = kept([measure(4), measure(5, 0)], halves=[half("first")])
    boxes, cuts = dataset.staff_boxes(end, "vn1", "Op1-1", EVENTS, set())
    assert [(b["bar"], b["count"]) for b in boxes] == [(4, 1), (5, 1)] and cuts == {5: Fraction(1, 4)}
    assert [e["pos"] for e in dataset.box_events(boxes[1], EVENTS, cuts)] == ["0", "1/8"]
    start = kept([measure(5), measure(6)], halves=[half("second")])
    boxes, cuts = dataset.staff_boxes(start, "vn1", "Op1-1", EVENTS, set())
    assert [(b["bar"], b["count"]) for b in boxes] == [(5, 0), (6, 1)]
    assert [e["pos"] for e in dataset.box_events(boxes[0], EVENTS, cuts)] == ["1/4", "3/8"]


def test_repeat_halves():
    """Bar 7's halves, cut where the pickup starts: both in the staff, or one ending it."""
    both = kept([measure(6), measure(7, 1), measure(7, 0)], irregular=[REPEAT])
    boxes, cuts = dataset.staff_boxes(both, "vn1", "Op1-1", EVENTS, {7})
    assert cuts == {7: Fraction(3, 8)}
    assert [len(dataset.box_events(b, EVENTS, cuts)) for b in boxes] == [1, 3, 1]
    end = kept([measure(6), measure(7, 0)], irregular=[REPEAT])
    boxes, cuts = dataset.staff_boxes(end, "vn1", "Op1-1", EVENTS, {7})
    assert [e["pos"] for e in dataset.box_events(boxes[1], EVENTS, cuts)] == ["0", "1/8", "1/4"]


def test_left_out():
    rest = kept([measure(4), {"bars": [["Op1-1", "I", 5], ["Op1-1", "I", 6]], "count": 2}], irregular=["a multi-bar rest"])
    assert dataset.staff_boxes(rest, "vn1", "Op1-1", EVENTS, set()) == (None, "a multi-bar rest")
    # no pickup: a bar a repeat splits can't be cut
    boxes, cuts = dataset.staff_boxes(kept([measure(6), measure(7, 0)], irregular=[REPEAT]), "vn1", "Op1-1",
                                      {k: v for k, v in EVENTS.items() if k != "0"}, {7})
    assert cuts == {7: False} and dataset.box_events(boxes[1], EVENTS, cuts) is None
