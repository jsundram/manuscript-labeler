# /// script
# requires-python = ">=3.11"
# dependencies = ["torch", "transformers", "peft", "pillow", "numpy"]
# ///
"""Closed questions answered from MuSViT's features: how many grace notes,
how many stems carrying two or more heads (a double stop or chord). The
cheapest of the three ways to give the reader a reasoning loop
(reports/2026-11-03-open-model-bars, "Where to go next"): a reasoner asks,
these heads answer, see_test.py's bars score them by d'.

    uv run experiments/musvit/questions.py features [--encoder d5|musvit] [--layers 12]   # once per encoder
    uv run experiments/musvit/questions.py train NAME [--features d5-L12] [--epochs 8]
    uv run experiments/musvit/questions.py test NAME <edition> <see-log>

The encoder is frozen: musvit-D5's (adapters folded in), or MuSViT as
pretrained, before any reading was trained on it. A layer's patch vectors,
(rows, columns, 768), are kept per staff in half precision under
$MUSVIT_QUESTIONS (default ~/Data/manuscript-labeler/musvit/questions),
features-<encoder>-L<layer>/ (12, the last, after its final norm; a middle
layer as it leaves that layer; re-made by `features`). A head gives every patch a count for each question
(a small MLP, then a convolution across columns for context); a staff's
answer is the sum over its patches, a bar's the sum over its columns. It
trains on staff totals alone, read from the staves' LMX (no positions are
labelled): what it learns about where is whatever makes the totals come
out right.

The staves are D5's own training sets (train_b6k.py), less D5's
practice-exam staves (dev-L.txt), kept to choose the pass. The test is
see_test.py's bars of Op48-4 I in F-Po RES 507 (16), a copy no reader
trained on, cut as D5 reads them (compare.staff_crop) from the edition's
export, each bar's columns from its box.
"""

import argparse
import json
import os
import random
import re
import sys
from pathlib import Path
from statistics import NormalDist

import numpy as np
import torch
from torch import nn

MUS = Path(__file__).resolve().parent
sys.path[:0] = [str(MUS), str(MUS.parent / "zeus"), str(MUS.parents[1])]
import proto  # noqa: E402

READER = "D5-B6k-d11-op48x3-s1"  # musvit-D5
STAVES = Path.home() / ".cache/manuscript-labeler/zeus"
SETS = ("dataL2", "dataM5", "dataW4", "dataP4", "dataG213-4")  # train_b6k.py's, Op. 48 from dataL2
HELD_OUT = "samples.D-Dl_Mus.3403-P-513.txt"
OUT = Path(os.environ.get("MUSVIT_QUESTIONS", Path.home() / "Data/manuscript-labeler/musvit/questions"))
QUESTIONS = ("grace", "chord")
Z = NormalDist().inv_cdf


def answers(tokens: list[str]) -> list[int]:
    """A staff's (or a measure's) true counts: grace notes, and stems with
    two or more heads (LMX writes `chord` before each head after a stem's
    first; one stem, however many heads, counts once)."""
    grace = tokens.count("grace")
    chords, prev_chord = 0, False
    for k, t in enumerate(tokens):
        if t == "chord":
            if not prev_chord:
                chords += 1
            prev_chord = True
        elif re.fullmatch(r"[A-G][#b-]*\d", t) and (k == 0 or tokens[k - 1] != "chord"):
            prev_chord = False
    return [grace, chords]


def encoder(device: str, which: str = "d5"):
    """D5's encoder, or MuSViT's as pretrained (read at D5's strip height, as D5 was trained from it)."""
    model, _ = proto.load(READER, "best.pt")  # sets proto.H (96) either way
    if which == "musvit":
        from transformers import ViTModel
        enc = ViTModel.from_pretrained(proto.ENCODERS["full"], add_pooling_layer=False)
        return (enc.to(device).eval().half() if device == "mps" else enc.to(device).eval()), (torch.float16 if device == "mps" else torch.float32)
    model = proto.for_reading(model, device)
    return model.encoder, next(model.parameters()).dtype


@torch.no_grad()
def patches(enc, dtype, device: str, src, layers=(12,)) -> dict[int, np.ndarray]:
    """One staff (a path or encoded bytes) through the encoder: each layer's (rows, cols, D), half precision."""
    x = proto.image(src)
    x = x[None, None].expand(1, 3, *x.shape) if x.dim() == 2 else x[None]
    out = enc(pixel_values=x.to(device, dtype), interpolate_pos_encoding=True, output_hidden_states=True)
    rows = proto.H // proto.PATCH
    got = {}
    for n in layers:
        hs = (out.last_hidden_state if n == 12 else out.hidden_states[n])[0, 1:]
        got[n] = hs.reshape(rows, -1, hs.shape[-1]).float().cpu().numpy().astype(np.float16)
    return got


def training_staves() -> list[tuple[str, Path, list[str], bool]]:
    """(set/samples file, stave path without suffix, its tokens, kept to choose the pass) for every staff D5
    trained or was chosen on: Op. 48's lists as train_b6k.py names them, every other set's samples."""
    lists = {k: {t.split("/staves/")[-1].replace("dataL/", "dataL2/") for t in (MUS / "drivers" / f"{k}-L.txt").read_text().split()}
             for k in ("train", "dev")}
    out = []
    for s in SETS:
        for f in sorted((STAVES / s).glob("samples.*.txt")):
            name = f"{s}/{f.name}"
            if f.name == HELD_OUT or (s == "dataL2" and name not in lists["train"] | lists["dev"]):
                continue
            for line in f.read_text().split():
                p = f.parent / line
                if p.with_suffix(".lmx").exists():
                    out.append((name, p, p.with_suffix(".lmx").read_text().split(), name in lists["dev"]))
    return out


def features(a):
    enc, dtype = encoder(a.device, a.encoder)
    index = []
    staves = training_staves()
    for k, (name, p, toks, dev) in enumerate(staves):
        rel = p.relative_to(STAVES).with_suffix(".npy")
        fs = {n: OUT / f"features-{a.encoder}-L{n}" / rel for n in a.layers}
        if not all(f.exists() for f in fs.values()):
            for n, x in patches(enc, dtype, a.device, p.with_suffix(".jpg"), a.layers).items():
                fs[n].parent.mkdir(parents=True, exist_ok=True)
                np.save(fs[n], x)
        index.append({"file": str(rel), "samples": name, "answers": answers(toks), "dev": dev})
        if k % 250 == 0:
            print(f"{k} of {len(staves)}", flush=True)
    for n in a.layers:
        (OUT / f"index-{a.encoder}-L{n}.json").write_text(json.dumps(index))
    print(f"{len(index)} staves, {sum(i['dev'] for i in index)} kept to choose the pass; "
          f"grace notes {sum(i['answers'][0] for i in index)}, chords {sum(i['answers'][1] for i in index)}")


class Head(nn.Module):
    """Every patch a non-negative count per question, with a little context across columns."""

    def __init__(self, dim=768, d=256):
        super().__init__()
        self.patch = nn.Sequential(nn.LayerNorm(dim), nn.Linear(dim, d), nn.GELU())
        self.across = nn.Conv1d(d, d, 5, padding=2)
        self.out = nn.Linear(d, len(QUESTIONS))

    def forward(self, x):  # (B, rows, cols, D) -> (B, cols, Q): each column's counts, the rows summed
        h = self.patch(x)
        b, r, c, d = h.shape
        h = h + self.across(h.reshape(b * r, c, d).transpose(1, 2)).transpose(1, 2).reshape(b, r, c, d).relu()
        return nn.functional.softplus(self.out(h)).sum(1)


def load_batch(items, tag: str):
    """A batch of staves' vectors; a tag of two sets joined by + gives each patch both, side by side."""
    xs = [np.concatenate([np.load(OUT / f"features-{t}" / i["file"]) for t in tag.split("+")], -1) for i in items]
    c = max(x.shape[1] for x in xs)
    x = torch.zeros(len(xs), xs[0].shape[0], c, xs[0].shape[2])
    mask = torch.zeros(len(xs), c, dtype=torch.bool)
    for k, a in enumerate(xs):
        x[k, :, : a.shape[1]] = torch.from_numpy(a.astype(np.float32))
        mask[k, : a.shape[1]] = True
    return x, mask, torch.tensor([i["answers"] for i in items], dtype=torch.float32)


def staff_counts(head, x, mask):
    return (head(x) * mask[..., None]).sum(1)


def evaluate(head, items, tag, device, bs=16):
    """Per question: staves with the mark that the head says have one, staves without it that it says do; mean abs error."""
    head.eval()
    said, true = [], []
    with torch.no_grad():
        for k in range(0, len(items), bs):
            x, mask, y = load_batch(items[k: k + bs], tag)
            said.append(staff_counts(head, x.to(device), mask.to(device)).cpu())
            true.append(y)
    said, true = torch.cat(said), torch.cat(true)
    out = {}
    for q, name in enumerate(QUESTIONS):
        out[name] = rates([(t > 0, s >= 0.5) for t, s in zip(true[:, q].tolist(), said[:, q].tolist())])
        out[name]["mae"] = (said[:, q] - true[:, q]).abs().mean().item()
    head.train()
    return out


def rates(pairs) -> dict:
    """[(there, said)] -> counts and d' (log-linear correction, as see_figure.py)."""
    pos = [s for t, s in pairs if t]
    neg = [s for t, s in pairs if not t]
    h, f = sum(pos), sum(neg)
    d = Z((h + 0.5) / (len(pos) + 1)) - Z((f + 0.5) / (len(neg) + 1))
    return {"hits": h, "there": len(pos), "false": f, "absent": len(neg), "d": round(d, 2)}


def train(a):
    index = json.loads((OUT / f"index-{a.features.split('+')[0]}.json").read_text())  # every set lists the same staves
    tr, dev = [i for i in index if not i["dev"]], [i for i in index if i["dev"]]
    random.seed(a.seed)
    torch.manual_seed(a.seed)
    head = Head(768 * len(a.features.split("+"))).to(a.device)
    opt = torch.optim.AdamW(head.parameters(), lr=a.lr, weight_decay=0.01)
    run = OUT / "runs" / a.name
    run.mkdir(parents=True, exist_ok=True)
    (run / "config.json").write_text(json.dumps({"features": a.features, "epochs": a.epochs, "lr": a.lr, "seed": a.seed}))
    log, best = [], None
    for ep in range(1, a.epochs + 1):
        random.shuffle(tr)
        total = 0.0
        for k in range(0, len(tr), a.batch_size):
            x, mask, y = load_batch(tr[k: k + a.batch_size], a.features)
            pred = staff_counts(head, x.to(a.device), mask.to(a.device))
            loss = nn.functional.poisson_nll_loss(pred, y.to(a.device), log_input=False)
            opt.zero_grad()
            loss.backward()
            opt.step()
            total += loss.item() * len(y)
        ev = evaluate(head, dev, a.features, a.device)
        score = sum(ev[q]["d"] for q in QUESTIONS)
        log.append({"pass": ep, "loss": total / len(tr), **ev})
        print(json.dumps(log[-1]), flush=True)
        if best is None or score > best:
            best = score
            torch.save(head.state_dict(), run / "best.pt")
    (run / "log.json").write_text(json.dumps(log, indent=1))


def number(v):
    """The export's systems hold numbers and lists as strings."""
    try:
        return json.loads(v) if isinstance(v, str) else v
    except ValueError:
        return v


def test(a):
    """see_test.py's bars: the head's count over each bar's columns, against the final notes."""
    import compare
    tag = json.loads((OUT / "runs" / a.name / "config.json").read_text())["features"]
    sets = [t.rsplit("-L", 1) for t in tag.split("+")]
    head = Head(768 * len(sets)).to(a.device)
    head.load_state_dict(torch.load(OUT / "runs" / a.name / "best.pt", map_location=a.device))
    head.eval()
    entries = [json.loads(l) for l in a.log.read_text().splitlines()]
    truth = {(e["part"], e["bar"], e["question"]): e["true"] for e in entries}
    wanted = {(p, b) for p, b, _ in truth}
    pdf = next(a.edition.glob("sources/*/F-Po_RES-507-16.pdf"))
    export = json.loads(pdf.with_name(pdf.stem + ".bars.json").read_text())
    boxes = [b for b in export["bars"] if b["movement"] == a.movement and (b["part"], b["bar"]) in wanted]
    encs = [encoder(a.device, which) for which, _ in sets]
    said = {}
    for sid in sorted({b["system"] for b in boxes}):
        s = {k: number(v) for k, v in export["systems"][sid].items()}
        g = compare.page_image(pdf, int(s["page"]))
        H_, W_ = g.shape[:2]
        sp = (s["bottom"] - s["top"]) / 4 * H_
        x0 = int(max(0, s["left"] * W_ - sp))
        crop = compare.staff_crop(g, s)
        x = np.concatenate([patches(enc, dtype, a.device, crop, (int(layer),))[int(layer)]
                            for (enc, dtype), (_, layer) in zip(encs, sets)], -1)
        f = torch.from_numpy(x.astype(np.float32))[None].to(a.device)
        with torch.no_grad():
            cols = head(f)[0].cpu()  # (cols, Q)
        im = proto.opened(crop)
        scale = min(proto.MAXW, round(im.width * proto.H / im.height / proto.PATCH) * proto.PATCH) / im.width  # as proto.image
        for b in boxes:
            if b["system"] != sid:
                continue
            xs = [p[0] * W_ for p in b["quad"]]
            c0 = max(0, int((min(xs) - x0) * scale / proto.PATCH))
            c1 = min(cols.shape[0], int(np.ceil((max(xs) - x0) * scale / proto.PATCH)))
            key = (b["part"], b["bar"])
            said[key] = said.get(key, torch.zeros(len(QUESTIONS))) + cols[c0:c1].sum(0)
    out = {}
    for q, name in enumerate(QUESTIONS):
        pairs = [(truth[(p, b, name)] > 0, said[(p, b)][q].item() >= 0.5) for p, b in sorted(wanted) if (p, b) in said]
        out[name] = rates(pairs)
    print(json.dumps(out))
    (OUT / "runs" / a.name / "test.json").write_text(json.dumps(
        {"rates": out, "bars": [{"part": p, "bar": b, **{n: round(said[(p, b)][q].item(), 3) for q, n in enumerate(QUESTIONS)},
                                 **{f"true_{n}": truth[(p, b, n)] for n in QUESTIONS}} for p, b in sorted(said)]}, indent=1))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("features")
    f.add_argument("--encoder", choices=["d5", "musvit"], default="d5")
    f.add_argument("--layers", type=int, nargs="+", default=[12], help="which layers' vectors to keep (12, the last)")
    t = sub.add_parser("train")
    t.add_argument("--features", default="d5-L12", help="<encoder>-L<layer>, as `features` wrote them; two joined by + "
                   "for both side by side")
    t.add_argument("name")
    t.add_argument("--epochs", type=int, default=8)
    t.add_argument("--lr", type=float, default=3e-4)
    t.add_argument("--batch-size", type=int, default=16)
    t.add_argument("--seed", type=int, default=0)
    e = sub.add_parser("test")
    e.add_argument("name")
    e.add_argument("edition", type=Path)
    e.add_argument("log", type=Path, help="a see_test.py log (its bars and their true counts)")
    e.add_argument("--movement", default="I")
    for p in (f, t, e):
        p.add_argument("--device", default="mps" if torch.backends.mps.is_available() else "cpu")
    a = ap.parse_args()
    {"features": features, "train": train, "test": test}[a.cmd](a)


if __name__ == "__main__":
    main()
