"""The MuSViT public-benchmark runs in parallel (but the first, already running), 60 s apart."""
import re, subprocess, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
S = Path(__file__).parent
MUS = Path("/Users/jsundram/Dropbox/Code/manuscript-labeler/experiments/musvit")
jobs = [(r, f, t) for r, f in (("E2-tf8", "best.pt"), ("D1-tf8-M", "best.pt"), ("D3-tf8-all", "reader.pt"))
        for t in ("dolores", "omniomr")][1:]
def one(k):
    run, file, test = jobs[k]
    time.sleep(60 * k)
    samples = f"/staves/public/{test}/samples.test.txt"
    args = [f"bench-{test}-{run}", "--init", run, "--init-file", file, "--epochs", "0", "--train", samples, "--dev", samples]
    r = subprocess.run(["modal", "run", "modal_app.py::main", "--args", " ".join(args)], cwd=MUS, capture_output=True, text=True)
    t = r.stdout + r.stderr
    (S / "bench" / f"{test}-{run}.log").write_text(t)
    m = re.search(r"dev SER ([\d.]+)\s+exact (\d+)/(\d+)\s+\(runaways (\d+); SER cut at 2x ([\d.]+)", t)
    line = f"{test} {run}: " + (f"SER {m.group(1)}, exact {m.group(2)}/{m.group(3)}, runaways {m.group(4)}, SER cut at 2x {m.group(5)}" if m else "FAILED " + t[-300:])
    print(line, flush=True)
    return line
with ThreadPoolExecutor(len(jobs)) as ex:
    lines = list(ex.map(one, range(len(jobs))))
(S / "bench" / "musvit-par-summary.txt").write_text("\n".join(lines) + "\n")
