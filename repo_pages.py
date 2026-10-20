"""The repo's write-ups as web pages, for the labeler's Reports link.

server.py serves /r/<path> from here: reports/ (the index, the journal and
every report), and the docs, experiments and model cards they link to.
Markdown is rendered to a page; images, saved artifact pages and code are
sent as they are. Nothing outside those folders, and nothing but these
kinds of file, is served.
"""
import html
import mimetypes
from pathlib import Path


REPO = Path(__file__).resolve().parent
ROOTS = ("reports", "docs", "experiments", "zeus-score")
MEDIA = {".jpg", ".jpeg", ".png", ".svg", ".gif", ".webp", ".pdf"}
TEXT = {".py", ".sh", ".txt", ".json", ".toml", ".lmx", ".csv"}
INDEXES = ("README.md", "index.html", "index.md")


def _markdown():
    """The renderer, imported on first use so tools that import server.py
    don't need markdown-it-py."""
    from markdown_it import MarkdownIt
    return MarkdownIt("commonmark", {"html": True}).enable(["table", "strikethrough"])  # as GitHub reads the repo's Markdown


STYLE = """
:root { --bg: #f4f2ee; --panel: #fff; --ink: #1f1d1a; --muted: #77726a; --line: #ddd8cf; --accent: #2c5fb8; --code: #efece6; }
@media (prefers-color-scheme: dark) { :root { --bg: #181a1d; --panel: #202327; --ink: #e6e3dc; --muted: #a29d94;
  --line: #34383d; --accent: #8fb0ff; --code: #2a2e33; color-scheme: dark; } }
body { margin: 0; background: var(--bg); color: var(--ink); font: 15px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
nav { padding: 8px 20px; border-bottom: 1px solid var(--line); background: var(--panel); font-size: 13px; }
nav a { margin-right: 14px; }
main { max-width: 900px; margin: 0 auto; padding: 8px 20px 60px; }
a { color: var(--accent); }
h1, h2, h3 { line-height: 1.25; text-wrap: balance; }
h1 { font-size: 26px; } h2 { font-size: 20px; margin-top: 2em; } h3 { font-size: 16px; }
table { border-collapse: collapse; display: block; overflow-x: auto; font-size: 13.5px; margin: 1em 0; }
th, td { border: 1px solid var(--line); padding: 5px 8px; vertical-align: top; text-align: left; }
th { background: var(--code); }
code { background: var(--code); padding: 1px 4px; border-radius: 3px; font-size: 0.9em; }
pre { background: var(--code); padding: 10px 12px; border-radius: 5px; overflow-x: auto; }
pre code { background: none; padding: 0; }
img { max-width: 100%; height: auto; border: 1px solid var(--line); border-radius: 4px; }
blockquote { margin: 1em 0; padding: 0 1em; border-left: 3px solid var(--line); color: var(--muted); }
"""

# a saved artifact page is its body only: give it a document around it
SKELETON = ('<!doctype html><html><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1"></head><body>{}</body></html>')


def resolve(rel: str) -> Path | None:
    """The file or folder /r/<rel> names, if it may be served."""
    p = (REPO / rel).resolve()
    if p != REPO and REPO not in p.parents:
        return None
    parts = p.relative_to(REPO).parts
    if not parts or parts[0] not in ROOTS or any(x.startswith(".") for x in parts):
        return None
    return p if p.exists() else None


def index_of(folder: Path) -> Path | None:
    return next((folder / n for n in INDEXES if (folder / n).is_file()), None)


def page(path: Path) -> tuple[bytes, str] | None:
    """A servable file as (body, content type); None for a kind not served."""
    ext = path.suffix.lower()
    if ext == ".md":
        rel = path.relative_to(REPO)
        body = _markdown().render(path.read_text())
        title = next((line.lstrip("# ").strip() for line in path.read_text().splitlines() if line.startswith("# ")), rel.name)
        doc = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
               f'<meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(title)}</title>'
               f'<style>{STYLE}</style></head><body><nav><a href="/r/reports/index.md">Reports</a>'
               f'<a href="/r/reports/journal.md">Journal</a><a href="/">Labeler</a>'
               f'<span style="color:var(--muted)">{html.escape(str(rel))}</span></nav><main>{body}</main></body></html>')
        return doc.encode(), "text/html; charset=utf-8"
    if ext == ".html":
        text = path.read_text()
        if not text.lstrip()[:15].lower().startswith("<!doctype"):
            text = SKELETON.format(text)
        return text.encode(), "text/html; charset=utf-8"
    if ext in MEDIA:
        return path.read_bytes(), mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if ext in TEXT:
        return path.read_bytes(), "text/plain; charset=utf-8"
    return None
