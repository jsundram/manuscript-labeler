# /// script
# requires-python = ">=3.11"
# dependencies = ["anthropic", "pillow"]
# ///
"""Can Claude tell a manuscript page's kind and part from the page alone?

    uv run experiments/llm/pages.py <edition-repo> [--limit N] [--sources A,B]

Every reviewed page: its render (the labeler's cache, else pdftoppm),
scaled to MAX_SIDE, sent with no other context; the answer (kind: music,
title, blank, other; part: vn1, vn2, va, vc, score or none) is compared
with the editor's labels. Answers are cached in OUT by source, page,
model and prompt, and saved even when a run stops partway, so a rerun
pays only for what's missing; a refusal or failure is not kept,
so a rerun asks again. The cost is from the kept answers' token counts at
Opus 5.5's price (the models that answered are listed: the server may
fall back to another; "?" for the mark answers saved before ask()
recorded it). The API key is ML_API_KEY in the labeler's .env
(never printed, never ANTHROPIC_API_KEY). The prompt, model and asking
are the labeler's own (reader.py), so this measures what the labeler
asks; marks.py shares this file's render, asking and saving.
"""

import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, as_completed, wait
from pathlib import Path

import anthropic
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
import labels  # noqa: E402
import reader  # noqa: E402
from reader import EFFORT, MAX_SIDE, MODEL, PRICE, ask  # noqa: E402
from reader import PAGE_PROMPT as PROMPT  # noqa: E402
from reader import PAGE_SCHEMA as SCHEMA  # noqa: E402

WORKERS = 4  # calls at once
RENDER_PX, JPEG_QUALITY = 2800, 90  # server.py's
CACHE = Path(os.environ.get("MANUSCRIPT_LABELER_CACHE", Path.home() / ".cache" / "manuscript-labeler")) / "renders"
OUT = Path(__file__).resolve().parent / "answers"


def api_key() -> str:
    return reader.api_key() or sys.exit("no ML_API_KEY in the environment or the labeler's .env")


def render(pdf: Path, page: int) -> bytes:
    """The page as the labeler renders it (JPEG bytes): its cache (keyed as
    server.py's Edition.render keys it, copied here so this needn't import
    the server; a change there only costs cache misses), else pdftoppm."""
    pdf = pdf.resolve()
    st = pdf.stat()
    key = hashlib.sha1(f"{pdf}:{st.st_size}:{st.st_mtime_ns}:{RENDER_PX}:{JPEG_QUALITY}".encode()).hexdigest()[:16]
    p = CACHE / key / f"p{page:03d}.jpg"
    if p.exists():
        return p.read_bytes()
    return subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page), "-scale-to", str(RENDER_PX), "-jpeg",
                           "-jpegopt", f"quality={JPEG_QUALITY}", "-singlefile", str(pdf)],
                          check=True, capture_output=True).stdout


def page_jpeg(pdf: Path, page: int) -> bytes:
    return reader.page_jpeg(Image.open(io.BytesIO(render(pdf, page))))


def load(out: Path) -> dict:
    return json.loads(out.read_text()) if out.exists() else {}


def save(out: Path, done: dict):
    """Atomically: a run killed mid-save leaves the old file."""
    out.parent.mkdir(exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=out.parent, prefix=f".{out.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(done, indent=1, sort_keys=True))
        os.chmod(tmp, 0o644)  # as the files around it (mkstemp makes 0600)
        os.replace(tmp, out)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def ask_all(requests, done: dict, out: Path, extra=lambda key: {}) -> dict[str, str]:
    """Ask each (key, prompt, schema, image, max_tokens) of `requests`, where
    image() makes the JPEG; WORKERS at a time, drawing from `requests` (which
    may be a generator) only as calls finish, so images are made as they're
    needed. Each answer (plus `extra(key)`) goes into `done` and is saved to
    `out` as it comes, those in flight when a run stops too. Returns the
    refusals and failures, the image's own included, which are not kept, as
    key -> why."""
    client, failed, pending = None, {}, {}

    def harvest(f):
        key = pending.pop(f)
        try:
            d = f.result()
        except Exception as e:  # noqa: BLE001 (a bad answer must not lose the others)
            failed[key] = f"{type(e).__name__}: {e}"
            return
        if "error" in d:
            failed[key] = d["error"]
        else:
            done[key] = {**d, **extra(key)}
            try:
                save(out, done)
            except Exception as e:  # noqa: BLE001 (kept in done: the next save may write it)
                print(f"{key}: not saved yet ({type(e).__name__}: {e})", file=sys.stderr)

    pool = ThreadPoolExecutor(WORKERS)
    try:
        for key, prompt, schema, image, max_tokens in requests:
            try:
                jpeg = image()
            except Exception as e:  # noqa: BLE001 (one bad page or box must not stop the run)
                failed[key] = f"image: {type(e).__name__}: {e}"
                continue
            client = client or anthropic.Anthropic(api_key=api_key(), max_retries=4)
            pending[pool.submit(ask, client, prompt, schema, jpeg, max_tokens)] = key
            while len(pending) >= WORKERS:  # so every call sent is running, none queued
                for f in wait(pending, return_when=FIRST_COMPLETED).done:
                    harvest(f)
    finally:
        # on a stop too: the calls already sent are paid for, so keep each as it lands
        try:
            if pending:
                print(f"waiting for the last {len(pending)} calls", file=sys.stderr)
            for f in as_completed(list(pending)):
                harvest(f)
        finally:
            pool.shutdown()
            for key, why in failed.items():
                print(f"{key}: {why}")
    return failed


def cost(answers) -> str:
    """What the answers cost, at Opus 5.5's price, and which models gave them."""
    answers = list(answers)
    usd = sum(d["usage"]["input_tokens"] * PRICE["input"] + d["usage"]["output_tokens"] * PRICE["output"]
              for d in answers) / 1e6
    models = Counter(d.get("model", "?") for d in answers)
    return f"${usd:.2f} (by {', '.join(f'{m} {n}' for m, n in models.most_common())})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edition", type=Path)
    ap.add_argument("--limit", type=int, help="ask about at most N new pages")
    ap.add_argument("--sources", help="comma-separated PDF names (without .pdf)")
    a = ap.parse_args()
    tag = hashlib.sha1(f"{MODEL}:{EFFORT}:{MAX_SIDE}:{PROMPT}:{json.dumps(SCHEMA)}".encode()).hexdigest()[:10]
    out = OUT / f"pages-{tag}.json"
    done = load(out)
    todo = []
    for lp, pdf in labels.labels_files(a.edition):
        if a.sources and pdf.stem not in a.sources.split(","):
            continue
        doc = labels.migrate(json.loads(lp.read_text()))
        for n, p in labels.sorted_pages(doc):
            if p.get("status") == "reviewed":
                todo.append((pdf, n, p))
    new = [(pdf, n, p) for pdf, n, p in todo if f"{pdf.stem}:{n}" not in done][: a.limit]
    failed = ask_all(((f"{pdf.stem}:{n}", PROMPT, SCHEMA, lambda pdf=pdf, n=n: page_jpeg(pdf, n), 4000)
                      for pdf, n, p in new), done, out)
    # score what has been asked
    rows = [(f"{pdf.stem}:{n}", p, done[f"{pdf.stem}:{n}"]) for pdf, n, p in todo if f"{pdf.stem}:{n}" in done]
    kind_ok = [r for r in rows if r[2]["kind"] == r[1]["kind"]]
    with_part = [r for r in rows if r[1]["kind"] in ("music", "title") and r[1].get("part")]
    part_ok = [r for r in with_part if r[2]["part"] == r[1]["part"]]
    said = [r for r in rows if r[2]["part"] != "none"]  # wherever Claude named one
    print(f"{len(rows)} of {len(todo)} pages answered, {cost(d for _, _, d in rows)}; "
          f"{len(new)} asked now, {len(failed)} refused or failed")
    print(f"kind: {len(kind_ok)}/{len(rows)}")
    print(f"part: {len(part_ok)}/{len(with_part)} music and title pages right; named one on {len(said)} pages, "
          f"right on {sum(r[2]['part'] == r[1].get('part') for r in said)}")
    for k, p, d in rows:
        if (d["kind"] != p["kind"] or (p["kind"] in ("music", "title") and p.get("part") and d["part"] != p["part"])
                or (d["part"] != "none" and d["part"] != p.get("part"))):
            print(f"  {k}: editor {p['kind']}/{p.get('part')}, Claude {d['kind']}/{d['part']} ({d['evidence']})")


if __name__ == "__main__":
    main()
