"""Boccherini 6k (D5-B6k): musvit-D4's Boccherini stage (24 passes of a 30-pass schedule, the same learning rate and
adapters) on the re-paired, re-detected sets, from Drawn 15k (SF1-h96-clef: the drawn staves with the clef-change
ones). Public 9k -> Drawn 15k -> Boccherini 6k. The Boccherini stage: Op. 48 (dataL2: the training and practice-exam
movements, not the clean test, KHM 603 I), dataM5 (Philhar's quartets, with the Madrid copies that were dataT),
dataW4 (Philhar's other works) but Dresden's Mus.3403 (M. Haydn's MH 411, held out as a test in a new hand and
music), dataP4 (the print's agreed bars), dataG213-4. Batches built by 4 worker processes on 5 reserved cores.

    uv run train_b6k.py [--name D5-B6k] [--epochs 30] [--stop-at 24] [--op48 1] [--init SF1-h96-clef] [--data b6k]

--op48 N lists Op. 48's staves N times (its own labels, the edition's hands, weighted up); --epochs and --stop-at
set the schedule (D5-B6k-s13: 13 of 16, about D4's number of steps on twice the staves); --init the drawn stage
(D5-B6k-d11: from Drawn 11k, D4's, to tell the new data's effect from Drawn 15k's); --data b3k with --init SF1-h96
repeats D4's run (D3S-h96-r2: was its Dresden bar count luck?)."""
import argparse
import subprocess
from pathlib import Path
S = Path(__file__).parent
MUS = S.parent
CACHE = Path.home() / ".cache/manuscript-labeler/zeus"
HELD_OUT = "samples.D-Dl_Mus.3403-P-513.txt"
ap = argparse.ArgumentParser()
ap.add_argument("--name", default="D5-B6k")
ap.add_argument("--epochs", default="30")
ap.add_argument("--stop-at", default="24")
ap.add_argument("--op48", type=int, default=1)
ap.add_argument("--init", default="SF1-h96-clef", help="the drawn stage to start from (SF1-h96: Drawn 11k, D4's)")
ap.add_argument("--seed", default="0", help="proto.py's --seed: another run of the same recipe")
ap.add_argument("--data", choices=["b6k", "b3k"], default="b6k",
                help="b3k: D4's Boccherini 3k (dataL2's Op. 48, dataM, dataT), to repeat D4's run")
a = ap.parse_args()
dev = [t.replace("/staves/dataL/", "/staves/dataL2/") for t in (S / "dev-L.txt").read_text().split()]
op48 = [t.replace("/staves/dataL/", "/staves/dataL2/") for t in (S / "train-L.txt").read_text().split() if "/dataL/" in t] + dev
sets = ("dataM5", "dataW4", "dataP4", "dataG213-4") if a.data == "b6k" else ("dataM", "dataT")
rest = [f"/staves/{d}/{p.name}" for d in sets for p in sorted((CACHE / d).glob("samples.*.txt")) if p.name != HELD_OUT]
args = [a.name, "--init", a.init, "--init-file", "best.pt", "--amp", "--seed", a.seed, "--workers", "4", "--train", *op48 * a.op48,
        *rest, "--dev", *dev, "--epochs", a.epochs, "--stop-at", a.stop_at, "--eval-every", a.epochs, "--lr", "1e-4",
        "--lora-r", "64", "--lora-mlp"]
r = subprocess.run(["modal", "run", "modal_app.py::main", "--gpu", "L40S", "--cpu", "5", "--args", " ".join(args)],
                   cwd=MUS, capture_output=True, text=True)
(S / f"{a.name}.log").write_text(r.stdout + r.stderr)
print("\n".join(l for l in (r.stdout + r.stderr).splitlines() if "training staves" in l or "epoch" in l or "stopping" in l
                or "Error" in l)[-3000:])
