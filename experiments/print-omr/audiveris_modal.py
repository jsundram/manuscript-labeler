# /// script
# requires-python = ">=3.11"
# dependencies = ["modal"]
# ///
"""Audiveris 5.11.0 (AGPL-3.0) on BA 2676's cleaned pages, on Modal, page by
page, into ~/Data/manuscript-labeler/experiments/print-omr/audiveris/<part>/.

    uv run experiments/print-omr/audiveris_modal.py vn1:14-18 vc:13-16 ...   (part:pages)

Why Modal: on the Mac, under the load other work puts on it (a load
average near 100), Audiveris's steps ran past any timeout (BEAMS, LEDGERS,
HEADS, 10+ minutes each on one page). The container is an L4 (the project's
rule for readings; Audiveris uses only its CPUs: 8 cores, 16 GB). The
Ubuntu 24.04 .deb from the release, which bundles its own Java.

Pages are split into two batches run at once (at most two GPUs), the
second launched a minute after the first. Each page writes p-NN.mxl (or
p-NN.mvtK.mxl, one per movement Audiveris finds on it) and its log.
Pages already done are skipped.
"""

import sys
import time
from pathlib import Path

import modal

DEB = "https://github.com/Audiveris/audiveris/releases/download/5.11.0/Audiveris-5.11.0-ubuntu24.04-x86_64.deb"
ROOT = Path.home() / "Data/manuscript-labeler/experiments/print-omr"

app = modal.App("print-omr-audiveris")
image = (modal.Image.from_registry("ubuntu:24.04", add_python="3.12")
         .env({"DEBIAN_FRONTEND": "noninteractive", "TZ": "Etc/UTC"})
         .apt_install("wget", "ca-certificates", "fontconfig", "libfreetype6", "libasound2t64", "libxi6",
                      "libxrender1", "libxtst6", "libgl1", "libgtk-3-0t64")
         .run_commands(f"wget -q {DEB} -O /tmp/audiveris.deb", "dpkg-deb -x /tmp/audiveris.deb /",  # its post-install script (desktop menus) fails in a container
                       "ls /opt/audiveris/bin"))


@app.function(image=image, gpu="L4", cpu=8, memory=16384, timeout=3 * 3600)
def read(pages: dict[str, bytes]) -> dict[str, bytes]:
    """{part/p-NN.png: PNG} -> {part/<file>: bytes} for every .mxl and .log written."""
    import subprocess
    import tempfile
    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for name, png in sorted(pages.items()):
            part, fname = name.split("/")
            src = tmp / "in" / part / fname
            src.parent.mkdir(parents=True, exist_ok=True)
            src.write_bytes(png)
            dest = tmp / "out" / part
            dest.mkdir(parents=True, exist_ok=True)
            t = time.time()
            r = subprocess.run(["/opt/audiveris/bin/Audiveris", "-batch", "-export", "-output", str(dest),
                                "-constant", "org.audiveris.omr.Main.sheetStepTimeOut=600", "--", str(src)],
                               capture_output=True, text=True)
            print(f"{name}: {time.time() - t:.0f} s, exit {r.returncode}", flush=True)
            for f in dest.iterdir():
                if f.suffix in (".mxl", ".log") and f.name.startswith(Path(fname).stem):
                    out[f"{part}/{f.name}"] = f.read_bytes()
            (dest / "stdout.txt").write_text(r.stdout[-5000:] + r.stderr[-5000:])
            out[f"{part}/{Path(fname).stem}.stdout.txt"] = (dest / "stdout.txt").read_bytes()
    return out


def parse(specs: list[str]) -> list[str]:
    names = []
    for s in specs:
        part, _, rng = s.partition(":")
        a, _, b = rng.partition("-")
        names += [f"{part}/p-{n:02d}.png" for n in range(int(a), int(b or a) + 1)]
    return names


@app.local_entrypoint()
def main(pages: str):
    names = [n for n in parse(pages.split()) if not list((ROOT / "audiveris").glob(n.replace(".png", ".*mxl")))]
    print(len(names), "pages to read")
    batches = [names[0::2], names[1::2]]
    calls = []
    for k, b in enumerate(batches):
        if not b:
            continue
        if k:
            time.sleep(60)  # staggered
        calls.append(read.spawn({n: (ROOT / "clean" / n).read_bytes() for n in b}))
    for c in calls:
        for name, data in c.get().items():
            f = ROOT / "audiveris" / name
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)
    print("done")


if __name__ == "__main__":
    sys.exit("run with: modal run experiments/print-omr/audiveris_modal.py --pages 'vn1:14-18 vc:13-16'")
