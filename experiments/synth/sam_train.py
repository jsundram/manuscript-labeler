# /// script
# requires-python = ">=3.11"
# dependencies = ["torch==2.14.1", "torchvision", "transformers==5.20.1", "pillow", "numpy"]
# ///
"""Fine-tune Segment Anything 2.1 (small)'s mask decoder on sam_data.py's examples: the image encoder frozen, a point
per head or stem and a box per other symbol, the loss SAM's own (focal 20 : dice 1) against the classical masks.
Each window is padded white to a square (the music isn't stretched) before the model's 1024 x 1024.

    uv run experiments/synth/sam_train.py TRAIN_DIR TEST_DIR OUT_DIR [--epochs 6] [--zero-shot]

Prints, per kind, the mean overlap (IoU) with the held-out windows' masks, before training and after each epoch;
saves the best epoch's decoder weights (OUT_DIR/decoder.pt; by the mean over kinds) and the last (last.pt).
"""
import argparse
import json
import random
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from transformers import Sam2Model

MEAN = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
STD = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)
POINT_KINDS = ("head", "stem")


def load(path: Path) -> dict:
    z = np.load(path)
    img = z["image"]
    h, w = img.shape
    n = len(z["kinds"])
    masks = np.unpackbits(z["masks"], axis=-1)[..., :w].reshape(n, h, w).astype(bool)
    s = max(h, w)
    top, left = (s - h) // 2, (s - w) // 2
    sq = np.full((s, s), 255, np.uint8)
    sq[top:top + h, left:left + w] = img
    msq = np.zeros((n, s, s), bool)
    msq[:, top:top + h, left:left + w] = masks
    pr = z["prompts"].astype(np.float32) + np.array([left, top, left, top], np.float32)
    return {"name": path.stem, "image": sq, "kinds": [str(k) for k in z["kinds"]], "prompts": pr * 1024 / s,
            "masks": msq, "s": s}


def pixels(img: np.ndarray, dev) -> torch.Tensor:
    t = torch.from_numpy(img).float().div(255).expand(3, -1, -1)
    t = F.interpolate(t[None], size=(1024, 1024), mode="bilinear", align_corners=False)[0]
    return ((t - MEAN) / STD)[None].to(dev)


def targets(masks: np.ndarray, dev) -> torch.Tensor:
    t = torch.from_numpy(masks).float()[None]
    return (F.interpolate(t, size=(256, 256), mode="area")[0] > 0.3).float().to(dev)


def predict(model, emb, ex, idx, dev, kind):
    """Low-res mask logits (n, 256, 256) for the examples idx, all points or all boxes."""
    p = torch.from_numpy(ex["prompts"][idx]).to(dev)
    if kind == "point":
        out = model(image_embeddings=emb, input_points=p[None, :, None, :2], input_labels=torch.ones(1, len(idx), 1, dtype=torch.long, device=dev),
                    multimask_output=False)
    else:
        out = model(image_embeddings=emb, input_boxes=p[None], multimask_output=False)
    return out.pred_masks[0, :, 0]


def loss_fn(logits, tgt):
    p = torch.sigmoid(logits)
    ce = F.binary_cross_entropy_with_logits(logits, tgt, reduction="none")
    pt = p * tgt + (1 - p) * (1 - tgt)
    focal = (0.25 * tgt + 0.75 * (1 - tgt)) * (1 - pt) ** 2 * ce
    inter = (p * tgt).sum((1, 2))
    dice = 1 - (2 * inter + 1) / (p.sum((1, 2)) + tgt.sum((1, 2)) + 1)
    return 20 * focal.mean((1, 2)).mean() + dice.mean()


def evaluate(model, data, dev, embed):
    model.eval()
    ious = defaultdict(list)
    with torch.no_grad():
        for ex in data:
            emb = embed(ex)
            tgt = targets(ex["masks"], dev)
            for kind in ("point", "box"):
                idx = np.array([i for i, k in enumerate(ex["kinds"]) if (k in POINT_KINDS) == (kind == "point")])
                if len(idx) == 0:
                    continue
                pred = predict(model, emb, ex, idx, dev, kind) > 0
                t = tgt[idx] > 0.5
                inter = (pred & t).sum((1, 2)).float()
                union = (pred | t).sum((1, 2)).float().clamp(min=1)
                for i, v in zip(idx, (inter / union).tolist()):
                    ious[ex["kinds"][i].split("-")[0] if ex["kinds"][i].startswith(("rest", "flag", "accidental")) else ex["kinds"][i]].append(v)
    model.train()
    return {k: (round(float(np.mean(v)), 3), len(v)) for k, v in sorted(ious.items())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("train", type=Path)
    ap.add_argument("test", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--epochs", type=int, default=6)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--max-per-call", type=int, default=24)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--zero-shot", action="store_true", help="only score the untrained model")
    ap.add_argument("--init", type=Path, help="start from this decoder.pt (an earlier stage's)")
    a = ap.parse_args()
    dev = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
    random.seed(0)
    torch.manual_seed(0)
    model = Sam2Model.from_pretrained("facebook/sam2.1-hiera-small").to(dev)
    if a.init:
        model.load_state_dict(torch.load(a.init, map_location="cpu"), strict=False)
    for p in model.parameters():
        p.requires_grad = False
    for p in list(model.mask_decoder.parameters()) + list(model.prompt_encoder.parameters()):
        p.requires_grad = True
    train = [load(f) for f in sorted(a.train.glob("*.npz"))][: a.limit]
    test = [load(f) for f in sorted(a.test.glob("*.npz"))][: a.limit]
    print(f"{len(train)} training windows, {len(test)} test windows, on {dev}", flush=True)
    cache = {}

    # the frozen encoder's features, once per window, kept on the GPU (about 8 MB a window): the held-out windows
    # always, the training ones while they fit; past that they're recomputed each time (the encoder is quick)
    keep = {ex["name"] for ex in test} | ({ex["name"] for ex in train} if len(train) + len(test) <= 1500 else set())

    def embed(ex):
        if ex["name"] in cache:
            return [f.float() for f in cache[ex["name"]]]
        with torch.no_grad():
            feats = model.get_image_embeddings(pixels(ex["image"], dev))
        if ex["name"] in keep:
            cache[ex["name"]] = [f.half() if dev != "cpu" else f for f in feats]
        return [f.float() for f in feats]

    a.out.mkdir(parents=True, exist_ok=True)
    log = {"zero-shot": evaluate(model, test, dev, embed)}
    print("untrained:" if not a.init else "at the start:", json.dumps(log["zero-shot"]), flush=True)

    def mean_iou(r):  # each kind alike, so heads and stems don't drown the rest
        return float(np.mean([v for v, n in r.values() if n >= 5]))
    best = mean_iou(log["zero-shot"]) if a.init else -1.0
    if a.zero_shot:
        return
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=a.lr, weight_decay=0.01)
    for ep in range(1, a.epochs + 1):
        t0, total, n = time.time(), 0.0, 0
        random.shuffle(train)
        for ex in train:
            emb = embed(ex)
            tgt = targets(ex["masks"], dev)
            for kind in ("point", "box"):
                idx = [i for i, k in enumerate(ex["kinds"]) if (k in POINT_KINDS) == (kind == "point")]
                random.shuffle(idx)
                for c in range(0, len(idx), a.max_per_call):
                    sel = np.array(idx[c:c + a.max_per_call])
                    loss = loss_fn(predict(model, emb, ex, sel, dev, kind), tgt[sel])
                    opt.zero_grad()
                    loss.backward()
                    opt.step()
                    total, n = total + loss.item(), n + 1
        log[f"epoch {ep}"] = evaluate(model, test, dev, embed)
        print(f"epoch {ep}: loss {total / max(1, n):.4f} ({time.time() - t0:.0f} s); test IoU {json.dumps(log[f'epoch {ep}'])}", flush=True)
        weights = {k: v for k, v in model.state_dict().items() if k.startswith(("mask_decoder", "prompt_encoder"))}
        torch.save(weights, a.out / "last.pt")
        if mean_iou(log[f"epoch {ep}"]) > best:  # decoder.pt: the best epoch on the held-out windows
            best = mean_iou(log[f"epoch {ep}"])
            torch.save(weights, a.out / "decoder.pt")
            log["best"] = ep
            print(f"  best so far (mean IoU {best:.3f})", flush=True)
    (a.out / "log.json").write_text(json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
