# /// script
# requires-python = ">=3.11"
# dependencies = ["anthropic", "pillow"]
# ///
"""Can Claude find the text boxes on a title page, and read them?

    uv run experiments/llm/boxes.py <edition-repo> [--limit N] [--overlays DIR]

Every reviewed title page, sent as the labeler sends a page (MAX_SIDE),
asking for each line of writing: its box, in pixels of the image sent,
and its text (the editor's convention: the copyist's spelling,
abbreviations expanded). Each of the editor's marks is matched to the
Claude box that overlaps it most (intersection over union, each box used
once); scored: how many are found (IoU at least 0.5, and at least 0.3),
how far the matched boxes' edges are off, how many of Claude's boxes
match none of the editor's, and whether a matched box's text is the
editor's (ignoring case, accents, spacing and punctuation). --overlays
draws both on each page (the editor's green, Claude's red). Cached,
saved and asked through pages.py.
"""

import argparse
import hashlib
import io
import json
import statistics
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from marks import norm  # noqa: E402
from pages import EFFORT, MAX_SIDE, MODEL, OUT, ask_all, cost, load, page_jpeg, render  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import labels  # noqa: E402

PROMPT = """This is a title page or cover from a scanned late-18th-century manuscript of a string quartet. The image is {w} x {h} pixels.

Find each line of writing on it (a title, a date, a part's name, the composer's name, a dedication) and give its box in pixels of this image, drawn close around the ink: x0, y0 the top-left corner, x1, y1 the bottom-right. Skip library stamps, shelfmarks, and page or folio numbers.

For each, transcribe the text as an editor would type it: the words in full, with the copyist's abbreviations expanded ("All.tto" is "Allegretto") and superscript letters joined, keeping the copyist's spelling, capitals and punctuation otherwise.
"""
SCHEMA = {
    "type": "object",
    "properties": {"lines": {"type": "array", "items": {
        "type": "object",
        "properties": {"text": {"type": "string"}, **{k: {"type": "integer"} for k in ("x0", "y0", "x1", "y1")}},
        "required": ["text", "x0", "y0", "x1", "y1"],
        "additionalProperties": False,
    }}},
    "required": ["lines"],
    "additionalProperties": False,
}


def iou(a, b) -> float:
    """Boxes as (x0, y0, x1, y1), page fractions."""
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    inter = w * h
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


def claude_boxes(d: dict, size) -> list[tuple]:
    """Claude's lines as ((x0, y0, x1, y1) page fractions, text)."""
    w, h = size
    return [((min(l["x0"], l["x1"]) / w, min(l["y0"], l["y1"]) / h, max(l["x0"], l["x1"]) / w,
              max(l["y0"], l["y1"]) / h), l["text"]) for l in d["lines"]]


def match(editor: list[tuple], claude: list[tuple]) -> list[tuple]:
    """Pairs (editor index, Claude index, IoU), best overlap first, each box used once."""
    pairs = sorted(((iou(e[0], c[0]), i, j) for i, e in enumerate(editor) for j, c in enumerate(claude)),
                   reverse=True)
    used_e, used_c, out = set(), set(), []
    for v, i, j in pairs:
        if v > 0 and i not in used_e and j not in used_c:
            used_e.add(i), used_c.add(j)
            out.append((i, j, v))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edition", type=Path)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--overlays", type=Path, help="draw the boxes on each page here")
    a = ap.parse_args()
    tag = hashlib.sha1(f"{MODEL}:{EFFORT}:{MAX_SIDE}:{PROMPT}:{json.dumps(SCHEMA)}".encode()).hexdigest()[:10]
    out = OUT / f"boxes-{tag}.json"
    done = load(out)
    todo = []
    for lp in sorted(a.edition.glob("sources/*/*.labels.json")):
        pdf = lp.with_name(lp.name.replace(".labels.json", ".pdf"))
        doc = labels.migrate(json.loads(lp.read_text()))
        todo += [(pdf, n, p) for n, p in labels.sorted_pages(doc)
                 if p.get("status") == "reviewed" and p.get("kind") == "title"]
    sizes = {}  # the image sent, which Claude's pixels are in

    def image(pdf, n):
        jpeg = page_jpeg(pdf, n)
        sizes[(pdf, n)] = Image.open(io.BytesIO(jpeg)).size
        return jpeg

    def request(pdf, n):
        jpeg = image(pdf, n)
        w, h = sizes[(pdf, n)]
        return f"{pdf.stem}:{n}", PROMPT.format(w=w, h=h), SCHEMA, lambda: jpeg, 8000

    new = [(pdf, n) for pdf, n, _ in todo if f"{pdf.stem}:{n}" not in done][: a.limit]
    failed = ask_all((request(pdf, n) for pdf, n in new), done, out,
                     extra=lambda key: {"size": next(s for (pdf, n), s in sizes.items() if f"{pdf.stem}:{n}" == key)})

    found5 = found3 = total = extra = text_ok = text_n = 0
    edges, rows = [], []
    for pdf, n, p in todo:
        d = done.get(f"{pdf.stem}:{n}")
        if not d:
            continue
        rows.append(d)
        ed = [((m["x"], m["y"], m["x"] + m["w"], m["y"] + m["h"]), (m.get("text") or "").strip(), m["id"])
              for m in p.get("marks", [])]
        cl = claude_boxes(d, d["size"])
        pairs = match(ed, cl)
        total += len(ed)
        found5 += sum(v >= 0.5 for _, _, v in pairs)
        found3 += sum(v >= 0.3 for _, _, v in pairs)
        extra += len(cl) - sum(v >= 0.3 for _, _, v in pairs)
        lines = [f"{pdf.stem} p{n}: {len(ed)} marks, {len(cl)} Claude boxes"]
        for i, j, v in pairs:
            e, c = ed[i], cl[j]
            if v >= 0.3:
                # edge error as a fraction of the page's height (both axes, so it reads as one scale)
                w, h = d["size"]
                edges += [abs(e[0][k] - c[0][k]) * (w / h if k % 2 == 0 else 1) for k in range(4)]
                if e[1]:
                    text_n += 1
                    text_ok += norm(e[1]) == norm(c[1])
            lines.append(f"   {v:.2f} {e[2]} {e[1]!r} / {c[1]!r}")
        for i in set(range(len(ed))) - {i for i, _, v in pairs if v >= 0.3}:
            lines.append(f"   missed {ed[i][2]} {ed[i][1]!r}")
        for j in set(range(len(cl))) - {j for _, j, v in pairs if v >= 0.3}:
            lines.append(f"   extra {cl[j][1]!r}")
        print("\n".join(lines))
        if a.overlays:
            img = Image.open(io.BytesIO(render(pdf, n))).convert("RGB")
            dr = ImageDraw.Draw(img)
            W, H = img.size
            for b, _, _ in ed:
                dr.rectangle([b[0] * W, b[1] * H, b[2] * W, b[3] * H], outline=(0, 160, 0), width=6)
            for b, _ in cl:
                dr.rectangle([b[0] * W, b[1] * H, b[2] * W, b[3] * H], outline=(220, 0, 0), width=4)
            a.overlays.mkdir(parents=True, exist_ok=True)
            img.thumbnail((1400, 1400))
            img.save(a.overlays / f"{pdf.stem}-p{n:02d}.jpg", quality=80)
    print(f"\n{len(rows)} of {len(todo)} title pages answered, {cost(rows)}; {len(new)} asked now, "
          f"{len(failed)} refused or failed")
    print(f"found: {found5}/{total} at IoU >= 0.5, {found3}/{total} at >= 0.3; {extra} Claude boxes match none")
    if edges:
        print(f"edges off (fraction of page height): median {statistics.median(edges):.3f}, "
              f"90th percentile {sorted(edges)[int(0.9 * len(edges))]:.3f}")
    print(f"text of a found box: {text_ok}/{text_n}")


if __name__ == "__main__":
    main()
