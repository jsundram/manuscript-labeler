# /// script
# requires-python = ">=3.11"
# dependencies = ["anthropic", "pillow"]
# ///
"""Can Claude read the text in a mark's box as the editor transcribed it?

    uv run experiments/llm/marks.py <edition-repo> [--limit N] [--mode blind|known]

Every transcribed mark (text, tempo, title, other) on a reviewed page: the
box, with a margin, cut from the page render and sent alone. "blind":
transcribe it, following the copyist's spelling with abbreviations
expanded (the editor's convention). "known": the same, but offered the
texts the editor entered on the reviewed pages of every other source
(not only the same work's; the labeler's /api/marktexts would also offer
unreviewed pages' texts and this source's own), to pick one if it
matches. Scored against the editor's text: exact, and ignoring case,
accents, spacing and punctuation. Cached, saved and asked through
pages.py; an answer is reused only for the same box and, in "known"
mode, the same offered texts.
"""

import argparse
import functools
import hashlib
import io
import json
import sys
import unicodedata
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pages import EFFORT, MODEL, OUT, ask_all, cost, load, render  # noqa: E402
from reader import KNOWN, MARGIN  # noqa: E402
from reader import MARK_KINDS as KINDS  # noqa: E402
from reader import MARK_PROMPT as PROMPT  # noqa: E402
from reader import MARK_SCHEMA as SCHEMA  # noqa: E402
from reader import mark_jpeg as crop  # noqa: E402
from reader import mark_prompt, offered  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import labels  # noqa: E402


def norm(t: str) -> str:
    """Lower case, without accents, punctuation, spaces or line breaks; the
    ordinal's "°" (or "˚") read as "º" (an "o"); other symbols (a fermata
    sign) kept."""
    t = unicodedata.normalize("NFKD", t.replace("°", "º").replace("˚", "º")).lower()
    return "".join(c for c in t if unicodedata.category(c)[0] not in "MPZ"
                   and unicodedata.category(c) not in ("Cc", "Cf"))


def box(m: dict) -> list[float]:
    return [round(m[k], 5) for k in ("x", "y", "w", "h")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edition", type=Path)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--mode", choices=["blind", "known"], default="blind")
    a = ap.parse_args()
    marks = []  # (source, page, mark)
    for lp, pdf in labels.labels_files(a.edition):
        doc = labels.migrate(json.loads(lp.read_text()))
        for n, p in labels.sorted_pages(doc):
            if p.get("status") == "reviewed":
                marks += [(pdf, n, m) for m in p.get("marks", [])
                          if m.get("kind") in KINDS and (m.get("text") or "").strip()
                          and not m.get("text_auto")]  # Claude's own reading isn't the editor's
    texts = {}  # source -> the texts entered in the other sources, most used first
    for pdf in {pdf for pdf, _, _ in marks}:
        count = {}
        for q, _, m in marks:
            if q != pdf:
                count[m["text"].strip()] = count.get(m["text"].strip(), 0) + 1
        texts[pdf] = sorted(count, key=lambda t: (-count[t], t))
    prompts = f"{PROMPT}:{KNOWN}" if a.mode == "known" else PROMPT  # blind never sends KNOWN
    tag = hashlib.sha1(f"{MODEL}:{EFFORT}:{MARGIN}:{a.mode}:{prompts}:{json.dumps(SCHEMA)}".encode()).hexdigest()[:10]
    out = OUT / f"marks-{a.mode}-{tag}.json"
    done = load(out)
    key = lambda pdf, n, m: f"{pdf.stem}:{n}:{m['id']}"
    asked = {key(pdf, n, m): {"box": box(m), **({"offered": offered(texts[pdf])} if a.mode == "known" else {})}
             for pdf, n, m in marks}
    current = lambda k: k in done and all(done[k].get(f) == v for f, v in asked[k].items())
    new = [x for x in marks if not current(key(*x))][: a.limit]

    def requests():
        """Each new mark's crop: a page rendered once for all its marks (when
        the first is asked, so a failure is that mark's) and then let go."""
        page = None
        for pdf, n, m in sorted(new, key=lambda x: (str(x[0]), x[1])):
            if page is None or page[0] != (pdf, n):
                page = ((pdf, n), functools.cache(
                    lambda pdf=pdf, n=n: Image.open(io.BytesIO(render(pdf, n))).convert("RGB")))
            text = mark_prompt(texts[pdf] if a.mode == "known" else [])
            yield key(pdf, n, m), text, SCHEMA, lambda img=page[1], m=m: crop(img(), m), 2000

    failed = ask_all(requests(), done, out, extra=asked.get)
    rows = [(m, done[key(pdf, n, m)], key(pdf, n, m)) for pdf, n, m in marks if current(key(pdf, n, m))]
    print(f"{a.mode}: {len(rows)} of {len(marks)} marks answered, {cost(d for _, d, _ in rows)}; "
          f"{len(new)} asked now, {len(failed)} refused or failed")
    exact = sum(d["text"].strip() == m["text"].strip() for m, d, _ in rows)
    loose = sum(norm(d["text"]) == norm(m["text"]) for m, d, _ in rows)
    print(f"exact {exact}/{len(rows)}; ignoring case, accents, spacing, punctuation {loose}/{len(rows)}")
    for m, d, k in rows:
        if norm(d["text"]) != norm(m["text"]):
            print(f"  {k} [{m['kind']}]: editor {m['text']!r}, Claude {d['text']!r}{'' if d['legible'] else ' (illegible)'}")


if __name__ == "__main__":
    main()
