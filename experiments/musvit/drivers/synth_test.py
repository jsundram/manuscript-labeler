"""The synthesis test: D1's recipe (from E2-tf8; Op. 48 + re-paired Philhar; practice exam for early stopping) on
dataL2, without (S0) and with (S1) synthetic staves: half of each pass drawn afresh from dataS (copyist.py: OpenScore
quartets and our own training music, drawn in our copyists' manners). Then the clean test for both.
D1 for reference: practice exam 0.189 at pass 24, clean test 263/347 (Modal)."""
import re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
S = Path(__file__).parent
MUS = Path("/Users/jsundram/Dropbox/Code/manuscript-labeler/experiments/musvit")
CACHE = Path.home() / ".cache/manuscript-labeler/zeus"
out = []


def done(code=0):
    (S / "synth-summary.md").write_text("\n".join(out) + "\n"); print("\n".join(out)); sys.exit(code)


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode:
        out.append(f"FAILED: {' '.join(map(str, cmd))[:300]}\n{(r.stdout + r.stderr)[-2000:]}"); done(1)
    return r.stdout + r.stderr


run(["modal", "volume", "put", "--force", "musvit-staves", str(CACHE / "dataS"), "/dataS"])
op48 = [t.replace("/staves/dataL/", "/staves/dataL2/") for t in (S / "train-L.txt").read_text().split() if "/dataL/" in t]
dataM = [f"/staves/dataM/{p.name}" for p in sorted((CACHE / "dataM").glob("samples.*.txt"))]
dev = [t.replace("/staves/dataL/", "/staves/dataL2/") for t in (S / "dev-L.txt").read_text().split()]
synth = ["/staves/dataS/samples.S-osq.txt", "/staves/dataS/samples.S-own.txt"]
common = ["--init", "E2-tf8", "--init-file", "best.pt", "--amp", "--train", *op48, *dataM, "--dev", *dev,
          "--epochs", "30", "--lr", "1e-4", "--eval-every", "3", "--patience", "3", "--lora-r", "64", "--lora-mlp"]
runs = {"S0-tf8-L2": common, "S1-tf8-L2-synth50": common + ["--replay", "0.5", "--replay-from", *synth]}


def train(name):
    t = run(["modal", "run", "modal_app.py::main", "--gpu", "L40S", "--args", " ".join([name, *runs[name]])], cwd=MUS)
    (S / f"{name}.log").write_text(t)
    stav = re.search(r"(\d+) training staves", t)
    rep = re.search(r"replay: .*", t)
    sers = re.findall(r"epoch +(\d+) .*dev SER ([\d.]+)", t)
    best = min(sers, key=lambda x: float(x[1])) if sers else None
    line = (f"{name}: {stav.group(1) if stav else '?'} training staves{'; ' + rep.group(0) if rep else ''}; practice exam by pass: "
            + ", ".join(f"{e} {s}" for e, s in sers) + (f"; best {best[1]} at pass {best[0]}" if best else ""))
    r = run(["uv", "run", str(MUS / "read.py"), str(Path.home() / "Dropbox/Code/boccherini-opus-48"), "--run", name, "--file", "best.pt"],
            cwd=MUS.parent.parent)
    m = re.search(r"bars exact (\d+)/347.*", r)
    return line + f"\n{name} clean test: {m.group(0) if m else '?'}"


with ThreadPoolExecutor(2) as ex:
    for res in ex.map(train, runs):
        out.append(res)
out.append("D1 (dataL, for reference): practice exam 0.189 at pass 24; clean test 263/347 on Modal")
done()
