# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow"]
# ///
"""Local labeling server.

    uv run server.py <edition-repo> [--port 8048] [--no-open]

Serves the editor (`static/`), renders PDF pages with `pdftoppm`, proposes
staves and bar lines (`detect.py`), and saves labels next to each source PDF:

    <pdf>.labels.json   the editor's working file (schema-versioned)
    <pdf>.bars.json     flat bar export for the synoptic build, rewritten on save

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
import labels  # noqa: E402

HERE = Path(__file__).parent
STATIC = HERE / "static"
RENDER_PX = 2800  # long side of a page render; detect.py was tuned near this
JPEG_QUALITY = 90  # PNG at this size is ~7 MB and takes seconds to encode
BACKUP_EVERY = 60  # seconds between backups of one file
BACKUPS_KEPT = 100


class Edition:
    def __init__(self, root: Path, cache: Path):
        self.root = root.resolve()
        self.cache = cache
        self.write_lock = threading.Lock()
        self.render_locks: dict[str, threading.Lock] = {}
        self.render_locks_lock = threading.Lock()
        self.page_counts: dict[str, int] = {}
        self.prerendering: set[str] = set()
        self.grays: dict[str, object] = {}  # a few decoded pages, for snapping

    # -- paths ---------------------------------------------------------------

    def pdf(self, rel: str) -> Path:
        """Resolve a pdf path from the client, refusing anything outside the edition."""
        p = (self.root / rel).resolve()
        if p.suffix.lower() != ".pdf" or not p.is_file() or self.root not in p.parents:
            raise LookupError(f"no such source: {rel}")
        return p

    def rel(self, p: Path) -> str:
        return p.relative_to(self.root).as_posix()

    @staticmethod
    def labels_path(pdf: Path) -> Path:
        return pdf.with_name(pdf.stem + ".labels.json")

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
        with the kind it's usually given: suggestions for the editor."""
        seen: dict[str, dict] = {}
        for lp in self.root.glob("sources/**/*.labels.json"):
            try:
                doc = json.loads(lp.read_text())
            except (ValueError, OSError):
                continue
            for page in doc.get("pages", {}).values():
                for m in page.get("marks", []):
                    text = (m.get("text") or "").strip()
                    if not text:
                        continue
                    e = seen.setdefault(text, {"text": text, "n": 0, "kinds": {}})
                    e["n"] += 1
                    e["kinds"][m.get("kind", "text")] = e["kinds"].get(m.get("kind", "text"), 0) + 1
        out = sorted(seen.values(), key=lambda e: (-e["n"], e["text"].lower()))
        return [{"text": e["text"], "n": e["n"], "kind": max(e["kinds"], key=e["kinds"].get)} for e in out]

    def load(self, rel: str) -> dict:
        pdf = self.pdf(rel)
        rows = self.readme_rows()
        info = labels.source_info(rel, rows)
        lp = self.labels_path(pdf)
        readonly = None
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
        expected = labels.parse_structure(sp.read_text()) if sp else {}
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
            "labels_file": self.rel(lp),
        }

    # -- saving --------------------------------------------------------------

    def save(self, rel: str, doc: dict, if_match: str) -> dict:
        pdf = self.pdf(rel)
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
            atomic_write(lp, data)
            atomic_write(self.bars_path(pdf), dump(labels.round_floats(labels.bars_export(doc))))
            return {"etag": hashlib.sha1(data).hexdigest()}

    def backup(self, lp: Path, data: bytes):
        d = self.cache / "backups" / self.root.name / self.rel(lp).replace("/", "__").removesuffix(".json")
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

    def detect(self, rel: str, page: int) -> dict:
        from PIL import Image

        import detect

        img = Image.open(self.render(rel, page))
        corners = detect.find_page_corners(img)
        return {"systems": detect.detect_page(img), "corners": corners, "look": detect.page_look(img, corners)}


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
                return self.send_json(ed.detect(q["pdf"], int(q["page"])))
            if path == "/api/snap":
                f = {k: float(q[k]) for k in ("top", "bottom", "x0", "x1")}
                return self.send_json(ed.snap(q["pdf"], int(q["page"]), **f))
            if path == "/api/snapstart":
                f = {k: float(q[k]) for k in ("top", "bottom", "x")}
                return self.send_json(ed.snap_start(q["pdf"], int(q["page"]), **f))
            if path == "/api/bars":
                return self.send_json(labels.bars_export(ed.load(q["pdf"])["labels"]))
            return self.error(HTTPStatus.NOT_FOUND, "not found")
        except (LookupError, KeyError, ValueError) as e:
            return self.error(HTTPStatus.BAD_REQUEST, str(e))
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
