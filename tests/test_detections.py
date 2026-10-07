"""The vote between the labeler's bar lines and the detectors' cached
predictions (detections.py), as detect.detect_page's `vote` step."""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
import detections  # noqa: E402

W, H = 1000, 1400  # page pixels


def test_vote_keeps_what_most_voters_propose():
    got = detections.vote({"a": [0.10, 0.50], "b": [0.101, 0.70], "c": [0.102, 0.503]}, 0.006, 2)
    assert [round(x, 3) for x in got] == [0.101, 0.502]


def det(name, threshold=0.3):
    return {"name": name, "threshold": threshold}


def run(preds, own_xs, left=100, right=900, kinds=None):
    """The vote step on one staff at y 280-322 (gap 10.5 px), blank paper (no strokes to snap to)."""
    st = {"top": 280, "bottom": 322, "gap": 10.5}
    band = np.full((80, W), 230.0)
    local = {"top": 20, "bottom": 62}
    bars = [{"x0": x - 1, "x1": x + 1, "kind": (kinds or {}).get(x, "single")} for x in own_xs]
    step = detections.make_vote(preds, W, H)
    return step(st, band, local, bars, left, right, (0, W))


def cached(*xs, top=280 / H, conf=0.9):
    return [{"top": top, "bars": [[x / W, conf] for x in xs]}]


def mids(bars):
    return [round((b["x0"] + b["x1"]) / 2) for b in bars]


def test_majority_kept_own_geometry_and_kind():
    preds = [(det("a"), cached(300, 450, 600)), (det("b"), cached(451, 600))]
    out = run(preds, [300, 600], kinds={600: "double"})
    assert mids(out) == [300, 450, 600]            # 450 by both detectors
    assert out[2]["kind"] == "double"               # its own bar line, as it was
    assert out[1]["x0"] == out[1]["x1"]             # new, upright (no stroke to fit on blank paper)


def test_outvoted_and_below_threshold():
    preds = [(det("a"), cached(300)), (det("b"), cached(300, 700, conf=0.1) + [])]
    assert mids(run(preds, [300, 600])) == [300]   # 600 only its own; b's 700 below threshold


def test_fewer_than_three_voters_leaves_the_staff_alone():
    preds = [(det("a"), cached(450))]
    assert mids(run(preds, [300, 600])) == [300, 600]
    preds = [(det("a"), cached(450)), (det("b"), cached(450, top=0.5))]  # b's staff elsewhere
    assert mids(run(preds, [300, 600])) == [300, 600]


def test_no_reach_before_the_clef_some_past_the_end():
    # left end 100, right 900, a staff space 10.5 px: 95 is before the left end, 905 in reach, 930 not
    preds = [(det("a"), cached(95, 905, 930)), (det("b"), cached(95, 905, 930))]
    assert mids(run(preds, [])) == [905]


def test_each_own_bar_line_used_once():
    # two kept groups both near own 302: it's used once, the other group fitted (here upright) and merged away
    preds = [(det("a"), cached(296, 303)), (det("b"), cached(301))]
    out = run(preds, [302])
    assert len(out) == 1 and mids(out) == [302]


def test_page_predictions_ignore_a_changed_pdf_and_failed_pages(tmp_path):
    cache, edition = tmp_path / "cache", tmp_path / "edition"
    (edition / "sources").mkdir(parents=True)
    pdf = edition / "sources" / "x.pdf"
    pdf.write_bytes(b"%PDF-1")
    d = cache / "models" / "detectors" / "yolo"
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps({"name": "yolo", "sha": "abcdef0123456789", "threshold": 0.3}))
    [det_] = detections.detectors(cache)
    f = detections.cache_file(det_, edition, "sources/x.pdf", cache)
    f.parent.mkdir(parents=True)
    page = {"staves": [{"top": 0.2, "bars": [[0.3, 0.9]]}]}
    f.write_text(json.dumps({"pdf_identity": detections.pdf_identity(pdf), "pages": {"1": page, "2": {"error": "x"}}}))
    assert detections.page_predictions(edition, "sources/x.pdf", 1, cache)[0][1] == page["staves"]
    assert detections.page_predictions(edition, "sources/x.pdf", 2, cache) == []
    assert detections.has_predictions(edition, cache) == ["yolo"]
    pdf.write_bytes(b"%PDF-1 a better scan")
    assert detections.page_predictions(edition, "sources/x.pdf", 1, cache) == []


def test_a_broken_cache_file_is_ignored(tmp_path):
    cache, edition = tmp_path / "cache", tmp_path / "edition"
    (edition / "sources").mkdir(parents=True)
    (edition / "sources" / "x.pdf").write_bytes(b"%PDF-1")
    d = cache / "models" / "detectors" / "yolo"
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps({"name": "yolo", "sha": "abcdef0123456789", "threshold": 0.3}))
    [det_] = detections.detectors(cache)
    f = detections.cache_file(det_, edition, "sources/x.pdf", cache)
    f.parent.mkdir(parents=True)
    f.write_text('{"pdf_identity": "x", "pages": [1, 2]}')
    assert detections.page_predictions(edition, "sources/x.pdf", 1, cache) == []
