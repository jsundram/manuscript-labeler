"""experiments/zeus/dataset.py: which staves autopair.py kept can be
labelled (labellable), and each staff's part of a bar split across a line
break or by a repeat (staff_boxes, box_events); and autopair.py's re-cut
of such a bar where the alignment paired it whole on one staff (recut)."""

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


# -- autopair.recut: a bar the line breaks, paired whole on one staff, its other piece extra

import autopair  # noqa: E402


def note(pitch, onset, dur="quarter"):
    return {"kind": "note", "dur": dur, "dots": 0, "grace": False, "pitches": [pitch], "onset": Fraction(onset)}


BAR5 = [note("C5", 0), note("E5", "1/4"), note("G5", "1/2"), note("B5", "3/4")]
BAR6 = [note("D5", 0, "whole")]


def recut(end_of_a, start_of_b, b_pairs_more=True):
    """Staff A ends with measure 0 (paired whole with bar 5), staff B opens
    with measure 1 (extra), then measure 2 (bar 6) if b_pairs_more."""
    tok = lambda evs: autopair.tokens(evs, autopair.steps_enc)
    Z = [tok(end_of_a), tok(start_of_b), tok(BAR6)]
    path = [("one", [0], [0]), ("extra", [1], [])] + ([("one", [2], [1])] if b_pairs_more else [("extra", [2], [])])
    return autopair.recut(path, Z, [tok(BAR5), tok(BAR6)], [BAR5, BAR6], {0}, [[("I", 5)], [("I", 6)]], set(),
                          ["A", "B", "B"])


def test_recut_a_split_bar():
    """A's piece read twice as long (as long as the bar): split at the half."""
    first_doubled = [note("C5", 0, "half"), note("E5", "1/2", "half")]
    path = recut(first_doubled, BAR5[2:])
    assert path[0] == ("split", [0, 1], [0])
    assert autopair.break_cut(autopair.tokens(first_doubled, autopair.steps_enc),
                              autopair.tokens(BAR5[2:], autopair.steps_enc), BAR5)[0] == Fraction(1, 2)


def test_recut_not_a_whole_bar():
    """A reads as the whole bar: it holds it, and B's extra measure is something else (a second ending)."""
    assert recut(BAR5, BAR5[2:])[0] == ("one", [0], [0])


def test_recut_not_into_a_staff_that_pairs_nothing():
    first_doubled = [note("C5", 0, "half"), note("E5", "1/2", "half")]
    assert recut(first_doubled, BAR5[2:], b_pairs_more=False)[0] == ("one", [0], [0])
