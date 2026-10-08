# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow"]
# ///
"""Model cards for the bar-line finders: what each model is, what data went
into it, how it trains, how its training converged, how it does by hand,
and where it could go next.

    uv run experiments/barlines/cards.py <corpus-dir> [--edition <edition-repo>] [--with NAME=DIR ...]

Reads the corpus (corpus.json, tiles/), each method's scored test result
(results/*.json), the detectors' training logs (runs/: Ultralytics'
results.csv and args.yaml, Detectron2's metrics.json) and, if present, the
cross-validation and cross-hand logs in logs/ (crossval.log,
crossval-paper.log, crosshand.log: those scripts' output). With --edition,
records the commit of each source's labels. Writes plain HTML (inline SVG
charts, no scripts) to static/models/, served by the labeler at
/static/models/. Rerun after retraining to refresh the cards.
"""

import argparse
import csv
import html
import itertools
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import cumulative_times  # noqa: E402
from harness import match  # noqa: E402

OUT = HERE.parent.parent / "static" / "models"
HANDS = ["KHM", "Paris A", "Paris B", "Vma"]
HAND_NOTE = {"KHM": "D-B KHM 602 and 603 (Op. 48 Nos. 1, 2), one copyist",
             "Paris A": "F-Po RES 507 (14) (No. 3), Violin I and Cello: one paper and hand",
             "Paris B": "F-Po RES 507 (14), Violin II and Viola: another paper and hand",
             "Vma": "F-Pn Vma ms 1067 (1) (No. 3), a later copy, photographed"}
PARTS = {"vn1": "Violin I", "vn2": "Violin II", "va": "Viola", "vc": "Cello"}
COLORS = ["#2c5fb8", "#d9822b", "#2e7d32", "#7b3fb5", "#c62828", "#77726a"]


def hand(l: dict) -> str:
    if l["source"].startswith("D-B"):
        return "KHM"
    if l["source"].startswith("F-Pn"):
        return "Vma"
    return "Paris A" if l["part"] in ("vn1", "vc") else "Paris B"


def present_hands(c: dict) -> list[str]:
    """The hands with any lines in this corpus, in HANDS order."""
    present = {hand(l) for l in c["lines"]}
    return [h for h in HANDS if h in present]


def hands_in(c: dict) -> list[str]:
    """The hands with test lines in this corpus, in HANDS order."""
    present = {hand(l) for l in c["lines"] if l["split"] == "test"}
    return [h for h in HANDS if h in present]


# -- what each model is: the parts no log records -------------------------

DETECTOR_DATA = ("Tiles 640 px wide (stepping 480) of the straightened lines, at the labeler's "
                 "render size, each bar line a box the staff's height and a staff space wide. "
                 "A tenth of the training lines are validation: early stopping, the confidence "
                 "threshold. The test lines are never seen.")

MODELS = [
    {
        "key": "yolo26n-ends", "status": "labeler", "result": "yolo-yolo26n", "run": "yolo26n", "kind": "ultralytics",
        "corpus": "prod", "heldout": "bl4",
        "title": "YOLO26n with staff ends",
        "links": [("Ultralytics YOLO26 docs", "https://docs.ultralytics.com/models/yolo26/"),
                  ("Ultralytics licensing", "https://www.ultralytics.com/license"),
                  ("our training script", "https://github.com/jsundram/manuscript-labeler/blob/main/experiments/barlines/run_yolo.py"),
                  ("how the labeler uses it", "https://github.com/jsundram/manuscript-labeler/blob/main/detections.py")],
        "summary": "YOLO26n trained on the reviewed lines (a tenth held back for testing), cut across the paper's width, to box bar lines and also "
                   "where each staff starts (its clef, key and time) and ends. The labeler's cached detector for both.",
        "card": {
            "Architecture": "YOLO26 nano: single-stage detector, end to end (no NMS step)",
            "Parameters": "about 2.4 million (published)",
            "Starting weights": "yolo26n.pt, COCO-pretrained (Ultralytics)",
            "Licence": "AGPL-3.0 (Ultralytics); fine for the editor's own use, not bundled with the MIT labeler",
            "Input": "a 640 px tile of a staff straightened across the paper's whole width, 3 staff spaces above and below",
            "Output": "boxes of three classes: \"barline\" (its centre is the bar line), \"start\" (from the staff's left end to "
                      "where the music starts) and \"end\" (centred on the staff's right end)",
            "Where it runs": "in the labeler from 2026-10-08: its predictions for every page are cached "
                             "(tools/predict_barlines.py); it votes on each staff's bar lines, and its surest start and end "
                             "boxes (at least 0.25 sure) set the staff's ends and music start (detections.make_ends)",
        },
        "how": [
            "As YOLO26n's bar-line model, with two more classes. corpus.py --paper cuts each reviewed staff across the paper's width "
            "(as the labeler's cache does) and records the editor's left end, music start and right end; tiles.py boxes the "
            "region from the left end to the music start as \"start\" and a staff space around the right end as \"end\", "
            "only where a tile holds all of the box. Mirroring is off: it would turn an end into a start.",
            "This is the model for use, trained on every reviewed source with a tenth of the lines held back (its test lines). "
            "How it does on a copy it never saw comes from the same recipe trained without F-Pn Vma ms 1067 (1) (below).",
        ],
        "measured": (
            "<h2 style='margin-top:12px'>Staff ends and music starts, in the labeler</h2>"
            "<p>The held-out model's starts and ends, cached and used by the labeler's detection, against the editor's, "
            "on the held-out corpus's test lines (experiments/barlines/landmarks.py; results.md, 2026-10-07). "
            "Share within 1 staff space / over 3; then the labeler's bar line errors, the model in the vote.</p>"
            "<table><tr><th></th><th>familiar: before</th><th>familiar: with it</th><th>Vma: before</th><th>Vma: with it</th></tr>"
            "<tr><td>left end</td><td>71% / 21%</td><td>90% / 3%</td><td>81% / 13%</td><td>89% / 4%</td></tr>"
            "<tr><td>music start</td><td>44% / 37%</td><td>81% / 6%</td><td>81% / 17%</td><td>86% / 6%</td></tr>"
            "<tr><td>right end</td><td>56% / 22%</td><td>95% / 2%</td><td>79% / 3%</td><td>96% / 0%</td></tr>"
            "<tr><td>bar line errors</td><td>18 of 431</td><td>6</td><td>29 of 376</td><td>26</td></tr></table>"
            "<p class='muted'>Before: the earlier YOLO26n in the vote and the rules for the ends. Shares are over the lines "
            "where the model answers too (all but 2 Vma lines). Measured 2026-10-07 and written here by hand, not recomputed "
            "by this script: rerun landmarks.py after a retrain. The 'before' column ran on the GPU with the earlier cache "
            "format, the others on predictions made on the CPU.</p>"),
        "future": [
            "Mosaics off for the start and end classes: a mosaic seam can clip a box tiles.py kept whole.",
            "Kinds of bar line (double, repeat, final) as classes, and the clef as a class of the start box, from the editor's clef marks.",
            "Retrain as more copies are reviewed; each new hand so far has helped the next.",
            "D-FINE small (Apache-2.0) on the same lines, held out the same way: the best of the earlier models on an unseen copy.",
        ],
    },
    {
        "key": "yolo26n", "status": "retired", "result": "yolo-yolo26n", "run": "yolo26n", "kind": "ultralytics",
        "title": "YOLO26n",
        "links": [("Ultralytics YOLO26 docs", "https://docs.ultralytics.com/models/yolo26/"),
                  ("Ultralytics licensing", "https://www.ultralytics.com/license"),
                  ("our training script", "https://github.com/jsundram/manuscript-labeler/blob/main/experiments/barlines/run_yolo.py")],
        "summary": "Ultralytics' newest small detector, fine-tuned to box bar lines on tiles of the straightened lines.",
        "card": {
            "Architecture": "YOLO26 nano: single-stage detector, end to end (no NMS step), small-target-aware label assignment",
            "Parameters": "about 2.4 million (published)",
            "Starting weights": "yolo26n.pt, COCO-pretrained (Ultralytics)",
            "Licence": "AGPL-3.0 (Ultralytics); fine for the editor's own use, not bundled with the MIT labeler",
            "Input": "a 640 px tile of a straightened staff line, 3 staff spaces above and below",
            "Output": "boxes with confidences; a bar line is the centre of a box above the threshold",
            "Where it runs": "in the labeler's bar-line vote from 2026-10-07 (cached by tools/predict_barlines.py); retired 2026-10-08 for YOLO26n with staff ends",
        },
        "how": [
            "Training starts from weights already trained on COCO's everyday photographs and adjusts all of them to one class, "
            "\"bar line\". Each epoch shows the network every training tile once, with random changes (shifts, scaling, colour, "
            "mosaics of four tiles) so it learns the stroke rather than the tiles. After each epoch it is scored on the "
            "validation tiles; the best epoch's weights are kept.",
            "YOLO26 differs from YOLO11 mainly in training: it predicts one box per object directly (no overlap "
            "suppression afterwards), drops the box-shape distribution loss, and assigns small objects to the network's outputs "
            "with more care, which suits strokes 2-4 pixels wide.",
        ],
        "future": [
            "More labelled hands: each new copyist's pages, reviewed in the labeler, are new training data (the corpus is rebuilt from reviewed pages).",
            "Longer training: box tightness (mAP50-95) and validation loss were still improving at the last epoch; recall had levelled off.",
            "Larger variants (YOLO26s, m) if the nano model's errors plateau; at a few times the cost per line.",
            "YOLO27 and later: a drop-in swap (--model), retrained on the same tiles and compared here.",
            "Classes for double, repeat and final bar lines, which the labeler records but the detector doesn't yet tell apart.",
            "As the learned filter's proposer: its boxes as candidates (or a feature) for the cheap filter that retrains on save.",
            "A permissively licensed alternative of similar speed (RT-DETR, D-FINE: Apache-2.0) if it should ship with the labeler.",
        ],
    },
    {
        "key": "yolo11n", "status": "labeler", "result": "yolo-yolo11n", "run": "yolo11n", "kind": "ultralytics",
        "title": "YOLO11n",
        "links": [("Ultralytics YOLO11 docs", "https://docs.ultralytics.com/models/yolo11/"),
                  ("our training script", "https://github.com/jsundram/manuscript-labeler/blob/main/experiments/barlines/run_yolo.py")],
        "summary": "Ultralytics' previous small detector, fine-tuned to box bar lines on tiles of the straightened lines.",
        "card": {
            "Architecture": "YOLO11 nano: single-stage detector with NMS",
            "Parameters": "about 2.6 million (published)",
            "Starting weights": "yolo11n.pt, COCO-pretrained (Ultralytics)",
            "Licence": "AGPL-3.0 (Ultralytics); fine for the editor's own use, not bundled with the MIT labeler",
            "Input": "a 640 px tile of a straightened staff line, 3 staff spaces above and below",
            "Output": "boxes with confidences; a bar line is the centre of a box above the threshold",
            "Where it runs": "in the labeler: one of the two cached detectors in the bar-line vote (tools/predict_barlines.py)",
        },
        "how": [
            "Training starts from weights already trained on COCO's everyday photographs and adjusts all of them to one class, "
            "\"bar line\". Each epoch shows the network every training tile once, with random changes (shifts, scaling, colour, "
            "mosaics of four tiles) so it learns the stroke rather than the tiles. After each epoch it is scored on the "
            "validation tiles; the best epoch's weights are kept.",
        ],
        "future": [
            "Superseded by YOLO26n if that matches or beats it; kept for comparison.",
            "More labelled hands, longer training (box tightness still rising at the last epoch), larger variants.",
        ],
    },
    {
        "key": "yolo26n-mlx", "status": "experiment", "result": "yolo-mlx-yolo26n", "run": "yolo26n-mlx", "kind": "mlx",
        "title": "YOLO26n on MLX",
        "summary": "The same YOLO26 nano, trained and run natively on Apple silicon with MLX instead of PyTorch.",
        "links": [("yolo-mlx", "https://github.com/thewebAI/yolo-mlx"), ("MLX", "https://github.com/ml-explore/mlx"),
                  ("Ultralytics YOLO26 docs", "https://docs.ultralytics.com/models/yolo26/"),
                  ("our training script", "https://github.com/jsundram/manuscript-labeler/blob/main/experiments/barlines/run_yolo_mlx.py")],
        "card": {
            "Architecture": "YOLO26 nano, reimplemented in MLX (thewebAI/yolo-mlx)",
            "Parameters": "about 2.4 million (published)",
            "Starting weights": "Ultralytics' yolo26n.pt (COCO), converted to MLX",
            "Licence": "AGPL-3.0 (yolo-mlx, following Ultralytics)",
            "Input": "a 640 px tile of a straightened staff line, 3 staff spaces above and below",
            "Output": "boxes with confidences; a bar line is the centre of a box above the threshold",
            "Where it runs": "experiments only (experiments/barlines/run_yolo_mlx.py, in yolo-mlx's own environment)",
        },
        "how": [
            "The YOLO26 network and its training rebuilt on MLX, Apple's array library, which runs on the Mac's GPU without "
            "PyTorch. Its authors report about twice the inference speed and 2.6 times the training speed of PyTorch's MPS "
            "backend. Training follows Ultralytics' schedule, but its augmentation is simpler: colour, flips, scale and "
            "shift, no mosaics. It logs a single training loss and Ultralytics' validation metrics per epoch.",
            "Here it was slower, not faster: about 4 minutes an epoch against Ultralytics' 83 seconds on the same GPU. "
            "The GPU sat 13-43% busy: yolo-mlx prepares each batch (loading, augmenting) on one CPU thread, and other "
            "work was running on the machine, so the timing isn't a clean comparison. Its checkpoints hold only the "
            "weights, so a run cut off at the 2-hour job limit can't resume; this one ran 25 epochs (Ultralytics' 50).",
        ],
        "future": [
            "If it matches Ultralytics' accuracy, the fast way to retrain YOLO on this Mac, and a lighter dependency than PyTorch for the labeler.",
            "Mosaic augmentation and 50 epochs, to see whether they close the gap to Ultralytics' YOLO26n (35 errors against 16).",
            "Faster batch preparation (several workers, as Ultralytics does), so the GPU isn't left waiting; then a clean timing on an idle machine.",
            "A young project (its last commit June 2026): check it keeps up with Ultralytics.",
        ],
    },
    {
        "key": "dfine", "status": "experiment", "result": "dfine-dfine-small-coco", "run": "dfine", "kind": "dfine",
        "title": "D-FINE small",
        "summary": "A transformer detector (DETR family, 2024), fine-tuned to box bar lines on the same tiles; Apache-licensed.",
        "links": [("D-FINE paper (2024)", "https://arxiv.org/abs/2410.13842"), ("D-FINE code", "https://github.com/Peterande/D-FINE"),
                  ("Hugging Face transformers docs", "https://huggingface.co/docs/transformers/model_doc/d_fine"),
                  ("pretrained weights", "https://huggingface.co/ustc-community/dfine-small-coco"),
                  ("our training script", "https://github.com/jsundram/manuscript-labeler/blob/main/experiments/barlines/run_dfine.py")],
        "card": {
            "Architecture": "D-FINE: a real-time DETR (transformer decoder over a convolutional backbone) that refines box edges as distributions; no NMS",
            "Parameters": "about 10 million (published, small)",
            "Starting weights": "ustc-community/dfine-small-coco (COCO), via Hugging Face transformers",
            "Licence": "Apache-2.0",
            "Input": "a 640 px tile of a straightened staff line, resized to 640 × 192",
            "Output": "a fixed set of boxes with confidences; a bar line is the centre of a box above the threshold",
            "Where it runs": "experiments only; trains on the Mac's GPU with a one-line workaround (dfine_patch.py)",
        },
        "how": [
            "Instead of scoring anchors, a transformer decoder sends a fixed number of queries over the tile's features; "
            "each query becomes one box or \"nothing\". Training matches queries to the editor's bar lines one to one (the "
            "Hungarian algorithm) and penalises the mismatch, so there is no overlap suppression afterwards. D-FINE's "
            "contribution is to predict each box edge as a probability distribution, refined layer by layer.",
            "Our run: AdamW (learning rate 1e-4, 1e-5 for the backbone), batches of 8 tiles, random horizontal flips, "
            "40 epochs; the epoch with the lowest validation loss is kept. Resumable after the 2-hour job limit (--resume).",
            "On the Mac's GPU, transformers' D-FINE fails in training (\"mat2 must be a matrix\"): one layer weights its "
            "bin probabilities with F.linear and a 1-D vector, whose backward pass PyTorch's MPS backend mishandles "
            "(pytorch/pytorch#188891; a fix, #188931, is in review). dfine_patch.py writes the same sum as a matrix "
            "product: identical results, and about 2.8 times faster than training on the CPU.",
        ],
        "future": [
            "The Apache-licensed choice if a detector should ship with the labeler.",
            "Drop dfine_patch.py once PyTorch ships the fix (#188931); report the 1-D F.linear to transformers so D-FINE works on MPS for everyone.",
            "Its larger sizes (medium, large) if small plateaus; RT-DETR v2 as a sibling to compare.",
        ],
    },
    {
        "key": "detectron2", "status": "experiment", "result": "detectron2-faster-rcnn-r50", "run": "detectron2", "kind": "detectron2",
        "title": "Detectron2 Faster R-CNN",
        "links": [("Detectron2", "https://github.com/facebookresearch/detectron2"),
                  ("model zoo", "https://github.com/facebookresearch/detectron2/blob/main/MODEL_ZOO.md"),
                  ("Faster R-CNN paper (2015)", "https://arxiv.org/abs/1506.01497"),
                  ("Feature Pyramid Networks paper (2017)", "https://arxiv.org/abs/1612.03144"),
                  ("our training script", "https://github.com/jsundram/manuscript-labeler/blob/main/experiments/barlines/run_detectron2.py")],
        "summary": "Meta's two-stage detector (ResNet-50 with a feature pyramid), fine-tuned to box bar lines on the same tiles.",
        "card": {
            "Architecture": "Faster R-CNN, ResNet-50 FPN backbone; anchors narrowed for tall thin boxes (aspect 2, 4, 8)",
            "Parameters": "about 41 million (published)",
            "Starting weights": "COCO-pretrained faster_rcnn_R_50_FPN_3x (Detectron2 model zoo)",
            "Licence": "Apache-2.0",
            "Input": "a 640 px tile of a straightened staff line, scaled to 192 px high",
            "Output": "boxes with confidences; a bar line is the centre of a box above the threshold",
            "Where it runs": "experiments only; needs a source build on macOS (see run_detectron2.py)",
        },
        "how": [
            "A two-stage detector: a region-proposal network suggests places that might hold a bar line, and a second head "
            "classifies and refines each. Training starts from COCO weights and runs a fixed number of iterations (batches of "
            "8 tiles) with a learning rate that drops at 70% and 90% of the run. It doesn't score itself on the validation "
            "tiles while training; only its losses are logged, so the chart shows those.",
            "Its confidence threshold is chosen on the validation lines. On a hand it has never seen, its confidences fall "
            "below that threshold: trained on KHM alone it missed 41-57% of the Paris bar lines at its KHM threshold.",
        ],
        "future": [
            "The most accurate model here and Apache-2.0, but about a second per line and a source build on macOS: a candidate for a \"detect harder\" button rather than every page.",
            "More labelled hands; a threshold that adapts to a new hand (or a confidence calibration step) so it doesn't go quiet on unfamiliar ink.",
            "Faster: a smaller backbone, CoreML export, or distilling it into the small models.",
        ],
    },
    {
        "key": "learned", "status": "labeler", "result": "learned-labeler", "run": None, "kind": "learned",
        "also": [("on the straightened lines (run_learned.py --widths --paper: the editor's staves, not detected ones)",
                  "learned-gbm-widths-paper")],
        "title": "Learned filter (labeler)",
        "links": [("scikit-learn HistGradientBoostingClassifier", "https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html"),
                  ("learn.py", "https://github.com/jsundram/manuscript-labeler/blob/main/learn.py"), ("detect.py (candidates)", "https://github.com/jsundram/manuscript-labeler/blob/main/detect.py")],
        "summary": "Gradient-boosted trees choosing among detection's candidate strokes, in two passes (the second sees the bar widths). What the labeler runs.",
        "card": {
            "Architecture": "candidate strokes (detect.candidates) + HistGradientBoosting (scikit-learn), two passes",
            "Parameters": "up to 300 trees of up to 15 leaves, per pass (fewer if scikit-learn's early stopping, on by default above 10,000 candidates, ends training sooner)",
            "Starting weights": "none: trained from scratch on the editor's reviewed pages",
            "Licence": "BSD-3 (scikit-learn); the labeler is MIT",
            "Input": "each candidate stroke's measurements: staff coverage (whole, by thirds), lean, width, darkness, note heads attached, ink beyond the staff, neighbours, distance from the music start; second pass adds the first pass's probability and the bar widths it implies",
            "Output": "bar lines, none closer than 4 staff spaces",
            "Where it runs": "in the labeler (learn.py): retrained in the background when a reviewed page changes",
        },
        "how": [
            "Detection searches every column of a straightened staff, at many leans, for strokes covering much of the staff's "
            "height, loosely (faint bar lines included). Each candidate gets a few measurements; the editor's bar lines say which "
            "candidates are bar lines. A gradient-boosted classifier learns from those examples; a second pass adds each "
            "candidate's first-pass probability and the bars it would make with its neighbours (a missed bar line leaves a bar "
            "twice the typical width). The second pass learns from first passes that never saw its pages.",
            "Training takes seconds, so the labeler retrains whenever a reviewed page changes. It can only choose among "
            "candidates: a bar line too faint to become one is missed whatever it has learned. Shifting each staff so its "
            "paper reads the same (ink = 66 levels darker than its paper) brought the Paris second hand's bar lines from 76% "
            "to 98% candidates.",
        ],
        "future": [
            "More reviewed pages: it retrains on its own; pages of a new hand help most where its candidates already reach the bar lines.",
            "The candidate stage is its ceiling: better proposals (a detector's boxes as candidates or as a feature) would lift it.",
            "Per-hand context: features relative to the line's own ink and paper, so a faint hand isn't read as faint strokes.",
            "The KHM cost of the looser ink cutoff (more false bar lines): a feature or second threshold to win it back.",
        ],
    },
    {
        "key": "rules", "status": "labeler", "result": "classical", "run": None, "kind": "rules",
        "title": "Hand-tuned rules",
        "links": [("detect.py (find_barlines)", "https://github.com/jsundram/manuscript-labeler/blob/main/detect.py"),
                  ("the tuning tool", "https://github.com/jsundram/manuscript-labeler/blob/main/tools/tune_barlines.py")],
        "summary": "The original bar-line tests in detect.py: tuned by hand against the editor's corrections on KHM 602.",
        "card": {
            "Architecture": "rules: full-height stroke, no note head attached, spacing, a fainter pass where a bar is too wide",
            "Parameters": "a dozen constants (detect.py)",
            "Starting weights": "none",
            "Licence": "MIT (this repository)",
            "Input": "a straightened staff",
            "Output": "bar lines",
            "Where it runs": "in the labeler until a learned model exists",
        },
        "how": [
            "No training. The rules below (detect.find_barlines) run on each straightened staff, after the clef and key "
            "signature. Their constants were tuned by grid search against the editor's corrections on KHM 602 pages 2, 3 "
            "and 6 (tools/tune_barlines.py), then re-tuned on KHM 602 and 603. They know nothing of other hands: every "
            "number is in staff spaces, but the ink cutoff is a fixed grey level.",
        ],
        "steps": [
            ("Ink", "A pixel is ink if darker than 120 (of 255). Fixed: the faint brown ink of the Paris copy's second hand is "
             "mostly lighter, which is why the rules miss two thirds of its bar lines."),
            ("Stroke coverage", "For every column, try straight strokes leaning from −0.3 to +0.3 (horizontal pixels per "
             "vertical pixel, in steps of 0.03) and keep the lean whose stroke crosses the most ink between the top and "
             "bottom staff lines. Coverage is that share of the staff's height."),
            ("Skip the clef and key", "Columns before the music start are ignored."),
            ("Candidate strokes", "Runs of neighbouring columns (gaps of up to 3 pixels) whose coverage is over COVER of the "
             "staff's height. A run wider than 0.6 staff spaces is a beam or a smudge, not a line."),
            ("Not a stem", "Walk along the stroke from a space above the staff to a space below, skipping the staff lines' "
             "rows, and measure the ink running across it. A note head or a beam is wider than ATTACH_WIDTH spaces; if "
             "more than ATTACH_ROWS spaces' worth of rows are that wide, the stroke is a stem."),
            ("Double bars", "Strokes closer than 1.2 staff spaces are one double bar (or the thick and thin lines of a repeat)."),
            ("Bars are wide", "No two bar lines closer than MIN_BAR staff spaces: of a tighter cluster, keep the stroke "
             "with the least ink across it."),
            ("Faint bar lines", "Bars on a line are roughly even. Where a gap is more than WIDE_GAP times the line's typical "
             "bar, accept a weaker stroke (coverage over FAINT) at least MIN_BAR spaces from either end, the strongest "
             "near the middle of the gap."),
            ("The line's end", "The search runs a staff space past the ruled lines' end, where a final bar line often sits."),
        ],
        "future": ["Retired in favour of the learned filter wherever reviewed pages exist; kept as the fallback and the baseline.",
                   "Its stroke search and stem test live on inside the learned filter as candidate measurements."],
    },
]


GLOSSARY = [
    ("Found, false, missed", "Our measure, and the one that matters: a bar line is found if the model puts one within 0.6% "
     "of the page width (about a staff space) of the editor's; a false one is a bar line where the editor has none (a "
     "delete in the labeler), a missed one an editor's bar line with none near it (a click). Errors = false + missed."),
    ("Confidence", "The detector's score, 0 to 1, that a box holds a bar line. Every box comes with one; we keep the boxes "
     "above a threshold, chosen on the validation lines to make the fewest errors."),
    ("Precision, recall", "Of the boxes kept, the share that are bar lines (precision); of the bar lines, the share that "
     "were boxed (recall). Ultralytics reports them per validation tile at its own confidence cut-off."),
    ("Box", "What the detectors learn to draw: a rectangle the staff's height plus half a space each way, one staff space "
     "wide, centred on each of the editor's bar lines. Its edges are a convention we chose; only its centre's x is used."),
    ("Overlap (IoU)", "How much a predicted box and a true box coincide: the area they share divided by the area either "
     "covers. 1 is the same box; 0.5 is a box shifted by about a third of its width."),
    ("mAP50", "Mean average precision: precision averaged over every confidence threshold (the area under the "
     "precision-recall curve), counting a box right if its overlap with a true box is at least 0.5. Close to our "
     "measure: a bar line boxed roughly in the right place."),
    ("mAP50-95, box tightness", "The same averaged over overlap cut-offs 0.50, 0.55 … 0.95, so it rewards boxes whose "
     "edges match the true box exactly (box tightness). Our measure ignores the edges, so this keeps rising after the "
     "bar lines are already found."),
    ("Epoch, iteration", "An epoch is one pass over every training tile (YOLO). An iteration is one batch of 8 tiles "
     "(Detectron2); 3000 iterations is about 23 passes over the tiles."),
    ("Training, validation, test lines", "Training lines teach the model; validation lines (a tenth of the training "
     "lines, held out) pick the epoch and threshold and show progress; test lines are scored once at the end and "
     "never influence anything."),
]

LOSSES = {
    "ultralytics": [
        ("What a loss is", "A number the training lowers, batch by batch, by adjusting the network's weights: how far its "
         "boxes and scores on the training tiles are from the editor's. It has no units (it's built from overlaps and "
         "log-probabilities); only its trend and the gap between training and validation mean anything. The validation "
         "losses are the same numbers on tiles it never trains on: if they stop falling while the training ones keep "
         "going, it is memorising."),
        ("Box loss", "1 − CIoU for each box matched to a bar line: the overlap, less penalties for the distance between "
         "centres and the difference in shape. 0 when a box sits exactly on the truth. Weighted 7.5 in the total."),
        ("Class loss", "Binary cross-entropy of the \"bar line\" score at every place the network looks: low when it is "
         "confident where there is a bar line and quiet where there isn't. Weighted 0.5."),
        ("Shape loss (DFL, YOLO11)", "YOLO11 predicts each box edge as a distribution over positions; this loss pulls "
         "those towards the true edge. YOLO26 drops it and predicts edges directly."),
        ("How it relates to our goal", "Most of the box loss is about the box's top, bottom and width, which we don't use; "
         "the class loss and the box's horizontal centre are what decide whether a bar line is found. That's why the "
         "card also shows our measure on the validation lines at each saved checkpoint."),
    ],
    "dfine": [
        ("What a loss is", "A number the training lowers, batch by batch: how far the detector's boxes and scores on the "
         "training tiles are from the editor's, after matching each of its queries to at most one bar line. No units; "
         "averaged per tile. The training and validation losses are not comparable: in training D-FINE adds "
         "denoising queries (noisy copies of the true boxes to repair) and losses at every decoder layer, which "
         "evaluation leaves out, so the training loss is about ten times the validation loss by construction. Watch "
         "each line's own trend."),
        ("Its parts", "A classification loss (varifocal: the score should equal the box's overlap with its bar line), "
         "an L1 distance and a generalised-overlap (GIoU) loss on the boxes, and D-FINE's own losses on the edge "
         "distributions, summed over the decoder's layers."),
        ("How it relates to our goal", "As with the other detectors, much of it is about box edges we don't use; "
         "whether a bar line is found depends on the score and the box's centre, shown below on the validation lines."),
    ],
    "detectron2": [
        ("What a loss is", "A number the training lowers, batch by batch: how far the detector's proposals, scores and "
         "boxes on the training tiles are from the editor's. No units; only the trend means anything. Detectron2 logs "
         "only the training losses, so our measure on the validation lines (from its saved checkpoints) shows whether "
         "it generalises."),
        ("Proposal losses", "The first stage proposes places that might hold a bar line: a cross-entropy for "
         "\"something here or not\" at each anchor box, and a smooth-L1 distance for how far each anchor must move "
         "and stretch to fit."),
        ("Classification loss", "Cross-entropy of \"bar line\" against \"background\" for 128 proposals per tile."),
        ("Box regression loss", "Smooth-L1 distance between the predicted and true corrections to each proposal's "
         "centre and size, relative to the proposal's own size."),
        ("How it relates to our goal", "Total loss is the sum of the four. As with YOLO, much of it is about box edges "
         "we don't use; whether a bar line is found depends on the classification score and the box's centre."),
    ],
}


ENDS_TERM = ("Start, end boxes", "On the staff-ends model only, two classes beside the bar line's box: a start box the "
             "staff's height from its left end to where the music starts, and an end box a staff space wide centred on its "
             "right end. Its class loss, confidences and Ultralytics' metrics cover all three; found, false and missed count "
             "bar lines only.")


def glossary(ends: bool = False) -> str:
    return ("<section class='card'><h2>Terms</h2><dl class='gloss'>"
            + "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in GLOSSARY + ([ENDS_TERM] if ends else []))
            + "</dl></section>")


def losses(kind: str) -> str:
    if kind not in LOSSES:
        return ""
    return ("<h2 style='margin-top:12px'>The losses</h2><dl class='gloss'>"
            + "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in LOSSES[kind]) + "</dl>")


def trainviz(run: Path, unit: str, minutes_of=None) -> str:
    """Our measure at each saved checkpoint, the last one's confidences, and drawings (trainviz.py)."""
    p = run / "trainviz.json"
    if not p.exists():
        return ("<p class='note'>No checkpoints judged yet: run experiments/barlines/trainviz.py on this run "
                "(YOLO needs --save-period when training).</p>")
    tv = json.loads(p.read_text())
    cks = tv["checkpoints"]
    if minutes_of:  # the same clock as the loss charts
        for ck in cks + tv.get("examples", []):
            n = re.findall(r"\d+", ck["label" if "label" in ck else "checkpoint"])
            if n:
                ck["minutes"] = minutes_of(int(n[0]))
    mins = [ck["minutes"] for ck in cks]
    v = tv["validation"]
    # a first checkpoint that has barely started would flatten the rest of
    # the curve: cap the axis at the others and say so
    errs_ = [ck["false"] + ck["missed"] for ck in cks]
    rest = max(errs_[1:], default=0)
    cap = None
    if len(errs_) > 2 and errs_[0] > 4 * max(rest, 1):
        cap = (0, nice_step(rest * 1.3, 4) * -(-(rest * 1.3) // nice_step(rest * 1.3, 4)) or 1)
    off = (f"The first checkpoint ({cks[0]['label']}, {cks[0]['minutes']:.0f} min) is off the scale: "
           f"{cks[0]['false']} false, {cks[0]['missed']} missed. " if cap else "")
    out = chart(f"Finding bar lines on the {v['lines']} validation lines ({v['bar_lines']} bar lines), at each saved {unit}",
                [("errors (false + missed)", mins, [ck["false"] + ck["missed"] for ck in cks]),
                 ("false", mins, [ck["false"] for ck in cks]), ("missed", mins, [ck["missed"] for ck in cks])],
                "minutes of training", "bar lines",
                top=[(ck["minutes"], re.sub(r"^\D+", "", ck["label"])) for ck in cks], top_label=unit + "s", ylim=cap,
                note=off + "Each checkpoint at the confidence threshold best for it on these lines.")
    cf = tv.get("confidence")
    if cf:
        out += histogram(f"Confidences of the last checkpoint's detections on the validation lines",
                         [("on a bar line", cf["bar_lines"]), ("not on a bar line", cf["not_bar_lines"])], cf["threshold"],
                         note=f"Detections below 0.05 aren't reported. {cf['never_proposed']} bar line{'' if cf['never_proposed'] == 1 else 's'} had no detection "
                              f"near {'it' if cf['never_proposed'] == 1 else 'them'} at all. Detections right of the threshold are kept: blue ones are found bar lines, "
                              "orange ones false bar lines; blue left of it are bar lines missed at this threshold. The "
                              "wider the empty gap between the colours, the less the threshold matters.")
    ex = tv.get("examples", [])
    if ex:
        out += ("<div class='examples'><h2 style='margin-top:12px'>What it found during training</h2>"
                "<p class='key note'>One validation line per hand at the first, middle and last checkpoint: "
                "<span style='background:#2e7d32'></span>found (with confidence) <span style='background:#c62828'></span>false "
                "<span style='background:#d9822b'></span>missed (lower half).</p>")
        for e in ex:
            out += (f"<figure><img src='{esc(e['file'])}' alt='{esc(e['caption'])}'>"
                    f"<figcaption>{esc(e['caption'])} · {e['minutes']:.0f} min · found {e['found']}, false {e['false']}, "
                    f"missed {e['missed']}</figcaption></figure>")
        out += "</div>"
    return out


# -- reading --------------------------------------------------------------

def read_csv(p: Path) -> list[dict]:
    """Rows as numbers; a `time` column made cumulative across resumed runs
    (Ultralytics restarts its clock when a run resumes)."""
    with p.open() as f:
        rows = [{k.strip(): float(v) for k, v in r.items() if v not in ("", None)} for r in csv.DictReader(f)]
    if rows and "time" in rows[0] and "epoch" in rows[0]:
        times = cumulative_times([int(r["epoch"]) for r in rows], [r["time"] for r in rows], p.parent)
        for r, t in zip(rows, times):
            r["time"] = t
    return rows


def epoch_minutes(rows: list[dict]):
    """epoch -> minutes since the start, for trainviz's checkpoints."""
    by = {int(r["epoch"]): r["time"] / 60 for r in rows}
    return lambda e: by.get(e, 0.0)


def read_yaml(p: Path) -> dict:
    out = {}
    for line in p.read_text().splitlines():
        m = re.match(r"^(\w+):\s*(.*)$", line)
        if m:
            out[m[1]] = m[2]
    return out


def by_hand(c: dict, res: dict) -> dict:
    test = [l for l in c["lines"] if l["split"] == "test"]
    out = {}
    for h in HANDS + ["all"]:
        f = fp = m = 0
        for l in test:
            if h != "all" and hand(l) != h:
                continue
            a, b, d = match(res["lines"].get(l["id"], []), [bb["x"] for bb in l["bars"]], c["tolerance_frac"] * l["page_w"])
            f, fp, m = f + a, fp + b, m + d
        out[h] = (f, fp, m)
    return out


def parse_crossval(p: Path) -> dict:
    """{method: {"all": (f, fp, m), source: (f, fp, m)}} from crossval.py's output."""
    out, cur = {}, None
    if not p.exists():
        return out
    for line in p.read_text().splitlines():
        m = re.match(r"^(\S+): all \d+ lines: found (\d+), false (\d+), missed (\d+)", line)
        if m:
            cur = m[1]
            out[cur] = {"all": tuple(int(x) for x in m.groups()[1:])}
            continue
        m = re.match(r"^\s+(\S+): found (\d+), false (\d+), missed (\d+)", line)
        if m and cur:
            out[cur][m[1]] = tuple(int(x) for x in m.groups()[1:])
    return out


def parse_crosshand(p: Path) -> dict:
    """{target hand: [(label, f, fp, m, per100)], "settings": its settings
    line} from crosshand.py's output."""
    out, cur = {}, None
    if not p.exists():
        return out
    for line in p.read_text().splitlines():
        if line.startswith("settings:"):
            out["settings"] = line.removeprefix("settings:").strip()
            continue
        m = re.match(r"^(Paris [AB]) \(all", line)
        if m:
            cur = m[1]
            out[cur] = []
            continue
        m = re.match(r"^\s+(.+?)\s+found\s+(\d+)\s+false\s+(\d+)\s+missed\s+(\d+)\s+errors\s+\d+\s+\(\s*([\d.]+) per 100", line)
        if m and cur:
            out[cur].append((m[1], int(m[2]), int(m[3]), int(m[4]), float(m[5])))
    return out


def label_commits(edition: Path | None, sources: list[str]) -> dict:
    out = {}
    if not edition:
        return out
    for pdf in sources:
        lp = pdf.replace(".pdf", ".labels.json")
        r = subprocess.run(["git", "-C", str(edition), "log", "-1", "--format=%h %ad", "--date=short", "--", lp],
                           capture_output=True, text=True)
        out[pdf] = r.stdout.strip() or "uncommitted"
    return out


# -- drawing --------------------------------------------------------------

def esc(s) -> str:
    return html.escape(str(s))


CLIPS = itertools.count()


def nice_step(span: float, target: int = 6) -> float:
    """A round tick step (1, 2, 5, 10, 15, 20, 30... ) giving about `target` ticks."""
    raw = span / max(1, target)
    for step in (0.01, 0.02, 0.05, 0.1, 0.2, 0.25, 0.5, 1, 2, 5, 10, 15, 20, 30, 60, 120):
        if step >= raw:
            return step
    return raw


def chart(title: str, series: list[tuple[str, list, list]], xlabel: str, ylabel: str = "",
          ylim: tuple | None = None, top: list[tuple[float, str]] | None = None, top_label: str = "",
          w: int = 640, h: int = 250, note: str = "") -> str:
    """A line chart as inline SVG: series (label, xs, ys); a round grid on
    both axes; `top`: secondary ticks (x, label) along the top (epochs)."""
    pts = [(x, y) for _, xs, ys in series for x, y in zip(xs, ys)]
    if not pts:
        return ""
    xmax = max(p[0] for p in pts) or 1.0
    xs_step = nice_step(xmax)
    x0, x1 = 0.0, xs_step * -(-xmax // xs_step)
    if ylim:
        y0, y1 = ylim
    else:
        lo, hi = min(0.0, min(p[1] for p in pts)), max(p[1] for p in pts) or 1.0
        st = nice_step(hi - lo, 5)
        y0, y1 = st * (lo // st), st * -(-hi // st)
    ys_step = nice_step(y1 - y0, 5)
    L, R, T, B = 50, 14, 26 if top else 12, 38
    sx = lambda x: L + (x - x0) / (x1 - x0) * (w - L - R)
    sy = lambda y: T + (1 - (y - y0) / (y1 - y0)) * (h - T - B)
    clip = f"c{next(CLIPS)}"
    out = [f'<figure><figcaption>{esc(title)}</figcaption><svg viewBox="0 0 {w} {h}" role="img">'
           f'<clipPath id="{clip}"><rect x="{L - 4}" y="{T - 4}" width="{w - L - R + 8}" height="{h - T - B + 8}"/></clipPath>']
    yv = y0
    while yv <= y1 + 1e-9:
        out.append(f'<line class="grid" x1="{L}" x2="{w - R}" y1="{sy(yv):.1f}" y2="{sy(yv):.1f}"/>'
                   f'<text class="tick" x="{L - 6}" y="{sy(yv) + 4:.1f}" text-anchor="end">{yv:g}</text>')
        yv += ys_step
    xv = x0
    while xv <= x1 + 1e-9:
        out.append(f'<line class="grid v" x1="{sx(xv):.1f}" x2="{sx(xv):.1f}" y1="{T}" y2="{h - B}"/>'
                   f'<text class="tick" x="{sx(xv):.1f}" y="{h - B + 15}" text-anchor="middle">{xv:g}</text>')
        xv += xs_step
    for x, label in top or []:
        out.append(f'<line class="epoch" x1="{sx(x):.1f}" x2="{sx(x):.1f}" y1="{T - 5}" y2="{T}"/>'
                   + (f'<text class="tick" x="{sx(x):.1f}" y="{T - 8}" text-anchor="middle">{esc(label)}</text>' if label else ""))
    if top_label:
        out.append(f'<text class="tick" x="{L - 6}" y="{T - 8}" text-anchor="end">{esc(top_label)}</text>')
    out.append(f'<text class="axis" x="{(L + w - R) / 2}" y="{h - 6}" text-anchor="middle">{esc(xlabel)}</text>')
    if ylabel:
        out.append(f'<text class="axis" x="13" y="{(T + h - B) / 2}" text-anchor="middle" '
                   f'transform="rotate(-90 13 {(T + h - B) / 2})">{esc(ylabel)}</text>')
    for i, (label, xs, ys) in enumerate(series):
        d = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in zip(xs, ys))
        col = COLORS[i % len(COLORS)]
        out.append(f'<g clip-path="url(#{clip})"><polyline fill="none" stroke="{col}" stroke-width="1.8" points="{d}"/>')
        if len(xs) <= 12:
            out += [f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="2.8" fill="{col}"/>' for x, y in zip(xs, ys)]
        out.append("</g>")
    out.append("</svg><ul class='legend'>" + "".join(
        f'<li><span style="background:{COLORS[i % len(COLORS)]}"></span>{esc(lbl)}</li>' for i, (lbl, _, _) in enumerate(series)) + "</ul>"
        + (f"<p class='note'>{note}</p>" if note else "") + "</figure>")
    return "".join(out)


def histogram(title: str, groups: list[tuple[str, list]], threshold: float | None, w: int = 640, h: int = 220,
              note: str = "") -> str:
    """Counts of confidences in 0.05-wide bins, one bar per group per bin."""
    bins = 20
    counts = [[0] * bins for _ in groups]
    for g, (_, vals) in enumerate(groups):
        for v in vals:
            counts[g][min(bins - 1, int(v * bins))] += 1
    ymax = max(max(c) for c in counts) or 1
    step = nice_step(ymax, 4)
    ytop = step * -(-ymax // step)
    L, R, T, B = 50, 14, 12, 38
    bw = (w - L - R) / bins
    sy = lambda y: T + (1 - y / ytop) * (h - T - B)
    out = [f'<figure><figcaption>{esc(title)}</figcaption><svg viewBox="0 0 {w} {h}" role="img">']
    yv = 0.0
    while yv <= ytop + 1e-9:
        out.append(f'<line class="grid" x1="{L}" x2="{w - R}" y1="{sy(yv):.1f}" y2="{sy(yv):.1f}"/>'
                   f'<text class="tick" x="{L - 6}" y="{sy(yv) + 4:.1f}" text-anchor="end">{yv:g}</text>')
        yv += step
    for k in range(0, bins + 1, 2):
        x = L + k * bw
        out.append(f'<text class="tick" x="{x:.1f}" y="{h - B + 15}" text-anchor="middle">{k / bins:g}</text>')
    gw = bw / (len(groups) + 0.5)
    for g in range(len(groups)):
        for k, n in enumerate(counts[g]):
            if n:
                x = L + k * bw + g * gw + gw * 0.25
                out.append(f'<rect x="{x:.1f}" y="{sy(n):.1f}" width="{gw:.1f}" height="{sy(0) - sy(n):.1f}" fill="{COLORS[g % len(COLORS)]}"/>'
                           f'<text class="tick" x="{x + gw / 2:.1f}" y="{sy(n) - 3:.1f}" text-anchor="middle">{n}</text>')
    if threshold is not None:
        x = L + threshold * (w - L - R)
        out.append(f'<line class="thresh" x1="{x:.1f}" x2="{x:.1f}" y1="{T}" y2="{h - B}"/>'
                   f'<text class="tick" x="{x - 4:.1f}" y="{T + 10}" text-anchor="end">threshold {threshold:g}</text>')
    out.append(f'<text class="axis" x="{(L + w - R) / 2}" y="{h - 6}" text-anchor="middle">confidence</text>')
    out.append("</svg><ul class='legend'>" + "".join(
        f'<li><span style="background:{COLORS[g % len(COLORS)]}"></span>{esc(lbl)} ({len(v)})</li>' for g, (lbl, v) in enumerate(groups))
        + "</ul>" + (f"<p class='note'>{note}</p>" if note else "") + "</figure>")
    return "".join(out)


def table(head: list, rows: list) -> str:
    return ("<table><thead><tr>" + "".join(f"<th>{esc(x)}</th>" for x in head) + "</tr></thead><tbody>"
            + "".join("<tr>" + "".join(f"<td>{x}</td>" for x in r) + "</tr>" for r in rows) + "</tbody></table>")


def errs(t: tuple) -> str:
    f, fp, m = t
    n = f + m
    return f"<b>{fp + m}</b> <span class='muted'>({fp} false, {m} missed; {100 * (fp + m) / n:.1f} per 100)</span>" if n else "—"


def page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title><link rel="stylesheet" href="models.css"></head>
<body><main>{body}
<footer class="muted">Generated {date.today().isoformat()} by experiments/barlines/cards.py from the training runs and scored results.</footer>
</main></body></html>
"""


CSS = """:root {
  --bg: #f4f2ee; --panel: #ffffff; --ink: #1f1d1a; --muted: #77726a; --line: #ddd8cf;
  --accent: #2c5fb8; --auto: #d9822b; --ok: #2e7d32; --bad: #c62828;
  font: 13px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); }
main { max-width: 900px; margin: 0 auto; padding: 24px 16px 48px; }
h1 { font-size: 20px; margin: 0 0 4px; }
h2 { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin: 0 0 8px; }
.muted { color: var(--muted); }
a { color: var(--accent); }
.lede { font-size: 14px; margin: 0 0 6px; }
.links { margin: 0 0 16px; font-size: 12px; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; margin: 0 0 14px; }
.pill { display: inline-block; font-size: 11px; padding: 1px 8px; border-radius: 10px; border: 1px solid var(--line); margin-left: 6px; vertical-align: middle; }
.pill.ok { color: var(--ok); border-color: var(--ok); }
.pill.auto { color: var(--auto); border-color: var(--auto); }
table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
th, td { text-align: left; padding: 4px 8px 4px 0; border-bottom: 1px solid var(--line); vertical-align: top; }
th { font-weight: 600; color: var(--muted); font-size: 12px; }
dl.kv { display: grid; grid-template-columns: 150px 1fr; gap: 4px 12px; margin: 0; }
dl.kv dt { color: var(--muted); }
dl.kv dd { margin: 0; }
figure { margin: 8px 0 14px; }
figcaption { font-weight: 600; margin-bottom: 4px; }
svg { width: 100%; height: auto; background: var(--panel); }
svg .grid { stroke: var(--line); stroke-width: 1; }
svg .tick { font-size: 10px; fill: var(--muted); }
svg .axis { font-size: 11px; fill: var(--muted); }
svg .grid.v { stroke-dasharray: 2 3; }
svg .epoch { stroke: var(--muted); stroke-width: 1; }
svg .thresh { stroke: var(--ink); stroke-width: 1.2; stroke-dasharray: 4 3; }
.note { font-size: 12px; color: var(--muted); margin: 4px 0 0; }
dl.gloss { display: grid; grid-template-columns: 150px 1fr; gap: 6px 12px; margin: 0; }
dl.gloss dt { font-weight: 600; }
dl.gloss dd { margin: 0; }
.examples figure { margin: 6px 0 10px; }
.examples img { width: 100%; border: 1px solid var(--line); border-radius: 4px; display: block; }
.examples figcaption { font-weight: 400; font-size: 12px; color: var(--muted); }
.key span { display: inline-block; width: 14px; height: 3px; margin: 0 4px 0 10px; vertical-align: middle; }
ul.legend { list-style: none; padding: 0; margin: 4px 0 0; display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 12px; }
ul.legend span { display: inline-block; width: 12px; height: 3px; margin-right: 5px; vertical-align: middle; }
ul.future li { margin-bottom: 4px; }
footer { margin-top: 24px; font-size: 11px; }
@media (max-width: 600px) { dl.kv, dl.gloss { grid-template-columns: 1fr; } dl.kv dt, dl.gloss dt { margin-top: 6px; } }
"""


# -- sections -------------------------------------------------------------

def data_section(c: dict, corpus: Path, commits: dict, detector: bool, trained: bool = True) -> str:
    val = set(json.loads((corpus / "tiles" / "val_ids.json").read_text())) if (corpus / "tiles" / "val_ids.json").exists() else set()
    rows = []
    groups = {}
    for l in c["lines"]:
        split = "test" if l["split"] == "test" else ("validation" if l["id"] in val else "train")
        g = groups.setdefault((hand(l), l["source"], l["part"]), {"train": [0, 0], "validation": [0, 0], "test": [0, 0], "pages": set()})
        g[split][0] += 1
        g[split][1] += len(l["bars"])
        g["pages"].add(l["page"])
    order = {h: i for i, h in enumerate(HANDS)}
    for (h, src, part), g in sorted(groups.items(), key=lambda kv: (order[kv[0][0]], kv[0][1], kv[0][2])):
        rows.append([esc(h), esc(src), esc(PARTS.get(part, part)), len(g["pages"]),
                     f"{g['train'][0]} / {g['train'][1]}", f"{g['validation'][0]} / {g['validation'][1]}", f"{g['test'][0]} / {g['test'][1]}"])
    tot = lambda s: (sum(g[s][0] for g in groups.values()), sum(g[s][1] for g in groups.values()))
    rows.append(["<b>all</b>", "", "", sum(len(g["pages"]) for g in groups.values()),
                 "<b>%d / %d</b>" % tot("train"), "<b>%d / %d</b>" % tot("validation"), "<b>%d / %d</b>" % tot("test")])
    tiles = ""
    if detector and (corpus / "tiles" / "yolo" / "images").exists():
        n = {s: len(list((corpus / "tiles" / "yolo" / "images" / s).glob("*.png"))) for s in ("train", "val")}
        ends = (" Each staff also has a start box (left end to music start) and an end box (around its right end), where "
                "a tile holds all of it." if any("staff_right" in l for l in c["lines"]) else "")
        tiles = f"<p>{esc(DETECTOR_DATA + ends)} Tiles: {n['train']} training, {n['val']} validation.</p>"
    srcs = "".join(f"<li>{esc(s)}: labels at {esc(v)}</li>" for s, v in commits.items())
    head = "Data that went into it" if trained else "Data it was scored on (it isn't trained)"
    return (f"<section class='card'><h2>{head}</h2>"
            f"<p>Every counted staff line on the editor's <i>reviewed</i> music pages, straightened along the editor's "
            f"bend, with the editor's bar lines as the truth"
            + (", cut across the paper's whole width, with the editor's left end, music start and right end"
               if any("staff_right" in l for l in c["lines"]) else "")
            + f". Lines are split at random (seed {c.get('seed', 1)}), "
            f"stratified by source; the test lines are never trained on. Cells: lines / bar lines.</p>"
            + table(["hand", "source", "part", "pages", "train", "validation", "test"], rows)
            + tiles + (f"<ul class='muted'>{srcs}</ul>" if srcs else "")
            + "<p class='muted'>" + " · ".join(f"<b>{esc(h)}</b>: {esc(HAND_NOTE[h])}" for h in present_hands(c))
            + "</p></section>")


def results_section(c: dict, res: dict | None, extra: str = "", also: list | None = None) -> str:
    if not res:
        return "<section class='card'><h2>Results</h2><p class='muted'>Not scored on this corpus yet.</p></section>"
    bh = by_hand(c, res)
    rows = [[esc(h), errs(bh[h])] for h in hands_in(c) + ["all"]]
    if also:
        extra = "<p>For comparison:</p>" + table(["run", "all"], [[esc(label), errs(by_hand(c, r)["all"])] for label, r in also]) + extra
    return (f"<section class='card'><h2>Results on the test lines</h2>"
            f"<p>A prediction counts if within 0.6% of the page width of one of the editor's bar lines (one to one). "
            f"Errors are false bar lines (a delete) plus missed ones (a click). "
            + (f"Confidence threshold {res['threshold']}, chosen on validation lines; " if res.get("threshold") is not None else "")
            + ("End to end, as the labeler runs: staves, edges and music start detected on whole pages, test lines' labels hidden from training; " if res.get("method") == "learned-labeler" else "")
            + f"{res['infer_s'] * 1000:.0f} ms per line on this Mac.</p>"
            + table(["hand", "errors"], rows) + extra + "</section>")


def ultralytics_section(run: Path) -> tuple[str, str]:
    rows = read_csv(run / "results.csv")
    args = read_yaml(run / "args.yaml")
    mins = [r["time"] / 60 for r in rows]
    get = lambda k: [r.get(k, 0.0) for r in rows]
    every = 10 if len(rows) > 30 else 5
    top = [(r["time"] / 60, str(int(r["epoch"])) if int(r["epoch"]) % every == 0 else "") for r in rows]
    charts = (chart("Ultralytics' validation metrics against training time", [
        ("recall", mins, get("metrics/recall(B)")), ("precision", mins, get("metrics/precision(B)")),
        ("mAP50 (found, loosely boxed)", mins, get("metrics/mAP50(B)")), ("mAP50-95 (box tightness)", mins, get("metrics/mAP50-95(B)"))],
        "minutes of training", ylim=(0, 1), top=top, top_label="epochs",
        note="Per validation tile, at Ultralytics' own settings; see Terms. Ticks along the top mark the end of each epoch.")
        + chart("Losses against training time (lower is better; no units)", [
            ("train box", mins, get("train/box_loss")), ("validation box", mins, get("val/box_loss")),
            ("train class", mins, get("train/cls_loss")), ("validation class", mins, get("val/cls_loss"))],
            "minutes of training", top=top, top_label="epochs"))
    best = max(rows, key=lambda r: 0.1 * r.get("metrics/mAP50(B)", 0) + 0.9 * r.get("metrics/mAP50-95(B)", 0))
    last = rows[-1]
    tail = rows[-max(3, len(rows) // 10):]
    still = (tail[-1].get("metrics/mAP50-95(B)", 0) - tail[0].get("metrics/mAP50-95(B)", 0))
    verdict = (f"Trained {int(last['epoch'])} epochs in {last['time'] / 60:.0f} minutes. The best epoch "
               f"(Ultralytics' fitness: mostly box tightness) was {int(best['epoch'])}. Over the last {len(tail)} epochs "
               f"recall moved {tail[-1].get('metrics/recall(B)', 0) - tail[0].get('metrics/recall(B)', 0):+.3f} and "
               f"mAP50-95 {still:+.3f}: " + ("still improving, so a longer run may help a little." if still > 0.005 else "levelled off."))
    keys = ["epochs", "patience", "batch", "imgsz", "optimizer", "lr0", "lrf", "momentum", "weight_decay", "warmup_epochs",
            "fliplr", "mosaic", "close_mosaic", "translate", "scale", "hsv_h", "hsv_s", "hsv_v", "erasing", "device", "seed"]
    hp = "<dl class='kv'>" + "".join(f"<dt>{esc(k)}</dt><dd>{esc(args[k])}</dd>" for k in keys if k in args) + "</dl>"
    return charts + f"<p>{esc(verdict)}</p>" + trainviz(run, "epoch", epoch_minutes(rows)), hp + losses("ultralytics")


def epoch_ticks(rows: list[dict]) -> list[tuple[float, str]]:
    every = 10 if len(rows) > 30 else 5
    return [(r["time"] / 60, str(int(r["epoch"])) if int(r["epoch"]) % every == 0 else "") for r in rows]


def mlx_section(run: Path) -> tuple[str, str]:
    rows = read_csv(run / "results.csv")
    mins = [r["time"] / 60 for r in rows]
    get = lambda k: [r.get(k, 0.0) for r in rows]
    top = epoch_ticks(rows)
    charts = (chart("Validation metrics against training time", [
        ("recall", mins, get("metrics/recall(B)")), ("precision", mins, get("metrics/precision(B)")),
        ("mAP50 (found, loosely boxed)", mins, get("metrics/mAP50(B)")), ("mAP50-95 (box tightness)", mins, get("metrics/mAP50-95(B)"))],
        "minutes of training", ylim=(0, 1), top=top, top_label="epochs", note="As yolo-mlx reports them each epoch; see Terms.")
        + chart("Training loss against training time (lower is better; no units)", [("train", mins, get("train/loss"))],
                "minutes of training", top=top, top_label="epochs",
                note="yolo-mlx logs one total of the box and class losses (as YOLO26's), and no validation loss."))
    verdict = f"Trained {int(rows[-1]['epoch'])} epochs in {rows[-1]['time'] / 60:.0f} minutes."
    hp = "<dl class='kv'>" + "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in [
        ("epochs", int(rows[-1]["epoch"])), ("batch", 16), ("imgsz", 640), ("patience", 25),
        ("augmentation", "HSV colour, horizontal flips, scale and shift (no mosaics)"), ("device", "Metal (MLX)")]) + "</dl>"
    return charts + f"<p>{esc(verdict)}</p>" + trainviz(run, "epoch", epoch_minutes(rows)), hp + losses("ultralytics")


def dfine_section(run: Path) -> tuple[str, str]:
    rows = read_csv(run / "log.csv")
    mins = [r["time"] / 60 for r in rows]
    top = epoch_ticks(rows)
    charts = chart("Losses per tile against training time (lower is better; no units)", [
        ("train", mins, [r["train/loss"] for r in rows]), ("validation", mins, [r["val/loss"] for r in rows])],
        "minutes of training", top=top, top_label="epochs",
        note="Not comparable with each other: training adds denoising and per-layer losses that validation leaves out "
             "(see The losses). The kept weights are from the epoch with the lowest validation loss.")
    best = min(rows, key=lambda r: r["val/loss"])
    verdict = (f"Trained {int(rows[-1]['epoch'])} epochs in {rows[-1]['time'] / 60:.0f} minutes on the Mac's GPU; lowest "
               f"validation loss at epoch {int(best['epoch'])}.")
    hp = "<dl class='kv'>" + "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in [
        ("epochs", int(rows[-1]["epoch"])), ("batch", "8 tiles"), ("optimizer", "AdamW, weight decay 1e-4"),
        ("learning rate", "1e-4 (backbone 1e-5), constant"), ("gradient clipping", "0.1"),
        ("input", "640 × 192"), ("augmentation", "horizontal flips"), ("device", "mps (with dfine_patch.py)")]) + "</dl>"
    return charts + f"<p>{esc(verdict)}</p>" + trainviz(run, "epoch", epoch_minutes(rows)), hp + losses("dfine")


def d2_records(run: Path) -> list[dict]:
    """metrics.json's records of the last run (it appends), each with
    `minutes`: wall clock since the start, summing the logged seconds per
    iteration over the iterations since the previous record."""
    recs = [json.loads(l) for l in (run / "metrics.json").read_text().splitlines() if l.strip()]
    recs = [r for r in recs if "total_loss" in r]
    start = max((i for i in range(1, len(recs)) if recs[i]["iteration"] < recs[i - 1]["iteration"]), default=0)
    recs, t, prev = recs[start:], 0.0, -1
    for r in recs:
        t += (r["iteration"] - prev) * r.get("time", 0.0)
        prev = r["iteration"]
        r["minutes"] = t / 60
    return recs


def d2_minutes(recs: list[dict], iteration: int) -> float:
    return min(recs, key=lambda r: abs(r["iteration"] - iteration))["minutes"]


def detectron2_section(run: Path) -> tuple[str, str]:
    recs = d2_records(run)
    mins = [r["minutes"] for r in recs]
    get = lambda k: [r.get(k, 0.0) for r in recs]
    charts = (chart("Training losses against training time (lower is better; no units)", [
        ("total", mins, get("total_loss")), ("classification", mins, get("loss_cls")),
        ("box regression", mins, get("loss_box_reg")), ("proposals", mins, get("loss_rpn_cls"))], "minutes of training",
        note="Logged every 20 iterations on the training batches; noisy because each batch is only 8 tiles."))
    last = recs[-1]
    verdict = (f"{last['iteration'] + 1} iterations of 8 tiles in about {mins[-1]:.0f} minutes; the learning rate "
               f"drops at 70% and 90% of the run. No validation score is logged during training: the losses show "
               f"how well it fits the training tiles, the results below how well it does on unseen lines.")
    hp = "<dl class='kv'>" + "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in [
        ("iterations", last["iteration"] + 1), ("batch", "8 tiles"), ("base learning rate", "0.005, ×0.1 at 70% and 90%"),
        ("input", "192 px high (640 px tiles scaled)"), ("anchors", "aspect 2, 4, 8 (tall and thin)"),
        ("augmentation", "horizontal flips"), ("ROI batch", "128 proposals per image"), ("device", "mps")]) + "</dl>"
    return charts + f"<p>{esc(verdict)}</p>" + trainviz(run, "iteration", lambda it: d2_minutes(recs, it - 1)), hp + losses("detectron2")


def learned_section(crosshand: dict, cv: dict, cvp: dict) -> tuple[str, str]:
    charts = ""
    series = []
    settings = crosshand.get("settings")
    for target, rows in ((k, v) for k, v in crosshand.items() if k != "settings"):
        for widths in (False, True):
            pts = [(int(m[1]), r[4]) for r in rows if (m := re.match(r"k=(\d+)( \+ widths)?$", r[0])) and bool(m[2]) == widths]
            if pts:
                series.append((f"{target}{' + widths' if widths else ''}", [p[0] for p in pts], [p[1] for p in pts]))
    if series:
        charts += chart("Errors per 100 bar lines on a new hand, against how many of its pages were in training (plus all of KHM)",
                        series, "pages of the new hand in training")
        charts += ("<p class='muted'>From crosshand.py on the straightened lines: tested on the hand's other pages, "
                   "errors summed over random draws of the pages. "
                   + (f"Its settings: {esc(settings)}." if settings else
                      "Its log doesn't record its settings (an older run): rerun it to state them.") + "</p>")
    tab = ""
    if cv or cvp:
        rows = []
        for name, label in (("learned+widths", "learned filter + bar widths"), ("learned", "learned filter"), ("classical", "hand-tuned rules")):
            for tag, d in (("ink cutoff 120", cv), ("ink relative to paper", cvp)):
                if name == "classical" and d is cvp:
                    continue  # the rules don't use candidates: the same either way
                if name in d:
                    srcs = [k for k in d[name] if k != "all"]
                    rows.append([esc(label), esc(tag), errs(d[name]["all"])] + [errs(d[name][s]) for s in srcs])
        if rows:
            srcs = [k for k in (cv or cvp)["learned+widths"] if k != "all"]
            tab = ("<p>5-fold cross-validation over every line (each tested once):</p>"
                   + table(["method", "candidates", "all"] + srcs, rows))
    hp = "<dl class='kv'>" + "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in [
        ("classifier", "HistGradientBoostingClassifier"), ("trees", "300, learning rate 0.05, up to 15 leaves"),
        ("class weight", "balanced"), ("second pass", "cross-fitted over 5 groups of pages"),
        ("threshold", "F1 on a tenth of the reviewed pages, held out"),
        ("candidates", "staff coverage over 0.5; ink at least 66 levels darker than the staff's paper"),
        ("retraining", "automatic, when a reviewed page changes")]) + "</dl>"
    return charts + tab, hp


# -- pages ----------------------------------------------------------------

def rules_section(mdl: dict) -> tuple[str, str]:
    """The rules, step by step, and their constants as detect.py has them now."""
    sys.path.insert(0, str(HERE.parent.parent))
    import detect
    names = {"COVER": "share of the staff's height a bar line must cover", "ATTACH_WIDTH": "ink across the stroke this wide (spaces) is a note head or beam",
             "ATTACH_ROWS": "this many spaces' worth of such rows make it a stem", "MIN_BAR": "narrowest bar (staff spaces)",
             "WIDE_GAP": "a gap this many times the typical bar may hide a faint bar line", "FAINT": "coverage accepted in such a gap",
             "LEAN": "steepest lean tried (dx per dy)", "END_SLACK": "staff spaces a bar line may stop short of the outer lines"}
    steps = "<ol>" + "".join(f"<li><b>{esc(k)}.</b> {esc(v)}</li>" for k, v in mdl["steps"]) + "</ol>"
    hp = "<dl class='kv'>" + "".join(f"<dt>{k} = {getattr(detect, k)}</dt><dd>{esc(v)}</dd>" for k, v in names.items() if hasattr(detect, k)) + "</dl>"
    return steps, hp


def model_page(mdl: dict, c: dict, corpus: Path, results: dict, commits: dict, logs: dict,
               heldout: tuple | None = None) -> str:
    res = results.get(mdl["result"])
    train_s = res.get("train_s") if res else None
    pill = {"labeler": "<span class='pill ok'>in the labeler</span>",
            "retired": "<span class='pill auto'>retired</span>"}.get(mdl.get("status"), "<span class='pill auto'>experiment</span>")
    card = dict(mdl["card"])
    if res:
        card["Training time"] = f"{train_s / 60:.0f} minutes" if train_s and train_s > 90 else (f"{train_s:.0f} s" if train_s else "none")
        card["Per line"] = f"{res['infer_s'] * 1000:.0f} ms on this Mac"
    run = corpus / "runs" / mdl["run"] if mdl["run"] else None
    if run and run.exists():
        wts = list(run.glob("weights/best.pt")) + list(run.glob("model_final.pth"))
        if wts:
            card["Weights file"] = f"{wts[0].stat().st_size / 1e6:.1f} MB"
    conv, hp = "", ""
    if mdl["kind"] == "ultralytics" and run and (run / "results.csv").exists():
        conv, hp = ultralytics_section(run)
    elif mdl["kind"] == "mlx" and run and (run / "results.csv").exists():
        conv, hp = mlx_section(run)
    elif mdl["kind"] == "dfine" and run and (run / "log.csv").exists():
        conv, hp = dfine_section(run)
    elif mdl["kind"] == "detectron2" and run and (run / "metrics.json").exists():
        conv, hp = detectron2_section(run)
    elif mdl["kind"] == "rules":
        steps, hp = rules_section(mdl)
        mdl = {**mdl, "how": mdl["how"]}
        conv = ""
        hp = steps + "<h2 style='margin-top:12px'>Constants (detect.py, now)</h2>" + hp
    elif mdl["kind"] == "learned":
        conv, hp = learned_section(logs["crosshand"], logs["crossval"], logs["crossval-paper"])
    body = (f"<p><a href='index.html'>← all models</a></p><h1>{esc(mdl['title'])}{pill}</h1>"
            f"<p class='lede'>{esc(mdl['summary'])}</p>"
            + ("<p class='links'>" + " · ".join(f"<a href='{esc(u)}'>{esc(t)}</a>" for t, u in mdl.get("links", [])) + "</p>" if mdl.get("links") else "")
            + "<section class='card'><h2>Model card</h2><dl class='kv'>"
            + "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in card.items()) + "</dl></section>"
            + data_section(c, corpus, commits, mdl["kind"] in ("ultralytics", "detectron2", "mlx", "dfine"), mdl["kind"] != "rules")
            + "<section class='card'><h2>How training works</h2>" + "".join(f"<p>{esc(p)}</p>" for p in mdl["how"])
            + (f"<h2 style='margin-top:12px'>{'The rules, in order' if mdl['kind'] == 'rules' else 'Settings'}</h2>{hp}" if hp else "") + "</section>"
            + (f"<section class='card'><h2>Training</h2>{conv}</section>" if conv else "")
            + results_section(c, res, also=[(label, results[k]) for label, k in mdl.get("also", []) if k in results])
            + heldout_section(heldout, mdl)
            + (glossary(any("staff_right" in l for l in c["lines"])) if mdl["kind"] in ("ultralytics", "detectron2", "mlx", "dfine") else "")
            + "<section class='card'><h2>Future directions</h2><ul class='future'>"
            + "".join(f"<li>{esc(f)}</li>" for f in mdl["future"]) + "</ul></section>")
    return page(f"{mdl['title']} · model card", body)


def heldout_section(heldout: tuple | None, mdl: dict) -> str:
    """The same recipe trained without one source, scored on it: how the model
    does on a copy it never saw."""
    if not heldout and not mdl.get("measured"):
        return ""
    out = "<section class='card'><h2>On a copy it never saw</h2>"
    if heldout:
        hc, hres = heldout
        bh = by_hand(hc, hres)
        out += ("<p>Trained the same way without " + esc(", ".join(sorted({l["source"] for l in hc["lines"]}
                - {l["source"] for l in hc["lines"] if l["split"] == "train"}))) + f" (threshold {hres['threshold']}):</p>"
                + table(["hand", "errors"], [[esc(h), errs(bh[h])] for h in hands_in(hc) + ["all"]]))
    return out + mdl.get("measured", "") + "</section>"


def index_page(c: dict, results: dict, written: set) -> str:
    rows, other = [], []
    hs = hands_in(c)
    for mdl in MODELS:
        link = f"<a href='{mdl['key']}.html'>{esc(mdl['title'])}</a>"
        if mdl.get("corpus"):  # trained and scored on a corpus of its own
            if mdl["key"] in written:
                other.append(f"<li>{link}: {esc(mdl['summary'])}</li>")
            continue
        res = results.get(mdl["result"])
        if not res:
            rows.append([link] + ["—"] * (len(hs) + 2) + [esc(mdl["card"]["Licence"].split(" ")[0])])
            continue
        bh = by_hand(c, res)
        rows.append([link] + [f"<b>{bh[h][1] + bh[h][2]}</b>" for h in hs + ["all"]]
                    + [f"{res['infer_s'] * 1000:.0f} ms", esc(mdl["card"]["Licence"].split(" ")[0])])
    test = [l for l in c["lines"] if l["split"] == "test"]
    n = {h: sum(len(l["bars"]) for l in test if hand(l) == h) for h in hs}
    body = ("<h1>Bar-line models</h1><p class='lede'>Every model that finds bar lines in the manuscripts: what it is, "
            "what it was trained on, how its training went, and where it could go next.</p>"
            + (f"<section class='card'><h2>Trained on later corpora</h2><ul>{''.join(other)}</ul>"
               "<p class='muted'>Each card has its own data, training and results.</p></section>" if other else "")
            + "<section class='card'><h2>Errors on the test lines (false + missed)</h2>"
            + table(["model"] + [f"{h} ({n[h]})" for h in hs] + [f"all ({sum(n.values())})", "per line", "licence"], rows)
            + "<p class='muted'>One random split of this corpus's reviewed lines; the Paris columns are small. "
              "Each model's card has its cross-validation or training curves.</p></section>" + glossary())
    return page("Bar-line models", body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus", type=Path)
    ap.add_argument("--edition", type=Path)
    ap.add_argument("--with", dest="more", action="append", default=[], metavar="NAME=DIR",
                    help="a further corpus, for the cards that name it (e.g. prod=..., bl4=...)")
    args = ap.parse_args()
    if any("=" not in x for x in args.more):
        ap.error("--with takes NAME=DIR")
    named = dict(x.split("=", 1) for x in args.more)

    def load(d: Path):
        c = json.loads((d / "corpus.json").read_text())
        rs = {}
        for p in (d / "results").glob("*.json"):
            r = json.loads(p.read_text())
            rs[r["method"]] = r
        return c, rs
    c, results = load(args.corpus)
    logs = {"crossval": parse_crossval(args.corpus / "logs" / "crossval.log"),
            "crossval-paper": parse_crossval(args.corpus / "logs" / "crossval-paper.log"),
            "crosshand": parse_crosshand(args.corpus / "logs" / "crosshand.log")}
    commits = label_commits(args.edition, sorted({l["pdf"] for l in c["lines"]}))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "models.css").write_text(CSS)
    written = set()
    for mdl in MODELS:
        if mdl.get("corpus"):
            if mdl["corpus"] not in named:
                print(f"{mdl['key']}: skipped, needs --with {mdl['corpus']}=DIR")
                continue
            d = Path(named[mdl["corpus"]])
            mc, mres = load(d)
            held = None
            if mdl.get("heldout") in named:
                hc, hres = load(Path(named[mdl["heldout"]]))
                held = (hc, hres[mdl["result"]]) if mdl["result"] in hres else None
            if mdl.get("heldout") and held is None:
                print(f"{mdl['key']}: no held-out result (--with {mdl['heldout']}=DIR with {mdl['result']}); "
                      "its card says how it does on an unseen copy without that table")
            page_html = model_page(mdl, mc, d, mres, label_commits(args.edition, sorted({l["pdf"] for l in mc["lines"]})),
                                   logs, held)
        else:
            page_html = model_page(mdl, c, args.corpus, results, commits, logs)
        (OUT / f"{mdl['key']}.html").write_text(page_html)
        written.add(mdl["key"])
    (OUT / "index.html").write_text(index_page(c, results, written))
    print(f"wrote {OUT}/index.html and {len(written)} model cards")


if __name__ == "__main__":
    main()
