# /// script
# requires-python = "==3.10.*"
# dependencies = [
#   "zeus @ git+https://github.com/OmniOMR/zeus.git@main",
#   "tensorflow-macos==2.12.0; sys_platform == 'darwin' and platform_machine == 'arm64'",
#   "numpy", "pillow",
# ]
# [tool.uv]
# # Zeus pins tensorflow 2.12, which has no wheel for Apple silicon; Apple's
# # tensorflow-macos 2.12 is the same version
# override-dependencies = ["tensorflow; sys_platform != 'darwin' or platform_machine != 'arm64'"]
# ///
"""Zeus (OmniOMR) zero-shot on our staves: what it reads, the clefs it
reads, and whether its bar count matches the editor's bar lines.

    uv run experiments/barlines/zeus_eval.py <corpus> <model-dir> [--hint]

<corpus> is built with corpus.py --paper (staves cut across the paper, their
ends recorded); every viola and cello test line is read, and the violin
lines of a few pages. <model-dir> is an unpacked Zeus snapshot, e.g.
ayce-2026-08-03.model (solo staff, CC BY-NC-SA; download links in Zeus's
README). Each staff is cropped from its left end to its right end, a
staff space beyond each, 2.5 above and below, its paper brightened to
white (grey, not thresholded: Zeus read our clefs and bars better so).

Zeus reads a staff into LMX tokens (no positions). Reported per part: the
clefs it read, and on how many lines its count of measures equals the
editor's bar lines on that staff (which doesn't depend on the clef). Its
own clef is replaced afterwards by the part's usual one (viola alto,
cello bass; not yet the editor's clef marks, so a tenor passage comes out
wrong), keeping the staff positions it read and moving the pitches to
match; --hint instead steers the decoder (where
Zeus writes a clef, the part's usual one is forced), which also changes
the notes it reads after it: on our lines, for the worse.
"""

import argparse
import io
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

STEPS = "CDEFGAB"
MIDDLE = {"G2": ("B", 4), "F4": ("D", 3), "C3": ("C", 4), "C4": ("A", 3)}  # pitch on the middle line
USUAL = {"vn1": "G2", "vn2": "G2", "va": "C3", "vc": "F4"}


def reclef(lmx: str, to: str) -> str:
    """The part's clef in place of Zeus's, each pitch kept on its staff position."""
    num = lambda s, o: o * 7 + STEPS.index(s)
    clef, out = None, []
    for t in lmx.split():
        if t.startswith("clef:"):
            clef = t[5:]
            out.append("clef:" + to)
            continue
        m = re.fullmatch(r"([A-G])(\d)", t)
        if m and clef in MIDDLE and clef != to:
            n = num(m[1], int(m[2])) - num(*MIDDLE[clef]) + num(*MIDDLE[to])
            t = f"{STEPS[n % 7]}{n // 7}"
        out.append(t)
    return " ".join(out)


def crop(corpus: Path, l: dict) -> bytes:
    g = np.asarray(Image.open(corpus / l["file"]).convert("L")).astype(np.float32)
    sp = l["space"]
    x0, x1 = int(max(0, l["staff_left"] - sp)), int(min(g.shape[1], l["staff_right"] + sp))
    y0, y1 = int(max(0, l["staff_top"] - 2.5 * sp)), int(min(g.shape[0], l["staff_bottom"] + 2.5 * sp))
    c = g[y0:y1, x0:x1]
    b = io.BytesIO()
    Image.fromarray(np.clip(c / np.percentile(c, 90) * 255, 0, 255).astype(np.uint8)).save(b, "PNG")
    return b.getvalue()


def hinted(tm):
    """Zeus's greedy decoder, with the clef it writes chosen by a bias
    (FIRST for a staff's first clef, LATER after it) set per batch."""
    import tensorflow as tf
    from zeus.model.keras_model import KerasModel

    is_clef = tf.constant([t.startswith("clef:") for t in tm.tokens])
    first = tf.Variable(tf.zeros([len(tm)]), trainable=False)
    later = tf.Variable(tf.zeros([len(tm)]), trainable=False)

    @tf.function
    def decoder_inference(self, encoded, max_length):
        self._target_rnn.cell.setup_memory(encoded)
        batch_size = tf.shape(encoded)[0]
        index = tf.zeros([], tf.int32)
        inputs = tf.fill([batch_size], self.BOS)
        states = self._target_rnn.cell.get_initial_state(batch_size=batch_size, dtype=tf.float32)
        results = tf.TensorArray(tf.int32, size=max_length)
        result_lengths = tf.fill([batch_size], max_length)
        seen = tf.zeros([batch_size], tf.bool)
        while tf.math.logical_and(index < max_length, tf.math.reduce_any(result_lengths == max_length)):
            hidden = self._target_embedding(inputs)
            hidden, states = self._target_rnn.cell(hidden, states)
            hidden = self._target_output_layer(hidden)
            predictions = tf.argmax(hidden, axis=-1, output_type=tf.int32)
            # the change: where Zeus writes a clef, the bias picks which one
            bias = tf.where(seen[:, None], later[None], first[None])
            clef = tf.argmax(tf.where(is_clef[None], hidden + bias, -1e30), axis=-1, output_type=tf.int32)
            wants = tf.gather(is_clef, predictions)
            predictions = tf.where(wants, clef, predictions)
            seen = seen | wants
            results = results.write(index, predictions)
            result_lengths = tf.where((predictions == self.EOS) & (result_lengths > index), index, result_lengths)
            inputs = predictions
            index += 1
        return tf.RaggedTensor.from_tensor(tf.transpose(results.stack()), lengths=result_lengths)

    KerasModel.decoder_inference = decoder_inference

    def set_part(part):
        b = np.full(len(tm), -1e9, np.float32) * np.array([t.startswith("clef:") for t in tm.tokens])
        b[tm.token_to_index("clef:" + USUAL[part])] = 0.0
        first.assign(b)
        later.assign(b)
    return set_part


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus", type=Path)
    ap.add_argument("model", type=Path)
    ap.add_argument("--hint", action="store_true", help="force the part's clef while decoding")
    args = ap.parse_args()
    from zeus import InferenceOptions, Zeus
    from zeus.model.token_map import TokenMap

    set_part = hinted(TokenMap.load_from_model_folder(args.model)) if args.hint else None
    model = Zeus.load(args.model)  # after the patch: loading traces the decoder
    c = json.loads((args.corpus / "corpus.json").read_text())
    test = [l for l in c["lines"] if l["split"] == "test" and "staff_left" in l and l["part"] in USUAL]
    violins = {(l["pdf"], l["page"]) for l in test if l["part"] in ("vn1", "vn2")}
    keep = set(sorted(violins)[::max(1, len(violins) // 4)])
    lines = [l for l in test if l["part"] in ("va", "vc") or (l["pdf"], l["page"]) in keep]
    rows = []
    for part in sorted({l["part"] for l in lines}):
        group = [l for l in lines if l["part"] == part]
        if set_part:
            set_part(part)
        for l, lmx in zip(group, model.predict([crop(args.corpus, l) for l in group], InferenceOptions(batch_size=16))):
            bars = sum(l["staff_left"] < b["x"] <= l["staff_right"] + l["space"] for b in l["bars"])
            rows.append({"id": l["id"], "part": part, "bars": bars, "lmx": lmx,
                         "in_part_clef": reclef(lmx, USUAL[part]),
                         "clefs": [t[5:] for t in lmx.split() if t.startswith("clef:")]})
    print(f"{len(rows)} lines{' (clef forced while decoding)' if args.hint else ''}")
    for part in sorted({r["part"] for r in rows}):
        g = [r for r in rows if r["part"] == part]
        clefs = Counter(" ".join(r["clefs"]) or "none" for r in g)
        same = sum(r["lmx"].split().count("measure") == r["bars"] for r in g)
        print(f"  {part} ({len(g)} lines): clefs read {dict(clefs.most_common())}; bar count matches {same}/{len(g)}")
    out = args.corpus / "zeus" / f"zeus{'-hint' if args.hint else ''}.json"  # not results/: those are bar-line methods
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rows, indent=1))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
