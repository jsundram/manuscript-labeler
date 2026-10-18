# /// script
# requires-python = ">=3.11"
# dependencies = ["torch", "transformers", "peft", "safetensors", "pillow", "numpy"]
# ///
"""Package a trained MuSViT reader for release, as zeus-score fetches
models: a folder of reader.safetensors (the whole reader, its encoder's
adapters folded in, in half precision), reader.json (the encoder's config
and the decoder's shape), vocab.json, LICENSE and NOTICE.md, and the
folder as NAME-VERSION.tar.gz beside it. proto.load_release reads it back.

    uv run experiments/musvit/release.py RUN FILE NAME VERSION --out DIR --licence LICENSE --notice NOTICE.md

Prints the sha256 of reader.safetensors and of the archive, for the
registry (zeus-score/zeus_score/models.json).
"""

import argparse
import hashlib
import json
import shutil
import sys
import tarfile
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proto  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("file", help="reader.pt or best.pt")
    ap.add_argument("name")
    ap.add_argument("version")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--licence", type=Path, required=True, help="the CC BY-NC-SA 4.0 text")
    ap.add_argument("--notice", type=Path, required=True, help="NOTICE.md: what the model is, its licence, attribution")
    a = ap.parse_args()
    from safetensors.torch import save_file

    model, vocab = proto.load(a.run, a.file)
    if model.lstm is not None or model.zeus is not None:
        sys.exit("release.py: only readers with the transformer decoder are released")
    model.encoder = model.encoder.merge_and_unload()
    model.eval()
    state = {k: v.detach().half().contiguous() for k, v in model.state_dict().items()}
    d = a.out / f"{a.name}@{a.version}"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    save_file(state, d / "reader.safetensors")
    reader = {"vit": model.encoder.config.to_dict(), "d": model.project.out_features,
              "layers": len(model.decoder.layers), "decoder": "transformer", "memory": model.memory,
              "height": proto.H, "from": {"run": a.run, "file": a.file}}
    (d / "reader.json").write_text(json.dumps(reader, indent=1))
    (d / "vocab.json").write_text(json.dumps(vocab, indent=1))
    shutil.copy(a.licence, d / "LICENSE")
    weights = sha256(d / "reader.safetensors")
    (d / "NOTICE.md").write_text(a.notice.read_text().rstrip() + f"\n\nsha256 of reader.safetensors:\n{weights}\n")

    # read back: the same parameters, to half precision
    back, _ = proto.load_release(d)
    for k, v in back.state_dict().items():
        assert torch.equal(v, state[k].float()), k

    archive = a.out / f"{a.name}-{a.version}.tar.gz"
    with tarfile.open(archive, "w:gz") as t:
        for f in sorted(d.iterdir()):
            t.add(f, arcname=f"{d.name}/{f.name}")
    print(f"{d}\n  reader.safetensors {(d / 'reader.safetensors').stat().st_size / 1e6:.0f} MB, sha256 {weights}")
    print(f"{archive}\n  {archive.stat().st_size / 1e6:.0f} MB, sha256 {sha256(archive)}")


if __name__ == "__main__":
    main()
