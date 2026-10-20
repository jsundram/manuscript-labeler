"""pointer.py on a Modal GPU, with the reader from the musvit volume and the staves from musvit-staves' pos/.

    modal volume put musvit-staves DIR pos/DIR        # pos_data.py's staves, once per set
    modal run experiments/musvit/pointer_modal.py --args "NAME --train /staves/pos/A /staves/pos/B --test /staves/pos/C"

The run lands in the musvit volume's runs/NAME/ (pointer.pt, log.json, predictions-*.json); fetch it with
`modal volume get musvit runs/NAME <dir>`.
"""
import os
import shlex
import subprocess
from pathlib import Path

import modal

HERE = Path(__file__).parent
app = modal.App("musvit-pointer")
image = (modal.Image.debian_slim(python_version="3.12")
         .uv_pip_install("torch", "transformers", "peft", "pillow", "numpy")
         .add_local_file(HERE / "proto.py", "/root/proto.py")
         .add_local_file(HERE / "pointer.py", "/root/pointer.py"))
cache = modal.Volume.from_name("musvit")
staves = modal.Volume.from_name("musvit-staves")


def local_copy(src: str, dst: str, threads: int = 64):
    """The staves to the container's disk first, 64 at a time (modal_app.local_copy: a volume file's first read is slow)."""
    from concurrent.futures import ThreadPoolExecutor
    files = [Path(d) / f for d, _, fs in os.walk(src) for f in fs]

    def one(f):
        out = Path(dst) / f.relative_to(src)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(f.read_bytes())
    with ThreadPoolExecutor(threads) as ex:
        list(ex.map(one, files))
    print(f"copied {len(files)} files", flush=True)


@app.function(image=image, gpu="L4", timeout=8 * 3600, volumes={"/cache": cache, "/staves": staves})
def train(args: list[str]):
    local_copy("/staves/pos", "/tmp/pos")
    args = [a.replace("/staves/pos/", "/tmp/pos/", 1) for a in args]
    try:
        subprocess.run(["python", "/root/pointer.py", *args], check=True, env={**os.environ, "MUSVIT_CACHE": "/cache"})
    finally:
        cache.commit()


@app.local_entrypoint()
def main(args: str, gpu: str = "L4"):
    train.with_options(gpu=gpu).remote(shlex.split(args))
