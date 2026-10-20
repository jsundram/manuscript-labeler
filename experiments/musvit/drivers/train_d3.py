"""The release reader (D3-tf8-all): D1's recipe and pass (24 of a 30-pass schedule) on everything but the clean test:
Op. 48 (the practice exam's movements too), every re-paired Philhar staff, and the Madrid copies."""
import subprocess
from pathlib import Path
S = Path(__file__).parent
MUS = Path("/Users/jsundram/Dropbox/Code/manuscript-labeler/experiments/musvit")
CACHE = Path.home() / ".cache/manuscript-labeler/zeus"
dev = (S / "dev-L.txt").read_text().split()
op48 = [t for t in (S / "train-L.txt").read_text().split() if "/dataL/" in t] + dev
rest = [f"/staves/{d}/{p.name}" for d in ("dataM", "dataT") for p in sorted((CACHE / d).glob("samples.*.txt"))]
args = ["D3-tf8-all", "--init", "E2-tf8", "--init-file", "best.pt", "--amp", "--train", *op48, *rest, "--dev", *dev,
        "--epochs", "30", "--stop-at", "24", "--eval-every", "30", "--lr", "1e-4", "--lora-r", "64", "--lora-mlp"]
r = subprocess.run(["modal", "run", "modal_app.py::main", "--gpu", "L40S", "--args", " ".join(args)], cwd=MUS,
                   capture_output=True, text=True)
(S / "D3-tf8-all.log").write_text(r.stdout + r.stderr)
print("\n".join(l for l in (r.stdout + r.stderr).splitlines() if "training staves" in l or "epoch 24" in l or "stopping" in l
                or "Error" in l)[-2000:])
