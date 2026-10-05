# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow"]
# ///
"""Cut the corpus's lines into detector tiles, in YOLO and COCO formats.

    uv run experiments/barlines/tiles.py <corpus-dir>

Lines are ~2300 x 165 px; shrinking them to a detector's input size would
leave bar lines a pixel or two wide, so they're cut at full resolution into
640 px wide tiles overlapping by 160. Each bar line is one box (class 0,
"barline"): its lean plus most of a staff space wide, the staff's height
plus half a space above and below. 10% of the training lines are held out
as "val" for the detectors' own early stopping; test lines aren't tiled
(models are run on whole test lines by `predict_line`).

Writes <corpus>/tiles/{yolo,coco}/... and <corpus>/tiles/data.yaml.
"""

import json
import random
import sys
from pathlib import Path

from PIL import Image

TILE, STEP = 640, 480


def boxes(line: dict) -> list[tuple[float, float, float, float]]:
    """Bar-line boxes in crop pixels: (x0, y0, x1, y1)."""
    sp = line["space"]
    y0, y1 = line["staff_top"] - 0.5 * sp, line["staff_bottom"] + 0.5 * sp
    out = []
    for b in line["bars"]:
        lean = abs(b["x1"] - b["x0"])
        half = (lean + 0.8 * sp) / 2
        out.append((b["x"] - half, y0, b["x"] + half, y1))
    return out


def windows(width: int) -> list[int]:
    xs = list(range(0, max(1, width - TILE) + 1, STEP))
    if xs[-1] + TILE < width:
        xs.append(width - TILE)
    return xs


def main():
    corpus = Path(sys.argv[1])
    c = json.loads((corpus / "corpus.json").read_text())
    rng = random.Random(7)
    train = [l for l in c["lines"] if l["split"] == "train"]
    rng.shuffle(train)
    val_ids = {l["id"] for l in train[: max(1, len(train) // 10)]}
    out = corpus / "tiles"
    coco = {s: {"images": [], "annotations": [], "categories": [{"id": 1, "name": "barline"}]} for s in ("train", "val")}
    n_img = n_ann = 0
    for line in train:
        split = "val" if line["id"] in val_ids else "train"
        img = Image.open(corpus / line["file"]).convert("L")
        bx = boxes(line)
        for x in windows(line["width"]):
            tile = img.crop((x, 0, x + TILE, line["height"]))
            name = f"{line['id']}-x{x:04d}"
            for d in ("yolo/images", "yolo/labels", "coco"):
                (out / d / split).mkdir(parents=True, exist_ok=True)
            tile.convert("RGB").save(out / "yolo/images" / split / f"{name}.png")
            n_img += 1
            coco[split]["images"].append({"id": n_img, "file_name": f"{name}.png", "width": TILE, "height": line["height"]})
            yl = []
            for (a, b0, c1, d) in bx:
                a2, c2 = max(a - x, 0), min(c1 - x, TILE)
                if c2 - a2 < (c1 - a) * 0.6:  # mostly outside this tile
                    continue
                w, h = c2 - a2, d - b0
                yl.append(f"0 {(a2 + w / 2) / TILE:.6f} {(b0 + h / 2) / line['height']:.6f} {w / TILE:.6f} {h / line['height']:.6f}")
                n_ann += 1
                coco[split]["annotations"].append({"id": n_ann, "image_id": n_img, "category_id": 1,
                                                   "bbox": [a2, b0, w, h], "area": w * h, "iscrowd": 0})
            (out / "yolo/labels" / split / f"{name}.txt").write_text("\n".join(yl))
    for split in coco:
        (out / "coco" / f"{split}.json").write_text(json.dumps(coco[split]))
    (out / "val_ids.json").write_text(json.dumps(sorted(val_ids)))
    (out / "data.yaml").write_text(f"path: {out / 'yolo'}\ntrain: images/train\nval: images/val\nnames:\n  0: barline\n")
    for split in coco:
        print(f"{split}: {len(coco[split]['images'])} tiles, {len(coco[split]['annotations'])} boxes")


if __name__ == "__main__":
    main()
