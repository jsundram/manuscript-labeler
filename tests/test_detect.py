"""Detection on the reviewed test sources, D-B KHM 602 and 603 (skipped if
they aren't here). Set KHM602 / KHM603 to their paths if your edition repo
lives elsewhere.

The fixtures freeze the editor's corrections (tests/fixtures). Bar counts
from this tool are meant to feed Structure.ily one day, so a regression in
either direction matters. Re-freeze a fixture and its limits together,
after re-tuning on more pages (tools/tune_barlines.py)."""

import json
import os
import shutil
import statistics
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import detect  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from score_barlines import render, score_page, truth_systems  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
EDITION = Path.home() / "Dropbox/Code/boccherini-opus-48/sources"
PDF = Path(os.environ.get("KHM602", EDITION / "G226/D-B_KHM-602.pdf"))
PDF603 = Path(os.environ.get("KHM603", EDITION / "G227/D-B_KHM-603.pdf"))
pytestmark = pytest.mark.skipif(not shutil.which("pdftoppm"), reason="pdftoppm not available")


def needs(pdf: Path):
    return pytest.mark.skipif(not pdf.exists(), reason=f"{pdf.name} not available")


@needs(PDF)
def test_title_page_has_no_bar_lines(tmp_path):
    systems = detect.detect_page(render(PDF, 1, tmp_path))
    assert sum(len(s["barlines"]) for s in systems) == 0


@needs(PDF)
def test_first_viola_page_finds_all_ten_staves(tmp_path):
    systems = detect.detect_page(render(PDF, 2, tmp_path))
    assert len(systems) == 10
    for s in systems:
        # music starts after the clef, right of the staff's left edge
        assert 0.10 < s["left"] < s["start"] < 0.22
        assert s["right"] > 0.9
    # 10 lines, ~74 bars; detection is a proposal, so only a loose check
    assert 60 <= sum(len(s["barlines"]) for s in systems) <= 95


# (pdf, fixture, at least this share found, at most this many false).
# 2026-10-02: KHM 602 pp. 2, 3, 6: 179 of 194 found, 3 false (the second
# copyist, staggered key signatures); KHM 603, one or two pages per part:
# 190 of 213, 6 false.
BAR_LINES = [
    pytest.param(PDF, "khm602_barlines.json", 0.90, 5, marks=needs(PDF), id="KHM602"),
    pytest.param(PDF603, "khm603_barlines.json", 0.85, 8, marks=needs(PDF603), id="KHM603"),
]


@pytest.mark.parametrize("pdf, fixture, min_found, max_false", BAR_LINES)
def test_bar_lines_match_the_editors(tmp_path, pdf, fixture, min_found, max_false):
    truth = json.loads((FIXTURES / fixture).read_text())
    found = false = missed = 0
    for n, page in truth["pages"].items():
        f, fp, m = score_page(truth_systems(page), detect.detect_page(render(pdf, int(n), tmp_path)))
        found, false, missed = found + f, false + fp, missed + m
    assert found / (found + missed) >= min_found, f"found {found} of {found + missed}"
    assert false <= max_false, f"{false} false bar lines"


# (pdf, fixture, left edge within a space on at least this share, crops off
# by at most this many spaces on average). 2026-10-02: KHM 602 80%, ~0.5
# (a fixed 2.5 was off by 1.2-1.3); KHM 603 37 of 40, 0.36.
STAVES = [
    pytest.param(PDF, "khm602_staves.json", 0.75, 0.8, marks=needs(PDF), id="KHM602"),
    pytest.param(PDF603, "khm603_staves.json", 0.85, 0.6, marks=needs(PDF603), id="KHM603"),
]


@pytest.mark.parametrize("pdf, fixture, min_left, max_crop", STAVES)
def test_staff_edges_and_crops_match_the_editors(tmp_path, pdf, fixture, min_left, max_crop):
    truth = json.loads((FIXTURES / fixture).read_text())
    left_ok, crop_err, n_left = 0, [], 0
    for n, page in truth["pages"].items():
        img = render(pdf, int(n), tmp_path)
        w, h = img.size
        det = detect.detect_page(img)
        for s in page["staves"]:
            d = min(det, key=lambda q: abs(q["top"] - s["top"]))
            space = (s["bottom"] - s["top"]) / 4 * h
            n_left += 1
            left_ok += abs(s["left"] - d["left"]) * w <= space
            crop_err += [abs(s[k] - d[k]) for k in ("above", "below") if k in s]
    assert left_ok / n_left >= min_left, f"left edge within a space on {left_ok} of {n_left} staves"
    assert sum(crop_err) / len(crop_err) <= max_crop, f"crops off by {sum(crop_err) / len(crop_err):.2f} spaces"


@needs(PDF603)
def test_music_start_from_the_previous_pages_room(tmp_path):
    """KHM 603's staggered key signatures defeat reading the start from the
    ink; the room the editor set on their previous page of the part (here
    violin I p. 9, for p. 10) puts it right. Lines after the first, which
    also carries the time signature."""
    truth = json.loads((FIXTURES / "khm603_staves.json").read_text())
    prev, page = truth["pages"]["9"]["staves"], truth["pages"]["10"]["staves"]
    img9 = render(PDF603, 9, tmp_path)
    w, h = img9.size
    room = statistics.median(((s["start"] - s["left"]) * w) / ((s["bottom"] - s["top"]) / 4 * h)
                             for s in prev[1:])
    img = render(PDF603, 10, tmp_path)
    w, h = img.size

    def misses(det):
        out = []
        for s in page[1:]:
            d = min(det, key=lambda q: abs(q["top"] - s["top"]))
            out.append(abs(d["start"] - s["start"]) * w / ((s["bottom"] - s["top"]) / 4 * h))
        return out

    # 2026-10-02: misses (spaces) 3.5, 2.0, 6.3, 6.7 without; 1.7, 2.0, 2.7, 0.0 with
    without, with_room = misses(detect.detect_page(img)), misses(detect.detect_page(img, room))
    assert sum(with_room) <= sum(without) * 2 / 3, f"with room {with_room}, without {without}"
    assert statistics.median(with_room) <= 2, f"with room {with_room}"
