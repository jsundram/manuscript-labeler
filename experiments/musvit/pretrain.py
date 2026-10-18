# /// script
# requires-python = ">=3.11"
# dependencies = ["torch", "transformers", "pillow", "numpy"]
# ///
"""Go on pretraining MuSViT on our manuscripts, without labels (BRIEF.md;
README.md, "Next"): its own task, rebuilding the 70% of each image's
patches that are hidden (a masked autoencoder), on staves cut from every
page (modal_app.cut_all), at the size the reader reads them (128 px high,
their own width).

    modal run experiments/musvit/modal_app.py::pretrain_main --args "NAME [--epochs 20] [--exclude STEM ...]"

The staves are under /staves/unlabeled/<pdf>/; --exclude leaves out whole
manuscripts (by default the clean test's and the practice exams': seeing
their images, even unlabelled, would flatter the scores). 2% of the staves
are kept back to measure the rebuild. The encoder and its rebuilding
decoder are saved as weights/<NAME>/ in the musvit volume, loadable as
MuSViT is (proto.py: --encoder NAME).
"""

import argparse
import math
import os
import random
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image

CACHE = Path(os.environ.get("MUSVIT_CACHE", Path.home() / ".cache" / "manuscript-labeler" / "musvit"))
H, PATCH, MAXW = 128, 16, 2688
HELD_OUT = ["D-B_KHM-602", "D-B_KHM-603", "F-Po_RES-507-17", "F-Pn_Vma-ms-1067-3"]


def load(path: Path) -> torch.Tensor:
    im = Image.open(path).convert("L")
    w = min(MAXW, max(PATCH, round(im.width * H / im.height / PATCH) * PATCH))
    a = np.asarray(im.resize((w, H), Image.BILINEAR), dtype=np.float32) / 255
    return torch.from_numpy(a)


def batches(items: list[Path], size: int, shuffle: bool):
    """Batches of staves of nearly one width, each cut to the batch's
    narrowest (masking a padded batch would rebuild padding)."""
    widths = {p: Image.open(p).size for p in items}
    order = sorted(items, key=lambda p: widths[p][0] / widths[p][1])
    chunks = [order[k: k + size] for k in range(0, len(order), size)]
    if shuffle:
        random.shuffle(chunks)
    for chunk in chunks:
        ims = [load(p) for p in chunk]
        w = min(i.shape[1] for i in ims)
        yield torch.stack([i[:, :w] for i in ims])[:, None].expand(-1, 3, -1, -1).contiguous()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--base", default="musvit", help="weights/<base>: the MuSViT to go on from")
    ap.add_argument("--staves", type=Path, default=Path("/tmp/staves/unlabeled"))
    ap.add_argument("--exclude", nargs="*", default=[], help="manuscripts to leave out besides the held-out ones")
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--batch-size", type=int, default=32)
    a = ap.parse_args()
    random.seed(0)
    torch.manual_seed(0)
    from transformers import ViTMAEForPreTraining

    a.exclude = HELD_OUT + a.exclude
    items = sorted(p for p in a.staves.rglob("*.jpg") if p.parent.name not in a.exclude)
    random.Random(0).shuffle(items)
    n_dev = max(1, len(items) // 50)
    dev, train = items[:n_dev], items[n_dev:]
    left = sorted({p.parent.name for p in a.staves.rglob("*.jpg")} & set(a.exclude))
    print(f"{len(train)} staves to pretrain on, {len(dev)} kept back; left out: {left}", flush=True)

    model = ViTMAEForPreTraining.from_pretrained(CACHE / "weights" / a.base).cuda()
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=0.05, betas=(0.9, 0.95))
    steps = a.epochs * math.ceil(len(train) / a.batch_size)
    warm = max(1, steps // 20)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1, (s + 1) / warm) * 0.5 * (1 + math.cos(math.pi * min(s, steps) / steps)))

    def rebuild_loss(xs) -> float:
        model.eval()
        total = n = 0
        g = torch.Generator(device="cuda").manual_seed(0)  # the same patches hidden each time
        with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
            for x in xs:
                x = x.cuda()
                noise = torch.rand(x.shape[0], (x.shape[2] // PATCH) * (x.shape[3] // PATCH), device="cuda", generator=g)
                total += model(pixel_values=x, noise=noise, interpolate_pos_encoding=True).loss.item() * x.shape[0]
                n += x.shape[0]
        model.train()
        return total / n

    out = CACHE / "weights" / a.name
    print(f"before: rebuild loss on the kept-back staves {rebuild_loss(batches(dev, a.batch_size, False)):.4f}", flush=True)
    for ep in range(1, a.epochs + 1):
        t0, total, nb = time.time(), 0.0, 0
        for x in batches(train, a.batch_size, True):
            with torch.autocast("cuda", dtype=torch.bfloat16):
                loss = model(pixel_values=x.cuda(), interpolate_pos_encoding=True).loss
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            total, nb = total + loss.item(), nb + 1
        dl = rebuild_loss(batches(dev, a.batch_size, False))
        print(f"epoch {ep:2}  loss {total / nb:.4f}  {time.time() - t0:5.0f} s  kept back {dl:.4f}", flush=True)
        model.save_pretrained(out)


if __name__ == "__main__":
    main()
