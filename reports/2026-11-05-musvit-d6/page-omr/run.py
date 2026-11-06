# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["page-omr @ git+https://github.com/tobiashornbogen/page-omr@e369a44a8232ddcf0ddd915f7e07b19cdcb91b61", "torch", "torchvision"]
# ///
"""page-omr's reading of each page folder's page.png, as their
scripts/inference.py makes it (greedy, post-processed and repaired), on the
Mac's GPU in float32:

    uv run run.py tobiashornbogen/page-omr-a1-kern OUT/*/
"""
import sys
import time
from pathlib import Path

import torch
from PIL import Image
from omr.inference.postprocess import postprocess_output
from omr.inference.repair import repair_kern_prediction
from omr.utils.hub import load_from_hub

repo, dirs = sys.argv[1], [Path(d) for d in sys.argv[2:]]
dev = "mps" if torch.backends.mps.is_available() else "cpu"
model, tok, proc, cfg = load_from_hub(repo, device=dev)
name = repo.split("/")[-1]
for d in dirs:
    out = d / f"{name}.krn"
    if out.exists():
        continue
    t0 = time.time()
    px = proc(Image.open(d / "page.png").convert("RGB"), return_tensors="pt")["pixel_values"].to(dev)
    with torch.no_grad():
        ids = model.generate(px, max_length=3072, num_beams=1, repetition_penalty=1.0)
    raw = tok.decode(ids[0].tolist(), skip_special_tokens=True)
    (d / f"{name}.raw.krn").write_text(raw)
    out.write_text(repair_kern_prediction(postprocess_output(raw)))
    print(d.name, f"{time.time() - t0:.0f} s", len(raw), "chars", flush=True)
