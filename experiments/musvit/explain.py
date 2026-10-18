# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["torch==2.14.1", "transformers==5.20.1", "safetensors==0.8.0", "numpy", "pillow"]
# ///
"""Look inside a MuSViT reader as it reads one staff, for the explainer
page (explainer.html): everything it sees and weighs, saved as one JSON.

    uv run experiments/musvit/explain.py <edition> --source D-B_KHM-603 --movement I --part va --bar 27 \\
        --out va-27.json [--enc-layers all]
    uv run experiments/musvit/explain.py <edition> --source D-B_KHM-603 --movement I --summary --out movement.json [--model ~/.cache/manuscript-labeler/models/musvit/musvit-D3@2026-10-18] \\
        [--results experiments/zeus/results/D-B_KHM-603-I-musvit-D3-tf8-all-mps.json] \\
        [--scores <zeus-score output for the encoding>] [--zeus-results <Zeus J's>] [--light]

The staff holding that bar is cut as the reader was trained on it
(compare.py's crop) and read greedily, one symbol at a time, exactly as
proto.Reader.read_cached reads, with the attention weights kept:

- `meta`: the staff, and what it is part of, read from the edition: the work
  (quartet, key, movement, tempo) and the manuscript (library, shelfmark,
  the catalogue's description);
- `page`: the page (downscaled JPEG) and the staff's box on it;
- `crop`: what the reader sees, 128 px high, and the 8-row grid of 16 px
  patches it cuts it into;
- `enc_attn`: for three encoder layers, where each patch looks: its 48
  strongest targets among the patches (`idx`, uint16) and their weights
  (`val`, the 12 heads averaged, scaled to each patch's strongest, 0-255)
  (left out with --light);
- `steps`: each symbol written, its five likeliest choices, and the bar it
  belongs to; `self_layers`: every decoder layer's look back at the start
  token and the symbols so far (scaled to each row's maximum); `cross`: for each symbol, its attention over the patches in
  each of the 8 decoder layers (heads averaged; scaled to each map's
  maximum; with --light, the layers' average and the last layer only); `heads`: the last layer's 8 heads apart (not with --light);
  `self`: the last layer's attention over the symbols before it;
- `bars`: compare.py's verdict per bar on this reading (its events against
  the encoding's), with the clean test's (where the staff was read in a batch
  of 8, which changes a reading a little) and Zeus J's;
- `scored`: the encoding handed to the reader teacher-forced (zeus-score's
  output): each token's log-probability and the reader's preference.

Arrays are base64 of uint8, row-major, with their shapes beside them.
"""

import argparse
import base64
import hashlib
import io
import json
import math
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "zeus"), str(HERE)]
import compare  # noqa: E402
import proto  # noqa: E402

MODEL = Path.home() / ".cache/manuscript-labeler/models/musvit/musvit-D3@2026-10-18"
RESULTS = HERE.parent / "zeus" / "results"
TOPK = 48  # the encoder's attention: each patch's strongest targets only


def b64(a: np.ndarray) -> str:
    return base64.b64encode(np.ascontiguousarray(a, np.uint8).tobytes()).decode()


def quant(a: np.ndarray) -> np.ndarray:
    """Each map (the last axis) scaled to its maximum, 0-255."""
    m = a.max(-1, keepdims=True)
    return np.round(a / np.where(m > 0, m, 1) * 255).astype(np.uint8)


def jpeg(a, quality=88, width=None) -> str:
    im = Image.fromarray(a) if isinstance(a, np.ndarray) else a
    if width and im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.convert("L").save(buf, "JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode()


@torch.no_grad()
def look(model, vocab, x, mask, light: bool, enc_layers=(0, 5, 11)):
    """Read one staff greedily as Reader.read_cached does, keeping the
    attention: the encoder's (three layers) and the decoder's."""
    enc = model.encoder
    out = {}
    if not light and enc_layers:
        enc.config._attn_implementation = "eager"  # the attention weights, not just their result
        r = enc(pixel_values=x, interpolate_pos_encoding=True, output_attentions=True)
        enc.config._attn_implementation = "sdpa"  # and read as the reader always reads: the same numbers as without the maps
        hs = enc(pixel_values=x, interpolate_pos_encoding=True).last_hidden_state
        att = torch.stack([r.attentions[i][0].float().mean(0)[1:, 1:] for i in enc_layers])  # patches only, heads averaged
        top = att.topk(TOPK, -1)
        out["enc_attn"] = (top.indices.cpu().numpy().astype(np.uint16), quant(top.values.cpu().numpy()))
    else:
        hs = enc(pixel_values=x, interpolate_pos_encoding=True).last_hidden_state
    mem = model.project(hs)  # (1, 1 + patches, d)
    b, d = 1, mem.shape[-1]
    layers = model.decoder.layers
    nh = layers[0].self_attn.num_heads
    hd = d // nh
    see = (~mask)[:, None, None, :]

    def heads(t):
        return t.reshape(b, -1, nh, hd).transpose(1, 2)

    def attend(q, k, v, allow=None):
        w = (q @ k.transpose(-1, -2)) / math.sqrt(hd)
        if allow is not None:
            w = w.masked_fill(~allow, float("-inf"))
        w = w.softmax(-1)
        return (w @ v).transpose(1, 2).reshape(b, -1, d), w[0, :, 0]  # (heads, keys)

    cross = [(heads(F.linear(mem, l.multihead_attn.in_proj_weight[d: 2 * d], l.multihead_attn.in_proj_bias[d: 2 * d])),
              heads(F.linear(mem, l.multihead_attn.in_proj_weight[2 * d:], l.multihead_attn.in_proj_bias[2 * d:])))
             for l in layers]
    past = [[None, None] for _ in layers]
    inv = {i: t for t, i in vocab.items()}
    tok = torch.tensor([vocab[proto.BOS]], device=mem.device)
    steps, cross_maps, head_maps, self_maps = [], [], [], []
    for t in range(proto.MAXLEN - 1):
        h = (model.embed(tok) + model.pos[t])[:, None]
        per_layer, self_rows = [], []
        for li, (l, (ck, cv), kv) in enumerate(zip(layers, cross, past)):
            q, k, v = F.linear(l.norm1(h), l.self_attn.in_proj_weight, l.self_attn.in_proj_bias).chunk(3, -1)
            kv[0] = heads(k) if kv[0] is None else torch.cat([kv[0], heads(k)], 2)
            kv[1] = heads(v) if kv[1] is None else torch.cat([kv[1], heads(v)], 2)
            a, w_self = attend(heads(q), kv[0], kv[1])
            h = h + l.self_attn.out_proj(a)
            q = F.linear(l.norm2(h), l.multihead_attn.in_proj_weight[:d], l.multihead_attn.in_proj_bias[:d])
            a, w_cross = attend(heads(q), ck, cv, see)
            h = h + l.multihead_attn.out_proj(a)
            h = h + l.linear2(l.activation(l.linear1(l.norm3(h))))
            per_layer.append(w_cross[:, 1:].float().cpu().numpy())  # (heads, patches): the CLS token left out
            self_rows.append(w_self.float().mean(0).cpu().numpy())
        p = model.out(model.decoder.norm(h[:, 0])).float().softmax(-1)[0]
        top = p.topk(5)
        tok = top.indices[:1]
        steps.append({"tok": inv[int(tok)], "top": [[inv[int(i)], round(float(v), 4)] for v, i in zip(top.values, top.indices)]})
        cross_maps.append(np.stack([w.mean(0) for w in per_layer]))
        self_maps.append(self_rows)
        head_maps.append(per_layer[-1])
        if int(tok) == vocab[proto.EOS]:
            break
    out["steps"] = steps
    cross_maps = np.stack(cross_maps)  # (T, layers, patches)
    if light:  # the layers' average and the last layer
        cross_maps = np.stack([cross_maps.mean(1), cross_maps[:, -1]], 1)
    out["cross"] = quant(cross_maps)
    if not light:
        out["heads"] = quant(np.stack(head_maps))    # (T, heads, patches)
    # the look back at the symbols so far: the last layer, and the layer that looks back most narrowly
    out["self"] = [[round(float(v), 3) for v in rows[-1]] for rows in self_maps]
    if not light:  # every layer's: (T, layers, T + 1) over the start token and the symbols, zero beyond the present
        T, Ln = len(self_maps), len(self_maps[0])
        full = np.zeros((T, Ln, T + 1), np.float32)
        for t_, rows in enumerate(self_maps):
            for l_, r in enumerate(rows):
                full[t_, l_, : len(r)] = r
        out["self_layers"] = quant(full)
    return out


def judge(lmx: str, staff: list[dict], export: dict, events: dict) -> list[dict]:
    """compare.py's verdict on one staff's reading, bar by bar: its events
    against the encoding's (events: the edition's events.py --json for the
    part and movement). A bar split across staves isn't judged here."""
    part, mvt = staff[0]["part"], staff[0]["movement"]
    times, now = {}, {}
    for b in export["bars"]:
        pm = (b["part"], b["movement"])
        now[pm] = b["signature"].get("time", now.get(pm, "4/4"))
        times[(b["part"], b["movement"], b["bar"])] = now[pm]
    per_bar = Counter((b["part"], b["movement"], b["bar"]) for b in export["bars"] if (b["part"], b["movement"]) == (part, mvt))
    ends: list = []
    measures, _ = compare.parse(lmx, ends)
    if len(measures) != len(staff):
        measures = compare.reconcile(measures, ends, compare.wanted(staff, times, per_bar))
    out = []
    for i, b in enumerate(staff):
        row = {"bar": b["bar"]}
        if per_bar[(part, mvt, b["bar"])] > 1 or len(b["clefs"]) != 1 or str(b["bar"]) not in events:
            out.append({**row, "judged": False})
            continue
        enc = compare.encoded(events[str(b["bar"])])
        if measures is None:
            out.append({**row, "judged": True, "encoded": " ".join(map(compare.text, enc)), "read": "", "exact": False,
                        "errors": ["unread"]})
            continue
        zs = [compare.zeus_event(e, b["clefs"][0]) for e in measures[i]]
        errors = []
        for x, y in compare.align(enc, zs):
            if x is None:
                errors.append("extra")
            elif y is None:
                errors.append("missed")
            elif not compare.same(enc[x], zs[y]):
                errors += compare.what_differs(enc[x], zs[y])
        out.append({**row, "judged": True, "encoded": " ".join(map(compare.text, enc)), "read": " ".join(map(compare.text, zs)),
                    "exact": len(enc) == len(zs) and all(map(compare.same, enc, zs)), "errors": errors})
    return out


def identify(edition: Path, export: dict, movement: str) -> dict:
    """What the staff is part of, from the edition: the work (sources/README.md's
    table, the movement's key and tempo from Op48-<n>/Structure.ily) and the
    manuscript (the library from the siglum list, the table's description)."""
    src = export["source"]
    g, siglum, shelf = src.get("gerard"), src.get("siglum", ""), src.get("shelfmark", "")
    out = {"work": "", "manuscript": f"{siglum} {shelf}".strip(), "short": f"{siglum} {shelf}".strip()}
    readme = edition / "sources" / "README.md"
    text = readme.read_text() if readme.exists() else ""
    libraries = dict(re.findall(r"`([A-Z]{1,3}-[A-Za-z]+)` = ([^.`]+(?:\.[^.`]+)*?)\.", text))
    pdf = Path(src.get("pdf", "")).name
    row = next((l for l in text.splitlines() if pdf and f"`G{g}/{pdf}`" in l), "")
    cells = [c.strip() for c in row.strip().strip("|").split("|")] if row else []
    quartet = next((c for c in reversed([l.split("|")[1].strip() for l in text.splitlines()
                    if l.startswith("| Op.") and text.index(l) <= text.index(row)])), "") if row else ""
    opus = re.match(r"Op\. (\d+)/(\d+), G (\d+)", quartet)
    n = int(opus.group(2)) if opus else (g - 225 if g else None)
    key = tempo = ""
    struct = edition / f"Op48-{n}" / "Structure.ily" if n else None
    if struct and struct.exists():
        m = re.search(r"\\tag #'mvt" + re.escape(movement) + r" \{(.*?)\n\}", struct.read_text(), re.S)
        if m:
            k = re.search(r"\\key ([a-g])(is|es|s)? \\(major|minor)", m.group(1))
            if k:
                key = k.group(1).upper() + {"is": "-sharp", "es": "-flat", "s": "-flat", None: ""}[k.group(2)] + " " + k.group(3)
            tm = re.search(r'\\tempo "([^"]+)"', m.group(1))
            tempo = tm.group(1) if tm else ""
    if opus:
        out["work"] = (f"Boccherini, String Quartet{' in ' + key if key else ''}, Op. {opus.group(1)} No. {opus.group(2)} "
                       f"(G. {opus.group(3)}), movement {movement}" + (f", {tempo}" if tempo else ""))
    library = " ".join(libraries.get(siglum, siglum).split())
    desc = cells[2] if len(cells) > 2 else ""
    first, _, rest = desc.partition(". ")
    if ", " in first:  # the catalogue's shelfmark keeps its brackets: "Paris, Vma ms 1067 (1)"
        shelf = first.split(", ", 1)[1].replace("RES-", "RES ")
    keep = [s for s in re.split(r"(?<=\.)\s+", rest) if s and not re.search(r"images|[Pp]hotograph|photos", s)]
    out["manuscript"] = f"{library}, {shelf} ({siglum})" + (". " + " ".join(keep) if keep else "")
    out["short"] = f"{siglum} {shelf}"
    return out


def events_for(a, export, part):
    if a.events:
        return json.loads((a.events / f"{part}-{a.movement}.json").read_text())
    quartet = f"Op48-{export['source']['gerard'] - 225}"
    return json.loads(subprocess.run(["uv", "run", "--offline", str(a.edition / "scripts" / "events.py"), quartet,
                                      part, a.movement, "--json"], capture_output=True, text=True, check=True).stdout)


def cut(pdf, export, sid, pages={}):
    """The page and the staff's crop, as the reader was trained on it (PNG, and the JPEG it reads)."""
    s = export["systems"][sid]
    if s["page"] not in pages:
        pages.clear()
        pages[s["page"]] = compare.page_image(pdf, s["page"])
    page = pages[s["page"]]
    png = compare.staff_crop(page, s)
    buf = io.BytesIO()
    Image.open(io.BytesIO(png)).convert("L").save(buf, "JPEG", quality=95)
    return page, png, buf.getvalue()


def with_bars(steps, staff):
    """Each symbol's bar: a `measure` token starts the staff's next bar."""
    k = -1
    for st in steps:
        if st["tok"] == "measure":
            k += 1
        st["bar"] = staff[max(k, 0)]["bar"] if k < len(staff) else None


def verdicts(path, part, mvt):
    """compare.py's verdicts per bar from a results file (the clean test, where staves are read in batches of 8)."""
    if not path or not path.exists():
        return {}
    return {b["bar"]: {"read": b["zeus"], "exact": b["exact"], "errors": b["errors"]}
            for b in json.loads(path.read_text())["bars"] if b["part"] == part and b["movement"] == mvt}


def summary(a, pdf, export, model, vocab, dtype):
    """Every staff of the movement read alone: per bar, the verdict, how sure the reader was, and a thumbnail."""
    zres = a.zeus_results or RESULTS / f"{a.source}-{a.movement}-J-lr1e5-e8.model.json"
    out = {"meta": {"source": a.source, "movement": a.movement, "model": a.model.name,
                    **identify(a.edition, export, a.movement)}, "parts": {}}
    for part in ("vn1", "vn2", "va", "vc"):
        boxes = [b for b in export["bars"] if b["part"] == part and b["movement"] == a.movement]
        if not boxes:
            continue
        events, zeus = events_for(a, export, part), verdicts(zres, part, a.movement)
        staves = []
        for sid in dict.fromkeys(b["system"] for b in boxes):
            staff = [b for b in boxes if b["system"] == sid]
            _, png, crop_jpeg = cut(pdf, export, sid)
            x, mask, _, _ = proto.batch([(crop_jpeg, [])], vocab)
            got = look(model, vocab, x.to(a.device, dtype), mask.to(a.device), True, ())
            with_bars(got["steps"], staff)
            reading = [st["tok"] for st in got["steps"] if st["tok"] != proto.EOS]
            bars = judge(" ".join(reading), staff, export, events)
            for b in bars:
                ps = [st["top"][0][1] for st in got["steps"] if st["bar"] == b["bar"]]
                b["sure"] = round(min(ps), 3) if ps else None
                b["unsure"] = [[st["tok"], st["top"][0][1], st["top"][1][0], st["top"][1][1]]
                               for st in got["steps"] if st["bar"] == b["bar"] and st["top"][0][1] < 0.75]
                z = zeus.get(b["bar"])
                b["zeus_j"] = {"exact": z["exact"], "read": z["read"]} if z else None
            seen = (x[0, 0].numpy() * 255).round().astype(np.uint8)
            thumb = Image.fromarray(seen).resize((seen.shape[1] // 2, 64), Image.LANCZOS)
            staves.append({"sid": sid, "page": export["systems"][sid]["page"], "bars": bars, "thumb": jpeg(thumb, 72)})
            print(f"  {part} {sid}: {sum(b.get('exact', False) for b in bars)}/{len(bars)} right", flush=True)
        out["parts"][part] = staves
    a.out.write_text(json.dumps(out, separators=(",", ":")))
    print(f"wrote {a.out} ({a.out.stat().st_size / 1e6:.1f} MB)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edition", type=Path)
    ap.add_argument("--source", default="D-B_KHM-603")
    ap.add_argument("--movement", default="I")
    ap.add_argument("--part")
    ap.add_argument("--bar", type=int, help="any bar on the staff")
    ap.add_argument("--summary", action="store_true", help="every staff of the movement, per bar (no attention)")
    ap.add_argument("--model", type=Path, default=MODEL)
    ap.add_argument("--results", type=Path, help="compare.py's results for the reader (default D3's on the source)")
    ap.add_argument("--zeus-results", type=Path, help="Zeus J's (default its results file for the source)")
    ap.add_argument("--scores", type=Path, help="zeus-score's output for the encoding, by this reader")
    ap.add_argument("--events", type=Path, help="the encoding's events, DIR/<part>-<movement>.json "
                    "(default: the edition's scripts/events.py)")
    ap.add_argument("--light", action="store_true", help="leave out the encoder's attention and the separate heads")
    ap.add_argument("--enc-layers", default="1,6,12", help="encoder layers whose attention to keep: numbers, or all")
    ap.add_argument("--note", default="", help="a caption for the page")
    ap.add_argument("--device", default="mps" if torch.backends.mps.is_available() else "cpu",
                    help="as the clean test read (the Mac's GPU, half precision)")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if not a.summary and (a.part is None or a.bar is None):
        ap.error("give --part and --bar, or --summary")

    pdf = next(a.edition.glob(f"sources/*/{a.source}.pdf"))
    export = json.loads(pdf.with_name(pdf.stem + ".bars.json").read_text())
    model, vocab = proto.load_release(a.model)
    model = proto.for_reading(model, a.device)
    dtype = next(model.parameters()).dtype
    if a.summary:
        return summary(a, pdf, export, model, vocab, dtype)
    n_enc = model.encoder.config.num_hidden_layers
    enc_layers = tuple(range(n_enc)) if a.enc_layers == "all" else tuple(int(v) - 1 for v in a.enc_layers.split(","))

    boxes = [b for b in export["bars"] if b["part"] == a.part and b["movement"] == a.movement]
    sid = next(b["system"] for b in boxes if b["bar"] == a.bar)
    staff = [b for b in boxes if b["system"] == sid]
    s = export["systems"][sid]
    page, png, crop_jpeg = cut(pdf, export, sid)
    x, mask, _, _ = proto.batch([(crop_jpeg, [])], vocab)
    seen = (x[0, 0].numpy() * 255).round().astype(np.uint8)  # what the reader sees: 128 px high
    rows, cols = proto.H // proto.PATCH, x.shape[-1] // proto.PATCH
    got = look(model, vocab, x.to(a.device, dtype), mask.to(a.device), a.light, enc_layers)
    reading = [st["tok"] for st in got["steps"] if st["tok"] != proto.EOS]
    with_bars(got["steps"], staff)

    bars = judge(" ".join(reading), staff, export, events_for(a, export, a.part))
    results = a.results or RESULTS / f"{a.source}-{a.movement}-musvit-D3-tf8-all-mps.json"
    zres = a.zeus_results or RESULTS / f"{a.source}-{a.movement}-J-lr1e5-e8.model.json"
    batch, zeus = verdicts(results, a.part, a.movement), verdicts(zres, a.part, a.movement)
    for b in bars:
        b["clean_test"], b["zeus_j"] = batch.get(b["bar"]), zeus.get(b["bar"])

    # the reading the clean test scored, to say whether this one is the same
    key = f"{sid}:{hashlib.sha1(png).hexdigest()[:10]}"
    cached = HERE.parent / "zeus" / "answers" / f"{a.source}-musvit-D3-tf8-all-mps.json"
    same = None
    if cached.exists() and key in json.loads(cached.read_text()):
        same = json.loads(cached.read_text())[key].split() == reading

    scored = None
    if a.scores and a.scores.exists():
        st = next((r for r in json.loads(a.scores.read_text())["staves"] if r["sid"] == sid), None)
        if st:
            sh = st["shifts"]["0"]
            scored = {"tokens": st["tokens"], "lp": sh["lp"], "best": sh["best"], "best_lp": sh["best_lp"],
                      "bars": st["bars"], "approximate": st["approximate"]}

    H, W = page.shape
    out = {
        "meta": {"source": a.source, "movement": a.movement, "part": a.part, "sid": sid, "page": s["page"],
                 "bars": [b["bar"] for b in staff], "model": a.model.name, "note": a.note,
                 "same_as_clean_test": same, **identify(a.edition, export, a.movement)},
        "page": {"jpg": jpeg(page.astype(np.uint8), 80, 1100), "w": W, "h": H,
                 "box": {k: s[k] for k in ("left", "right", "top", "bottom")}},
        "crop": {"jpg": jpeg(seen, 92), "w": int(seen.shape[1]), "h": int(seen.shape[0]),
                 "hi": jpeg(Image.open(io.BytesIO(png)), 88, 2400), "rows": rows, "cols": cols},
        "steps": got["steps"],
        "cross": {"shape": list(got["cross"].shape), "data": b64(got["cross"]),
                  "layers": ["all"] + [len(model.decoder.layers)] if a.light else list(range(1, len(model.decoder.layers) + 1))},
        "self": got["self"],
        "self_layers": {"shape": list(got["self_layers"].shape), "data": b64(got["self_layers"])} if "self_layers" in got else None,
        "bars": bars,
        "scored": scored,
    }
    if "enc_attn" in got:
        idx, val = got["enc_attn"]
        out["enc_attn"] = {"layers": [i + 1 for i in enc_layers], "shape": list(val.shape),
                           "idx": base64.b64encode(idx.astype("<u2").tobytes()).decode(), "val": b64(val)}
    if "heads" in got:
        out["heads"] = {"shape": list(got["heads"].shape), "data": b64(got["heads"])}
    a.out.write_text(json.dumps(out, separators=(",", ":")))
    print(f"{a.source} {a.part} {sid} bars {staff[0]['bar']}-{staff[-1]['bar']}: {len(reading)} symbols, "
          f"{rows}x{cols} patches; same as the clean test's reading: {same}; {a.out.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
