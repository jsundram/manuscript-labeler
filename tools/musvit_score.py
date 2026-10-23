# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = [
#   # transformers fixes the encoder's weight names the released file is saved under
#   "torch==2.14.1", "transformers==5.20.1", "safetensors==0.8.0", "numpy", "pillow",
#   # the LMX writer Zeus uses (dataset.py writes the readings with it), at Zeus's pin
#   "linearized-musicxml @ git+https://github.com/OMR-Research/lmx.git@87fca1c38bda83bc032596ab00af28412f92941d",
# ]
# ///
"""tools/zeus_score.py with a MuSViT reader (experiments/musvit/release.py's
folder) in Zeus's place: the same inputs, options and output, the model
`engine` "musvit". Each staff is cut as the reader was trained on it (the
same crop as Zeus's), read at 128 px high, and handed the reading
teacher-forced; on the Mac's GPU in half precision.

    uv run tools/musvit_score.py --model <release folder> --pdf ... (as zeus_score.py)
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if (HERE.parent / "experiments" / "musvit" / "proto.py").exists():  # a labeler checkout; in zeus-score they're beside this
    sys.path.insert(0, str(HERE.parent / "experiments" / "musvit"))
try:
    import zeus_score as engine
except ImportError:  # in the zeus-score package, zeus_score.py is engine/score.py
    import score as engine
import proto  # noqa: E402


class Reader:
    """A MuSViT reader, teacher-forced, one staff at a time: as zeus_score.Zeus."""
    engine = "musvit"
    commit = None
    too_long = f"its reading is longer than the reader's {proto.MAXLEN - 1} tokens"

    def __init__(self, path: Path):
        import torch
        self.torch, self.weights = torch, path / "reader.safetensors"
        self.device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        model, self.vocab = proto.load_release(path)
        self.model = proto.for_reading(model, self.device)
        self.dtype = next(self.model.parameters()).dtype
        self.inv = {i: t for t, i in self.vocab.items()}

    def unknown(self, toks: list[str]) -> list[str]:
        return sorted({t for t in toks if t not in self.vocab})

    def score(self, jpeg: bytes, readings: list[list[str]]) -> list[dict] | None:
        torch, v = self.torch, self.vocab
        if max(len(r) for r in readings) >= proto.MAXLEN:
            return None
        x, mask, _, _ = proto.batch([(jpeg, [])], v)
        mask = mask.to(self.device)
        out = []
        with torch.no_grad():
            mem = self.model.encode(x.to(self.device, self.dtype))
            for toks in readings:
                ids = [v.get(t, v[proto.UNK]) for t in toks] + [v[proto.EOS]]
                y = torch.tensor([[v[proto.BOS]] + ids[:-1]], device=self.device)
                lp = torch.log_softmax(self.model.decode(mem, mask, y)[0].float(), -1).cpu()
                best = lp.argmax(-1)
                out.append({"lp": [round(float(lp[k, i]), 3) for k, i in enumerate(ids)],
                            "best": [self.inv[int(i)] for i in best],
                            "best_lp": [round(float(lp[k, i]), 3) for k, i in enumerate(best)]})
        return out

    def read(self, jpegs: list[bytes], batch: int) -> tuple[list[dict], dict]:
        """The reader's own readings of the staves, greedy, `batch` at a time
        in order of width (as in training; 1: each alone): per staff its
        tokens, and per token and the end, its log-probability, the runner-up
        and that one's; and how it was decoded."""
        torch, v = self.torch, self.vocab
        order = sorted(range(len(jpegs)), key=lambda k: proto.aspect((jpegs[k], [])))
        out = [None] * len(jpegs)
        for k in range(0, len(order), batch):
            chunk = order[k: k + batch]
            x, mask, _, _ = proto.batch([(jpegs[i], []) for i in chunk], v)
            scores: list = []
            with torch.no_grad():
                mem = self.model.encode(x.to(self.device, self.dtype))
                ids = self.model.read_cached(mem, mask.to(self.device), v[proto.BOS], v[proto.EOS], scores=scores)
            for i, row, sc in zip(chunk, ids, scores):
                out[i] = {"tokens": [self.inv[t] for t in row], "ended": len(sc) == len(row) + 1,
                          "lp": [round(s[0], 3) for s in sc], "runner_up": [self.inv[s[1]] for s in sc],
                          "runner_up_lp": [round(s[2], 3) for s in sc]}
        precision = {torch.float16: "float16", torch.bfloat16: "bfloat16", torch.float32: "float32"}[self.dtype]
        return out, {"method": "greedy", "beam": 1, "batch": batch, "batch_order": "by width",
                     "device": self.device, "precision": precision, "max_tokens": proto.MAXLEN - 1}


if __name__ == "__main__":
    engine.main(Reader)
