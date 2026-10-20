"""The cheap runs (NEXT.md E1, and the strip-height test), on Modal.

    python cheap.py replay   # H1-L2 (no replay), H1-L2-r10, H1-L2-r30 in parallel, then each scored
    python cheap.py height   # E2-h96 (stage 1 at 96 px, E2-tf8's recipe), D1-h96 (D1's recipe on dataL), clean test

Readings land in this folder (<test>-<run>.json); summary in <mode>-summary.md.
"""
import json, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
S = HERE.parent
MUS = Path("/Users/jsundram/Dropbox/Code/manuscript-labeler/experiments/musvit")
LAB, E = MUS.parent.parent, Path.home() / "Dropbox/Code/boccherini-opus-48"
CACHE = Path.home() / ".cache/manuscript-labeler/zeus"
P = "/staves/public"
STAGE1 = [f"{P}/dolores/samples.train.txt", f"{P}/dolores/samples.validation.txt",
          f"{P}/omniomr/samples.train.txt", f"{P}/omniomr/samples.validation.txt"]
STAGE2 = ["--epochs", "30", "--lr", "1e-4", "--eval-every", "3", "--patience", "3", "--lora-r", "64", "--lora-mlp"]
out = []


def log(s):
    out.append(s)
    print(s, flush=True)


def run(cmd, name=None, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    t = r.stdout + r.stderr
    if name:
        (HERE / f"{name}.log").write_text(t)
    if r.returncode:
        log(f"FAILED: {' '.join(map(str, cmd))[:300]}\n{t[-2000:]}")
    return t


def train(name, args, gpu="L40S"):
    t = run(["modal", "run", "modal_app.py::main", "--gpu", gpu, "--args", " ".join([name, *args])], name, cwd=MUS)
    stav = re.search(r"(\d+) training staves.*", t)
    rep = re.search(r"replay: .*", t)
    sers = re.findall(r"epoch +(\d+) .*dev SER ([\d.]+)", t)
    best = min(sers, key=lambda x: float(x[1])) if sers else None
    log(f"{name}: {stav.group(0) if stav else '?'}; {rep.group(0) + '; ' if rep else ''}practice exam "
        + ", ".join(f"{e} {s}" for e, s in sers) + (f"; best {best[1]} at pass {best[0]}" if best else ""))
    return t


def clean(name, file="best.pt"):
    t = run(["uv", "run", str(MUS / "read.py"), str(E), "--run", name, "--file", file], f"clean-{name}", cwd=LAB)
    m = re.search(r"bars exact (\d+)/347", t)
    log(f"{name} clean test: {m.group(1) if m else '?'}/347 bars exact")


def read_sets(jobs):
    """jobs: [(tag, run, file, samples path on the volume)] -> HERE/<tag>-<run>.json, all in one app."""
    sys.path.insert(0, str(MUS))
    import modal
    from modal_app import app, read_samples
    with modal.enable_output(), app.run():
        calls = [read_samples.spawn(r, f, s) for _, r, f, s in jobs]
        for (tag, r, f, s), c in zip(jobs, calls):
            (HERE / f"{tag}-{r}.json").write_text(json.dumps(c.get()))
            print("read", tag, r, flush=True)


def replay():
    op48 = [t.replace("/dataL/", "/dataL2/") for t in (S / "train-L.txt").read_text().split() if "/dataL/" in t]
    keep = [p.name for p in sorted((CACHE / "dataM").glob("samples.*.txt")) if not re.match(r"samples\.Op(22|32)-", p.name)]
    tr = op48 + [f"/staves/dataM/{n}" for n in keep]
    dev = [t.replace("/dataL/", "/dataL2/") for t in (S / "dev-L.txt").read_text().split()]
    base = ["--init", "E2-tf8", "--init-file", "best.pt", "--amp", "--train", *tr, "--dev", *dev, *STAGE2]
    runs = {"H1-L2": [], "H1-L2-r10": ["--replay", "0.1", "--replay-from", *STAGE1],
            "H1-L2-r30": ["--replay", "0.3", "--replay-from", *STAGE1]}
    with ThreadPoolExecutor(3) as ex:
        list(ex.map(lambda kv: train(kv[0], base + kv[1]), runs.items()))
    for r in runs:  # one at a time: compare.py renders and caches pages
        clean(r)
    madrid = [f"/staves/dataT/{p.name}" for p in sorted((CACHE / "dataT").glob("samples.*.txt"))]
    sets = [("madrid", s) for s in madrid] + [("op32", "/staves/dataM/samples.Op32-G201-206.txt"),
                                              ("dolores", f"{P}/dolores/samples.test.txt"),
                                              ("omniomr", f"{P}/omniomr/samples.test.txt")]
    jobs = [(f"{tag}{i}" if tag == "madrid" else tag, r, "best.pt", s)
            for r in runs for i, (tag, s) in enumerate(sets)]
    read_sets(jobs)
    (HERE / "replay-done").write_text("\n".join(runs))


def height2():
    op48 = [t for t in (S / "train-L.txt").read_text().split() if "/dataL/" in t]
    dataM = [f"/staves/dataM/{p.name}" for p in sorted((CACHE / "dataM").glob("samples.*.txt"))]
    dev = (S / "dev-L.txt").read_text().split()
    train("D1-h96", ["--init", "E2-h96", "--init-file", "best.pt", "--amp", "--train", *op48, *dataM, "--dev", *dev, *STAGE2])
    clean("D1-h96")
    read_sets([("dolores", "E2-h96", "best.pt", f"{P}/dolores/samples.test.txt"),
               ("dolores", "D1-h96", "best.pt", f"{P}/dolores/samples.test.txt")])


def height():
    extra = ([f"/staves/dataJ/{p.name}" for p in sorted((CACHE / "dataJ").glob("samples.*.txt"))]
             + [f"/staves/dataG/{p.name}" for p in sorted((CACHE / "dataG").glob("samples.*union*.txt"))]
             + ["/staves/dataK/samples.F-Po_RES-507-17-II.txt", "/staves/dataK/samples.F-Pn_Vma-ms-1067-3-noslur-II.txt"])
    t = train("E2-h96", ["--encoder", "full", "--amp", "--train", *STAGE1, "--vocab-extra", *extra,
                         "--dev", f"{P}/dolores/samples.test400.txt", "--dev-limit", "200", "--epochs", "60",
                         "--eval-every", "5", "--patience", "3", "--layers", "8", "--height", "96"])
    if "dev SER" not in t:
        log("stage 1 did not finish"); return
    op48 = [t for t in (S / "train-L.txt").read_text().split() if "/dataL/" in t]
    dataM = [f"/staves/dataM/{p.name}" for p in sorted((CACHE / "dataM").glob("samples.*.txt"))]
    dev = (S / "dev-L.txt").read_text().split()
    train("D1-h96", ["--init", "E2-h96", "--init-file", "best.pt", "--amp", "--train", *op48, *dataM, "--dev", *dev, *STAGE2])
    clean("D1-h96")
    read_sets([("dolores", "E2-h96", "best.pt", f"{P}/dolores/samples.test.txt"),
               ("dolores", "D1-h96", "best.pt", f"{P}/dolores/samples.test.txt")])


if __name__ == "__main__":
    mode = sys.argv[1]
    try:
        {"replay": replay, "height": height, "height2": height2}[mode]()
    finally:
        (HERE / f"{mode}-summary.md").write_text("\n".join(out) + "\n")
