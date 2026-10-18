"""Run proto.py on a Modal GPU (BRIEF.md, "Modal").

    modal run experiments/musvit/modal_app.py::main --args "NAME --train /staves/dataJ/samples.X.txt ..." [--gpu L4]

Volumes (made once with `modal volume create` and `modal volume put`):
  musvit-staves  /staves  dataset.py's staves: dataJ/, dataG/ (no pickles; its
                          three symlinked per-hand folders weren't uploaded, so
                          use dataG's *-union sets), public/{dolores,omniomr}
                          at 256 px high. Paths under /staves/ are copied to
                          the container's disk first (local_copy).
  musvit         /cache   weights/musvit-light (and musvit), runs/NAME/

The run's model and log land in the musvit volume's runs/NAME/; fetch them
with `modal volume get musvit runs/NAME <dir>`. The Modal client is a uv
tool: `uv tool install modal`.
"""

import os
import shlex
import subprocess
from pathlib import Path

import modal

app = modal.App("musvit-zeus")
image = (modal.Image.debian_slim(python_version="3.12")
         .uv_pip_install("torch", "transformers", "peft", "pillow", "numpy")
         .add_local_file(Path(__file__).parent / "proto.py", "/root/proto.py")
         .add_local_file(Path(__file__).parent / "pretrain.py", "/root/pretrain.py"))
LABELER = Path(__file__).resolve().parent.parent.parent
cut_image = (modal.Image.debian_slim(python_version="3.12").apt_install("poppler-utils")
             .uv_pip_install("numpy", "pillow")
             .add_local_file(LABELER / "detect.py", "/root/cut/detect.py")
             .add_local_file(LABELER / "labels.py", "/root/cut/labels.py")
             .add_local_file(LABELER / "experiments" / "zeus" / "compare.py", "/root/cut/compare.py"))
cache = modal.Volume.from_name("musvit")
staves = modal.Volume.from_name("musvit-staves")


def local_copy(src="/staves", dst="/tmp/staves", threads=64, skip=("pdfs", "unlabeled")):
    """Copy the volume's staves to the container's own disk first. Opening a
    file on the volume the first time takes about 0.15 s, so reading
    11,000 staves one by one left the GPU idle for close to an hour; 64 at
    a time takes about a minute."""
    import time
    from concurrent.futures import ThreadPoolExecutor
    t = time.time()
    files = [Path(d) / f for d, _, fs in os.walk(src) for f in fs
             if not f.endswith(".pickle") and Path(d).relative_to(src).parts[:1] not in [(k,) for k in skip]]
    def one(f):
        out = Path(dst) / f.relative_to(src)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(f.read_bytes())
    with ThreadPoolExecutor(threads) as ex:
        list(ex.map(one, files))
    print(f"copied {len(files)} files to {dst} in {time.time() - t:.0f} s", flush=True)


@app.function(image=image, gpu="L4", timeout=24 * 3600, volumes={"/cache": cache, "/staves": staves})
def train(args: list[str]):
    local_copy()
    args = [a.replace("/staves/", "/tmp/staves/", 1) if a.startswith("/staves/") else a for a in args]
    try:
        subprocess.run(["python", "/root/proto.py", *args], check=True, env={**os.environ, "MUSVIT_CACHE": "/cache"})
    finally:
        cache.commit()


@app.function(image=image, gpu="L4", timeout=1800, volumes={"/cache": cache})
def read(run: str, file: str, crops: dict[str, bytes]) -> dict[str, str]:
    """LMX for each staff crop, by a trained run's reader (read.py)."""
    os.environ["MUSVIT_CACHE"] = "/cache"
    import sys
    sys.path.insert(0, "/root")
    import proto
    return proto.read_crops(run, file, crops, "cuda")


@app.function(image=image, gpu="L4", timeout=6 * 3600, volumes={"/cache": cache, "/staves": staves})
def read_samples(run: str, file: str, samples: str) -> dict[str, str]:
    """LMX for each staff of a samples file in the staves volume (its lines,
    the staves' paths without suffix), by a trained run's reader: for test
    sets too big to send (the public benchmarks)."""
    from concurrent.futures import ThreadPoolExecutor
    os.environ["MUSVIT_CACHE"] = "/cache"
    import sys
    sys.path.insert(0, "/root")
    import proto
    root = Path(samples).parent
    lines = Path(samples).read_text().split()
    with ThreadPoolExecutor(64) as ex:  # each file's first read off the volume is slow
        crops = dict(zip(lines, ex.map(lambda l: (root / l).with_suffix(".jpg").read_bytes(), lines)))
    return proto.read_crops(run, file, crops, "cuda")


@app.function(image=image, gpu="L4", timeout=3600, volumes={"/cache": cache})
def read_nbest(run: str, file: str, crops: dict[str, bytes], k: int = 8) -> dict[str, list]:
    """Up to k readings of each staff crop, with log-probabilities (read.py --beam)."""
    os.environ["MUSVIT_CACHE"] = "/cache"
    import sys
    sys.path.insert(0, "/root")
    import proto
    return proto.read_nbest(run, file, crops, "cuda", k)


@app.function(image=cut_image, cpu=2, memory=4096, timeout=3600, volumes={"/staves": staves})
def cut_pages(pdf: str, pages: list[int]) -> int:
    """Every staff the labeler's detector finds on these pages of a PDF in
    /staves/pdfs, cut as compare.py cuts a staff (straightened, 2.5 spaces
    above and below), saved 256 px high under /staves/unlabeled/<pdf>/: for
    pretraining MuSViT on our manuscripts without labels."""
    import io
    import sys
    sys.path.insert(0, "/root/cut")
    import compare
    import detect
    from PIL import Image
    out = Path("/staves/unlabeled") / Path(pdf).stem
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for page in pages:
        try:
            g = compare.page_image(Path(pdf), page)
            systems = detect.detect_page(Image.fromarray(g.astype("uint8")))
        except Exception as e:  # a blank or odd page: skip it, say so
            print(f"{Path(pdf).name} p{page}: {type(e).__name__} {e}", flush=True)
            continue
        for i, s in enumerate(systems):
            im = Image.open(io.BytesIO(compare.staff_crop(g, s))).convert("L")
            if im.height < 8 or im.width < 64:
                continue
            im = im.resize((max(1, round(im.width * 256 / im.height)), 256), Image.LANCZOS)
            im.save(out / f"p{page:03d}s{i + 1}.jpg", quality=92)
            n += 1
    staves.commit()
    return n


@app.function(image=cut_image, volumes={"/staves": staves})
def page_counts() -> dict[str, int]:
    import subprocess
    counts = {}
    for f in sorted(Path("/staves/pdfs").rglob("*.pdf")):
        info = subprocess.run(["pdfinfo", str(f)], capture_output=True, text=True).stdout
        counts[str(f)] = int(next(l.split()[1] for l in info.splitlines() if l.startswith("Pages:")))
    return counts


@app.function(image=image, gpu="L40S", timeout=24 * 3600, volumes={"/cache": cache, "/staves": staves})
def pretrain(args: list[str]):
    local_copy(skip=("pdfs", "dataJ", "dataG", "dataK", "public"))
    try:
        subprocess.run(["python", "/root/pretrain.py", *args], check=True, env={**os.environ, "MUSVIT_CACHE": "/cache"})
    finally:
        cache.commit()


@app.local_entrypoint()
def pretrain_main(args: str):
    pretrain.remote(shlex.split(args))


@app.local_entrypoint()
def cut_all(chunk: int = 10):
    """modal run modal_app.py::cut_all: cut every page of every uploaded PDF."""
    jobs = [(pdf, list(range(k, min(k + chunk, n + 1))))
            for pdf, n in page_counts.remote().items() for k in range(1, n + 1, chunk)]
    print(f"{len(jobs)} jobs of up to {chunk} pages", flush=True)
    total = sum(cut_pages.starmap(jobs))
    print(f"cut {total} staves", flush=True)


@app.local_entrypoint()
def main(args: str, gpu: str = "L4"):
    train.with_options(gpu=gpu).remote(shlex.split(args))
