# /// script
# requires-python = "==3.11.*"
# dependencies = ["oemer==0.1.5", "numpy"]
# ///
"""oemer's staff finding (github.com/BreezeWhite/oemer, MIT: an end-to-end
OMR system whose U-Nets were trained partly on handwritten music, CVC-
MUSCIMA), zero-shot on the staff-segmentation test pages, scored as
staves_seg.py scores detect.py and the segmentation model.

    uv run experiments/barlines/oemer_eval.py <seg-dir> <edition>

For each test page: oemer's staff and symbol prediction (generate_pred),
then its staff extraction; each staff's top, bottom, left and right,
matched to the editor's staves by height. oemer has no music start or crop.
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def main():
    seg, edition = Path(sys.argv[1]), Path(sys.argv[2])
    import os

    import cv2
    # oemer still uses the aliases numpy 1.24 removed (np.int ...); its old
    # dependency set can't be installed on Python 3.11, so restore them
    for name, t in (("int", int), ("float", float), ("bool", bool)):
        if not hasattr(np, name):
            setattr(np, name, t)

    from oemer import layers
    from oemer.ete import CHECKPOINTS_URL, MODULE_PATH, clear_data, download_file, generate_pred
    from oemer.staffline_extraction import extract as staff_extract

    # its weights aren't in the package: fetched on first use, as oemer's own CLI does
    if not os.path.exists(os.path.join(MODULE_PATH, "checkpoints/unet_big/model.onnx")):
        for title, url in CHECKPOINTS_URL.items():
            sub = "unet_big" if title.startswith("1st") else "seg_net"
            download_file(title, url, os.path.join(MODULE_PATH, "checkpoints", sub, title.split("_")[1]))

    sys.path.insert(0, str(ROOT))
    import labels

    meta = [m for m in json.loads((seg / "pages.json").read_text()) if m["split"] == "test"]
    counts, rows, secs = [0, 0, 0], [], []
    for m in meta:
        doc = json.loads(labels.labels_path(edition / m["pdf"]).read_text())
        truth = labels.counted_systems(doc["pages"][str(m["page"])])
        path = seg / "images" / "test" / f"{m['name']}.jpg"
        t0 = time.perf_counter()
        clear_data()
        staff, symbols, stems_rests, notehead, clefs_keys = generate_pred(str(path))
        image = cv2.resize(cv2.imread(str(path)), (staff.shape[1], staff.shape[0]))
        for name, layer in (("stems_rests_pred", stems_rests), ("clefs_keys_pred", clefs_keys), ("notehead_pred", notehead),
                            ("symbols_pred", symbols), ("staff_pred", staff), ("original_image", image)):
            layers.register_layer(name, layer)
        try:
            staffs, _ = staff_extract()
            found = [{"left": s.x_left / staff.shape[1], "right": s.x_right / staff.shape[1],
                      "top": s.y_upper / staff.shape[0], "bottom": s.y_lower / staff.shape[0]} for s in np.ravel(staffs)]
        except Exception as e:  # oemer gives up on some pages
            print(f"{m['name']}: oemer failed ({type(e).__name__}: {e})")
            found = []
        secs.append(time.perf_counter() - t0)
        used = set()
        for s in truth:
            sp = (s["bottom"] - s["top"]) / 4
            mid = (s["top"] + s["bottom"]) / 2
            d, i = min(((abs((f["top"] + f["bottom"]) / 2 - mid), i) for i, f in enumerate(found) if i not in used), default=(1, -1))
            if i < 0 or d > 2 * sp:
                counts[1] += 1
                continue
            used.add(i)
            counts[0] += 1
            f = found[i]
            spw = sp * m["h"] / m["w"]
            rows.append({"left": abs(f["left"] - s["left"]) / spw, "right": abs(f["right"] - s["right"]) / spw,
                         "top": abs(f["top"] - s["top"]) / sp, "bottom": abs(f["bottom"] - s["bottom"]) / sp})
        counts[2] += len(found) - len(used)
        print(f"{m['name']}: {len(found)} staves found, {len(truth)} labelled ({secs[-1]:.0f} s)", flush=True)
    print(f"\noemer: staves found {counts[0]}, missed {counts[1]}, false {counts[2]}; {np.mean(secs):.0f} s a page")
    for k in ("left", "right", "top", "bottom"):
        v = np.array([r[k] for r in rows])
        if len(v):
            print(f"  {k:6s} median {np.median(v):5.2f} spaces, within 1 space {np.mean(v <= 1):5.0%}, over 3 spaces {np.mean(v > 3):5.0%}")


if __name__ == "__main__":
    main()
