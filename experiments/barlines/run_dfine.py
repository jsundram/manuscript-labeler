# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = ["transformers>=4.52", "torch", "numpy", "pillow", "timm", "scipy"]
# ///
"""D-FINE (Apache-2.0) fine-tuned on the bar-line tiles, via Hugging Face Transformers.

    uv run experiments/barlines/run_dfine.py <corpus-dir> [--model ustc-community/dfine-small-coco] [--epochs 40]

Starts from COCO-pretrained weights with a new one-class head ("barline"),
trains on the CPU (the Mac GPU backend fails in its backward pass) with random horizontal flips, keeps the
epoch with the lowest validation loss, then runs on the test lines.
"""

import argparse
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import finish  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus", type=Path)
    ap.add_argument("--model", default="ustc-community/dfine-small-coco")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch", type=int, default=8)
    # On the Mac's GPU (MPS) D-FINE's backward pass fails ("mat2 must be a
    # matrix", torch 2.x, with or without empty tiles); the CPU works.
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args()

    import torch
    from PIL import Image, ImageOps
    from transformers import AutoImageProcessor, DFineForObjectDetection

    device = args.device
    tiles = args.corpus / "tiles"
    proc = AutoImageProcessor.from_pretrained(args.model)
    # Tiles are 640 x ~165: the default 640 x 640 input stretches them and
    # spends most of the compute on stretched pixels (18 min an epoch on the
    # CPU); 640 x 192 keeps bar lines at full resolution for a third of that.
    size = {"height": 192, "width": 640}
    model = DFineForObjectDetection.from_pretrained(
        args.model, num_labels=1, id2label={0: "barline"}, label2id={"barline": 0},
        ignore_mismatched_sizes=True).to(device)

    def load(split):
        c = json.loads((tiles / "coco" / f"{split}.json").read_text())
        anns = {}
        for a in c["annotations"]:
            anns.setdefault(a["image_id"], []).append(a)
        return [(tiles / "yolo" / "images" / split / im["file_name"], im, anns.get(im["id"], [])) for im in c["images"]]

    def batch(items, flip):
        imgs, targets = [], []
        for path, im, anns in items:
            img = Image.open(path).convert("RGB")
            boxes = [list(a["bbox"]) for a in anns]
            if flip and random.random() < 0.5:
                img = ImageOps.mirror(img)
                boxes = [[im["width"] - x - w, y, w, h] for x, y, w, h in boxes]
            imgs.append(img)
            targets.append({"image_id": im["id"], "annotations": [
                {"bbox": b, "category_id": 0, "area": b[2] * b[3], "iscrowd": 0} for b in boxes]})
        enc = proc(images=imgs, annotations=targets, return_tensors="pt", size=size)
        labels = [{k: v.to(device) for k, v in t.items()} for t in enc["labels"]]
        return enc["pixel_values"].to(device), labels

    train, val = load("train"), load("val")
    opt = torch.optim.AdamW([
        {"params": [p for n, p in model.named_parameters() if "backbone" in n], "lr": 1e-5},
        {"params": [p for n, p in model.named_parameters() if "backbone" not in n], "lr": 1e-4},
    ], weight_decay=1e-4)
    out = args.corpus / "runs" / "dfine"
    out.mkdir(parents=True, exist_ok=True)
    best, t0 = float("inf"), time.perf_counter()
    for epoch in range(args.epochs):
        model.train()
        random.shuffle(train)
        tl = 0.0
        for i in range(0, len(train), args.batch):
            px, labels = batch(train[i:i + args.batch], flip=True)
            loss = model(pixel_values=px, labels=labels).loss
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 0.1)
            opt.step()
            tl += loss.item()
        model.eval()
        vl = 0.0
        with torch.no_grad():
            for i in range(0, len(val), args.batch):
                px, labels = batch(val[i:i + args.batch], flip=False)
                vl += model(pixel_values=px, labels=labels).loss.item()
        print(f"epoch {epoch + 1}: train {tl:.1f} val {vl:.2f} ({time.perf_counter() - t0:.0f} s)", flush=True)
        if vl < best:
            best = vl
            model.save_pretrained(out / "best")
    train_s = time.perf_counter() - t0

    model = DFineForObjectDetection.from_pretrained(out / "best").to(device).eval()

    def detect_tile(tile):
        with torch.no_grad():
            enc = proc(images=tile, return_tensors="pt", size=size)
            outputs = model(pixel_values=enc["pixel_values"].to(device))
        r = proc.post_process_object_detection(outputs, threshold=0.05, target_sizes=[(tile.height, tile.width)])[0]
        return [(float((b[0] + b[2]) / 2), float(s)) for b, s in zip(r["boxes"].cpu().tolist(), r["scores"].cpu().tolist())]

    finish(args.corpus, f"dfine-{args.model.split('/')[-1]}", detect_tile, train_s,
           f"D-FINE {args.model.split('/')[-1]}, COCO-pretrained, {args.epochs} epochs, {device}")


if __name__ == "__main__":
    main()
