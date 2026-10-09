"""Run with: uv run --with pytest --with numpy --with pillow --with scikit-learn pytest tests"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import labels  # noqa: E402
import server  # noqa: E402


def bl(id, x, **kw):
    return {"id": id, "x0": x, "x1": x, "kind": "single", "auto": False, "bar_count": 1,
            "ends_movement": False, **kw}


def system(id, top, barlines, **kw):
    return {"id": id, "top": top, "bottom": top + 0.03, "left": 0.05, "right": 0.95,
            "start": 0.1, "auto": False, "barlines": barlines, **kw}


def page(part, systems, status="reviewed", kind="music"):
    return {"status": status, "kind": kind, "part": part, "clef": "alto", "notes": "",
            "systems": systems, "marks": []}


def doc(pages):
    return {"schema": labels.SCHEMA, "source": {"pdf": "sources/x.pdf"}, "pages": pages}


def test_numbering_runs_across_pages_and_restarts_at_movement():
    d = doc({
        "1": page(None, [], kind="title"),
        "2": page("va", [
            system("p2s2", 0.5, [bl("c", 0.3), bl("d", 0.6, ends_movement=True)]),
            system("p2s1", 0.1, [bl("a", 0.6), bl("b", 0.3)]),  # out of order on purpose
        ]),
        "3": page("va", [system("p3s1", 0.1, [bl("e", 0.4, bar_count=2), bl("f", 0.8)])]),
    })
    got = [(n["right"]["id"], n["movement"], n["bar"], n["count"]) for n in labels.number_bars(d)]
    assert got == [("b", "I", 1, 1), ("a", "I", 2, 1), ("c", "I", 3, 1), ("d", "I", 4, 1),
                   ("e", "II", 1, 2), ("f", "II", 3, 1)]


def test_parts_number_independently_and_cue_staves_dont_count():
    d = doc({
        "1": page("va", [system("p1s1", 0.1, [bl("a", 0.5)])]),
        "2": page("vc", [system("p2s1", 0.1, [bl("x", 0.5)], role="cue"),
                         system("p2s2", 0.3, [bl("b", 0.5)])]),
        "3": page("va", [system("p3s1", 0.1, [bl("c", 0.5)])]),
    })
    got = [(n["part"], n["bar"]) for n in labels.number_bars(d)]
    assert got == [("va", 1), ("vc", 1), ("va", 2)]


def test_pickup_is_bar_zero_and_does_not_advance():
    d = doc({"1": page("va", [system("s", 0.1, [bl("p", 0.2, bar_count=0), bl("a", 0.5)])])})
    assert [(n["bar"], n["count"]) for n in labels.number_bars(d)] == [(0, 0), (1, 1)]


def test_quad_follows_slant_and_has_margin():
    s = {"top": 0.2, "bottom": 0.24, "left": 0.05, "right": 0.95, "start": 0.1}
    left = {"x0": 0.30, "x1": 0.28}
    right = {"x0": 0.40, "x1": 0.38}
    q = labels.bar_quad(s, left, right)
    space = 0.01
    assert q[0][1] == pytest.approx(0.2 - 2.5 * space)
    assert q[2][1] == pytest.approx(0.24 + 2.5 * space)
    # above the staff the line continues its lean: x grows going up
    assert q[0][0] == pytest.approx(0.30 + 0.02 * 2.5 * space / 0.04)
    assert q[2][0] == pytest.approx(0.38 - 0.02 * 2.5 * space / 0.04)
    first = labels.bar_quad(s, None, right)
    assert first[0][0] == first[3][0] == 0.1


def test_quad_follows_bend_and_crop_margins():
    s = {"top": 0.2, "bottom": 0.24, "left": 0.0, "right": 1.0, "start": 0.1,
         "bend": [0.0, 0.0, 0.0, 0.0, -0.04], "above": 4, "below": 1}
    assert labels.bend_at(s, 0.5) == 0
    assert labels.bend_at(s, 0.875) == pytest.approx(-0.02)
    assert labels.bend_at(s, 2.0) == pytest.approx(-0.04)  # flat beyond the end
    q = labels.bar_quad(s, {"x0": 0.5, "x1": 0.5}, {"x0": 1.0, "x1": 1.0})
    # left side flat, right side lifted by 0.04; 4 spaces above, 1 below
    assert q[0][1] == pytest.approx(0.2 - 0.04)
    assert q[3][1] == pytest.approx(0.24 + 0.01)
    assert q[1][1] == pytest.approx(0.2 - 0.04 - 0.04)
    assert q[2][1] == pytest.approx(0.24 + 0.01 - 0.04)


def test_export_complete_needs_review_end_and_no_unlabeled_pages():
    sys1 = system("p2s1", 0.1, [bl("a", 0.5), bl("b", 0.8, ends_movement=True)])
    d = doc({"2": page("va", [sys1])})
    assert labels.bars_export(d)["complete"] == {"va": []}  # page 1 unlabeled
    d["pages"]["1"] = page(None, [], kind="title")
    assert labels.bars_export(d)["complete"] == {"va": ["I"]}
    d["pages"]["2"]["status"] = "edited"
    assert labels.bars_export(d)["complete"] == {"va": []}


def test_export_attaches_marks_inside_the_bar():
    p = page("va", [system("p1s1", 0.1, [bl("a", 0.5), bl("b", 0.8)])])
    p["marks"] = [{"id": "p1m1", "x": 0.6, "y": 0.11, "w": 0.02, "h": 0.01, "kind": "text"}]
    bars = labels.bars_export(doc({"1": p}))["bars"]
    assert [b["marks"] for b in bars] == [[], ["p1m1"]]


def test_per_bar_crop_overrides_the_staff():
    s = {"top": 0.2, "bottom": 0.24, "left": 0.0, "right": 1.0, "above": 4}
    q = labels.bar_quad(s, None, {"x0": 0.5, "x1": 0.5, "above": 1, "below": 0})
    assert q[0][1] == pytest.approx(0.2 - 0.01)
    assert q[3][1] == pytest.approx(0.24)


def test_tempo_mark_above_the_music_goes_to_first_bar_below():
    p = page("va", [system("p1s1", 0.2, [bl("a", 0.5), bl("b", 0.8)])])
    p["marks"] = [{"id": "t", "x": 0.6, "y": 0.02, "w": 0.1, "h": 0.02, "kind": "tempo", "text": "Andante"}]
    p["corners"] = {"points": [[0, 0], [1, 0], [1, 1], [0, 1]], "auto": True}
    out = labels.bars_export(doc({"1": p}))
    assert [b["marks"] for b in out["bars"]] == [["t"], []]
    assert out["pages"] == {"1": {"corners": [[0, 0], [1, 0], [1, 1], [0, 1]]}}


def test_mark_left_of_a_lines_music_goes_to_its_first_bar():
    # "Trio" written before the clef of the second line, not the line below
    p = page("va", [system("p1s1", 0.2, [bl("a", 0.5), bl("b", 0.8)]),
                    system("p1s2", 0.3, [bl("c", 0.5), bl("d", 0.8)]),
                    system("p1s3", 0.4, [bl("e", 0.5), bl("f", 0.8)])])
    p["marks"] = [{"id": "trio", "x": 0.01, "y": 0.305, "w": 0.06, "h": 0.03, "kind": "tempo", "text": "Trio"}]
    bars = labels.bars_export(doc({"1": p}))["bars"]
    assert [b["marks"] for b in bars] == [[], [], ["trio"], [], [], []]



def test_mark_left_of_music_where_crops_overlap_goes_to_the_nearer_line():
    # staves 0.05 apart: crops (2.5 spaces each way) overlap
    p = page("va", [system("p1s1", 0.2, [bl("a", 0.5)]), system("p1s2", 0.25, [bl("b", 0.5)])])
    p["marks"] = [{"id": "trio", "x": 0.01, "y": 0.245, "w": 0.06, "h": 0.01, "kind": "tempo", "text": "Trio"}]
    bars = labels.bars_export(doc({"1": p}))["bars"]
    assert [b["marks"] for b in bars] == [[], ["trio"]]


def test_text_below_the_last_line_goes_to_the_nearest_bar():
    p = page("va", [system("p1s1", 0.2, [bl("a", 0.5), bl("b", 0.8)])])
    p["marks"] = [{"id": "dc", "x": 0.7, "y": 0.35, "w": 0.2, "h": 0.03, "kind": "text", "text": "Da capo"}]
    bars = labels.bars_export(doc({"1": p}))["bars"]
    assert [b["marks"] for b in bars] == [[], ["dc"]]


def test_validate_catches_bad_data():
    good = doc({"1": page("va", [system("s1", 0.1, [bl("a", 0.5)])])})
    assert labels.validate(good) == []
    bad = json.loads(json.dumps(good))
    bad["pages"]["1"]["systems"][0]["barlines"].append(bl("a", 0.6))
    bad["pages"]["1"]["status"] = "done"
    errs = labels.validate(bad)
    assert any("duplicate id a" in e for e in errs)
    assert any("bad status" in e for e in errs)


def test_migrate_refuses_newer_schema():
    with pytest.raises(labels.NewerSchema):
        labels.migrate({"schema": labels.SCHEMA + 1})
    with pytest.raises(labels.SchemaError):
        labels.migrate({})


def test_migrate_keeps_a_schema_1_file_as_it_was():
    old = {"schema": 1, "source": {"pdf": "sources/x.pdf"},
           "pages": {"1": page("va", [system("s", 0.1, [bl("a", 0.5)])])}}
    new = labels.migrate(json.loads(json.dumps(old)))
    assert new["schema"] == labels.SCHEMA == 4
    assert {k: v for k, v in new.items() if k != "schema"} == {k: v for k, v in old.items() if k != "schema"}
    assert labels.validate(new) == []


def clef_mark(id, x, y, clef, w=0.02, h=0.03, kind="signature"):
    return {"id": id, "x": x - w / 2, "y": y - h / 2, "w": w, "h": h, "kind": kind, "clef": clef,
            "text": "", "note": ""}


def test_validate_signatures_on_marks_and_staves():
    d = doc({"1": page("vc", [system("s", 0.1, [bl("a", 0.5)], clef="bass", key=-1, time="3/4")])})
    d["pages"]["1"]["marks"] = [clef_mark("m1", 0.3, 0.115, "tenor"),
                                {**clef_mark("m2", 0.6, 0.115, "bass"), "key": 2, "time": "C"}]
    assert labels.validate(d) == []
    d["pages"]["1"]["marks"][0]["clef"] = "soprano"
    d["pages"]["1"]["marks"][1]["key"] = 9
    del d["pages"]["1"]["marks"][1]["clef"]
    d["pages"]["1"]["systems"][0]["time"] = "3:4"
    errs = labels.validate(d)
    assert any("bad clef 'soprano'" in e for e in errs) and any("bad key 9" in e for e in errs)
    assert any("bad time '3:4'" in e for e in errs)
    d["pages"]["1"]["marks"][1] = {k: v for k, v in d["pages"]["1"]["marks"][1].items() if k not in ("key", "time")}
    assert any("needs a clef, key or time" in e for e in labels.validate(d))


def test_migrate_2_renames_clef_marks_and_keeps_every_box():
    p = page("vc", [system("l1", 0.1, [bl("a", 0.5)]), system("l2", 0.3, [bl("b", 0.5)])])
    p["marks"] = [clef_mark("m1", 0.07, 0.115, "tenor", kind="clef"),   # at l1's start
                  clef_mark("m2", 0.4, 0.315, "bass", kind="clef")]     # mid-line on l2
    old = {"schema": 2, "source": {"pdf": "sources/x.pdf"}, "pages": {"1": p}}
    before = labels.bars_export(json.loads(json.dumps(old)))  # the old kind, read as schema 2 was
    new = labels.migrate(json.loads(json.dumps(old)))
    q = new["pages"]["1"]
    assert [(m["id"], m["kind"], m["x"]) for m in q["marks"]] == [(m["id"], "signature", m["x"]) for m in p["marks"]]
    assert all("clef" not in s for s in q["systems"])
    assert labels.validate(new) == []
    assert [b["clefs"] for b in labels.bars_export(new)["bars"]] == [["tenor"], ["tenor", "bass"]]
    assert [b["marks"] for b in labels.bars_export(new)["bars"]] == [b["marks"] for b in before["bars"]]


def test_clefs_follow_the_page_clef_and_clef_marks_in_reading_order():
    # three cello lines; tenor from mid-line 1 (inside its 2nd bar), back to
    # bass at the start of line 3; a clef on the cue staff changes nothing
    p = page("vc", [
        system("l1", 0.1, [bl("a", 0.3), bl("b", 0.6), bl("c", 0.9)]),
        system("cue", 0.2, [bl("q", 0.5)], role="cue"),
        system("l2", 0.3, [bl("d", 0.5), bl("e", 0.9)]),
        system("l3", 0.5, [bl("f", 0.5), bl("g", 0.9)]),
    ])
    p["clef"] = "bass"
    p["marks"] = [clef_mark("m1", 0.45, 0.115, "tenor"),   # inside l1's 2nd bar
                  clef_mark("m2", 0.07, 0.215, "treble"),  # on the cue staff
                  clef_mark("m3", 0.07, 0.515, "bass")]    # l3's own clef, before its music start
    bars = labels.bars_export(doc({"1": p}))["bars"]
    assert [(b["barline"], b["clefs"]) for b in bars] == [
        ("a", ["bass"]), ("b", ["bass", "tenor"]), ("c", ["tenor"]),
        ("d", ["tenor"]), ("e", ["tenor"]),
        ("f", ["bass"]), ("g", ["bass"])]


def test_a_clef_at_the_start_of_a_bar_governs_the_whole_bar():
    # bass returns right after bar line b (0.6): the next bar is all bass,
    # the one before all tenor; a clef in the middle of a bar still splits it
    p = page("vc", [system("l1", 0.1, [bl("a", 0.3), bl("b", 0.6), bl("c", 0.9)])])
    p["clef"] = "tenor"
    p["marks"] = [clef_mark("m1", 0.62, 0.115, "bass", w=0.03)]  # box from 0.605
    bars = labels.bars_export(doc({"1": p}))["bars"]
    assert [b["clefs"] for b in bars] == [["tenor"], ["tenor"], ["bass"]]
    p["marks"] = [clef_mark("m1", 0.75, 0.115, "bass", w=0.03)]
    bars = labels.bars_export(doc({"1": p}))["bars"]
    assert [b["clefs"] for b in bars] == [["tenor"], ["tenor"], ["tenor", "bass"]]


def test_on_a_score_page_a_clef_change_holds_only_on_its_staff():
    p = page("score", [system("vc", 0.1, [bl("a", 0.5)]), system("vn1", 0.3, [bl("b", 0.5)])])
    p["clef"] = "treble"
    p["marks"] = [clef_mark("m1", 0.3, 0.115, "tenor")]
    bars = labels.bars_export(doc({"1": p}))["bars"]
    assert [b["clefs"] for b in bars] == [["treble", "tenor"], ["treble"]]


def test_bar_export_keeps_its_own_schema():
    # the edition's build refuses any bar export but schema 1; clefs are additive
    assert labels.bars_export(doc({}))["schema"] == labels.EXPORT_SCHEMA == 1


STRUCTURE = r"""
\tag #'mvtI {
  \time 2/4
  \repeat volta 2 { s2*48 }       % first half: 48 bars
  \repeat volta 2 { s2*82 }
  \bar "|."
}
\tag #'mvtII {
  \tempo "Minuetto con moto"
  \repeat volta 2 { s2.*8  }
  \repeat volta 2 { s2.*28 }
  \key f \minor
  \tempo "Trio"
  \repeat volta 2 { s2.*16 }
  \repeat volta 2 { s2.*20 }
  \mark \markup { \italic "Minuetto da capo" }
}
\tag #'mvtIII {
  \repeat volta 2 { \partial 8 s8 s2*12 \alternative { { s2 } { s2 } } }
  s2*10
}
"""


def test_parse_structure():
    got = labels.parse_structure(STRUCTURE)
    assert got["I"]["total"] == 130
    assert [s["bars"] for s in got["I"]["segments"]] == [48, 82]
    assert got["II"]["total"] == 72
    assert {k: got["III"][k] for k in ("total", "pickup", "tempos", "segments", "changes")} == {
        "total": 24, "pickup": True, "tempos": [], "changes": [],
        "segments": [{"bars": 14, "repeat": True, "split": False, "heading": False},
                     {"bars": 10, "repeat": False, "split": False, "heading": False}]}
    assert got["II"]["tempos"] == ["Minuetto con moto", "Trio"]


README = """
| Quartet | File | Source | RISM | Online |
|---|---|---|---|---|
| Op. 48/1, G 226 | `G226/D-B_KHM-602.pdf` | Berlin, KHM 602. Copy. | [1001015844](https://rism.online/sources/1001015844) | [SBB](http://example/sbb) |
| Op. 48/3, G 228 | `G228/F-Pn_Vma-ms-1067-1.pdf` | Paris. | [840022755](https://rism.online/sources/840022755) | not online |
| | `G228/F-Po_RES-507-14.pdf` | Paris, [Gallica](x) record. | [840013721](https://rism.online/sources/840013721) | [Gallica](https://gallica/x) |
"""


def test_parse_structure_reads_key_and_time_as_written():
    text = r"""\tag #'mvtII {
      \time 3/4 \key b \minor
      \repeat volta 2 { \partial 4 s4 s2.*7 s2 }
      \key b \major
      \repeat volta 2 { s4 s2.*7 s2 }
    }
    \tag #'mvtI { \time 4/4 \key es \major s1*4 \time 2/2 s1*2 }"""
    got = labels.parse_structure(text)
    assert (got["II"]["key"], got["II"]["mode"], got["II"]["time"]) == (2, "minor", "3/4")
    assert got["II"]["changes"] == [{"bar": 8, "on_bar_line": False, "key": 5, "mode": "major"}]  # the Trio, from its upbeat completing bar 8
    assert (got["I"]["key"], got["I"]["time"]) == (-3, "C")        # 4/4 is printed as C
    assert got["I"]["changes"] == [{"bar": 5, "on_bar_line": True, "time": "C/"}]
    assert labels.key_fifths("fis", "minor") == 3 and labels.key_fifths("aes", "major") == -4
    assert labels.key_fifths("eses", "major") == 4 - 14  # E double flat
    assert labels.key_fifths("asas", "major") == 3 - 14 and labels.key_fifths("fisis", "major") == 6 + 7
    # \numericTimeSignature applies from where it is written
    two = labels.parse_structure(r"""\tag #'mvtI { \time 4/4 s1 } \tag #'mvtII { \numericTimeSignature \time 4/4 s1 }""")
    assert (two["I"]["time"], two["II"]["time"]) == ("C", "4/4")
    # changes inside a written-out repeat, every time round
    un = labels.parse_structure(r"""\tag #'mvtI { \time 2/4 \repeat unfold 2 { s2*2 \time 3/4 s2. \time 2/4 } }""")["I"]
    assert [(c["bar"], c["time"]) for c in un["changes"]] == [(3, "3/4"), (4, "2/4"), (6, "3/4"), (7, "2/4")]


def test_parse_structure_counts_a_short_last_bar():
    # Op. 48/3's Trio: its second half ends on a two-beat bar written \partial 2
    text = r"""\tag #'mvtII {
      \time 3/4
      \repeat volta 2 { \partial 4 s4 s2.*7 s2 }
      \repeat volta 2 { s4 s2.*27 s2 }
      \repeat volta 2 { s4 s2.*7 s2 }
      \repeat volta 2 { s4 s2.*23 \partial 2 s2 }
    }"""
    got = labels.parse_structure(text)["II"]
    assert got["pickup"] and got["total"] == 68
    assert [s["bars"] for s in got["segments"]] == [8, 28, 8, 24]
    # only a \partial at the very start is a pickup
    assert not labels.parse_structure(r"\tag #'mvtI { \time 3/4 s2.*23 \partial 2 s2 }")["I"]["pickup"]


def test_parse_structure_counts_by_duration_with_upbeats():
    """A minuet whose halves start with an upbeat and end with a short bar:
    LilyPond numbers the short bar and the next upbeat as one bar."""
    text = r"""
\tag #'mvtII {
  \time 3/4 \key d \major
  \tempo "Tempo di Minuetto"
  \repeat volta 2 { \partial 4 s4 s2.*7 s2 }
  \repeat volta 2 { s4 s2.*19 s2 }
  \key g \major
  \tempo "Trio"
  \repeat volta 2 { s4 s2.*7 s2 }
  \repeat volta 2 { s4 s2.*23 s2 }
}
\tag #'mvtI {
  \time 2/4
  s2*88
  \bar "|."
}
"""
    got = labels.parse_structure(text)
    assert [s["bars"] for s in got["II"]["segments"]] == [8, 20, 8, 24]
    assert got["II"]["total"] == 60 and got["II"]["pickup"]
    assert got["II"]["tempos"] == ["Tempo di Minuetto", "Trio"]
    # each half ends on a short bar, completed by the next half's upbeat;
    # the Trio's \tempo begins a section (its first repeat sign stands alone)
    assert [(s["split"], s["heading"]) for s in got["II"]["segments"]] == [
        (True, False), (True, False), (True, True), (True, False)]
    assert got["I"] == {"total": 88, "pickup": False, "tempos": [], "titles": [], "headings": [], "time": "2/4", "changes": [],
                        "segments": [{"bars": 88, "repeat": False, "split": False, "heading": False}]}


@pytest.mark.parametrize("body, want, pickup", [
    (r"\time 3/4 \repeat volta 2 { s2.*4 } \time 2/4 \repeat volta 2 { s2*6 }", [4, 6], False),  # meter change
    (r"\time 2/4 \repeat volta 2 { s2*11 \alternative { { s2 } { s2 } } } s2*4", [13, 4], False),
    (r"\time 2/4 %{ s2*99 %} s2*8", [8], False),                                  # block comment
    (r'\time 2/4 \mark \markup { "segue s" } s2*8', [8], False),                   # s-words in text
    (r"\time 2/4 \repeat unfold 2 { s2*4 }", [8], False),                          # written out twice
    # \partial after the start: the current bar's remaining length (LilyPond)
    (r"\time 3/4 \repeat volta 2 { s4 s2.*23 \partial 2 s2 }", [24], False),     # a short last bar counts
    (r"\time 3/4 s2.*2 \partial 2 s2 \partial 2 s2 \partial 2 s2", [5], False),  # three short bars
    (r"\time 3/4 \repeat volta 2 { s2.*2 \partial 2 s2 s2.*3 s4 } \repeat volta 2 { s2 s2.*2 }", [7, 2], False),
    (r"\time 3/4 \repeat volta 2 { s2.*4 } \repeat volta 2 { \partial 4 s4 s2.*3 s2 }", [4, 5], False),  # a later upbeat is a bar
    (r"\time 2/4 \partial 4 s8 s8 s2*4", [4], True),                             # a pickup in two spacers
    (r"\time 2/4 \partial 2 s4 s4 s2*8", [8], True),                             # a full-bar pickup
    (r"\time 3/4 \partial 4 * 3 s2. s2.*4", [4], True),                          # spaces in the duration
    (r'\time 3/4 \mark \markup { "da capo s" } \partial 4 s4 s2.*4', [4], True),  # text before the pickup
    (r"\time 3/4 \mark \markup { \italic Segue s } s2.*4", [4], False),           # an unquoted word
    (r"\time 3/4 \partial 4 s4 \partial 2 s2 s2.*4", [5], True),                 # a short bar right after the pickup
    (r"\time 3/4 s2. s s s", [4], False),                                          # a bare s repeats the last duration
    (r"\time 6/8 s2.*2 s4 s8 s8 \time 2/4 s2*2", [5], False),                      # meter change after a filled bar
    (r"\time 3/4 s2.*2 s2 \partial 2 s2 s2.*2", [5], False),                       # a \partial can lengthen a bar
    # checked against LilyPond 2.24
    (r"\time 4/4 s1 \repeat unfold 4 { s s8 }", [6], False),          # a bare s replayed with its own duration
    (r"\time 3/4 s2.*2 s", [4], False),                                 # a bare s keeps the multiplier
    (r"\partial 4 \time 3/4 s4 s2.*4", [4], True),                     # \partial before \time
    ('\\time 3/4 \\mark "50% slower" s2.*4\n\\tempo "Allegro" s2.*4', [8], False),  # % inside a string
    (r"\time 3/4 \mark \markup \bold { Fine s } s2.*4", [4], False),  # \markup with a command
    (r"s1*8 \partial 2 s2 s1*4", [13], False),                          # no \time: a later \partial isn't a pickup
    (r"\time 3/4 s2. * 4", [4], False),                                 # spaces in a spacer's multiplier
    (r"s1*4 \repeat volta 2 { \time 3/4 s2.*8 }", [4, 8], False),      # music before the first \time
])
def test_parse_structure_edge_cases(body, want, pickup):
    got = labels.parse_structure("\\tag #'mvtI { " + body + " }")["I"]
    assert [s["bars"] for s in got["segments"]] == want
    assert got["pickup"] == pickup  # only a \partial before any music


def test_parse_sources_readme_and_source_info(tmp_path):
    rows = labels.parse_sources_readme(README)
    r = rows["sources/G228/F-Po_RES-507-14.pdf"]
    assert r["work"] == "Op. 48/3, G 228"  # carried down from the row above
    assert r["rism"] == "840013721" and r["online"] == "https://gallica/x"
    assert r["description"] == "Paris, Gallica record."
    info = labels.source_info("sources/G226/D-B_KHM-602.pdf", rows)
    assert info["source"] == {"pdf": "sources/G226/D-B_KHM-602.pdf", "siglum": "D-B",
                              "shelfmark": "KHM 602", "rism": "1001015844", "gerard": 226}
    (tmp_path / "Op48-1").mkdir()
    (tmp_path / "Op48-1" / "Structure.ily").write_text("")
    assert labels.structure_path(tmp_path, info["display"]["work"]) == tmp_path / "Op48-1" / "Structure.ily"
    assert labels.structure_path(tmp_path, "Op. 48/3") is None


# ------------------------------------------------------------------ server save rules


@pytest.fixture
def edition(tmp_path):
    root = tmp_path / "ed"
    (root / "sources" / "G1").mkdir(parents=True)
    (root / "sources" / "G1" / "X_Y.pdf").write_bytes(b"%PDF-1.4 not really")
    return server.Edition(root, tmp_path / "cache")


def test_save_is_guarded_by_etag_and_backed_up(edition):
    rel = "sources/G1/X_Y.pdf"
    d = doc({"1": page("va", [system("s1", 0.1, [bl("a", 0.123456789)])])})
    e1 = edition.save(rel, d, "none")["etag"]
    lp = edition.root / "sources" / "G1" / "X_Y.labels.json"
    saved = json.loads(lp.read_text())
    assert saved["pages"]["1"]["systems"][0]["barlines"][0]["x0"] == 0.1235
    assert (edition.root / "sources" / "G1" / "X_Y.bars.json").exists()

    with pytest.raises(FileExistsError):
        edition.save(rel, d, "none")  # stale: the file exists now
    edition.save(rel, d, e1)
    backups = list((edition.cache / "backups").rglob("*.json"))
    assert len(backups) == 1 and json.loads(backups[0].read_text()) == saved


def test_save_brings_a_schema_1_document_up_to_date(edition):
    # a tab loaded before the upgrade still sends schema 1: its edits are kept
    rel = "sources/G1/X_Y.pdf"
    d = doc({"1": page("va", [system("s", 0.1, [bl("a", 0.5)])])})
    d["schema"] = 1
    edition.save(rel, d, "none")
    lp = edition.root / "sources" / "G1" / "X_Y.labels.json"
    assert json.loads(lp.read_text())["schema"] == labels.SCHEMA


def test_save_refuses_invalid_and_newer_files(edition):
    rel = "sources/G1/X_Y.pdf"
    with pytest.raises(ValueError):
        edition.save(rel, {"schema": labels.SCHEMA, "source": {}, "pages": {"1": {"status": "??"}}}, "none")
    lp = edition.root / "sources" / "G1" / "X_Y.labels.json"
    lp.write_text(json.dumps({"schema": 99, "pages": {}}))
    raw = lp.read_bytes()
    import hashlib
    with pytest.raises(labels.NewerSchema):
        edition.save(rel, doc({}), hashlib.sha1(raw).hexdigest())
    assert lp.read_bytes() == raw


def test_pdf_paths_cannot_escape_the_edition(edition, tmp_path):
    (tmp_path / "outside.pdf").write_bytes(b"x")
    with pytest.raises(LookupError):
        edition.pdf("../outside.pdf")
    with pytest.raises(LookupError):
        edition.pdf("sources/G1/X_Y.labels.json")


def test_snap_fits_a_slanted_bar_line_and_ignores_far_ones():
    """detect.snap_barline on a drawn staff: a slanted bar line placed
    upright a little off is fitted to the stroke; nothing near, no change."""
    import numpy as np
    from PIL import Image, ImageDraw

    import detect

    img = Image.new("L", (400, 200), 230)
    d = ImageDraw.Draw(img)
    top, gap = 60, 16
    for i in range(5):
        d.line([(0, top + i * gap), (400, top + i * gap)], fill=140, width=2)
    bottom = top + 4 * gap
    d.line([(206, top), (194, bottom)], fill=30, width=4)  # leans 12 px over the staff
    g = np.asarray(img, dtype=np.float32)

    r = detect.snap_barline(g, top, bottom, 205, 205)
    assert r is not None
    assert abs(r["x0"] - 206) <= 2 and abs(r["x1"] - 194) <= 2  # within the 4 px stroke
    assert detect.snap_barline(g, top, bottom, 300, 300) is None  # nothing within a space
