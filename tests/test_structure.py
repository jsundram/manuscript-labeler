"""A movement's Structure.ily block from a source's labels (structure.py)."""

import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import labels  # noqa: E402
import structure  # noqa: E402
from test_labels import bl, doc, page, system  # noqa: E402

TEMPLATE = r"""% header
\tag #'mvtI {
  \time 2/4 \key c \major
  \tempo "Allegro"
  \repeat volta 2 { s2*1 }       % first half: replace 1 with the bar count
  \repeat volta 2 { s2*1 }       % second half
  \bar "|."
}

%%% USEFUL SKELETON IDIOMS
"""


def quartet(rest_in=None, key=2, time="3/4", rest_to_short=False):
    """Movement I, four parts alike: an upbeat, 3 bars and a short one to a
    repeat, an upbeat, 3 bars to the end; Violin I states key and time.
    `rest_in`: a part writing bars 2-3 of the first half as one 2-bar rest
    (`rest_to_short`: bars 3-4 instead, ending at the short bar)."""
    pages = {}
    for n, part in enumerate(structure.PARTS, start=1):
        first = [bl(f"{part}u", 0.15, bar_count=0)]
        if part == rest_in and rest_to_short:
            first += [bl(f"{part}a", 0.3), bl(f"{part}b", 0.4), bl(f"{part}d", 0.6, kind="repeat_end", bar_count=2)]
        elif part == rest_in:
            first += [bl(f"{part}a", 0.3), bl(f"{part}b", 0.5, bar_count=2), bl(f"{part}d", 0.6, kind="repeat_end")]
        else:
            first += [bl(f"{part}a", 0.3), bl(f"{part}b", 0.4), bl(f"{part}c", 0.5), bl(f"{part}d", 0.6, kind="repeat_end")]
        second = [bl(f"{part}e", 0.2, bar_count=0), bl(f"{part}f", 0.4), bl(f"{part}g", 0.6), bl(f"{part}h", 0.8),
                  bl(f"{part}i", 0.9, kind="repeat_end", ends_movement=True)]
        sig = {"key": key, "time": time} if part == "vn1" else {}
        pages[str(n)] = page(part, [system(f"{part}1", 0.1, first, **sig), system(f"{part}2", 0.3, second)])
    return doc(pages)


def test_a_movement_from_the_labels():
    r = structure.propose(quartet(), "I", None, {"upbeat": "4", "mode0": "minor"})
    assert r["ok"], r["problems"]
    body = r["text"].split("\n", 1)[1]
    assert body == "\n".join([
        r"\tag #'mvtI {",
        r"  \time 3/4 \key b \minor",
        r"  \repeat volta 2 { \partial 4 s4 s2.*3 s2 }",
        r"  \repeat volta 2 { s4 s2.*3 s2 }",
        "}"])
    got = labels.parse_structure(r["text"])["I"]
    assert (got["total"], got["pickup"], got["key"], got["time"]) == (8, True, 2, "3/4")
    assert [q["id"] for q in r["questions"]] == ["mode0", "upbeat"]


def test_a_multi_bar_rest_agrees_with_the_bars_it_stands_for():
    assert structure.propose(quartet(rest_in="va"), "I", None, {"upbeat": "4"})["ok"]
    # even in the part the block is read from, ending at the short bar before an upbeat
    plain = structure.propose(quartet(), "I", None, {"upbeat": "4"})["text"].split("\n", 1)[1]
    rested = structure.propose(quartet(rest_in="vn1", rest_to_short=True), "I", None, {"upbeat": "4"})
    assert rested["ok"] and rested["text"].split("\n", 1)[1] == plain


def test_a_restated_key_is_no_change_and_asks_nothing():
    d = quartet()
    d["pages"]["1"]["systems"][1]["key"] = 2  # Violin I restates its key on line 2
    r = structure.propose(d, "I", None, {"upbeat": "4", "mode0": "minor"})
    assert r["ok"] and [q["id"] for q in r["questions"]] == ["mode0", "upbeat"]
    assert r["text"].count("\\key") == 1
    d["pages"]["1"]["systems"][1]["key"] = 5  # a real change: its mode defaults to the one before
    r = structure.propose(d, "I", None, {"upbeat": "4", "mode0": "minor"})
    assert r["ok"] and "\\key gis \\minor" in r["text"] and r["want"]["changes"] == [(4, "key", 5)]


def test_four_four_written_as_numbers():
    r = structure.propose(quartet(time="4/4"), "I", None, {"upbeat": "4"})
    assert r["ok"] and "\\numericTimeSignature \\time 4/4" in r["text"]
    r = structure.propose(quartet(time="C"), "I", None, {"upbeat": "4"})
    assert r["ok"] and "\\numericTimeSignature" not in r["text"]


def test_an_upbeat_must_fit_in_a_bar():
    for u in ("0", "2.", "x"):
        r = structure.propose(quartet(time="2/4"), "I", None, {"upbeat": u})
        assert not r["ok"] and any("upbeat" in p for p in r["problems"])
    assert not structure.propose(quartet(time="2/4"), "I", None, {"upbeat": "2"})["ok"]


def test_only_the_template_is_replaced():
    assert structure.is_template(TEMPLATE, "I") and structure.is_template(TEMPLATE, "IV")  # missing
    for body in (r"\time 2/4 \mvtIMusic", r"\time 2/4 R2*40", r"\time 2/4 \skip 2*40", r"\time 2/4 s2*40",
                 r"\time 2/4 \repeat volta 2 { s2*1 } c'2"):
        assert not structure.is_template("\\tag #'mvtI { " + body + " }", "I"), body
    # the labeler proposes nothing from a template's one-bar blocks
    assert structure.expected(TEMPLATE)["I"]["template"]
    assert not structure.expected(r"\tag #'mvtI { \time 2/4 s2*40 }")["I"]["template"]
    # the template's Minuet and Trio, with its "da capo" mark (Op48-4, as new-quartet.sh copies it)
    minuet = r"""\tag #'mvtII { \time 3/4 \tempo "Minuetto" \repeat volta 2 { s2.*1 } \key c \minor \tempo "Trio"
      \repeat volta 2 { s2.*1 }
      \once \override Score.RehearsalMark.break-visibility = #end-of-line-visible
      \once \override Score.RehearsalMark.self-alignment-X = #RIGHT
      \mark \markup { \italic "Minuetto da capo" } }"""
    assert structure.is_template(minuet, "II")


def test_parts_that_differ_are_named_and_nothing_is_offered():
    d = quartet()
    d["pages"]["4"]["systems"][0]["barlines"].insert(2, bl("vcx", 0.35))  # an extra bar in the cello
    r = structure.propose(d, "I", None, {"upbeat": "4"})
    assert not r["ok"] and not r["text"] and any("vc differs from vn1" in p for p in r["problems"])
    d = quartet()
    d["pages"]["2"]["systems"][0]["key"] = 3  # Violin II writes another key
    r = structure.propose(d, "I", None, {"upbeat": "4"})
    assert any("writes key 2" in p and "vn2 3" in p for p in r["problems"])


def test_writing_replaces_the_template_block_only():
    r = structure.propose(quartet(), "I", labels.parse_structure(TEMPLATE)["I"], {"upbeat": "4"})
    new = structure.write_block(TEMPLATE, "I", r["text"])
    assert new.startswith("% header\n% From the reviewed labels") and new.endswith("%%% USEFUL SKELETON IDIOMS\n")
    assert "s2*1" not in new and not structure.check(new, "I", r["want"])
    assert not structure.is_template(new, "I")
    # written again: the labeler's own comment line goes with its block
    again = structure.write_block(new, "I", r["text"])
    assert again == new
    # a movement not in the file goes after the last one
    added = structure.write_block(TEMPLATE, "II", r["text"].replace("mvtI", "mvtII"))
    assert added.index("mvtII") > added.index("mvtI") and labels.parse_structure(added)["II"]["total"] == 8


def test_durations():
    assert [structure.duration(Fraction(*f)) for f in ((1, 2), (3, 4), (1, 1), (3, 8), (5, 8))] == ["2", "2.", "1", "4.", "8*5"]
    assert structure.spacer(Fraction(3, 4), 7) == "s2.*7" and structure.spacer(Fraction(5, 8), 2) == "s8*10"


def mark(id, kind, text, y):
    return {"id": id, "x": 0.12, "y": y, "w": 0.06, "h": 0.015, "kind": kind, "text": text, "note": ""}


def test_a_movement_title_alone_is_a_tempo_with_a_tempo_a_section_label():
    d = quartet()
    d["pages"]["1"]["marks"] = [mark("t1", "title", "Trio", 0.26)]  # above line 2, which begins with its upbeat
    r = structure.propose(d, "I", None, {"upbeat": "4"})
    assert r["ok"] and '  \\tempo "Trio"\n  \\repeat volta 2 { s4 ' in r["text"]
    d["pages"]["1"]["marks"].append(mark("t2", "tempo", 'All. "con brio"', 0.24))
    r = structure.propose(d, "I", None, {"upbeat": "4"})
    assert r["ok"] and '  \\sectionLabel "Trio"\n  \\tempo "All. \\"con brio\\""\n' in r["text"]
    got = labels.parse_structure(r["text"])["I"]
    assert got["titles"] == ["Trio"] and got["tempos"] == ['All. "con brio"']  # escaped quotes read back
    assert got["headings"] == ["Trio", 'All. "con brio"']
    # one heading marked as both (older labels marked titles as tempos): written once
    d["pages"]["1"]["marks"][1] = mark("t2", "tempo", "Trio", 0.24)
    r = structure.propose(d, "I", None, {"upbeat": "4"})
    assert r["ok"] and r["text"].count("Trio") == 1 and "sectionLabel" not in r["text"]
    # a commented-out heading isn't one
    assert labels.parse_structure('\\tag #\'mvtI { \\time 2/4 % \\tempo "No"\n s2*4 }')["I"]["tempos"] == []
