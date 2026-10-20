"""Overnight chain (2026-10-18). Waits for repair.sh and madrid.sh, then:
1. builds the Philhar pairs with two voices from the new pairings (dataM),
2. builds the Madrid test staves from the both-readers pairings (dataT),
3. uploads them, retrains stage 2 of C1 and C4 on Op. 48 + dataM (D1, D2),
4. scores C1, C4, D1, D2 and Zeus J on Madrid, and D1, D2 on the clean test,
5. writes overnight-summary.md. Stops at the first failure; won't launch
training once this month's metered spend passes $85."""
import json, random, re, subprocess, sys, time
from pathlib import Path

S = Path(__file__).parent
LAB = Path("/Users/jsundram/Dropbox/Code/manuscript-labeler")
ZEUS, MUS = LAB / "experiments/zeus", LAB / "experiments/musvit"
E = Path.home() / "Dropbox/Code/boccherini-opus-48"
L = Path.home() / "Dropbox/Code/boccherini-quartet-data/lilypond"
CACHE = Path.home() / ".cache/manuscript-labeler/zeus"
M = "musvit-C4-bocch-tf8-L-best"
LOG = S / "overnight.log"
SUMMARY = S / "overnight-summary.md"
PHILHAR = {  # source: quartets (as repair.sh)
    "F-Pn_RES-507-2": "Op33-1,Op33-2,Op33-3,Op33-4,Op33-5,Op33-6",
    **{f"Op02-{n}-G{158 + n}": f"Op02-{n}" for n in range(1, 7)},
    **{f"Op02-4-CZ-Pu-{p}": "Op02-4" for p in ("va", "vc", "vn1", "vn2")},
    **{f"Op22-{n}-G{182 + n}": f"Op22-{n}" for n in range(1, 7)},
    **{f"Op22-6-Vmbr153-{p}": "Op22-6" for p in ("va", "vc", "vn1", "vn2")},
    **{f"Op22-Paris-{p}": "Op22-4,Op22-2,Op22-6,Op22-3" for p in ("va", "vc", "vn1", "vn2")},
    "Op32-G201-206": "Op32-1,Op32-2,Op32-3,Op32-4,Op32-5,Op32-6",
    **{f"Op33-{n}-G{206 + n}": f"Op33-{n}" for n in range(1, 7)},
}
MADRID = {f"Op22-{n}-EMc": f"Op22-{n}" for n in (1, 2, 3, 4, 6)}
out = []


def log(*a):
    line = " ".join(str(x) for x in a)
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(time.strftime("%H:%M ") + line + "\n")


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode:
        log("FAILED:", " ".join(map(str, cmd))[:300])
        log((r.stdout + r.stderr)[-1500:])
        finish(failed=True)
    return r.stdout + r.stderr


def finish(failed=False):
    SUMMARY.write_text("\n".join(out) + ("\n\n**Stopped at a failure; see overnight.log.**\n" if failed else "\n"))
    print(SUMMARY.read_text())
    sys.exit(1 if failed else 0)


def spend() -> float:
    t = run(["modal", "billing", "summary"])
    return float(re.search(r"Metered Cost:\s+([\d.]+)", t).group(1))


def busy() -> bool:
    return subprocess.run(["pgrep", "-f", "repair.sh|madrid.sh"], capture_output=True).returncode == 0


log("waiting for repair.sh (its repair.done marker)")
while not (S / "repair.done").exists():
    if (S / "repair.failed").exists():
        out.append("Re-pairing failed: see repair-pair.txt.")
        finish(failed=True)
    time.sleep(60)
for f in ("repair-summary", "repair-pair", "br7afukum"):
    p = S / f"{f}.txt" if f.startswith("repair") else S.parent / "tasks" / f"{f}.output"
    if p.exists():
        out.append(f"### {f}\n```\n{p.read_text()[-3000:]}\n```")

# 1-2: datasets
from concurrent.futures import ThreadPoolExecutor
for name, sources, res in (("dataM", PHILHAR, f"-any-count-{M}"), ("dataT", MADRID, "-any-count-both")):
    def build(item):
        src, q = item
        rf = ZEUS / "results" / f"autopair-{src}{res}.json"
        if not rf.exists():
            log("no pairing for", src, "- skipped")
            return 0
        t = run(["uv", "run", str(ZEUS / "dataset.py"), str(E), "--pairs", src, "--philhar", str(L), "--quartets", q,
                 "--any-count", "--results", str(rf), "--out", str(CACHE / name)], cwd=LAB)
        m = re.search(r"(\d+) staves kept", t)
        log(name, src, (m.group(0) if m else t.strip().splitlines()[-1][:200]))
        return int(m.group(1)) if m else 0
    with ThreadPoolExecutor(6) as ex:  # each source writes its own folder and samples file
        kept = sum(ex.map(build, sources.items()))
    out.append(f"{name}: {kept} staves kept")
    log(name, "total", kept)
old = sum(len(p.read_text().split()) for p in (CACHE / "dataG").glob("samples.*union*.txt"))
out.append(f"(dataG, Zeus F's pairing without two voices: {old} staves)")
for name in ("dataM", "dataT"):
    for p in (CACHE / name).glob("*.pickle"):
        p.unlink()
    run(["modal", "volume", "put", "--force", "musvit-staves", str(CACHE / name), f"/{name}"])

# 3: retrain stage 2 on Op. 48 (dataL, as train-L) + dataM
train_L = (S / "train-L.txt").read_text().split()
op48 = [t for t in train_L if "/dataL/" in t]
dataM = [f"/staves/dataM/{p.name}" for p in sorted((CACHE / "dataM").glob("samples.*.txt"))]
dev = (S / "dev-L.txt").read_text().split()
runs = {"D1-tf8-M": "E2-tf8", "D2-bocch-tf8-M": "G1-bocch-tf8"}
for name, init in runs.items():
    if spend() > 85:
        out.append(f"Not launched {name}: spend past $85.")
        continue
    args = ["--init", init, "--init-file", "best.pt", "--amp", "--train", *op48, *dataM, "--dev", *dev, "--epochs", "30",
            "--lr", "1e-4", "--eval-every", "3", "--patience", "3", "--lora-r", "64", "--lora-mlp"]
    log("training", name)
    t = run(["modal", "run", "modal_app.py::main", "--gpu", "L40S", "--args", " ".join([name, *args])], cwd=MUS)
    (S / f"{name}.log").write_text(t)
    best = re.findall(r"best ([\d.]+) kept", t) or sorted(re.findall(r"dev SER ([\d.]+)", t))[:1]
    stav = re.search(r"(\d+) training staves", t)
    out.append(f"{name} (from {init}): {stav.group(1) if stav else '?'} training staves, practice exam best {best[0] if best else '?'}")

# 4: clean test for the new readers
for name in runs:
    if not (S / f"{name}.log").exists():
        continue
    t = run(["uv", "run", str(MUS / "read.py"), str(E), "--run", name, "--file", "best.pt"], cwd=LAB)
    m = re.search(r"bars exact (\d+)/347", t)
    out.append(f"{name} clean test: {m.group(1) if m else '?'}/347 bars exact")

# Madrid: SER and exact staves for each reader; Zeus J from its pairing cache
samples = [f"/staves/dataT/{p.name}" for p in sorted((CACHE / "dataT").glob("samples.*.txt"))]
for name in ("C1-tf8-L", "C4-bocch-tf8-L", *[n for n in runs if (S / f"{n}.log").exists()]):
    t = run(["modal", "run", "modal_app.py::main", "--args",
             " ".join([f"madrid-{name}", "--init", name, "--init-file", "best.pt", "--epochs", "0", "--train", *samples,
                       "--dev", *samples])], cwd=MUS)
    m = re.search(r"dev SER ([\d.]+)\s+exact (\d+)/(\d+)", t)
    out.append(f"Madrid, {name}: SER {m.group(1)}, exact {m.group(2)}/{m.group(3)}" if m else f"Madrid, {name}: ? ({t[-200:]})")


def edits(a, b):
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


e = r = ex = n = 0
for src in MADRID:
    cache = ZEUS / "answers" / f"{src}-auto-J-lr1e5-e8.model.json"
    if not cache.exists():
        continue
    by_staff = {k.split(":")[0]: v.split() for k, v in json.loads(cache.read_text()).items()}
    for lmx in (CACHE / "dataT" / src).glob("*.lmx"):
        if lmx.stem in by_staff:
            want = lmx.read_text().split()
            d = edits(by_staff[lmx.stem], want)
            e, r, ex, n = e + d, r + len(want), ex + (d == 0), n + 1
out.append(f"Madrid, Zeus J: SER {e / max(r, 1):.3f}, exact {ex}/{n}")
log("done")
finish()
