# /// script
# requires-python = ">=3.11"
# dependencies = ["anthropic", "numpy", "pillow", "scikit-learn"]
# ///
"""Local labeling server.

    uv run server.py <edition-repo> [--port 8048] [--no-open]

Serves the editor (`static/`), renders PDF pages with `pdftoppm`, proposes
staves and bar lines (`detect.py`), asks Claude what each new page is and
what a mark's box says (`reader.py`, with ML_API_KEY in the labeler's .env),
and saves:

    data/<edition>/<pdf path>.labels.json   the editor's working file (schema-
                                            versioned), in this repo (labels.DATA)
    <pdf>.bars.json     flat bar export for the synoptic build, next to the PDF
                        in the edition, rewritten on save

Saving is atomic (temp file + rename), refuses to overwrite a file that
changed since the editor loaded it, and keeps rolling backups in the cache
directory (~/.cache/manuscript-labeler, or $MANUSCRIPT_LABELER_CACHE).
"""

import argparse
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).parent))
import crops  # noqa: E402
import labels  # noqa: E402
import reader  # noqa: E402
import structure  # noqa: E402

HERE = Path(__file__).parent
STATIC = HERE / "static"
RENDER_PX = 2800  # long side of a page render; detect.py was tuned near this
JPEG_QUALITY = 90  # PNG at this size is ~7 MB and takes seconds to encode
BACKUP_EVERY = 60  # seconds between backups of one file
BACKUPS_KEPT = 100


class Edition:
    def __init__(self, root: Path, cache: Path, data: Path = labels.DATA):
        self.root = root.resolve()
        self.cache = cache
        self.data = data  # where the labels files live (labels.labels_path)
        self.write_lock = threading.Lock()
        self.render_locks: dict[str, threading.Lock] = {}
        self.render_locks_lock = threading.Lock()
        self.page_counts: dict[str, int] = {}
        self.prerendering: set[str] = set()
        self.grays: dict[str, object] = {}  # a few decoded pages, for snapping
        # the learned bar-line filter (learn.py): trained in the background
        # from the reviewed pages, retrained when they change
        self.model = None
        self.model_state = "not trained"
        self.model_lock = threading.Lock()
        self.model_again = False
        # the learned crop edges (crops.py): the same, from the reviewed crops
        self.crop_model = None
        self.crop_state = "not trained"
        self.crop_lock = threading.Lock()
        self.crop_again = False
        # Claude's readings of pages and marks (reader.py): on with an API key
        key = reader.api_key()
        self.reader = reader.Reader(cache / "claude", key) if key else None

    # -- paths ---------------------------------------------------------------

    def pdf(self, rel: str) -> Path:
        """Resolve a pdf path from the client, refusing anything outside the edition."""
        p = (self.root / rel).resolve()
        if p.suffix.lower() != ".pdf" or not p.is_file() or self.root not in p.parents:
            raise LookupError(f"no such source: {rel}")
        return p

    def rel(self, p: Path) -> str:
        return p.relative_to(self.root).as_posix()

    def labels_path(self, pdf: Path) -> Path:
        return labels.labels_path(pdf, self.data, self.root)

    @staticmethod
    def bars_path(pdf: Path) -> Path:
        return pdf.with_name(pdf.stem + ".bars.json")

    def readme_rows(self) -> dict:
        f = self.root / "sources" / "README.md"
        return labels.parse_sources_readme(f.read_text()) if f.exists() else {}

    # -- sources -------------------------------------------------------------

    def num_pages(self, pdf: Path) -> int:
        key = f"{pdf}:{pdf.stat().st_mtime_ns}"
        if key not in self.page_counts:
            out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, check=True).stdout
            self.page_counts[key] = int(re.search(r"^Pages:\s+(\d+)", out, re.M).group(1))
        return self.page_counts[key]

    def list_sources(self) -> list[dict]:
        rows = self.readme_rows()
        out = []
        for pdf in sorted(self.root.glob("sources/**/*.pdf")):
            rel = self.rel(pdf)
            info = labels.source_info(rel, rows)
            statuses: dict[str, int] = {}
            lp = self.labels_path(pdf)
            if lp.exists():
                try:
                    doc = json.loads(lp.read_text())
                    for p in doc.get("pages", {}).values():
                        statuses[p.get("status", "?")] = statuses.get(p.get("status", "?"), 0) + 1
                except (ValueError, OSError):
                    statuses["unreadable"] = 1
            out.append({**info, "pdf": rel, "pages": self.num_pages(pdf), "statuses": statuses})
        return out

    def mark_texts(self) -> list[dict]:
        """Every mark text used in this edition's labels, most used first,
        with the kind it's usually given: suggestions for the editor, and
        the texts Claude is offered. Claude's readings count once their
        page is reviewed."""
        seen: dict[str, dict] = {}
        for lp, _ in labels.labels_files(self.root, self.data):
            try:
                doc = json.loads(lp.read_text())
            except (ValueError, OSError):
                continue
            for page in doc.get("pages", {}).values():
                for m in page.get("marks", []):
                    text = (m.get("text") or "").strip()
                    if not text or (m.get("text_auto") and page.get("status") != "reviewed"):
                        continue  # Claude's reading, not yet checked: not the editor's text
                    e = seen.setdefault(text, {"text": text, "n": 0, "kinds": {}})
                    e["n"] += 1
                    e["kinds"][m.get("kind", "text")] = e["kinds"].get(m.get("kind", "text"), 0) + 1
        out = sorted(seen.values(), key=lambda e: (-e["n"], e["text"].lower()))
        return [{"text": e["text"], "n": e["n"], "kind": max(e["kinds"], key=e["kinds"].get),
                 "kinds": sorted(e["kinds"])} for e in out]

    def load(self, rel: str) -> dict:
        pdf = self.pdf(rel)
        rows = self.readme_rows()
        info = labels.source_info(rel, rows)
        lp = self.labels_path(pdf)
        readonly = None
        old = labels.legacy_labels_path(pdf)
        if not lp.exists() and old.exists():
            # labelled before the labels moved here: copy them over (the
            # edition's file stays), or the source would open unlabelled and
            # its first save would overwrite its bar export
            with self.write_lock:
                if not lp.exists():
                    lp.parent.mkdir(parents=True, exist_ok=True)
                    atomic_write(lp, old.read_bytes())
        if lp.exists():
            raw = lp.read_bytes()
            etag = hashlib.sha1(raw).hexdigest()
            try:
                doc = labels.migrate(json.loads(raw))
            except labels.NewerSchema as e:
                doc, readonly = json.loads(raw), str(e)
        else:
            etag = "none"
            doc = labels.new_doc(info["source"])
        sp = labels.structure_path(self.root, info["display"].get("work", ""))
        stext = sp.read_text() if sp else None
        expected = structure.expected(stext) if sp else {}
        return {
            "pdf": rel,
            "labels": doc,
            "etag": etag,
            "readonly": readonly,
            "pages": self.num_pages(pdf),
            "source": info["source"],
            "display": info["display"],
            "expected": expected,
            "structure": self.rel(sp) if sp else None,
            # movements this source could write to Structure.ily now
            "structure_offers": structure.offers(doc, stext) if not readonly else [],
            "labels_file": lp.relative_to(self.data.parent).as_posix(),
            "barline_model": self.barline_state(),
            "crop_model": self.crop_state,
            "reader": self.reader_state(rel),
        }

    # -- saving --------------------------------------------------------------

    def save(self, rel: str, doc: dict, if_match: str) -> dict:
        pdf = self.pdf(rel)
        # a tab loaded before an upgrade sends the older schema: bring it up
        # to date (migrations keep every label) rather than refuse its edits
        doc = labels.migrate(doc) if isinstance(doc, dict) else doc
        errs = labels.validate(doc)
        if errs:
            raise ValueError("; ".join(errs[:10]))
        lp = self.labels_path(pdf)
        with self.write_lock:
            current = lp.read_bytes() if lp.exists() else None
            etag = hashlib.sha1(current).hexdigest() if current is not None else "none"
            if if_match != etag:
                raise FileExistsError("the labels file changed since it was loaded")
            if current is not None:
                try:
                    on_disk = json.loads(current).get("schema", 0)
                except ValueError:
                    on_disk = 0  # unreadable JSON: back it up below and replace it
                if isinstance(on_disk, int) and on_disk > labels.SCHEMA:
                    raise labels.NewerSchema("file is from a newer version; not overwriting")
                self.backup(lp, current)
            doc = labels.round_floats(doc)
            data = dump(doc)
            lp.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(lp, data)
            atomic_write(self.bars_path(pdf), dump(labels.round_floats(labels.bars_export(doc))))
            # what the model learns from changed: retrain (in the background)
            if reviewed_truth(current) != reviewed_truth(data):
                self.train_model()
            if reviewed_crops(current) != reviewed_crops(data):
                self.train_crops()
            # the movements it could now write to Structure.ily (a review may complete one)
            info = labels.source_info(rel, self.readme_rows())
            sp = labels.structure_path(self.root, info["display"].get("work", ""))
            return {"etag": hashlib.sha1(data).hexdigest(),
                    "structure_offers": structure.offers(doc, sp.read_text() if sp else None)}

    # -- Structure.ily, from a source's labels --------------------------------

    def structure(self, rel: str, movement: str, answers: dict, text: str | None = None) -> dict:
        """A movement's proposed Structure.ily block from this source's labels
        (structure.propose), and whether it may be written: only where the
        file has no real block for it yet (structure.is_template), from a
        labels file this version reads. `text`: Structure.ily as read once."""
        info = self.load(rel)
        sp = self.root / info["structure"] if info["structure"] else None
        if text is None:
            text = sp.read_text() if sp else ""
        existing = labels.parse_structure(text).get(movement)
        r = structure.propose(info["labels"], movement, existing, answers)
        template = structure.is_template(text, movement)
        r["file"] = info["structure"]
        r["etag"] = hashlib.sha1(text.encode()).hexdigest()
        r["writable"] = bool(sp) and template and r["ok"] and not info["readonly"]
        r["why"] = (None if r["writable"] else "no Structure.ily for this work (copy the template)" if not sp
                    else "this labels file is from a newer version of the labeler" if info["readonly"]
                    else "Structure.ily already has this movement: a difference here is between sources"
                    if not template else "; ".join(r["problems"]))
        return r

    def write_structure(self, rel: str, movement: str, answers: dict, if_match: str, shown: str) -> dict:
        """Write the proposed block into Structure.ily (backed up first): if
        still writable, the file is as it was when proposed (`if_match`) and
        the block is the one shown (`shown`, its hash). The file is read
        once, and everything decided from that reading."""
        with self.write_lock:
            info = self.load(rel)
            if not info["structure"]:
                raise ValueError("no Structure.ily for this work")
            sp = self.root / info["structure"]
            old = sp.read_text()
            r = self.structure(rel, movement, answers, old)
            if not r["writable"]:
                raise ValueError(r["why"])
            if r["etag"] != if_match:
                raise FileExistsError("Structure.ily changed since it was shown")
            if hashlib.sha1(r["text"].split("\n", 1)[1].encode()).hexdigest() != shown:
                raise FileExistsError("the labels changed since the block was shown: look again")
            new = structure.write_block(old, movement, r["text"])
            if structure.check(new, movement, r["want"]):  # the whole file, read back as the labeler will
                raise ValueError("the written file wouldn't read back as the labels say; not written")
            d = self.cache / "backups" / self.root.name / r["file"].replace("/", "__")
            d.mkdir(parents=True, exist_ok=True)
            (d / time.strftime("%Y%m%d-%H%M%S.ily")).write_text(old)
            atomic_write(sp, new.encode())
            return {"etag": hashlib.sha1(new.encode()).hexdigest(), "expected": structure.expected(new),
                    "offers": structure.offers(info["labels"], new)}

    def backup(self, lp: Path, data: bytes):
        rel = lp.relative_to(self.data / self.root.name).as_posix()  # as when it sat beside the PDF
        d = self.cache / "backups" / self.root.name / rel.replace("/", "__").removesuffix(".json")
        d.mkdir(parents=True, exist_ok=True)
        existing = sorted(d.glob("*.json"))
        if existing and time.time() - existing[-1].stat().st_mtime < BACKUP_EVERY:
            return
        (d / time.strftime("%Y%m%d-%H%M%S.json")).write_bytes(data)
        for old in sorted(d.glob("*.json"))[:-BACKUPS_KEPT]:
            old.unlink()

    # -- rendering and detection ---------------------------------------------

    def render(self, rel: str, page: int) -> Path:
        pdf = self.pdf(rel)
        if not 1 <= page <= self.num_pages(pdf):
            raise LookupError(f"no page {page}")
        st = pdf.stat()
        key = hashlib.sha1(f"{pdf}:{st.st_size}:{st.st_mtime_ns}:{RENDER_PX}:{JPEG_QUALITY}".encode()).hexdigest()[:16]
        out = self.cache / "renders" / key / f"p{page:03d}.jpg"
        if out.exists():
            return out
        with self.render_locks_lock:
            lock = self.render_locks.setdefault(str(out), threading.Lock())
        with lock:
            if out.exists():
                return out
            out.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=out.parent) as tmp:
                base = Path(tmp) / "r"
                subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page), "-scale-to", str(RENDER_PX),
                                "-jpeg", "-jpegopt", f"quality={JPEG_QUALITY}", "-singlefile",
                                str(pdf), str(base)], check=True, capture_output=True)
                os.replace(base.with_suffix(".jpg"), out)
        return out

    def prerender(self, rel: str, first: int = 1):
        """Render every page of a source in the background, starting at `first`,
        so paging through it doesn't wait on pdftoppm."""
        with self.render_locks_lock:
            if rel in self.prerendering:
                return
            self.prerendering.add(rel)

        def go():
            try:
                n = self.num_pages(self.pdf(rel))
                for page in list(range(first, n + 1)) + list(range(1, first)):
                    self.render(rel, page)
            except Exception:
                pass
            finally:
                with self.render_locks_lock:
                    self.prerendering.discard(rel)
        threading.Thread(target=go, daemon=True).start()

    def gray(self, rel: str, page: int):
        """The page as a grayscale array, keeping the last few decoded."""
        from PIL import Image

        import detect

        key = f"{rel}:{page}"
        if key not in self.grays:
            if len(self.grays) >= 4:
                self.grays.pop(next(iter(self.grays)))
            self.grays[key] = detect._gray(Image.open(self.render(rel, page)))
        return self.grays[key]

    def snap(self, rel: str, page: int, top: float, bottom: float, x0: float, x1: float) -> dict:
        """Fit a hand-placed bar line to the ink under it (detect.snap_barline).
        Everything in page fractions; {} if there's no stroke close enough."""
        import detect

        g = self.gray(rel, page)
        h, w = g.shape
        r = detect.snap_barline(g, top * h, bottom * h, x0 * w, x1 * w)
        return {"x0": r["x0"] / w, "x1": r["x1"] / w, "cover": r["cover"]} if r else {}

    def snap_start(self, rel: str, page: int, top: float, bottom: float, x: float) -> dict:
        """A music start near x snapped to clear paper (detect.snap_start), page fractions."""
        import detect

        g = self.gray(rel, page)
        h, w = g.shape
        r = detect.snap_start(g, top * h, bottom * h, x * w)
        return {"x": r / w} if r is not None else {}

    def detect(self, rel: str, page: int, room: float | None = None, corners: list | None = None) -> dict:
        """Detection on one page; `corners`, the editor's, else detected. Its
        bar lines are voted with the detectors' cached predictions for the
        page when there are any, and its staves' ends and music starts come
        from them where a detector learned those (detections.py); if reading
        them fails, detection goes ahead without."""
        from PIL import Image

        import detect
        import detections

        img = Image.open(self.render(rel, page))
        corners = corners or detect.find_page_corners(img)
        try:  # a bad cache mustn't stop detection
            preds = detections.page_predictions(self.root, rel, page, self.cache)
            vote = detections.make_vote(preds, img.size[0], img.size[1]) if preds else None
            ends = detections.make_ends(preds, img.size[0], img.size[1]) if preds else None
        except Exception as e:
            print(f"bar-line predictions unreadable for {rel} p{page}: {type(e).__name__}: {e}", flush=True)
            vote = ends = None
        # with the cached predictions; if they fail, with the vote alone, then without
        tries = [(vote, ends)]
        if vote is not None and ends is not None:
            tries.append((vote, None))
        if vote is not None or ends is not None:
            tries.append((None, None))
        for v, en in tries:
            try:
                systems = detect.detect_page(img, room, model=self.model, corners=corners, vote=v, ends=en)
                break
            except Exception as e:
                if v is None and en is None:
                    raise
                print(f"cached predictions failed on {rel} p{page} ({'ends' if en else 'vote'}): "
                      f"{type(e).__name__}: {e}", flush=True)
        if self.crop_model is not None:  # else crop_margins' rule
            try:
                crops.propose(detect._gray(img), systems, self.crop_model)
            except Exception as e:
                print(f"learned crops failed on {rel} p{page}: {type(e).__name__}: {e}", flush=True)
        return {"systems": systems, "corners": corners, "look": detect.page_look(img, corners)}

    # -- Claude's readings ---------------------------------------------------

    def reader_state(self, rel: str) -> dict:
        if self.reader is None:
            return {"on": False, "why": "off: no ML_API_KEY in the labeler's .env"}
        return {"on": True, **self.reader.spent(rel)}

    def read_page(self, rel: str, page: int, ask: bool = True) -> dict:
        """Claude's kind and part for a page and, on a title page, its lines
        of writing as marks' boxes with their text: cached, else asked
        (unless `ask` is false: then none when they haven't been). A failure
        to read the lines doesn't lose the page's reading (lines_error)."""
        from PIL import Image

        if self.reader is None:
            raise LookupError("reading is off: no ML_API_KEY in the labeler's .env")
        pdf = self.pdf(rel)
        if not 1 <= page <= self.num_pages(pdf):
            raise LookupError(f"no page {page}")
        a = self.reader.cached_page(rel, page)
        if a is None and ask:
            img = self.render(rel, page)  # a render failure is pdftoppm's, not Claude's
            try:
                a = self.reader.page(rel, page, lambda: Image.open(img))
            except Exception as e:
                raise reader.ReadFailed(f"{type(e).__name__}: {e}") from e
        a = a or {}
        out = {k: a[k] for k in ("kind", "part", "evidence", "error") if k in a}
        if a.get("kind") == "title":
            ln = self.reader.cached_lines(rel, page)
            if ln is None and ask:
                img = self.render(rel, page)
                try:
                    ln = self.reader.lines(rel, page, lambda: Image.open(img))
                except Exception as e:  # noqa: BLE001 (the page's reading still stands)
                    out["lines_error"] = f"{type(e).__name__}: {e}"
            if ln and "error" in ln:
                out["lines_error"] = ln["error"]
            elif ln:
                out["lines"] = reader.line_boxes(ln)
        return {**out, "reader": self.reader_state(rel)}

    def read_mark(self, rel: str, page: int, box: dict) -> dict:
        """Claude's reading of the text in a mark's box, offered the texts
        already typed for marks with words (most used first)."""
        from PIL import Image

        if self.reader is None:
            raise LookupError("reading is off: no ML_API_KEY in the labeler's .env")
        try:
            box = {k: float(box[k]) for k in ("x", "y", "w", "h")}
        except (KeyError, TypeError) as e:
            raise ValueError(f"box: {e}") from e
        img = Image.open(self.render(rel, page))
        known = [e["text"] for e in self.mark_texts() if set(e["kinds"]) & set(reader.MARK_KINDS)]  # the editor's
        if box["w"] <= 0 or box["h"] <= 0:
            raise ValueError("the mark's box is empty")
        try:
            a = self.reader.mark(rel, page, box, img, known)
        except ValueError:
            raise  # the box (mark_jpeg): the request's fault, not Claude's
        except Exception as e:
            raise reader.ReadFailed(f"{type(e).__name__}: {e}") from e
        return {**{k: a[k] for k in ("text", "legible", "error") if k in a}, "reader": self.reader_state(rel)}

    def barline_state(self) -> str:
        """How bar lines are found, for the source panel."""
        import detections
        try:
            names = detections.has_predictions(self.root, self.cache)
        except Exception:
            names = []
        if len(names) < 2:  # the vote needs two detectors
            return self.model_state
        return f"{self.model_state}; voted with {', '.join(names)} (cached predictions)"

    def train_model(self):
        """(Re)train the learned bar-line filter in the background. A request
        while training is running queues one more run after it."""
        if not self.model_lock.acquire(blocking=False):
            self.model_again = True
            return

        def go():
            from PIL import Image

            import learn

            try:
                while True:
                    self.model_again = False
                    self.model_state = "training"
                    try:
                        def render(pdf, n):
                            img = Image.open(self.render(self.rel(pdf), n))
                            img.load()
                            return img
                        m = learn.load_or_train(self.root, self.cache, render, self.data)
                        self.model = m
                        self.model_state = (f"learned from {m['pages']} reviewed pages ({m['bar_lines']} bar lines)"
                                            if m else "no reviewed pages yet: hand-tuned rules")
                    except Exception as e:  # keep the hand-tuned rules
                        self.model_state = f"not trained ({e}): hand-tuned rules"
                    print(f"bar lines: {self.model_state}", flush=True)
                    if not self.model_again:
                        break
            finally:
                self.model_lock.release()
        threading.Thread(target=go, daemon=True).start()

    def train_crops(self):
        """(Re)train the learned crop edges in the background, as train_model.
        Until a model exists, detection's crops are crop_margins' rule."""
        if not self.crop_lock.acquire(blocking=False):
            self.crop_again = True
            return

        def go():
            from PIL import Image

            import detect

            try:
                while True:
                    self.crop_again = False
                    self.crop_state = "training"
                    try:
                        def gray(pdf, n):
                            return detect._gray(Image.open(self.render(self.rel(pdf), n)))
                        m = crops.load_or_train(self.root, self.cache, gray, self.data)
                        self.crop_model = m
                        self.crop_state = (f"learned from {m['pages']} reviewed pages ({m['sides']} crop edges)"
                                           if m else "no reviewed crops yet: rules")
                    except Exception as e:  # keep the last model, if any, else the rules
                        self.crop_state = (f"retraining failed ({e}): the last model" if self.crop_model
                                           else f"not trained ({e}): rules")
                    print(f"crops: {self.crop_state}", flush=True)
                    if not self.crop_again:
                        break
            finally:
                self.crop_lock.release()
        threading.Thread(target=go, daemon=True).start()


def reviewed_crops(data: bytes | None):
    """The parts of a labels file the crop model learns from (crops.truth):
    each reviewed music page's staves and crops."""
    if not data:
        return None
    try:
        doc = json.loads(data)
    except ValueError:
        return None
    return {n: crops.truth(p) for n, p in doc.get("pages", {}).items()
            if p.get("status") == "reviewed" and p.get("kind") == "music"}


def reviewed_truth(data: bytes | None):
    """The parts of a labels file the bar-line model learns from: each
    reviewed music page's staves and bar lines."""
    if not data:
        return None
    try:
        doc = json.loads(data)
    except ValueError:
        return None
    return {n: [(s.get("top"), s.get("role"), [(b.get("x0"), b.get("x1")) for b in s.get("barlines", [])])
                for s in p.get("systems", [])]
            for n, p in doc.get("pages", {}).items() if p.get("status") == "reviewed" and p.get("kind") == "music"}


def dump(doc) -> bytes:
    return (json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def atomic_write(path: Path, data: bytes):
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix="." + path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


class Handler(BaseHTTPRequestHandler):
    edition: Edition

    def log_message(self, fmt, *args):
        if os.environ.get("LABELER_VERBOSE"):
            super().log_message(fmt, *args)

    def send_json(self, obj, status=HTTPStatus.OK):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path, cache: bool = False):
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "max-age=86400" if cache else "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def error(self, status, msg):
        self.send_json({"error": msg}, status)

    def route(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        return url.path, q

    def do_GET(self):
        path, q = self.route()
        ed = self.edition
        try:
            if path == "/":
                return self.send_file(STATIC / "index.html")
            if path.startswith("/static/"):
                f = (STATIC / path[len("/static/"):]).resolve()
                if STATIC.resolve() not in f.parents or not f.is_file():
                    return self.error(HTTPStatus.NOT_FOUND, "not found")
                return self.send_file(f)
            if path == "/api/marktexts":
                return self.send_json({"texts": ed.mark_texts()})
            if path == "/api/sources":
                return self.send_json({"edition": str(ed.root), "sources": ed.list_sources()})
            if path == "/api/source":
                return self.send_json(ed.load(q["pdf"]))
            if path == "/api/page":
                page = int(q["page"])
                f = ed.render(q["pdf"], page)
                ed.prerender(q["pdf"], page + 1)
                return self.send_file(f, cache=True)
            if path == "/api/detect":
                room = float(q["room"]) if q.get("room") else None
                corners = None
                if q.get("corners"):
                    try:
                        corners = [[float(x), float(y)] for x, y in json.loads(q["corners"])]
                    except TypeError as e:
                        raise ValueError(f"corners: {e}") from e
                    if len(corners) != 4:
                        raise ValueError("corners: four points")
                return self.send_json(ed.detect(q["pdf"], int(q["page"]), room, corners))
            if path == "/api/snap":
                f = {k: float(q[k]) for k in ("top", "bottom", "x0", "x1")}
                return self.send_json(ed.snap(q["pdf"], int(q["page"]), **f))
            if path == "/api/snapstart":
                f = {k: float(q[k]) for k in ("top", "bottom", "x")}
                return self.send_json(ed.snap_start(q["pdf"], int(q["page"]), **f))
            if path == "/api/structure":
                answers = {k: v for k, v in q.items() if k not in ("pdf", "movement")}
                return self.send_json(ed.structure(q["pdf"], q["movement"], answers))
            if path == "/api/read":
                return self.send_json(ed.read_page(q["pdf"], int(q["page"]), ask=q.get("ask") != "0"))
            if path == "/api/bars":
                return self.send_json(labels.bars_export(ed.load(q["pdf"])["labels"]))
            return self.error(HTTPStatus.NOT_FOUND, "not found")
        except (LookupError, KeyError, ValueError) as e:
            return self.error(HTTPStatus.BAD_REQUEST, str(e))
        except subprocess.CalledProcessError as e:
            return self.error(HTTPStatus.INTERNAL_SERVER_ERROR, f"{e.cmd[0]} failed: {e.stderr}")
        except reader.ReadFailed as e:
            return self.error(HTTPStatus.BAD_GATEWAY, f"Claude couldn't read it: {e}")

    def do_POST(self):
        path, q = self.route()
        if path not in ("/api/structure", "/api/readmark"):
            return self.error(HTTPStatus.NOT_FOUND, "not found")
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n))
            if path == "/api/readmark":
                return self.send_json(self.edition.read_mark(body["pdf"], int(body["page"]), body["box"]))
            return self.send_json(self.edition.write_structure(
                body["pdf"], body["movement"], body.get("answers", {}), self.headers.get("If-Match", ""),
                body.get("shown", "")))
        except FileExistsError as e:
            return self.error(HTTPStatus.CONFLICT, str(e))
        except (LookupError, KeyError, ValueError) as e:
            return self.error(HTTPStatus.BAD_REQUEST, str(e))
        except reader.ReadFailed as e:
            return self.error(HTTPStatus.BAD_GATEWAY, f"Claude couldn't read it: {e}")
        except subprocess.CalledProcessError as e:
            return self.error(HTTPStatus.INTERNAL_SERVER_ERROR, f"{e.cmd[0]} failed: {e.stderr}")

    def do_PUT(self):
        path, q = self.route()
        if path != "/api/labels":
            return self.error(HTTPStatus.NOT_FOUND, "not found")
        try:
            n = int(self.headers.get("Content-Length", 0))
            doc = json.loads(self.rfile.read(n))
            result = self.edition.save(q["pdf"], doc, self.headers.get("If-Match", ""))
            return self.send_json(result)
        except (FileExistsError, labels.NewerSchema) as e:
            return self.error(HTTPStatus.CONFLICT, str(e))
        except (LookupError, KeyError, ValueError) as e:
            return self.error(HTTPStatus.BAD_REQUEST, str(e))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edition", type=Path, help="edition repo (holds sources/**/*.pdf)")
    ap.add_argument("--port", type=int, default=8048)
    ap.add_argument("--no-open", action="store_true", help="don't open a browser")
    args = ap.parse_args()

    for tool in ("pdftoppm", "pdfinfo"):
        if not shutil.which(tool):
            sys.exit(f"{tool} not found. Install poppler: brew install poppler")
    if not (args.edition / "sources").is_dir():
        sys.exit(f"{args.edition} has no sources/ folder")

    cache = Path(os.environ.get("MANUSCRIPT_LABELER_CACHE", Path.home() / ".cache" / "manuscript-labeler"))
    Handler.edition = Edition(args.edition, cache)
    Handler.edition.train_model()
    Handler.edition.train_crops()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Labeling {Handler.edition.root} at {url}  (Ctrl-C to stop)")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
