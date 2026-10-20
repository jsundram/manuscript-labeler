"""Control for H1: D1's recipe on a random 1,060 of the Philhar staves (as many as H1 has), Op. 22 and Op. 32
left in; scored on Madrid, Op. 32 and the clean test."""
import re, subprocess, sys
from pathlib import Path
S = Path(__file__).parent
MUS = Path("/Users/jsundram/Dropbox/Code/manuscript-labeler/experiments/musvit")
LAB, E = MUS.parent.parent, Path.home() / "Dropbox/Code/boccherini-opus-48"
CACHE = Path.home() / ".cache/manuscript-labeler/zeus"
out = []

def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode:
        out.append(f"FAILED: {' '.join(map(str, cmd))[:200]}\n{(r.stdout + r.stderr)[-1500:]}")
        done(1)
    return r.stdout + r.stderr

def done(code=0):
    (S / "control-summary.md").write_text("\n".join(out) + "\n")
    print("\n".join(out)); sys.exit(code)

op48 = [t for t in (S / "train-L.txt").read_text().split() if "/dataL/" in t]
keep = ["subset-matched.txt"]
train = op48 + [f"/staves/dataM/{n}" for n in keep]
dev = (S / "dev-L.txt").read_text().split()
madrid = [f"/staves/dataT/{p.name}" for p in sorted((CACHE / "dataT").glob("samples.*.txt"))]
op32 = ["/staves/dataM/samples.Op32-G201-206.txt"]
name = "R1-tf8-matched"
args = [name, "--init", "E2-tf8", "--init-file", "best.pt", "--amp", "--train", *train, "--dev", *dev, "--epochs", "30",
        "--lr", "1e-4", "--eval-every", "3", "--patience", "3", "--lora-r", "64", "--lora-mlp"]
t = run(["modal", "run", "modal_app.py::main", "--gpu", "L40S", "--args", " ".join(args)], cwd=MUS)
(S / f"{name}.log").write_text(t)
stav = re.search(r"(\d+) training staves", t)
best = re.findall(r"best ([\d.]+) kept", t) or sorted(re.findall(r"dev SER ([\d.]+)", t))[:1]
out.append(f"{name}: {stav.group(1) if stav else '?'} training staves, practice exam best {best[0] if best else '?'}")
t = run(["uv", "run", str(MUS / "read.py"), str(E), "--run", name, "--file", "best.pt"], cwd=LAB)
m = re.search(r"bars exact (\d+)/347", t)
out.append(f"{name} clean test: {m.group(1) if m else '?'}/347 bars exact")
for test, samples in (("Madrid", madrid), ("Op32", op32)):
    for reader in (name,):
        t = run(["modal", "run", "modal_app.py::main", "--args", " ".join([f"{test.lower()}-{reader}", "--init", reader,
                 "--init-file", "best.pt", "--epochs", "0", "--train", *samples, "--dev", *samples])], cwd=MUS)
        m = re.search(r"dev SER ([\d.]+)\s+exact (\d+)/(\d+)", t)
        out.append(f"{test}, {reader}: SER {m.group(1)}, exact {m.group(2)}/{m.group(3)}" if m else f"{test}, {reader}: ? {t[-200:]}")
done()
