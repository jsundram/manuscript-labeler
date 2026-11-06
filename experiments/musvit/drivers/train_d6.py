# /// script
# requires-python = ">=3.11"
# ///
"""musvit-D6's Boccherini stage: D5's recipe (train_b6k.py --init SF1-h96 --op48 3 --seed 1) with the edition's
movements finished since D5 trained added, weighted as Op. 48's (dataL3: Op48-4 II in F-Po RES 507 (16), Op48-6 I and
II in RES 507 (18)). Op48-4 I (RES 507 (16)) stays out: the seeing test's bars and D6's held-out test.

    uv run train_d6.py --name D6-A                              # the new movements alone
    uv run train_d6.py --name D6-B --rare 1 --count-loss 0.5    # and the rare marks weighted up, and counted

--rare N lists every staff with a grace note or a chord N more times (each set's rare.txt, from the staves trained
on); --count-loss trains proto.py's count head beside the reader (reports/2026-11-03-open-model-bars).
"""
import argparse
import subprocess
from pathlib import Path

S = Path(__file__).parent
MUS = S.parent
CACHE = Path.home() / ".cache/manuscript-labeler/zeus"
HELD_OUT = "samples.D-Dl_Mus.3403-P-513.txt"
SETS = ("dataM5", "dataW4", "dataP4", "dataG213-4")
NEW = ["/staves/dataL3/samples.F-Po_RES-507-16-II.txt", "/staves/dataL3/samples.F-Po_RES-507-18-I-II.txt"]
ap = argparse.ArgumentParser()
ap.add_argument("--name", required=True)
ap.add_argument("--rare", type=int, default=0)
ap.add_argument("--count-loss", default="0")
ap.add_argument("--seed", default="1", help="D5's")
a = ap.parse_args()
dev = [t.replace("/staves/dataL/", "/staves/dataL2/") for t in (S / "dev-L.txt").read_text().split()]
op48 = [t.replace("/staves/dataL/", "/staves/dataL2/") for t in (S / "train-L.txt").read_text().split() if "/dataL/" in t] + dev
rest = [f"/staves/{d}/{p.name}" for d in SETS for p in sorted((CACHE / d).glob("samples.*.txt")) if p.name != HELD_OUT]
rare = [f"/staves/{d}/rare.txt" for d in ("dataL2", *SETS, "dataL3")] * a.rare
args = [a.name, "--init", "SF1-h96", "--init-file", "best.pt", "--amp", "--seed", a.seed, "--workers", "4",
        "--train", *(op48 + NEW) * 3, *rest, *rare, "--dev", *dev, "--epochs", "30", "--stop-at", "24", "--eval-every", "30",
        "--lr", "1e-4", "--lora-r", "64", "--lora-mlp", "--count-loss", a.count_loss]
r = subprocess.run(["modal", "run", "modal_app.py::main", "--gpu", "L40S", "--cpu", "5", "--args", " ".join(args)],
                   cwd=MUS, capture_output=True, text=True)
(S / f"{a.name}.log").write_text(r.stdout + r.stderr)
print(r.stdout[-2000:], r.stderr[-2000:])
