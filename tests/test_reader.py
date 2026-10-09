"""Claude's readings of pages and marks (reader.py), with the API call
replaced: the key, the cache, one call for a page asked twice at once,
the spend tally, the mark crop, and the server's use of them."""

import json
import sys
import threading
import time
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
import reader  # noqa: E402
import server  # noqa: E402

USAGE = {"input_tokens": 1_000_000, "output_tokens": 100_000}  # $4 + $2


class FakeAsk:
    def __init__(self, answer, delay=0.0):
        self.answer, self.delay, self.calls = answer, delay, []

    def __call__(self, client, prompt, schema, image, max_tokens):
        self.calls.append((prompt, image))
        time.sleep(self.delay)
        return dict(self.answer)


def fake_reader(tmp_path, answer, delay=0.0):
    r = reader.Reader(tmp_path / "claude", "k", ask=FakeAsk(answer, delay))
    r.client = object()  # never the real one
    return r


def page_image():
    return Image.new("RGB", (400, 600), "white")


def test_the_key_is_ml_api_key_never_anthropic_api_key(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    monkeypatch.delenv("ML_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not this one")
    assert reader.api_key(env) is None
    env.write_text('ANTHROPIC_API_KEY=nor this\nML_API_KEY="from-file"\n')
    assert reader.api_key(env) == "from-file"
    monkeypatch.setenv("ML_API_KEY", "from-env")
    assert reader.api_key(env) == "from-env"


def test_a_page_is_asked_once_and_cached(tmp_path):
    r = fake_reader(tmp_path, {"kind": "title", "part": "vn2", "evidence": "Violino 2.do", "usage": USAGE})
    a = r.page("sources/G1/X.pdf", 3, page_image)
    assert a["part"] == "vn2"
    assert r.page("sources/G1/X.pdf", 3, page_image)["part"] == "vn2"
    assert len(r.ask.calls) == 1
    # a fresh reader (the server restarted) still has it
    assert reader.Reader(tmp_path / "claude", "k").cached_page("sources/G1/X.pdf", 3)["kind"] == "title"
    assert r.spent("sources/G1/X.pdf") == {"pages": 1, "marks": 0, "dollars": 6.0}
    assert r.spent("sources/G1/Other.pdf") == {"pages": 0, "marks": 0, "dollars": 0}


def test_a_page_asked_twice_at_once_is_paid_for_once(tmp_path):
    r = fake_reader(tmp_path, {"kind": "music", "part": "none", "evidence": "nothing", "usage": USAGE}, delay=0.2)
    out = []
    ts = [threading.Thread(target=lambda: out.append(r.page("s.pdf", 1, page_image))) for _ in range(3)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len(r.ask.calls) == 1 and [a["kind"] for a in out] == ["music"] * 3


def test_a_refusal_is_cached_so_it_isnt_paid_for_on_every_open(tmp_path):
    r = fake_reader(tmp_path, {"error": "refused (test)", "usage": USAGE})
    assert "error" in r.page("s.pdf", 1, page_image)
    r.page("s.pdf", 1, page_image)
    assert len(r.ask.calls) == 1 and r.spent("s.pdf")["dollars"] == 6.0


def test_a_mark_is_read_with_the_known_texts_and_logged(tmp_path):
    r = fake_reader(tmp_path, {"text": "Menuetto", "legible": True, "usage": USAGE})
    box = {"x": 0.1, "y": 0.2, "w": 0.2, "h": 0.05}
    assert r.mark("s.pdf", 4, box, page_image(), ["Menuetto", "Trio"])["text"] == "Menuetto"
    prompt, image = r.ask.calls[0]
    assert prompt == reader.mark_prompt(["Menuetto", "Trio"]) and "Menuetto\nTrio" in prompt
    crop = Image.open(__import__("io").BytesIO(image))
    # the box (80 x 30 px) and a margin of 0.3 of its height on every side
    assert crop.size == (80 + 2 * 9, 30 + 2 * 9)
    assert r.spent("s.pdf") == {"pages": 0, "marks": 1, "dollars": 6.0}
    with pytest.raises(ValueError):
        reader.mark_jpeg(page_image(), {"x": 1.0, "y": 0.5, "w": 0.0, "h": 0.0})


def test_the_page_prompt_is_the_one_measured():
    # the test's cached answers are keyed by this prompt; a change means measuring again
    assert (ROOT / "experiments" / "llm" / "answers" / f"pages-{reader.PAGE_TAG}.json").exists()


@pytest.fixture
def edition(tmp_path, monkeypatch):
    root = tmp_path / "ed"
    (root / "sources" / "G1").mkdir(parents=True)
    (root / "sources" / "G1" / "X_Y.pdf").write_bytes(b"%PDF-1.4 not really")
    ed = server.Edition(root, tmp_path / "cache")
    img = tmp_path / "p.jpg"
    page_image().save(img)
    monkeypatch.setattr(ed, "num_pages", lambda pdf: 5)
    monkeypatch.setattr(ed, "render", lambda rel, page: img)
    return ed


def test_the_server_reads_a_page_and_a_mark(edition, tmp_path):
    rel = "sources/G1/X_Y.pdf"
    edition.reader = fake_reader(tmp_path, {"kind": "title", "part": "va", "evidence": "Viola", "text": "Viola",
                                            "legible": True, "usage": USAGE})
    assert edition.read_page(rel, 2, ask=False) == {"reader": {"on": True, "pages": 0, "marks": 0, "dollars": 0}}
    got = edition.read_page(rel, 2)
    assert (got["kind"], got["part"], got["reader"]["pages"]) == ("title", "va", 1)
    assert edition.read_mark(rel, 2, {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.05})["text"] == "Viola"
    with pytest.raises(LookupError):
        edition.read_page(rel, 9)
    with pytest.raises(ValueError):
        edition.read_mark(rel, 2, {"x": 0.1})
    with pytest.raises(ValueError):  # a 400, not "Claude couldn't read it"
        edition.read_mark(rel, 2, {"x": 0.1, "y": 0.1, "w": 0, "h": 0.05})


def test_claudes_unchecked_readings_are_not_offered_as_the_editors(edition, tmp_path):
    lp = edition.root / "sources" / "G1" / "X_Y.labels.json"
    mark = lambda i, text, auto: {"id": i, "x": 0, "y": 0, "w": 0.1, "h": 0.1, "kind": "tempo", "text": text,
                                  **({"text_auto": True} if auto else {})}
    lp.write_text(json.dumps({"pages": {
        "1": {"status": "edited", "marks": [mark("p1m1", "Larghetta", True), mark("p1m2", "Allegro", False)]},
        "2": {"status": "reviewed", "marks": [mark("p2m1", "Menuetto", True)]}}}))
    assert sorted(e["text"] for e in edition.mark_texts()) == ["Allegro", "Menuetto"]
    edition.reader = fake_reader(tmp_path, {"text": "Adagio", "legible": True, "usage": USAGE})
    edition.read_mark("sources/G1/X_Y.pdf", 1, {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.05})
    prompt = edition.reader.ask.calls[0][0]
    assert "Allegro" in prompt and "Menuetto" in prompt and "Larghetta" not in prompt


def test_reading_is_off_without_a_key(edition):
    edition.reader = None
    with pytest.raises(LookupError):
        edition.read_page("sources/G1/X_Y.pdf", 1)
    assert edition.reader_state("sources/G1/X_Y.pdf")["on"] is False


def test_a_failed_call_is_a_read_failure(edition, tmp_path):
    def boom(*a):
        raise ConnectionError("no network")
    edition.reader = reader.Reader(tmp_path / "claude", "k", ask=boom)
    edition.reader.client = object()
    with pytest.raises(reader.ReadFailed):
        edition.read_page("sources/G1/X_Y.pdf", 1)
    # and the next ask isn't stuck waiting on the failed one
    with pytest.raises(reader.ReadFailed):
        edition.read_page("sources/G1/X_Y.pdf", 1)


def test_text_auto_must_be_a_flag():
    import labels

    doc = labels.new_doc({"pdf": "x.pdf"})
    doc["pages"]["1"] = {"status": "edited", "kind": "music", "part": None, "clef": None, "systems": [],
                         "marks": [{"id": "p1m1", "x": 0, "y": 0, "w": 0.1, "h": 0.1, "kind": "text",
                                    "text": "Viola", "text_auto": "yes"}]}
    assert any("text_auto" in e for e in labels.validate(doc))
    doc["pages"]["1"]["marks"][0]["text_auto"] = True
    assert labels.validate(doc) == []
    json.dumps(doc)


# ------------------------------------------------------------------ the front end's use (node)

def js(expr):
    import re
    import shutil
    import subprocess

    if not shutil.which("node"):
        pytest.skip("node not installed")
    src = (ROOT / "static" / "app.js").read_text()
    pick = lambda pat: re.search(pat, src, re.S).group(0)
    code = "\n".join([pick(r"const PART_NAMES = .*?;"), pick(r"const esc = .*?;\n"),
                      pick(r"function firstGuess\(.*?\n\}"), pick(r"function readingNote\(.*?\n\}"),
                      f"console.log(JSON.stringify({expr}));"])
    return json.loads(subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout)


def test_a_new_pages_kind_and_part():
    music = {"colour": 0, "dark": 0.1}
    read = lambda kind, part: {"kind": kind, "part": part, "evidence": ""}
    cases = [
        # (Claude's reading, detection's music, the part carried) -> (kind, part)
        (read("title", "vn2"), False, "vn1", ("title", "vn2")),   # a new part's title page
        (read("title", "none"), False, "vn1", ("title", "vn1")),  # names none: keeps the part
        (read("music", "va"), True, "vn1", ("music", "vn1")),     # music carries the part on
        (read("music", "va"), True, None, ("music", "va")),       # nothing to carry: Claude's
        (read("blank", "none"), True, "vn1", ("blank", None)),    # Claude's kind over detection's
        (None, True, "vc", ("music", "vc")),                      # reading off: as before
        (None, False, "vc", ("title", "vc")),
    ]
    for r, m, carried, want in cases:
        got = js(f"firstGuess({json.dumps(r)}, {json.dumps(m)}, {json.dumps(music)}, {json.dumps(carried)})")
        assert (got["kind"], got["part"]) == want, (r, m, carried)


def test_claudes_reading_shows_only_where_it_disagrees():
    page = {"kind": "music", "part": "vn1"}
    assert js(f"readingNote({json.dumps(page)}, {{kind: 'music', part: 'none', evidence: 'nothing'}})") == ""
    assert js(f"readingNote({json.dumps(page)}, {{kind: 'music', part: 'vn1', evidence: 'x'}})") == ""
    note = js(f"readingNote({json.dumps(page)}, {{kind: 'music', part: 'va', evidence: 'alto clef'}})")
    assert "Viola" in note or "viola" in note.lower()
    assert "alto clef" in note
    assert "a title page" in js(f"readingNote({json.dumps(page)}, {{kind: 'title', part: 'none', evidence: ''}})")
