# /// script
# requires-python = ">=3.11"
# dependencies = ["modal"]
# ///
"""Readings of the public test staves by the MuSViT readers, all at once in one app (read_samples)."""
import json, sys
from pathlib import Path
B = Path(__file__).parent / "bench"
sys.path.insert(0, "/Users/jsundram/Dropbox/Code/manuscript-labeler/experiments/musvit")
import modal
from modal_app import app, read_samples
jobs = [(r, f, t) for r, f in (("E2-tf8", "best.pt"), ("D1-tf8-M", "best.pt"), ("D3-tf8-all", "reader.pt")) for t in ("dolores", "omniomr")]
with modal.enable_output(), app.run():
    calls = [read_samples.spawn(r, f, f"/staves/public/{t}/samples.test.txt") for r, f, t in jobs]
    for (r, f, t), c in zip(jobs, calls):
        (B / f"{t}-{r}.json").write_text(json.dumps(c.get()))
        print("read", t, r, flush=True)
