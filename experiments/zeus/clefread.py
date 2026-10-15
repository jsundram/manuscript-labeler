# /// script
# requires-python = "==3.10.*"
# dependencies = [
#   "zeus @ git+https://github.com/OmniOMR/zeus.git@c8569eb1c8b5bb24511de6a5e53ef2450de6206c",
#   "tensorflow-macos==2.12.0; sys_platform == 'darwin' and platform_machine == 'arm64'",
#   "numpy", "pillow",
# ]
# [tool.uv]
# # Zeus pins tensorflow 2.12, which has no wheel for Apple silicon;
# # tensorflow-macos 2.12 is the same.
# override-dependencies = ["tensorflow; sys_platform != 'darwin' or platform_machine != 'arm64'"]
# ///
"""Does Zeus read better when it may only write the clefs the labels give
the staff? Each staff is read twice, one at a time (greedy, as Zeus's own
predict): freely, and with every other clef token ruled out.

    uv run experiments/zeus/clefread.py <edition-repo> --source D-B_KHM-603 --movements I --model M
    uv run experiments/zeus/compare.py <edition-repo> --source D-B_KHM-603 --movements I --model x/<M>-free.model
    uv run experiments/zeus/compare.py <edition-repo> --source D-B_KHM-603 --movements I --model x/<M>-clef.model

The readings go to answers/ as models "<M>-free" and "<M>-clef", so
compare.py, run with the same --movements, scores them from its cache
(the --model directory needn't exist). The README has the result: no better.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import compare  # noqa: E402

# the labels' clefs as Zeus writes them
ZCLEF = {"treble": "clef:G2", "alto": "clef:C3", "tenor": "clef:C4", "bass": "clef:F4"}
MAXLEN = 700  # Zeus's InferenceOptions.max_prediction_length


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edition", type=Path)
    ap.add_argument("--source", default="D-B_KHM-603")
    ap.add_argument("--movements", nargs="+", help="only these movements (default: all)")
    ap.add_argument("--model", type=Path, required=True)
    a = ap.parse_args()

    pdf = next(a.edition.glob(f"sources/*/{a.source}.pdf"))
    export = json.loads(pdf.with_name(pdf.stem + ".bars.json").read_text())
    staves: dict[str, list[dict]] = {}
    for b in export["bars"]:
        if b["part"] in ("vn1", "vn2", "va", "vc") and (not a.movements or b["movement"] in a.movements):
            staves.setdefault(b["system"], []).append(b)

    import numpy as np
    import tensorflow as tf
    from zeus import Zeus
    from zeus.model.preprocess_image import preprocess_image

    model = Zeus.load(a.model)
    km, tm = model.model, model.token_map
    clef_ids = [i for i in range(len(tm)) if tm.index_to_token(i).startswith("clef:")]

    # Zeus's decoder_inference for one staff, with `bias` added to its logits.
    # One at a time: its attention doesn't mask a batch's padding.
    @tf.function(reduce_retracing=True)
    def read(img, bias):
        enc = km.encoder(tf.RaggedTensor.from_tensor(img[tf.newaxis], ragged_rank=2), training=False)
        km._target_rnn.cell.setup_memory(enc)
        inputs = tf.fill([1], km.BOS)
        states = km._target_rnn.cell.get_initial_state(batch_size=1, dtype=tf.float32)
        out = tf.TensorArray(tf.int32, size=MAXLEN)
        i, done = tf.constant(0), tf.constant(False)
        while i < MAXLEN and not done:
            h = km._target_embedding(inputs)
            h, states = km._target_rnn.cell(h, states)
            p = tf.argmax(km._target_output_layer(h) + bias[tf.newaxis], axis=-1, output_type=tf.int32)
            out = out.write(i, p[0])
            done = p[0] == km.EOS
            inputs = p
            i += 1
        return out.stack()[:i]

    readings = {"free": {}, "clef": {}}
    page = None
    for sid, boxes in staves.items():
        s = export["systems"][sid]
        if page is None or page[0] != s["page"]:
            page = (s["page"], compare.page_image(pdf, s["page"]))
        crop = compare.staff_crop(page[1], s)
        key = f"{sid}:{hashlib.sha1(crop).hexdigest()[:10]}"  # as compare.py keys its cache
        # As Zeus's predict prepares a staff: grey, its height, width by aspect up to 1500, no padding.
        img = preprocess_image(tf.constant(crop), height=model.architecture_options.height,
                               transformations=[], max_image_width=1500)
        allowed = {tm.token_to_index(ZCLEF[c]) for b in boxes for c in b["clefs"] if c in ZCLEF}
        for mode, got in readings.items():
            bias = np.zeros(len(tm), np.float32)
            if mode == "clef" and allowed:
                bias[[c for c in clef_ids if c not in allowed]] = -1e9
            ids = [int(t) for t in read(img, tf.constant(bias)).numpy()]
            if ids and ids[-1] == km.EOS:
                ids = ids[:-1]
            got[key] = tm.indices_to_lmx(ids)
    print(f"Zeus read {len(staves)} staves, free and limited to the labels' clefs")

    for mode, got in readings.items():
        f = HERE / "answers" / f"{a.source}-{a.model.name.removesuffix('.model')}-{mode}.model.json"
        old = json.loads(f.read_text()) if f.exists() else {}
        f.write_text(json.dumps({**old, **got}, indent=1, sort_keys=True))
        print("wrote", f.relative_to(HERE))


if __name__ == "__main__":
    main()
