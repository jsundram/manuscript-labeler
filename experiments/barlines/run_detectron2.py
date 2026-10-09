"""Detectron2 (Apache-2.0) Faster R-CNN R50-FPN fine-tuned on the bar-line tiles.

    <venv-with-detectron2>/bin/python experiments/barlines/run_detectron2.py <corpus-dir> [--iters 3000] [--device mps]

Detectron2 has no Mac wheels; build it into its own venv (torch first, then
`pip install --no-build-isolation git+https://github.com/facebookresearch/detectron2.git`
with SDKROOT=$(xcrun --show-sdk-path) and CPLUS_INCLUDE_PATH=$SDKROOT/usr/include/c++/v1).
Starts from COCO-pretrained weights from the model zoo.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import finish  # noqa: E402
from tiles import tile_classes  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus", type=Path)
    ap.add_argument("--iters", type=int, default=3000)
    ap.add_argument("--device", default="mps")
    args = ap.parse_args()

    import numpy as np
    from detectron2 import model_zoo
    from detectron2.config import get_cfg
    from detectron2.data.datasets import register_coco_instances
    from detectron2.engine import DefaultPredictor, DefaultTrainer

    tiles = args.corpus / "tiles"
    runs = args.corpus / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    landmarks = len(tile_classes(args.corpus)) > 1
    for split in ("train", "val"):
        ann = tiles / "coco" / f"{split}.json"
        if landmarks:
            # tiles with the staff's start and end too (corpus.py --paper): this
            # detector learns bar lines only, from a copy of the annotations
            # holding just those (category 1), the same images
            c = json.loads(ann.read_text())
            c["annotations"] = [a for a in c["annotations"] if a["category_id"] == 1]
            c["categories"] = [k for k in c["categories"] if k["id"] == 1]
            ann = runs / f"detectron2-barlines-{split}.json"
            ann.write_text(json.dumps(c))
        register_coco_instances(f"bl_{split}", {}, str(ann), str(tiles / "yolo" / "images" / split))

    cfg = get_cfg()
    cfg.merge_from_file(model_zoo.get_config_file("COCO-Detection/faster_rcnn_R_50_FPN_3x.yaml"))
    cfg.MODEL.WEIGHTS = model_zoo.get_checkpoint_url("COCO-Detection/faster_rcnn_R_50_FPN_3x.yaml")
    cfg.DATASETS.TRAIN, cfg.DATASETS.TEST = ("bl_train",), ()
    # tiles with no bar line (a clef, a margin) teach where there is none: keep them
    cfg.DATALOADER.FILTER_EMPTY_ANNOTATIONS = False
    cfg.DATALOADER.NUM_WORKERS = 2
    cfg.MODEL.ROI_HEADS.NUM_CLASSES = 1
    cfg.MODEL.ROI_HEADS.BATCH_SIZE_PER_IMAGE = 128
    # bar-line boxes are tall and thin: add narrow anchors
    cfg.MODEL.ANCHOR_GENERATOR.ASPECT_RATIOS = [[2.0, 4.0, 8.0]]
    cfg.INPUT.MIN_SIZE_TRAIN, cfg.INPUT.MAX_SIZE_TRAIN = (192,), 640
    cfg.INPUT.MIN_SIZE_TEST, cfg.INPUT.MAX_SIZE_TEST = 192, 640
    cfg.INPUT.RANDOM_FLIP = "horizontal"
    cfg.SOLVER.IMS_PER_BATCH = 8
    cfg.SOLVER.BASE_LR = 0.005
    cfg.SOLVER.MAX_ITER = args.iters
    cfg.SOLVER.STEPS = (int(args.iters * 0.7), int(args.iters * 0.9))
    cfg.SOLVER.CHECKPOINT_PERIOD = 500  # survive an interrupted run
    cfg.MODEL.DEVICE = args.device
    cfg.OUTPUT_DIR = str(runs / "detectron2")
    Path(cfg.OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    trainer = DefaultTrainer(cfg)
    trainer.resume_or_load(resume=False)
    trainer.train()
    train_s = time.perf_counter() - t0

    cfg.MODEL.WEIGHTS = str(Path(cfg.OUTPUT_DIR) / "model_final.pth")
    cfg.MODEL.ROI_HEADS.SCORE_THRESH_TEST = 0.05
    predictor = DefaultPredictor(cfg)

    def detect_tile(tile):
        inst = predictor(np.asarray(tile)[:, :, ::-1])["instances"].to("cpu")
        boxes = inst.pred_boxes.tensor.numpy()
        return [(float((b[0] + b[2]) / 2), float(s)) for b, s in zip(boxes, inst.scores.numpy())]

    finish(args.corpus, "detectron2-faster-rcnn-r50", detect_tile, train_s,
           f"Faster R-CNN R50-FPN, COCO-pretrained, {args.iters} iters, {args.device}")


if __name__ == "__main__":
    main()
