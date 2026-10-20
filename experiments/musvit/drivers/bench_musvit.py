"""Score MuSViT readers on the Dolores and OmniOMR test staves (score only, on Modal)."""
import re, subprocess, time
from pathlib import Path
S = Path(__file__).parent
MUS = Path("/Users/jsundram/Dropbox/Code/manuscript-labeler/experiments/musvit")
out = []
for run, file in (("E2-tf8", "best.pt"), ("D1-tf8-M", "best.pt"), ("D3-tf8-all", "reader.pt")):
    for test in ("dolores", "omniomr"):
        samples = f"/staves/public/{test}/samples.test.txt"
        args = [f"bench-{test}-{run}", "--init", run, "--init-file", file, "--epochs", "0", "--train", samples, "--dev", samples]
        r = subprocess.run(["modal", "run", "modal_app.py::main", "--args", " ".join(args)], cwd=MUS, capture_output=True, text=True)
        t = r.stdout + r.stderr
        (S / "bench" / f"{test}-{run}.log").write_text(t)
        m = re.search(r"dev SER ([\d.]+)\s+exact (\d+)/(\d+)\s+\(runaways (\d+); SER cut at 2x ([\d.]+)", t)
        out.append(f"{test} {run}: " + (f"SER {m.group(1)}, exact {m.group(2)}/{m.group(3)}, runaways {m.group(4)}, SER cut at 2x {m.group(5)}" if m else "FAILED " + t[-300:]))
        print(out[-1], flush=True)
(S / "bench" / "musvit-summary.txt").write_text("\n".join(out) + "\n")
