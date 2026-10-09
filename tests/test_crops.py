"""Learned crop edges (crops.py), on a drawn page."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import crops  # noqa: E402

pytest.importorskip("scipy")  # crops.candidates labels blobs with scipy.ndimage (scikit-learn brings it)

H = W = 1000
SP = 10  # staff space, px


def staff(id, top_px, **kw):
    return {"id": id, "top": top_px / H, "bottom": (top_px + 4 * SP) / H, "left": 0.1, "right": 0.9,
            "start": 0.15, "barlines": [{"x0": 0.5, "x1": 0.5}, {"x0": 0.85, "x1": 0.85}], **kw}


def page(*tops, empty=None):
    """A gray page with five-line staves at `tops` (px), a stem above each
    reaching 2 spaces out, a dynamic floating 1.5 spaces under each, and
    optionally an empty staff (ruled lines, no music) at `empty`."""
    g = np.full((H, W), 255.0, np.float32)
    for t in list(tops) + ([empty] if empty else []):
        for k in range(5):
            g[t + k * SP: t + k * SP + 2, 100:900] = 0
    for t in tops:
        g[t - 2 * SP: t + 2 * SP, 300:303] = 0                          # a stem from inside the staff
        g[t + 4 * SP + 15: t + 4 * SP + 20, 400:430] = 0                # a dynamic under it
    return g


def test_an_empty_ruled_staff_bounds_the_crop():
    g = page(300, empty=200)
    s = staff("a", 300)
    b = crops.band(g, s)
    o = crops.oriented(b, "above")
    # the empty staff's bottom line is 6 spaces above this one's top line
    assert crops.ruled(o, crops.BAND) == pytest.approx(6.0, abs=0.25)
    c, X = crops.candidates(b, np.nan, "above", 2.5)
    assert c[0] == crops.MIN_EDGE and c[-1] <= 6.0 * 1.1 + 1e-9
    assert X.shape == (len(c), len(crops.FEATURES))


def test_rooms_are_to_the_neighbours_facing_lines():
    a, b = staff("a", 300), staff("b", 400)
    up, down = crops.rooms([a, b], a)
    assert down == pytest.approx(6.0)   # a's bottom line at 340, b's top at 400
    assert crops.rooms([a, b], b)[0] == pytest.approx(6.0)
    assert np.isnan(up)  # the page's top is 30 spaces up: past the band


def test_an_older_sources_accepted_crop_isnt_learned_from():
    g = page(300, 400)
    a, b = staff("a", 300), staff("b", 400)
    today = crops.todays_crops(g, [a, b])
    a.update(above=today[id(a)][0], below=today[id(a)][1] + 1.0)   # below changed by the editor
    b.update(above=today[id(b)][0], below=today[id(b)][1])
    ex = crops.examples(g, {"systems": [a, b]}, old=True)
    learn = {(e["staff"], e["side"]): e["learn"] for e in ex}
    assert learn == {("a", "above"): False, ("a", "below"): True, ("b", "above"): False, ("b", "below"): False}
    assert all(e["learn"] and e["weight"] == crops.NEW_WEIGHT for e in crops.examples(g, {"systems": [a, b]}, old=False))


def test_it_learns_an_edge_and_proposes_it():
    pytest.importorskip("sklearn")
    # the editor keeps each staff's dynamic below (1.5-2 spaces out) and its stem above (2 spaces)
    pages = []
    for k in range(6):
        g = page(200 + 10 * k, 330 + 10 * k)
        ss = [staff("a", 200 + 10 * k, above=2.25, below=2.25), staff("b", 330 + 10 * k, above=2.25, below=2.25)]
        pages.append((g, ss))
    ex = [e for g, ss in pages for e in crops.examples(g, {"systems": ss}, old=False)]
    model = crops.fit(ex)
    g = page(250, 380)
    ss = [staff("a", 250), staff("b", 380)]
    for s in ss:
        s["above"], s["below"] = 2.5, 2.5  # crop_margins', as detection gives them
    crops.propose(g, ss, model)
    for s in ss:
        assert abs(s["above"] - 2.25) <= 0.25 and abs(s["below"] - 2.25) <= 0.25


def test_a_page_without_staves_or_bar_lines_doesnt_stop_a_save():
    import server
    data = json.dumps({"pages": {"1": {"status": "reviewed", "kind": "music"},
                                 "2": {"status": "reviewed", "kind": "music", "systems": [{"top": 0.1}]}}}).encode()
    assert server.reviewed_crops(data) == {"1": [], "2": [(0.1, None, None, None, None, None, [])]}
