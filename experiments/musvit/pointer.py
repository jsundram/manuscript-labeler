# /// script
# requires-python = ">=3.11"
# dependencies = ["torch", "transformers", "peft", "pillow", "numpy"]
# ///
"""Teach a trained reader to point: given a staff and its LMX (the true one in training; at use, the reader's own or
the edited one), where each note, rest and bar line is. The reader reads the LMX teacher-forced; a small head turns
each symbol's decoder states into a place on the image.

The head: a query from the decoder's state where it writes the symbol and the state after (which has seen it),
attending over the encoder's patches; the place is the attention's expected patch centre plus an offset from the query
and what it attended to. Losses: cross-entropy of the attention against the patch holding the target (against its
column only, for bar lines and rests the map places sideways only), and the place's distance in staff spaces (Huber).

Stage A (--stage A): the reader frozen, only the head trains: does the reader already know where things are?
Stage B (--stage B): the decoder trains too, its reading loss kept (--read-weight), from stage A's head.

    uv run experiments/musvit/pointer.py NAME --run D3-tf8-all --train DIR [...] --test DIR [...] [--stage A]

DIRs hold pos_data.py's staves (<name>.jpg, .lmx, .pos.json). Writes runs/NAME/pointer.pt (and decoder.pt in stage
B), log.json, and predictions.json: for each test staff, [token index, kind, x, y, x predicted, y predicted] in the
image's pixels, with its staff space. On Modal: pointer_modal.py.
"""
import argparse
import json
import math
import random
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn
import torch.nn.functional as F

import proto


def load_dir(d: Path) -> list[dict]:
    out = []
    for f in sorted(d.glob("*.pos.json")):
        p = json.loads(f.read_text())
        name = f.name[: -len(".pos.json")]
        out.append({"name": f"{d.name}/{name}", "jpg": f.with_name(name + ".jpg"),
                    "toks": f.with_name(name + ".lmx").read_text().split(), **p})
    return out


def model_size(w: int, h: int) -> tuple[int, float, float]:
    """The width the reader reads a staff at (proto.image) and the scale from image pixels to its pixels."""
    wm = min(proto.MAXW, round(w * proto.H / h / proto.PATCH) * proto.PATCH)
    return wm, wm / w, proto.H / h


def batch(items: list[dict], vocab: dict):
    x, mask, y_in, y_out = proto.batch([(it["jpg"], it["toks"]) for it in items], vocab)
    tgt = []  # (staff, token, x, y, has y, staff space), in the reader's pixels
    for k, it in enumerate(items):
        _, sx, sy = model_size(it["w"], it["h"])
        for tok, kind, tx, ty in it["targets"]:
            if tok < proto.MAXLEN - 2:
                tgt.append((k, tok, tx * sx, ty * sy, kind not in ("barline", "rest_x"), it["ss"] * sy))
    return x, mask, y_in, y_out, torch.tensor(tgt, dtype=torch.float32).reshape(-1, 6)


class Pointer(nn.Module):
    def __init__(self, d: int = 256):
        super().__init__()
        self.q = nn.Sequential(nn.Linear(2 * d, d), nn.GELU(), nn.Linear(d, d))
        self.k = nn.Linear(d, d)
        self.off = nn.Sequential(nn.Linear(2 * d, d), nn.GELU(), nn.Linear(d, 2))

    def forward(self, hs, mem, mask, staff, tok):
        """hs: decoder states (B, L, d); mem: patches (B, 1 + rows*cols, d), CLS first; staff, tok: (N,) which staff
        and token each target is. The attention over patches (N, rows*cols) and the place (N, 2), in pixels."""
        q = self.q(torch.cat([hs[staff, tok], hs[staff, tok + 1]], -1))
        k = self.k(mem[staff, 1:])
        logits = (k @ q[:, :, None]).squeeze(-1) / math.sqrt(q.shape[-1])
        logits = logits.float().masked_fill(mask[staff, 1:], -1e4)  # not -inf: a padded column's logsumexp would be NaN
        p = torch.softmax(logits, -1)
        n = mem.shape[1] - 1
        cols = n // (proto.H // proto.PATCH)
        idx = torch.arange(n, device=mem.device)
        centre = torch.stack([(idx % cols + 0.5) * proto.PATCH, (idx // cols + 0.5) * proto.PATCH], -1).float()
        ctx = (p[:, :, None] * mem[staff, 1:].float()).sum(1)
        off = torch.tanh(self.off(torch.cat([q.float(), ctx], -1))) * 1.5 * proto.PATCH
        return logits, p @ centre + off, cols


def states(reader, x, mask, y_in):
    """The reader's patches and its decoder's states, teacher-forced on y_in (proto.Reader.decode without .out)."""
    with proto.autocast():
        mem = reader.encode(x)
        L = y_in.shape[1]
        causal = torch.triu(torch.full((L, L), float("-inf"), device=x.device), 1)
        hs = reader.decoder(reader.embed(y_in) + reader.pos[:L], mem, tgt_mask=causal, memory_key_padding_mask=mask)
    return mem, hs


def losses(head, mem, hs, mask, tgt, dev):
    staff, tok = tgt[:, 0].long().to(dev), tgt[:, 1].long().to(dev)
    tx, ty, has_y, ss = (tgt[:, i].to(dev) for i in (2, 3, 4, 5))
    logits, place, cols = head(hs, mem, mask, staff, tok)
    col = (tx // proto.PATCH).clamp(0, cols - 1).long()
    row = (ty // proto.PATCH).clamp(0, proto.H // proto.PATCH - 1).long()
    lp = torch.log_softmax(logits, -1)
    joint = -lp.gather(1, (row * cols + col)[:, None]).squeeze(1)
    colmarg = torch.logsumexp(lp.reshape(len(lp), -1, cols), 1)
    sideways = -colmarg.gather(1, col[:, None]).squeeze(1)
    ce = torch.where(has_y > 0, joint, sideways).mean()
    dx = (place[:, 0] - tx) / ss
    dy = (place[:, 1] - ty) / ss * has_y
    dist = F.huber_loss(dx, torch.zeros_like(dx), delta=0.5) + F.huber_loss(dy, torch.zeros_like(dy), delta=0.5)
    return ce, dist, place


def evaluate(reader, head, data, vocab, dev, bs=8):
    was = reader.training
    head.eval()
    reader.eval()
    out = {}
    data = sorted(data, key=lambda it: it["w"] / it["h"])
    with torch.no_grad():
        for i in range(0, len(data), bs):
            chunk = data[i: i + bs]
            x, mask, y_in, _, tgt = batch(chunk, vocab)
            if not len(tgt):
                continue
            mem, hs = states(reader, x.to(dev), mask.to(dev), y_in.to(dev))
            _, _, place = losses(head, mem.float(), hs.float(), mask.to(dev), tgt, dev)
            for (k, tok, tx, ty, _, _), (px, py) in zip(tgt.tolist(), place.tolist()):
                it = chunk[int(k)]
                _, sx, sy = model_size(it["w"], it["h"])
                kind = next(t[1] for t in it["targets"] if t[0] == int(tok))
                out.setdefault(it["name"], {"ss": it["ss"], "points": []})["points"].append(
                    [int(tok), kind, round(tx / sx, 1), round(ty / sy, 1), round(px / sx, 1), round(py / sy, 1)])
    head.train()
    reader.train(was)
    reader.encoder.eval()
    return out


def summary(pred: dict) -> dict:
    """Per kind: how many, the median error in staff spaces (x and y; x only for bar lines and sideways rests), and
    the share within half a space."""
    errs = {}
    for v in pred.values():
        for tok, kind, tx, ty, px, py in v["points"]:
            ex, ey = abs(px - tx) / v["ss"], abs(py - ty) / v["ss"]
            e = ex if kind in ("barline", "rest_x") else math.hypot(ex, ey)
            errs.setdefault(kind, []).append((e, ex, ey))
    return {k: {"n": len(v), "median": round(float(np.median([e for e, _, _ in v])), 3),
                "median_x": round(float(np.median([x for _, x, _ in v])), 3),
                "median_y": round(float(np.median([y for _, _, y in v])), 3),
                "within_half": round(float(np.mean([e <= 0.5 for e, _, _ in v])), 3)} for k, v in sorted(errs.items())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--run", default="D3-tf8-all")
    ap.add_argument("--train", nargs="+", type=Path, default=[])
    ap.add_argument("--test", nargs="+", type=Path, required=True)
    ap.add_argument("--stage", choices=("A", "B"), default="A")
    ap.add_argument("--init", help="stage B: a stage A run's name, its pointer.pt to start from")
    ap.add_argument("--epochs", type=int, default=6)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--read-weight", type=float, default=1.0, help="stage B: the reading loss's weight")
    ap.add_argument("--bs", type=int, default=8)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--eval-only", action="store_true", help="score --init's head on the test sets, no training")
    a = ap.parse_args()
    dev = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
    random.seed(0)
    torch.manual_seed(0)
    reader, vocab = proto.load(a.run)
    reader = reader.to(dev)
    for p in reader.parameters():
        p.requires_grad = False
    if a.stage == "B":  # the decoder (and its embeddings) learn too; the encoder stays as it is
        for name, p in reader.named_parameters():
            if name.startswith(("decoder.", "embed.", "out.", "project.")):
                p.requires_grad = True
    reader.train(a.stage == "B")
    reader.encoder.eval()
    head = Pointer().to(dev)
    out = proto.CACHE / "runs" / a.name
    out.mkdir(parents=True, exist_ok=True)
    if a.init:
        head.load_state_dict(torch.load(proto.CACHE / "runs" / a.init / "pointer.pt", map_location="cpu"))
        dec = proto.CACHE / "runs" / a.init / "decoder.pt"  # a stage B run's decoder goes with its head
        if dec.exists():
            reader.load_state_dict(torch.load(dec, map_location="cpu"), strict=False)
    if a.eval_only:
        res = {}
        for d in a.test:
            pred = evaluate(reader, head, load_dir(d), vocab, dev)
            res[d.name] = summary(pred)
            (out / f"predictions-{d.name}.json").write_text(json.dumps(pred))
            print(d.name, json.dumps(res[d.name]), flush=True)
        (out / "log.json").write_text(json.dumps({"eval-only": res, "init": a.init}, indent=1))
        return
    train = [it for d in a.train for it in load_dir(d)]
    test = {d.name: load_dir(d) for d in a.test}
    if a.limit:
        random.shuffle(train)
        train = train[: a.limit]
    print(f"{len(train)} training staves; test", {k: len(v) for k, v in test.items()}, "on", dev, flush=True)
    params = list(head.parameters()) + [p for p in reader.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr=a.lr, weight_decay=0.01)
    steps = a.epochs * math.ceil(len(train) / a.bs)
    warm = max(1, steps // 20)  # a short warm-up, then cosine decay
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda i: min(1, (i + 1) / warm) * 0.5 * (1 + math.cos(math.pi * min(1, i / steps))))
    log = {"args": {k: str(v) for k, v in vars(a).items()}}
    for ep in range(1, a.epochs + 1):
        t0, tot = time.time(), np.zeros(3)
        order = sorted(train, key=lambda it: it["w"] / it["h"])  # width-sorted batches, shuffled in order
        chunks = [order[i: i + a.bs] for i in range(0, len(order), a.bs)]
        random.shuffle(chunks)
        for chunk in chunks:
            x, mask, y_in, y_out, tgt = batch(chunk, vocab)
            if not len(tgt):
                continue
            x, mask, y_in, y_out = x.to(dev), mask.to(dev), y_in.to(dev), y_out.to(dev)
            if a.stage == "A":
                with torch.no_grad():
                    mem, hs = states(reader, x, mask, y_in)
            else:
                with torch.no_grad(), proto.autocast():
                    feats = reader.encoder(pixel_values=x, interpolate_pos_encoding=True).last_hidden_state
                with proto.autocast():
                    mem = reader.project(feats)
                    L = y_in.shape[1]
                    causal = torch.triu(torch.full((L, L), float("-inf"), device=dev), 1)
                    hs = reader.decoder(reader.embed(y_in) + reader.pos[:L], mem, tgt_mask=causal, memory_key_padding_mask=mask)
            ce, dist, _ = losses(head, mem.float(), hs.float(), mask, tgt, dev)
            loss = ce + dist
            if a.stage == "B":
                with proto.autocast():
                    logits = reader.out(hs)
                read = F.cross_entropy(logits.float().reshape(-1, logits.shape[-1]), y_out.reshape(-1),
                                       ignore_index=vocab[proto.PAD])
                loss = loss + a.read_weight * read
                tot[2] += read.item()
            opt.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(params, 1.0)
            opt.step()
            sched.step()
            tot[:2] += [ce.item(), dist.item()]
        tot /= max(1, len(chunks))
        res = {}
        for k, v in test.items():
            pred = evaluate(reader, head, v, vocab, dev)
            res[k] = summary(pred)
            (out / f"predictions-{k}.json").write_text(json.dumps(pred))
        log[f"epoch {ep}"] = {"ce": round(tot[0], 4), "dist": round(tot[1], 4), "read": round(tot[2], 4), "test": res}
        print(f"epoch {ep} ({time.time() - t0:.0f} s): ce {tot[0]:.3f} dist {tot[1]:.3f} read {tot[2]:.3f}", flush=True)
        for k, r in res.items():
            print(f"  {k}: " + "; ".join(f"{kind} {s['median']:.2f} sp, {s['within_half']:.0%} ≤½ (n {s['n']})"
                                       for kind, s in r.items()), flush=True)
        torch.save(head.state_dict(), out / "pointer.pt")
        if a.stage == "B":
            torch.save({n: p for n, p in reader.state_dict().items() if n.startswith(("decoder.", "embed.", "out.", "project."))},
                       out / "decoder.pt")
        (out / "log.json").write_text(json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
