"""Claude reads a manuscript page and the text in a mark's box, as
proposals for the editor.

A page: its kind (music, title, blank, other) and whose part it is, from a
part name or the clefs. A mark: its text, following the copyist's
spelling with abbreviations expanded, and preferring a text the editor
has already typed when it says the same. The test on the reviewed pages
(experiments/llm/README.md): kind right on 93 of 95 pages; a part, when
Claude names one, right 56 times in 57 (violin pages without a part name
are declined: violin I and II look alike); mark text 134 of 167 offered
the texts already typed. The experiment scripts import these prompts, so
a rerun measures what the labeler asks (though the labeler offers every
checked text in the edition, and the experiment only other sources').

The API key is ML_API_KEY, from the environment or the labeler's .env
(never ANTHROPIC_API_KEY, never printed); without one, reading is off.
Each page's answer is cached by source, so a page is paid for once; each
mark's reading is logged. Both carry their token counts, which give what
was spent on each source.
"""

import base64
import hashlib
import io
import json
import os
import tempfile
import threading
from concurrent.futures import Future
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
MODEL = "claude-opus-5-5"
EFFORT = "low"
PRICE = {"input": 4.0, "output": 20.0}  # $ per million tokens (claude-opus-5-5)
MAX_SIDE = 1568  # a page is scaled to this, the most the model takes in
MARGIN = 0.3  # of a mark box's height, added on every side
MARK_KINDS = ("text", "tempo", "title", "other")  # marks with words to read

PAGE_PROMPT = """This is one page of a scanned late-18th-century manuscript of a string quartet: a set of parts (violin I, violin II, viola, cello), sometimes a score.

Say what the page is:
- kind: "music" (staves with music on them), "title" (a title page or cover, mostly text), "blank" (nothing written, or only empty ruled staves or bleed-through), or "other" (anything else, such as a binding, a library slip or a colour chart).
- part: whose part the page belongs to, from what is written on it (a part's name such as "Violino Primo", "Viola", "Basso" or "Violoncello"; the clefs), or "none" if the page doesn't say. "score" if it holds all the instruments at once.
- evidence: in a few words, what on the page tells you the part (quote any part name as written), or "nothing".
"""
PAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["music", "title", "blank", "other"]},
        "part": {"type": "string", "enum": ["vn1", "vn2", "va", "vc", "score", "none"]},
        "evidence": {"type": "string"},
    },
    "required": ["kind", "part", "evidence"],
    "additionalProperties": False,
}

MARK_PROMPT = """This is a cut-out from a late-18th-century Italian music manuscript (parts of a string quartet): a word or phrase written on the page, such as a tempo, a section title, a direction ("Segue il Trio", "Da Capo"), a dynamic, or a title-page line.

Transcribe it as an editor would type it: the words in full, with the copyist's abbreviations expanded ("All.tto mod.to" is "Allegretto moderato") and superscript letters joined, keeping the copyist's spelling, capitals and punctuation otherwise. Ignore music notation and ink from beyond the phrase.
"""
KNOWN = """
The editor has already typed these texts in other manuscripts of the same works. If this one says the same, answer with that text exactly; otherwise transcribe it:
{texts}
"""
MARK_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}, "legible": {"type": "boolean"}},
    "required": ["text", "legible"],
    "additionalProperties": False,
}


def tag(*parts) -> str:
    """A short key for what was asked: answers to another prompt aren't reused."""
    return hashlib.sha1(":".join(map(str, parts)).encode()).hexdigest()[:10]


PAGE_TAG = tag(MODEL, EFFORT, MAX_SIDE, PAGE_PROMPT, json.dumps(PAGE_SCHEMA))  # = experiments/llm/pages.py's


def api_key(env_file: Path = ROOT / ".env") -> str | None:
    """ML_API_KEY from the environment, else from the labeler's .env."""
    if os.environ.get("ML_API_KEY"):
        return os.environ["ML_API_KEY"]
    try:
        lines = env_file.read_text().splitlines()
    except OSError:
        return None
    for line in lines:
        k, _, v = line.partition("=")
        if k.strip() == "ML_API_KEY":
            return v.strip().strip('"').strip("'") or None
    return None


def jpeg(img: Image.Image, quality: int = 85) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def page_jpeg(img: Image.Image) -> bytes:
    """The page as sent: scaled to MAX_SIDE."""
    img = img.copy()
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    return jpeg(img)


def mark_jpeg(img: Image.Image, m: dict) -> bytes:
    """A mark's box (page fractions x, y, w, h) with MARGIN of its height around it."""
    w, h = img.size
    pad = MARGIN * m["h"] * h
    box = (max(0, m["x"] * w - pad), max(0, m["y"] * h - pad),
           min(w, (m["x"] + m["w"]) * w + pad), min(h, (m["y"] + m["h"]) * h + pad))
    if box[2] - box[0] < 1 or box[3] - box[1] < 1:
        raise ValueError("the mark's box is empty")
    return jpeg(img.crop(tuple(int(v) for v in box)), quality=90)


def offered(known: list[str]) -> str:
    """A short key for the texts offered with a mark (experiments/llm/marks.py's too)."""
    return hashlib.sha1("\n".join(known).encode()).hexdigest()[:10]


def mark_prompt(known: list[str]) -> str:
    return MARK_PROMPT + (KNOWN.format(texts="\n".join(known)) if known else "")


def ask(client, prompt: str, schema: dict, image: bytes, max_tokens: int) -> dict:
    """One image and a prompt; the structured answer, with the model that
    gave it and the tokens used, or {"error": ...} on a refusal."""
    r = client.beta.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": base64.standard_b64encode(image).decode()}},
            {"type": "text", "text": prompt},
        ]}],
    )
    paid = {"model": r.model, "usage": r.usage.to_dict()}
    if r.stop_reason == "refusal":
        return {"error": f"refused ({r.stop_details.category if r.stop_details else '?'})", **paid}
    text = next((b.text for b in r.content if b.type == "text"), "")
    try:
        return {**json.loads(text), **paid}
    except ValueError:  # cut off (max_tokens) or not JSON
        return {"error": f"unusable answer (stopped: {r.stop_reason})", **paid}


def dollars(answers) -> float:
    return sum(a["usage"]["input_tokens"] * PRICE["input"] + a["usage"]["output_tokens"] * PRICE["output"]
               for a in answers if "usage" in a) / 1e6


def save_json(path: Path, obj):
    """Atomically: a crash mid-write leaves the old file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, indent=1, sort_keys=True)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


class ReadFailed(Exception):
    """Claude couldn't be asked, or its answer couldn't be used."""


class Reader:
    """Asks Claude, caches page answers and logs mark readings under
    `cache` (one folder per source), and tallies what each source cost.
    `ask` is replaceable for tests."""

    def __init__(self, cache: Path, key: str, ask=ask):
        self.cache = cache
        self.key = key
        self.ask = ask
        self.client = None
        self.lock = threading.Lock()
        self.inflight: dict[tuple, Future] = {}  # a page being asked: later asks wait for it

    def _client(self):
        with self.lock:
            if self.client is None:
                import anthropic  # only when reading is on

                # a new page waits on its reading: don't let a stalled call hold it long
                self.client = anthropic.Anthropic(api_key=self.key, max_retries=2, timeout=60.0)
            return self.client

    def folder(self, source: str) -> Path:
        return self.cache / (Path(source).stem + "-" + hashlib.sha1(source.encode()).hexdigest()[:8])

    def _pages_file(self, source: str) -> Path:
        return self.folder(source) / f"pages-{PAGE_TAG}.json"

    def _marks_file(self, source: str) -> Path:
        return self.folder(source) / "marks.jsonl"

    def cached_page(self, source: str, page: int) -> dict | None:
        try:
            return json.loads(self._pages_file(source).read_text()).get(str(page))
        except (OSError, ValueError):
            return None

    def page(self, source: str, page: int, image) -> dict:
        """The page's kind and part: cached, else asked (image() makes the
        page image). A page asked twice at once is paid for once. A refusal
        or an unusable answer is cached too ({"error": ...}), so a page
        isn't paid for again each time it's opened."""
        hit = self.cached_page(source, page)
        if hit:
            return hit
        k = (source, page)
        with self.lock:
            hit = self.cached_page(source, page)  # answered since the look above
            if hit:
                return hit
            fut = self.inflight.get(k)
            mine = fut is None
            if mine:
                fut = self.inflight[k] = Future()
        if not mine:
            return fut.result()
        try:
            a = self.ask(self._client(), PAGE_PROMPT, PAGE_SCHEMA, page_jpeg(image()), 4000)
            with self.lock:  # one writer at a time per cache file
                f = self._pages_file(source)
                try:
                    done = json.loads(f.read_text())
                except (OSError, ValueError):
                    done = {}
                done[str(page)] = a
                save_json(f, done)
            fut.set_result(a)
            return a
        except BaseException as e:
            fut.set_exception(e)
            raise
        finally:
            with self.lock:
                self.inflight.pop(k, None)

    def mark(self, source: str, page: int, box: dict, image: Image.Image, known: list[str]) -> dict:
        """The text in a mark's box, offered `known` (texts the editor has typed)."""
        a = self.ask(self._client(), mark_prompt(known), MARK_SCHEMA, mark_jpeg(image, box), 2000)
        entry = {"page": page, "box": [round(box[k], 5) for k in ("x", "y", "w", "h")],
                 "offered": offered(known), **a}
        with self.lock:
            f = self._marks_file(source)
            f.parent.mkdir(parents=True, exist_ok=True)
            with f.open("a") as out:
                out.write(json.dumps(entry, sort_keys=True) + "\n")
        return a

    def spent(self, source: str) -> dict:
        """What reading this source has cost so far."""
        try:
            pages = list(json.loads(self._pages_file(source).read_text()).values())
        except (OSError, ValueError):
            pages = []
        marks = []
        try:
            for line in self._marks_file(source).read_text().splitlines():
                try:
                    marks.append(json.loads(line))
                except ValueError:
                    pass  # a line cut off by a crash
        except OSError:
            pass
        return {"pages": len(pages), "marks": len(marks), "dollars": round(dollars(pages + marks), 2)}
