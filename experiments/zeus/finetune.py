# /// script
# requires-python = "==3.10.*"
# dependencies = [
#   "zeus @ git+https://github.com/OmniOMR/zeus.git@c8569eb1c8b5bb24511de6a5e53ef2450de6206c",
#   "tensorflow-macos==2.12.0; sys_platform == 'darwin' and platform_machine == 'arm64'",
#   "numpy", "pillow",
# ]
# [tool.uv]
# override-dependencies = ["tensorflow; sys_platform != 'darwin' or platform_machine != 'arm64'"]
# ///
"""Fine-tune Zeus on staves built by dataset.py: Zeus's own `pickle` and
`train` commands, run in ~/.cache/manuscript-labeler/zeus/runs/ (where
Zeus writes its logs and each epoch's snapshot, logs/<name>-<time>/).

    uv run experiments/zeus/finetune.py NAME --train SAMPLES... --dev SAMPLES... [--epochs 30] [--lr 1e-4]
        [--decay cos|none] [--augment h:8]

SAMPLES are dataset.py's samples.*.txt files (pickled first, if not yet).
Starts from compare.MODEL, the snapshot measured zero-shot. The learning
rate decays to nothing over the run by a cosine (Zeus's default); the
augmentation is Zeus's default, a sideways shift of up to 8 px (its docs'
fuller set: h:8,rotate:1,v:4,de,en3:0.2,n:0.01,c:-1:1,b:-0.5:0.2).
"""

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = Path.home() / ".cache" / "manuscript-labeler" / "zeus" / "runs"
MODEL = Path.home() / ".cache" / "manuscript-labeler" / "models" / "zeus" / "ayce-2026-08-03.model"


def pickled(samples: Path) -> Path:
    p = samples.with_suffix(".pickle")
    if not p.exists() or p.stat().st_mtime < samples.stat().st_mtime:
        from zeus.data.zeus_dataset import ZeusDataset
        ZeusDataset.load_from_samples_file(samples_file_path=samples, image_suffix="",
                                           show_progress_bar=False, benevolent=False).write_to_pickle_file(p)
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--train", nargs="+", type=Path, required=True)
    ap.add_argument("--dev", nargs="+", type=Path, default=[])
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--decay", choices=["cos", "none"], default="cos")
    ap.add_argument("--augment", default="h:8")
    a = ap.parse_args()
    train = [str(pickled(p.resolve())) for p in a.train]
    dev = [str(pickled(p.resolve())) for p in a.dev]
    RUNS.mkdir(parents=True, exist_ok=True)
    os.chdir(RUNS)
    from zeus.cli.run import run
    sys.argv = ["zeus", "train", "--experiment", a.name, "--model-snapshot", str(MODEL),
                "--train", *train, *(["--dev", *dev] if dev else []), "--epochs", str(a.epochs),
                "--batch-size", str(a.batch_size), "--learning-rate", str(a.lr), "--lr-decay", a.decay, "--augment", a.augment, "--quiet-tf"]
    run()


if __name__ == "__main__":
    main()
