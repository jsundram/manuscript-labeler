"""The hand-or-music test (2026-10-19). SF1/SF2's recipe exactly (synth_first.py), only the synthetic stage's staves
changed: Philhar's music (philhar_lines.py: 2,444 paired staves at their manuscript length + 5,595 unpaired lines),
10,790 rows drawn two ways (philhar_render.py), the same rows in both:
  PF1-copyist / PF2-copyist: drawn by copyist.py in our copyists' hands;
  PF1-plain   / PF2-plain:   Verovio's plain engraving, printed font, nothing drawn.
Stage A from E2-tf8 on the synthetic rows alone (10 passes, practice exam every 2, patience 2); stage B D1's recipe on
dataL2 + dataM from stage A. Both arms run side by side (2 GPUs). Then the clean test for each, and paired bootstrap
intervals (bars exact, 347 bars, 10,000 resamples) against SF2, S0 and each other."""
import json, random, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
S = Path(__file__).parent
LAB = Path("/Users/jsundram/Dropbox/Code/manuscript-labeler")
MUS = LAB / "experiments/musvit"
RES = LAB / "experiments/zeus/results"
CACHE = Path.home() / ".cache/manuscript-labeler/zeus"
out = []


def done(code=0):
    (S / "philhar-first-summary.md").write_text("\n".join(out) + "\n"); print("\n".join(out)); sys.exit(code)


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode:
        out.append(f"FAILED: {' '.join(map(str, cmd))[:300]}\n{(r.stdout + r.stderr)[-2000:]}"); done(1)
    return r.stdout + r.stderr


for d in ("dataPc", "dataPp"):
    run(["modal", "volume", "put", "--force", "musvit-staves", str(CACHE / d), f"/{d}"])
op48 = [t.replace("/staves/dataL/", "/staves/dataL2/") for t in (S / "train-L.txt").read_text().split() if "/dataL/" in t]
dataM = [f"/staves/dataM/{p.name}" for p in sorted((CACHE / "dataM").glob("samples.*.txt"))]
dev = [t.replace("/staves/dataL/", "/staves/dataL2/") for t in (S / "dev-L.txt").read_text().split()]


def stage_a(data):
    return ["--init", "E2-tf8", "--init-file", "best.pt", "--amp", "--train", f"/staves/{data}/samples.P.txt", "--dev", *dev,
            "--epochs", "10", "--lr", "1e-4", "--eval-every", "2", "--patience", "2", "--lora-r", "64", "--lora-mlp"]


def stage_b(init):
    return ["--init", init, "--init-file", "best.pt", "--amp", "--train", *op48, *dataM, "--dev", *dev,
            "--epochs", "30", "--lr", "1e-4", "--eval-every", "3", "--patience", "3", "--lora-r", "64", "--lora-mlp"]


def train(name, args):
    t = run(["modal", "run", "modal_app.py::main", "--gpu", "L40S", "--args", " ".join([name, *args])], cwd=MUS)
    (S / f"{name}.log").write_text(t)
    stav = re.search(r"(\d+) training staves", t)
    sers = re.findall(r"epoch +(\d+) .*dev SER ([\d.]+)", t)
    best = min(sers, key=lambda x: float(x[1])) if sers else None
    return (f"{name}: {stav.group(1) if stav else '?'} training staves; practice exam by pass: "
            + ", ".join(f"{e} {s}" for e, s in sers) + (f"; best {best[1]} at pass {best[0]}" if best else ""))


def score(name):
    r = run(["uv", "run", str(MUS / "read.py"), str(Path.home() / "Dropbox/Code/boccherini-opus-48"), "--run", name,
             "--file", "best.pt"], cwd=LAB)
    m = re.search(r"bars exact (\d+)/347.*", r)
    return f"{name} clean test: {m.group(0) if m else '?'}"


def arm(tag):
    a, b = f"PF1-{tag}", f"PF2-{tag}"
    lines = [train(a, stage_a("dataPc" if tag == "copyist" else "dataPp")), score(a)]
    lines += [train(b, stage_b(a)), score(b)]
    return lines


with ThreadPoolExecutor(2) as ex:
    for lines in ex.map(arm, ("copyist", "plain")):
        out += lines


def exact(name):
    bars = json.loads((RES / f"D-B_KHM-603-I-musvit-{name}-best.json").read_text())["bars"]
    return {(b["part"], b["bar"]): b["exact"] for b in bars}


def ci(x, y, n=10000):
    """y's bars exact less x's, with a paired bootstrap 95% interval."""
    X, Y = exact(x), exact(y)
    keys = sorted(set(X) & set(Y))
    d = [int(Y[k]) - int(X[k]) for k in keys]
    rng = random.Random(0)
    boots = sorted(sum(rng.choice(d) for _ in d) for _ in range(n))
    return f"{y} against {x}: {sum(d):+d} bars ({boots[int(0.025 * n)]:+d} to {boots[int(0.975 * n)]:+d})"


out.append("")
for x, y in (("SF2-tf8-L2-after-synth", "PF2-copyist"), ("PF2-copyist", "PF2-plain"), ("SF2-tf8-L2-after-synth", "PF2-plain"),
             ("S0-tf8-L2", "PF2-copyist"), ("S0-tf8-L2", "PF2-plain"), ("SF1-synth", "PF1-copyist"), ("PF1-copyist", "PF1-plain")):
    out.append(ci(x, y))
out.append("For reference: SF1 0.228 practice exam, 222/347; SF2 0.170, 278/347; S0 0.181, 266/347")
done()
