# /// script
# requires-python = ">=3.11"
# dependencies = ["torch", "transformers", "peft", "safetensors", "pillow", "numpy"]
# ///
"""Would this staff pair now? A quick check for the labeler (server.py
/api/trypair): the editor fixes a staff of a paired manuscript, and asks
whether the pairing would now take it, without a batch re-pair.

    uv run experiments/zeus/trypair.py --serve      # JSON lines on stdin and stdout (the labeler runs this)
    uv run experiments/zeus/trypair.py SOURCE PAGE INDEX    # one staff of the detections, as a test

A request is {"source", "page", "systems": the page's staves as the
labels hold them, "staff": the index of the one to try, from the top}.
The page's staves of the part take the detections' place on that page;
each staff whose crop is new is read here, on the Mac's GPU, with the
released reader (musvit-D4, the pairing's D3S-h96); then autopair.judge
aligns a window of the part (WINDOW staves either side, and the bars the
pairing gave them, MARGIN more either way) with its encoding, and judges
it with the source's options. The encoding is cached on first use
(<cache>/zeus/encodings/): parsing Philhar's LilyPond takes about a
second a movement.

The answer: {"staves": [{"index", "status", "bars", "why", "plain",
"worst"}] for the page's staves of the part in the window, "took"}.
A window is not the whole part: on 300 staves of four sources (Op. 32,
KHM 620, KHM 587, Paris vn1) with the detections' own staves, it gave
the batch's verdict on all 300 (with 12 bars of margin, 290: the bars
past the window's staves skew the alignment's ends). The batch re-pair
(pair_all) is the real count. One reader only, where the older sources'
sets take two readers' agreement.
"""

import argparse
import hashlib
import io
import json
import pickle
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
LABELER = HERE.parents[1]
sys.path[:0] = [str(HERE), str(LABELER), str(HERE.parent / "musvit")]
import autopair  # noqa: E402
import compare  # noqa: E402
import pairing  # noqa: E402

CACHE = Path.home() / ".cache" / "manuscript-labeler"
READER = CACHE / "models" / "musvit" / "musvit-D4@2026-10-20"  # the release of D3S-h96, the pairing's reader
READINGS = "musvit-D3S-h96"
WINDOW = 6   # staves either side of the one tried
MARGIN = 2   # bars either side of those the pairing gave the window's staves
EDITION = Path.home() / "Dropbox/Code/boccherini-opus-48"
QUARTET_LILY = Path.home() / "Dropbox/Code/boccherini-quartet-data/lilypond"
SITE_LILY = Path.home() / "Data/manuscript-labeler/philhar-site/lily"
G213_XML = Path.home() / "Data/manuscript-labeler/zeus/g213/sq8454356_cleaned.musicxml"
PRINT = LABELER / "experiments/print-omr/G223/BA2676-G223.json"
FULL = dict(any_count=True, neighbours=True, neighbours_paired=True, short_ends=True, long_ends=True, head_box=False)


def recipe(source: str) -> dict:
    """The options a source was paired with (philhar-repair/build.sh,
    wayback-print-pairs, g213/README.md): its encoding and autopair's flags."""
    for line in (HERE / "philhar-repair" / "sources.txt").read_text().splitlines():
        f = line.split()
        if f and not line.startswith("#") and f[0] == source:
            return {"encoding": ("philhar", QUARTET_LILY, f[1].split(",")), **FULL}
    for line in (HERE / "wayback-print-pairs" / "sources.txt").read_text().splitlines():
        f = line.split()
        if f and not line.startswith("#") and f[1] == source:
            enc = ("philhar", SITE_LILY, f[3].split(",")) if f[0] == "W" else ("print", PRINT)
            return {"encoding": enc, **FULL, "head_box": True}
    if source.startswith("G213-"):
        return {"encoding": ("musicxml", G213_XML), **FULL, "neighbours_paired": False, "long_ends": False}
    raise LookupError(f"{source}: no recipe (not in philhar-repair, wayback-print-pairs or G. 213)")


def encoding(source: str, part: str, rec: dict):
    """autopair's encoding of the part (blocks, split bars), cached."""
    f = CACHE / "zeus" / "encodings" / f"{source}.{part}.pickle"  # (MusicXML's onsets are Fractions)
    if f.exists():
        return pickle.loads(f.read_bytes())
    kind = rec["encoding"][0]
    if kind == "philhar":
        blocks, split = autopair.philhar_encoding(EDITION, rec["encoding"][1], rec["encoding"][2], part)
    elif kind == "musicxml":
        blocks, split = autopair.musicxml_encoding(rec["encoding"][1], part)
    else:
        blocks, split = autopair.print_encoding(rec["encoding"][1], part)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(pickle.dumps((blocks, split)))
    return blocks, split


def window_blocks(blocks: list, lo: int, hi: int) -> list:
    """The encoding's bars from the lo-th to the hi-th, in its order."""
    out, k = [], 0
    for where, by_bar in blocks:
        keep = {}
        for bar, evs in sorted(by_bar.items(), key=lambda kv: int(kv[0])):
            if lo <= k <= hi:
                keep[bar] = evs
            k += 1
        if keep:
            out.append((where, keep))
    return out


class Reader:
    """The released reader, on the Mac's GPU if there is one: loaded by
    load() (the worker calls it in the background as it starts), or on
    first use."""

    def __init__(self):
        self.model = None
        self.lock = threading.Lock()

    def load(self):
        import proto
        import torch
        with self.lock:
            if self.model is None:
                model, self.vocab = proto.load_release(READER)
                self.device = "mps" if torch.backends.mps.is_available() else "cpu"
                self.model = proto.for_reading(model, self.device)

    def read(self, crops: dict[str, bytes]) -> dict[str, str]:
        import proto
        from PIL import Image
        self.load()
        jpegs = {}
        for key, png in crops.items():  # as read_auto.py saves them (dataset.py's JPEG at 95)
            buf = io.BytesIO()
            Image.open(io.BytesIO(png)).convert("L").save(buf, "JPEG", quality=95)
            jpegs[key] = buf.getvalue()
        dtype = next(self.model.parameters()).dtype
        inv = {i: t for t, i in self.vocab.items()}
        out = {}
        for key, png in jpegs.items():
            x, mask, _, _ = proto.batch([(png, [])], self.vocab)
            ids = self.model.read(x.to(self.device, dtype), mask.to(self.device),
                                  self.vocab[proto.BOS], self.vocab[proto.EOS])[0]
            out[key] = " ".join(inv[i] for i in ids)
        return out


class Trier:
    def __init__(self):
        self.reader = Reader()
        self.readings: dict[str, dict] = {}  # source -> {key: LMX}, the batch's and this session's

    def cache(self, source: str) -> dict:
        if source not in self.readings:
            f = HERE / "answers" / f"{source}-auto-{READINGS}.json"
            self.readings[source] = json.loads(f.read_text()) if f.exists() else {}
        return self.readings[source]

    def run(self, req: dict) -> dict:
        t0 = time.time()
        source, page, target = req["source"], int(req["page"]), int(req["staff"])
        auto = json.loads((HERE / "auto" / f"{source}.json").read_text())
        rec = recipe(source)
        pdf = Path(auto["pdf"])
        here = auto["pages"].get(str(page))
        if not here:
            raise LookupError(f"page {page} of {source} wasn't paired (not a part's page)")
        part = here["part"]
        if part not in autopair.PARTS:
            raise LookupError(f"page {page} is a {part} page: only part pages can be tried yet")
        new = sorted(req["systems"], key=lambda s: s["top"])
        # the part's staves in reading order, the labels' on this page
        staves = []
        for n, p in sorted(auto["pages"].items(), key=lambda kv: int(kv[0])):
            if p.get("part") != part:
                continue
            on = new if int(n) == page else sorted(p["systems"], key=lambda s: s["top"])
            staves += [(f"p{n}-{k}", int(n), s) for k, s in enumerate(on)]
        at = next(i for i, (sid, n, _) in enumerate(staves) if n == page and sid == f"p{page}-{target}")
        lo, hi = max(0, at - WINDOW), min(len(staves), at + WINDOW + 1)
        mine = staves[lo:hi]
        # their readings: the batch's where the crop is the same, else read here
        cache, lmx, crops, aspect, mis, todo = self.cache(source), {}, {}, {}, set(), {}
        pages = sorted({n for _, n, _ in mine})
        for n in pages:
            g = compare.page_image(pdf, n)
            aspect[n] = g.shape[0] / g.shape[1]
            on_page = [(sid, s) for sid, m, s in staves if m == n]
            mis |= autopair.mis_measured(g, on_page)
            for sid, s in on_page:
                if any(sid == x for x, _, _ in mine):
                    crops[sid] = compare.staff_crop(g, s)
        for sid, png in crops.items():
            key = f"{sid}:{hashlib.sha1(png).hexdigest()[:10]}"
            if key in cache:
                lmx[sid] = cache[key]
            else:
                todo[key] = png
        read = self.reader.read(todo) if todo else {}
        cache.update(read)
        for sid, png in crops.items():
            lmx.setdefault(sid, cache[f"{sid}:{hashlib.sha1(png).hexdigest()[:10]}"])
        # the encoding's bars around those the pairing gave the window's staves
        blocks, split = encoding(source, part, rec)
        order = [(*w, int(b)) for w, by_bar in blocks for b in sorted(by_bar, key=int)]
        index = {b: i for i, b in enumerate(order)}
        res = json.loads(pairing.results_file(source).read_text())
        given = {k["staff"]: k.get("bars") or [] for k in res["kept"] + res["not kept"]}
        ids = {sid for sid, n, _ in mine if n != page} | {f"p{n}-{k}" for n in [page]
                                                          for k in range(len(here["systems"]))}
        near = [index[tuple(b)] for sid in ids for b in given.get(sid, []) if tuple(b) in index]
        b0, b1 = (max(0, min(near) - MARGIN), max(near) + MARGIN) if near else (0, len(order))
        a = SimpleNamespace(**{k: v for k, v in rec.items() if k != "encoding"}, band=autopair.BAND, debug=[],
                            musicxml=rec["encoding"][1] if rec["encoding"][0] == "musicxml" else None,
                            print_bars=rec["encoding"][1] if rec["encoding"][0] == "print" else None)
        got = autopair.judge(part, mine, lmx, window_blocks(blocks, b0, b1), split, a, aspect, mis, {}, None)
        verdict = {k["staff"]: ("paired", k) for k in got["kept"]} | {k["staff"]: ("unpaired", k) for k in got["not kept"]}
        out = []
        for sid, n, s in mine:
            if n != page:
                continue
            status, k = verdict.get(sid, ("unknown", {}))
            out.append({"index": int(sid.split("-")[1]), "status": status, "bars": pairing.bars_text(k.get("bars") or []),
                        "why": pairing.explain(k.get("why", [])) if status == "unpaired" else [],
                        "plain": k.get("plain"), "worst": k.get("worst")})
        return {"staves": out, "read": len(read), "window": [mine[0][0], mine[-1][0]], "took": round(time.time() - t0, 1)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("source", nargs="?")
    ap.add_argument("page", nargs="?", type=int)
    ap.add_argument("index", nargs="?", type=int)
    ap.add_argument("--serve", action="store_true", help="answer JSON-line requests on stdin")
    a = ap.parse_args()
    trier = Trier()
    if a.serve:
        print(json.dumps({"ready": True}), flush=True)
        threading.Thread(target=trier.reader.load, daemon=True).start()  # ready by the first staff to read
        for line in sys.stdin:
            try:
                out = trier.run(json.loads(line))
            except Exception as e:  # an answer, never a dead worker
                out = {"error": f"{type(e).__name__}: {e}"}
            print(json.dumps(out), flush=True)
        return
    auto = json.loads((HERE / "auto" / f"{a.source}.json").read_text())
    systems = sorted(auto["pages"][str(a.page)]["systems"], key=lambda s: s["top"])
    print(json.dumps(trier.run({"source": a.source, "page": a.page, "systems": systems, "staff": a.index}), indent=1))


if __name__ == "__main__":
    main()
