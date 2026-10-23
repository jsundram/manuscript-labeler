"""Boccherini 6k (D5-B6k): musvit-D4's Boccherini stage (24 passes of a 30-pass schedule, the same learning rate and
adapters) on the re-paired, re-detected sets, from Drawn 15k (SF1-h96-clef: the drawn staves with the clef-change
ones). Public 9k -> Drawn 15k -> Boccherini 6k. The Boccherini stage: Op. 48 (dataL2: the training and practice-exam
movements, not the clean test, KHM 603 I), dataM5 (Philhar's quartets, with the Madrid copies that were dataT),
dataW4 (Philhar's other works) but Dresden's Mus.3403 (M. Haydn's MH 411, held out as a test in a new hand and
music), dataP4 (the print's agreed bars), dataG213-4. Batches built by 4 worker processes on 5 reserved cores."""
import subprocess
from pathlib import Path
S = Path(__file__).parent
MUS = S.parent
CACHE = Path.home() / ".cache/manuscript-labeler/zeus"
HELD_OUT = "samples.D-Dl_Mus.3403-P-513.txt"
dev = [t.replace("/staves/dataL/", "/staves/dataL2/") for t in (S / "dev-L.txt").read_text().split()]
op48 = [t.replace("/staves/dataL/", "/staves/dataL2/") for t in (S / "train-L.txt").read_text().split() if "/dataL/" in t] + dev
rest = [f"/staves/{d}/{p.name}" for d in ("dataM5", "dataW4", "dataP4", "dataG213-4")
        for p in sorted((CACHE / d).glob("samples.*.txt")) if p.name != HELD_OUT]
args = ["D5-B6k", "--init", "SF1-h96-clef", "--init-file", "best.pt", "--amp", "--workers", "4", "--train", *op48, *rest,
        "--dev", *dev, "--epochs", "30", "--stop-at", "24", "--eval-every", "30", "--lr", "1e-4", "--lora-r", "64",
        "--lora-mlp"]
r = subprocess.run(["modal", "run", "modal_app.py::main", "--gpu", "L40S", "--cpu", "5", "--args", " ".join(args)],
                   cwd=MUS, capture_output=True, text=True)
(S / "D5-B6k.log").write_text(r.stdout + r.stderr)
print("\n".join(l for l in (r.stdout + r.stderr).splitlines() if "training staves" in l or "epoch" in l or "stopping" in l
                or "Error" in l)[-3000:])
