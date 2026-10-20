# /// script
# requires-python = ">=3.11"
# dependencies = ["torch==2.14.1", "torchvision", "transformers==5.20.1", "pillow", "numpy"]
# ///
"""Score fine-tuned Segment Anything decoders (sam_train.py's decoder.pt) on several test sets at once: each set's
windows go through the frozen encoder once, then every decoder is scored on them (sam_train.evaluate: IoU per kind).
"untrained" is SAM's own decoder.

    uv run experiments/synth/sam_eval.py --decoders untrained RUN/decoder.pt [...] --tests DIR [...] [--json OUT]

Prints a table of the mean IoU over kinds (those with at least 5 symbols), decoders down, test sets across.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import torch
from transformers import Sam2Model

import sam_train


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--decoders", nargs="+", required=True, help="decoder.pt files, or 'untrained'")
    ap.add_argument("--tests", nargs="+", type=Path, required=True)
    ap.add_argument("--json", type=Path, help="write every score, per kind, here")
    a = ap.parse_args()
    dev = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
    model = Sam2Model.from_pretrained("facebook/sam2.1-hiera-small").to(dev).eval()
    own = {k: v.clone() for k, v in model.state_dict().items() if k.startswith(("mask_decoder", "prompt_encoder"))}
    weights = {d: own if d == "untrained" else torch.load(d, map_location="cpu") for d in a.decoders}
    scores = {}
    for t in a.tests:
        data = [sam_train.load(f) for f in sorted(t.glob("*.npz"))]
        with torch.no_grad():
            feats = {ex["name"]: [f.half() for f in model.get_image_embeddings(sam_train.pixels(ex["image"], dev))]
                     for ex in data}
        for d, w in weights.items():
            model.load_state_dict(w, strict=False)
            scores.setdefault(d, {})[t.name] = sam_train.evaluate(model, data, dev, lambda ex: [f.float() for f in feats[ex["name"]]])
            print(f"{t.name} {d}: {json.dumps(scores[d][t.name])}", flush=True)
        del feats
    names = [t.name for t in a.tests]
    label = {d: d if d == "untrained" else Path(d).parent.name for d in a.decoders}  # the run's directory
    width = max(len(v) for v in label.values())
    print("\nmean IoU over kinds".ljust(width + 1), *[n.rjust(14) for n in names])
    for d in a.decoders:
        row = [np.mean([v for v, n in scores[d][t].values() if n >= 5]) for t in names]
        print(label[d].ljust(width), *[f"{v:14.3f}" for v in row])
    if a.json:
        a.json.write_text(json.dumps(scores, indent=1))


if __name__ == "__main__":
    main()
