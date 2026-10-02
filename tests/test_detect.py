"""Detection on the first test source, D-B KHM 602 (skipped if it isn't here).

Set KHM602 to its path if your edition repo lives elsewhere."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))
import detect  # noqa: E402
from server import JPEG_QUALITY, RENDER_PX  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from score_barlines import score_page, truth_systems  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "khm602_barlines.json"

PDF = Path(os.environ.get("KHM602", Path.home() / "Dropbox/Code/boccherini-opus-48/sources/G226/D-B_KHM-602.pdf"))
pytestmark = pytest.mark.skipif(not PDF.exists() or not shutil.which("pdftoppm"), reason="test PDF not available")


def render(page: int, tmp: Path) -> Image.Image:
    base = tmp / f"p{page}"
    subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page), "-scale-to", str(RENDER_PX),
                    "-jpeg", "-jpegopt", f"quality={JPEG_QUALITY}", "-singlefile", str(PDF), str(base)], check=True)
    return Image.open(base.with_suffix(".jpg"))


def test_title_page_has_no_bar_lines(tmp_path):
    systems = detect.detect_page(render(1, tmp_path))
    assert sum(len(s["barlines"]) for s in systems) == 0


def test_first_viola_page_finds_all_ten_staves(tmp_path):
    systems = detect.detect_page(render(2, tmp_path))
    assert len(systems) == 10
    for s in systems:
        # music starts after the clef, right of the staff's left edge
        assert 0.10 < s["left"] < s["start"] < 0.22
        assert s["right"] > 0.9
    # 10 lines, ~74 bars; detection is a proposal, so only a loose check
    assert 60 <= sum(len(s["barlines"]) for s in systems) <= 95


def test_bar_lines_match_the_editors_corrections(tmp_path):
    """Detection against bar lines the editor corrected by hand (frozen in
    tests/fixtures). Bar counts here are meant to feed Structure.ily one
    day, so a regression in either direction matters. 2026-10-02: 179 of
    194 found, 3 false. Re-freeze the fixture and these limits together,
    after tuning on more pages (tools/tune_barlines.py)."""
    truth = json.loads(FIXTURE.read_text())
    found = false = missed = 0
    for n, page in truth["pages"].items():
        f, fp, m = score_page(truth_systems(page), detect.detect_page(render(int(n), tmp_path)))
        found, false, missed = found + f, false + fp, missed + m
    total = found + missed
    assert found / total >= 0.90, f"found {found} of {total}"
    assert false <= 5, f"{false} false bar lines"
