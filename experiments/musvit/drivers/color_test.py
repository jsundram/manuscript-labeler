"""The colour test: D1's recipe (from E2-tf8, Op. 48 + re-paired Philhar, practice exam for early stopping) on colour
crops, then the clean test in colour. Compare with D1: practice exam 0.189, clean test 263 (Modal) / 265 (Mac)."""
import re, subprocess, sys, time
from pathlib import Path
S = Path(__file__).parent
MUS = Path("/Users/jsundram/Dropbox/Code/manuscript-labeler/experiments/musvit")
CACHE = Path.home() / ".cache/manuscript-labeler/zeus"
T = S.parent / "tasks" / "b77psexcf.output"
out = []
def done(code=0):
    (S / "color-summary.md").write_text("\n".join(out) + "\n"); print("\n".join(out)); sys.exit(code)
def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode:
        out.append(f"FAILED: {' '.join(map(str, cmd))[:200]}\n{(r.stdout + r.stderr)[-1500:]}"); done(1)
    return r.stdout + r.stderr
while "dataT:" not in (T.read_text() if T.exists() else ""):
    if "Traceback" in (T.read_text() if T.exists() else ""):
        out.append("cutting failed: " + T.read_text()[-800:]); done(1)
    time.sleep(30)
out.append(T.read_text().strip())
for name in ("dataL-color", "dataM-color", "dataT-color"):
    run(["modal", "volume", "put", "--force", "musvit-staves", str(CACHE / name), f"/{name}"])
col = lambda p: p.replace("/staves/dataL/", "/staves/dataL-color/").replace("/staves/dataM/", "/staves/dataM-color/")
op48 = [col(t) for t in (S / "train-L.txt").read_text().split() if "/dataL/" in t]
dataM = [f"/staves/dataM-color/{p.name}" for p in sorted((CACHE / "dataM-color").glob("samples.*.txt"))]
dev = [col(t) for t in (S / "dev-L.txt").read_text().split()]
name = "D1c-tf8-M-color"
args = [name, "--init", "E2-tf8", "--init-file", "best.pt", "--amp", "--color", "--train", *op48, *dataM, "--dev", *dev,
        "--epochs", "30", "--lr", "1e-4", "--eval-every", "3", "--patience", "3", "--lora-r", "64", "--lora-mlp"]
t = run(["modal", "run", "modal_app.py::main", "--gpu", "L40S", "--args", " ".join(args)], cwd=MUS)
(S / f"{name}.log").write_text(t)
stav = re.search(r"(\d+) training staves", t)
sers = re.findall(r"epoch +(\d+) .*dev SER ([\d.]+)", t)
best = min(sers, key=lambda x: float(x[1])) if sers else None
out.append(f"{name}: {stav.group(1) if stav else '?'} training staves; practice exam by pass: " + ", ".join(f"{e} {s}" for e, s in sers)
           + (f"; best {best[1]} at pass {best[0]} (D1 grey: 0.189 at pass 24)" if best else ""))
t = run(["uv", "run", str(MUS / "read.py"), str(Path.home() / "Dropbox/Code/boccherini-opus-48"), "--run", name, "--file", "best.pt", "--color"],
        cwd=MUS.parent.parent)
m = re.search(r"bars exact (\d+)/347.*", t)
out.append(f"{name} clean test (colour): {m.group(0) if m else '?'} (D1 grey: 263/347 on Modal)")
done()
