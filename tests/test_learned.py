"""The learned bar-line filter (learn.py), trained on one quartet and tested
on the other: KHM 602's reviewed pages train it, KHM 603's frozen fixture
pages test it. Skipped when the edition repo isn't here.

2026-10-05, on all of KHM 603's reviewed pages: hand-tuned rules 73 missed,
12 false; learned 23 missed, 24 false."""

import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import detect  # noqa: E402
import labels  # noqa: E402
import learn  # noqa: E402
from score_barlines import render, score_page, truth_systems  # noqa: E402

EDITION = Path.home() / "Dropbox/Code/boccherini-opus-48"
PDF603 = EDITION / "sources/G227/D-B_KHM-603.pdf"

pytestmark = pytest.mark.skipif(
    not PDF603.exists() or not labels.labels_path(EDITION / "sources/G226/D-B_KHM-602.pdf").exists()
    or not shutil.which("pdftoppm"), reason="edition repo not available")


def test_learned_filter_beats_the_hand_tuned_rules_on_another_quartet(tmp_path):
    pytest.importorskip("sklearn")
    pages = [p for p in learn.reviewed_pages(EDITION) if p[0].name == "D-B_KHM-602.pdf"]
    model = learn.train(pages, lambda pdf, n: render(pdf, n, tmp_path))
    truth = json.loads((Path(__file__).parent / "fixtures" / "khm603_barlines.json").read_text())
    edits = {}
    for name, m in (("rules", None), ("learned", model)):
        found = false = missed = 0
        for n, page in truth["pages"].items():
            f, fp, mi = score_page(truth_systems(page), detect.detect_page(render(PDF603, int(n), tmp_path), model=m))
            found, false, missed = found + f, false + fp, missed + mi
        edits[name] = (found, false, missed)
    rules, learned = edits["rules"], edits["learned"]
    assert learned[1] + learned[2] < rules[1] + rules[2], f"learned {learned} vs rules {rules}"
    assert learned[0] / (learned[0] + learned[2]) >= 0.9, f"learned {learned}"
