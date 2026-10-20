# /// script
# requires-python = ">=3.11"
# dependencies = ["torch==2.14.1", "transformers==5.20.1", "safetensors==0.8.0", "peft", "pillow", "numpy"]
# ///
"""How well musvit-D1 (never trained on the practice exam) reads real staves it hasn't seen against synthetic
ones: the practice-exam staves (dataL2), synthetic staves of its own training music (S-own), and of new music (S-osq)."""
import random, sys, time
from pathlib import Path
sys.path.insert(0, "/Users/jsundram/Dropbox/Code/manuscript-labeler/experiments/musvit")
import proto
Z = Path.home() / ".cache/manuscript-labeler/zeus"
model, vocab = proto.load_release(Path.home() / ".cache/manuscript-labeler/models/musvit/musvit-D1@2026-10-18")
model = proto.for_reading(model, "mps")
inv = {i: t for t, i in vocab.items()}
N = int(sys.argv[1]) if len(sys.argv) > 1 else 120
sets = {
    "real (practice exam)": proto.staves([Z / "dataL2/samples.D-B_KHM-602-II.txt", Z / "dataL2/samples.F-Po_RES-507-17-I.txt",
                                          Z / "dataL2/samples.F-Pn_Vma-ms-1067-3-noslur-I.txt"]),
    "synthetic, its training music (S-own)": proto.staves([Z / "dataS/samples.S-own.txt"]),
    "synthetic, new music (S-osq)": proto.staves([Z / "dataS/samples.S-osq.txt"]),
}
for name, items in sets.items():
    random.Random(0).shuffle(items)
    items = sorted(items[:N], key=proto.aspect)
    errs = ref = capped = 0
    t = time.time()
    for k in range(0, len(items), 8):
        chunk = items[k:k + 8]
        x, mask, _, _ = proto.batch(chunk, vocab)
        got = model.read(x.to("mps", next(model.parameters()).dtype), mask.to("mps"), vocab[proto.BOS], vocab[proto.EOS])
        for (_, toks), g in zip(chunk, got):
            g = [inv[i] for i in g]
            ref += len(toks)
            capped += proto.edits(g[:2 * len(toks)], toks)
    print(f"{name}: {len(items)} staves, symbol error rate {capped / ref:.1%} ({time.time() - t:.0f} s)", flush=True)
