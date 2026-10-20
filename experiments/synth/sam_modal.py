"""sam_train.py on a Modal GPU: the training and test windows go up with the script, the log and decoder come back
(and are kept on the copyist-sam-runs volume under the out directory's name, in case they can't be written here).
sam_eval.py likewise, with --eval: test directories and decoders go up, the table comes back.

    modal run experiments/synth/sam_modal.py::main --train-dir DIR --test-dir DIR --out DIR [--epochs 8] [--gpu L4] [--init decoder.pt]
    modal run experiments/synth/sam_modal.py::evaluate --tests DIR,DIR --decoders untrained,RUN/decoder.pt --out FILE.json
"""
import subprocess
import sys
from pathlib import Path

import modal

HERE = Path(__file__).resolve().parent
image = (modal.Image.debian_slim(python_version="3.12")
         .pip_install("torch==2.14.1", "torchvision", "transformers==5.20.1", "pillow", "numpy")
         .add_local_file(HERE / "sam_train.py", "/root/sam_train.py")
         .add_local_file(HERE / "sam_eval.py", "/root/sam_eval.py"))
app = modal.App("copyist-sam", image=image)
hf = modal.Volume.from_name("hf-cache", create_if_missing=True)
runs = modal.Volume.from_name("copyist-sam-runs", create_if_missing=True)


@app.function(gpu="L4", timeout=6 * 3600, volumes={"/root/.cache/huggingface": hf, "/runs": runs})
def train(files: dict[str, bytes], args: list[str], name: str = "") -> dict[str, bytes]:
    import os
    for fname, b in files.items():
        p = Path("/data") / fname
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b)
    r = subprocess.run([sys.executable, "/root/sam_train.py", "/data/train", "/data/test", "/out", *args],
                       capture_output=True, text=True)
    print(r.stdout[-20000:], r.stderr[-4000:])
    out = {"stdout.txt": (r.stdout + "\n" + r.stderr[-4000:]).encode()}
    for f in Path("/out").glob("*") if Path("/out").exists() else []:
        out[f.name] = f.read_bytes()
    if name:
        keep = Path("/runs") / name
        keep.mkdir(parents=True, exist_ok=True)
        for k, b in out.items():
            (keep / k).write_bytes(b)
        runs.commit()
    return out


@app.function(gpu="L4", timeout=2 * 3600, volumes={"/root/.cache/huggingface": hf})
def score(files: dict[str, bytes], tests: list[str], decoders: list[str]) -> str:
    for fname, b in files.items():
        p = Path("/data") / fname
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b)
    r = subprocess.run([sys.executable, "/root/sam_eval.py", "--decoders", *decoders, "--tests", *tests,
                        "--json", "/data/scores.json"], capture_output=True, text=True, cwd="/root")
    print(r.stdout[-20000:], r.stderr[-4000:])
    return Path("/data/scores.json").read_text() if Path("/data/scores.json").exists() else ""


@app.local_entrypoint()
def main(train_dir: str, test_dir: str, out: str, epochs: int = 8, gpu: str = "L4", lr: float = 1e-4, init: str = ""):
    files = {f"train/{f.name}": f.read_bytes() for f in Path(train_dir).glob("*.npz")}
    files |= {f"test/{f.name}": f.read_bytes() for f in Path(test_dir).glob("*.npz")}
    args = ["--epochs", str(epochs), "--lr", str(lr)]
    if init:  # an earlier stage's decoder to start from
        files["init/decoder.pt"] = Path(init).read_bytes()
        args += ["--init", "/data/init/decoder.pt"]
    res = train.with_options(gpu=gpu).remote(files, args, Path(out).name)
    o = Path(out)
    o.mkdir(parents=True, exist_ok=True)
    for name, b in res.items():
        (o / name).write_bytes(b)
    print((o / "stdout.txt").read_text()[-3000:])


@app.local_entrypoint()
def evaluate(tests: str, decoders: str, out: str):
    """Each decoder goes up as /data/dec/<its run directory>/decoder.pt, so the table names the run."""
    files, tnames, dnames = {}, [], []
    for t in tests.split(","):
        files |= {f"tests/{Path(t).name}/{f.name}": f.read_bytes() for f in Path(t).glob("*.npz")}
        tnames.append(f"/data/tests/{Path(t).name}")
    for d in decoders.split(","):
        if d == "untrained":
            dnames.append(d)
            continue
        key = f"dec/{Path(d).parent.name}/decoder.pt"
        files[key] = Path(d).read_bytes()
        dnames.append(f"/data/{key}")
    Path(out).write_text(score.remote(files, tnames, dnames))
