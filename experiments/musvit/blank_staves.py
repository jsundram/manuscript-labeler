# /// script
# requires-python = ">=3.11"
# dependencies = ["torch", "transformers", "peft", "pillow", "numpy", "scikit-learn"]
# ///
"""False staves: can MuSViT's encoder tell a staff of music from one
detection proposes that has none (an empty ruled staff, a line of text)?
Detection proposes about one such staff on every third reviewed page
(tools/staff_edits.py: 45 on Op. 48's 111), and the editor deletes each.

    uv run experiments/musvit/blank_staves.py collect     # detection, crops, D5's reading and features
    uv run experiments/musvit/blank_staves.py score

`collect` detects every reviewed Op. 48 music page again (as
tools/staff_edits.py does, rules alone) and cuts each proposed staff as
the readers see it (compare.staff_crop). A staff the editor kept is music;
one they deleted (no kept staff within half a space) is not. Each is read
by musvit-D5 and passed through its frozen encoder; a staff's features are
its last layer's patch vectors, averaged and maxed over the staff.

`score`, leaving out one source at a time: a logistic regression on the
features, against two rules from the reading alone (no note read; fewer
than N tokens). Reported as the false staves caught when no staff of
music is lost, and at one lost in a hundred.

Written to $MUSVIT_BLANK (default ~/Data/manuscript-labeler/musvit/blank):
staves.json and features.npy, re-made by `collect`.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

import numpy as np

MUS = Path(__file__).resolve().parent
ROOT = MUS.parents[1]
sys.path[:0] = [str(MUS), str(MUS.parent / "zeus"), str(ROOT), str(ROOT / "tools")]
OUT = Path(os.environ.get("MUSVIT_BLANK", Path.home() / "Data/manuscript-labeler/musvit/blank"))
NOTE = re.compile(r"[A-G][#b-]*\d")


def collect(a):
    import torch
    from PIL import Image

    import compare
    import detect
    import proto
    import questions
    import staff_edits

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    files = sorted((ROOT / "data").glob("**/*.labels.json"))
    staves, crops = [], {}
    for f in files:
        doc = staff_edits.labels.migrate(json.loads(f.read_text()))
        pdf = staff_edits.pdf_for(f)
        pages = [(int(n), p) for n, p in doc["pages"].items() if p.get("status") == "reviewed" and p.get("kind") == "music"]
        if not pages or not pdf.exists():
            continue
        for n, p in sorted(pages, key=lambda x: x[0]):
            path = staff_edits.RENDERS / f"{pdf.stem}-p{n}.jpg"
            img = Image.open(path) if path.exists() else staff_edits.render(pdf, n, staff_edits.RENDERS)
            img.load()
            corners = (p.get("corners") or {}).get("points") or detect.find_page_corners(img)
            found = detect.detect_page(img, staff_edits.room_before(doc, n, img.size[1] / img.size[0]), corners=corners)
            pairs, _, _ = staff_edits.match(p["systems"], found)  # a cue staff too: music, though not counted
            kept = {id(d) for _, d in pairs}
            g = compare.page_image(pdf, n)
            for i, d in enumerate(found):
                key = f"{pdf.stem}/p{n}-{i}"
                crops[key] = compare.staff_crop(g, d)
                staves.append({"key": key, "source": pdf.stem, "page": n, "music": id(d) in kept,
                               "system": {k: d[k] for k in ("top", "bottom", "left", "right", "bend")}})
            print(f"{pdf.stem} p{n}: {len(found)} proposed, {len(found) - len(kept)} deleted by the editor", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"reading {len(crops)} staves with D5 ...", flush=True)
    read = proto.read_crops(questions.READER, "best.pt", crops, device)
    for s in staves:
        s["reading"] = read.get(s["key"], "")
    enc, dtype = questions.encoder(device, "d5")
    feats = []
    for s in staves:
        x = questions.patches(enc, dtype, device, crops[s["key"]])[12].astype(np.float32)
        v = x.reshape(-1, x.shape[-1])
        feats.append(np.concatenate([v.mean(0), v.max(0)]))
    np.save(OUT / "features.npy", np.stack(feats).astype(np.float32))
    (OUT / "staves.json").write_text(json.dumps(staves, indent=1))
    print(f"{len(staves)} staves, {sum(not s['music'] for s in staves)} not music -> {OUT}")


def caught(scores: np.ndarray, music: np.ndarray, lose: float) -> tuple[int, int]:
    """Higher score = more likely not music. At the threshold that loses at most `lose` of the staves of
    music: (false staves caught, staves of music lost)."""
    m = np.sort(scores[music])[::-1]
    k = int(np.floor(lose * len(m)))
    thr = m[k] if k < len(m) else -np.inf  # flag only what scores above the (k+1)-th highest staff of music
    flagged = scores > thr
    return int((flagged & ~music).sum()), int((flagged & music).sum())


def score(a):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    staves = json.loads((OUT / "staves.json").read_text())
    X = np.load(OUT / "features.npy")
    music = np.array([s["music"] for s in staves])
    src = np.array([s["source"] for s in staves])
    head = np.zeros(len(staves))
    for s in sorted(set(src)):
        test = src == s
        sc = StandardScaler().fit(X[~test])
        clf = LogisticRegression(C=0.05, max_iter=2000, class_weight="balanced").fit(sc.transform(X[~test]), ~music[~test])
        head[test] = clf.predict_proba(sc.transform(X[test]))[:, 1]
    notes = np.array([len(NOTE.findall(s["reading"])) for s in staves])
    tokens = np.array([len(s["reading"].split()) for s in staves])
    rules = {"head on D5's encoder (source left out)": head,
             "the reading's notes (fewer = blank)": -notes.astype(float),
             "the reading's tokens (fewer = blank)": -tokens.astype(float)}
    print(f"{len(staves)} proposed staves, {int((~music).sum())} not music (deleted by the editor)")
    for name, v in rules.items():
        c0, l0 = caught(v, music, 0.0)
        c1, l1 = caught(v, music, 0.01)
        print(f"  {name}: losing no staff of music, {c0} caught; losing 1%, {c1} caught ({l1} lost)")
    print("  no note read:", int(((notes == 0) & ~music).sum()), "of the false staves,",
          int(((notes == 0) & music).sum()), "staves of music")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=("collect", "score"))
    a = ap.parse_args()
    {"collect": collect, "score": score}[a.step](a)


if __name__ == "__main__":
    main()
