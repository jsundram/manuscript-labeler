# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "smashcima==1.1.2", "opencv-contrib-python==4.10.0.84", "numpy",
#   # sam_synth (prompt, windows, sheet_rows) and through it copyist (lmx_to_musicxml)
#   "verovio==6.3.0", "resvg-py==0.5.0", "lxml", "pillow", "linearized-musicxml==1.0.0",
# ]
# [tool.uv]
# # smashcima needs opencv's contrib build (cv2.ximgproc.thinning); the plain builds would shadow it
# override-dependencies = ["opencv-python-headless; sys_platform == 'never'", "opencv-python; sys_platform == 'never'"]
# ///
"""Training windows for Segment Anything from Smashcima (Mayer et al.): each staff written out by hand from
MUSCIMA++'s symbols (one of its 50 writers per staff), each symbol's mask its own sprites' ink, so the masks are exact.

Smashcima lays the music out on a page of its own (wrapping a long line onto more staves); each staff with music is
cropped (staff +-2.5 spaces) at a scale giving a staff space of the hand's size, rendered twice from the same scene:
the page (paper, staff lines, ink) and a map of which symbol owns each pixel. Clefs, time signatures, ledger lines
and staff lines are drawn but not masked. Smashcima draws no slurs, ties, tuplets, trills or grace notes.

Writes sam_data.py's format (OUT/<name>_w<i>.npz: image, kinds, prompts, masks), one window per pair of bars, so
sam_train.py trains on it unchanged.

Smashcima keeps its assets (MUSCIMA++, paper textures) under $MC_HOME (default ~/.cache/smashcima), fetched on
first run; MUSCIMA++'s address in smashcima 1.1.2 is dead (LINDAT moved), so it is pointed at the new one here.

    uv run experiments/synth/sam_smashcima.py LMX_DIR_OR_LIST --out DIR [--n 500] [--seed 0] [--hand berlin]
    uv run experiments/synth/sam_smashcima.py ONE.lmx --sheet OUT.png   # look at one
"""
import argparse
import json
import random
import sys
from pathlib import Path

import cv2
import numpy as np
import smashcima.assets.datasets.MuscimaPP as _mpp

_mpp.DOWNLOAD_URL = ("https://lindat.mff.cuni.cz/repository/server/api/core/bitstreams/"
                     "7906b7b4-0d9b-4b8f-a2f0-2196945beb39/content")
from smashcima.exporting.BitmapRenderer import BitmapRenderer  # noqa: E402
from smashcima.exporting.compositing.DefaultCompositor import SceneVisitor  # noqa: E402
from smashcima.geometry import Rectangle, Transform, mm_to_px  # noqa: E402
from smashcima.orchestration.BaseHandwrittenModel import BaseHandwrittenModel  # noqa: E402
from smashcima.scene import ComposedGlyph, Glyph, Sprite, ViewBox  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import copyist  # noqa: E402
from sam_synth import prompt, sheet_rows, windows  # noqa: E402

RESTS = {"restQuarter": "rest-quarter", "rest8th": "rest-eighth", "rest16th": "rest-16th"}


def kind_of(label: str) -> str | None:
    """Our kind for a Smashcima glyph label (smufl::noteheadBlack, smashcima::beam, ...); None: drawn, not masked."""
    name = label.split("::")[-1]
    if name.startswith("notehead"):
        return "head"
    if name == "stem":
        return "stem"
    if name.startswith("flag"):  # smufl::flag8thUp, or MUSCIMA++'s single strokes smashcima::flag16thDown
        return "flag"
    if name in ("beam", "beamHook"):
        return "beam"
    if name == "augmentationDot":
        return "dot"
    if name.startswith("rest"):
        return RESTS.get(name, "rest")
    if name.startswith("accidental"):
        return "accidental"
    if name.startswith("barline"):
        return "barline"
    if name == "slur":
        return "slur"
    return None


class _Sprites(SceneVisitor):
    """Each sprite in drawing order, with its glyph (not a composed one) and its space's transform to the canvas."""
    def __init__(self, space, to_canvas, out):
        self.space, self.space_to_canvas_transform, self.out = space, to_canvas, out

    def create_sub_visitor(self, sub):
        return _Sprites(sub, sub.transform.then(self.space_to_canvas_transform), self.out)

    def accept_sub_visitor(self, v):
        pass

    def visit_scene_object(self, obj):
        if isinstance(obj, Sprite):
            gs = [g for g in Glyph.many_of(obj, lambda g: g.sprites) if not isinstance(g, ComposedGlyph)]
            if gs:
                self.out.append((gs[0], obj, self.space_to_canvas_transform))


def owners(scene, rect: Rectangle, dpi: float, shape) -> tuple[np.ndarray, list]:
    """Which masked symbol owns each pixel of `rect` (0: none, i: kinds[i-1]), the later drawn on top."""
    root = scene.root_space
    to_canvas = Transform.translate(-rect.top_left_corner.vector).then(Transform.scale(mm_to_px(1, dpi=dpi)))
    recs = []
    _Sprites(root, to_canvas, recs).run()
    H, W = shape
    idm = np.zeros((H, W), np.int32)
    ids, kinds = {}, []
    for g, s, t in recs:
        k = kind_of(g.label)
        if k is None:
            continue
        M = s.get_pixels_to_parent_space_transform().then(t).matrix
        h, w = s.bitmap.shape[:2]
        corners = np.array([[0, 0, 1], [w, 0, 1], [0, h, 1], [w, h, 1]], np.float64) @ np.asarray(M).T
        x0, y0 = np.floor(corners.min(0)).astype(int) - 1
        x1, y1 = np.ceil(corners.max(0)).astype(int) + 1
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
        if x1 <= x0 or y1 <= y0:
            continue
        Mw = np.array(M, np.float64)
        Mw[:, 2] -= (x0, y0)
        a = cv2.warpAffine(s.bitmap[..., 3], Mw, (x1 - x0, y1 - y0), flags=cv2.INTER_LINEAR)
        if id(g) not in ids:
            kinds.append(k)
            ids[id(g)] = len(kinds)
        idm[y0:y1, x0:x1][a > 77] = ids[id(g)]  # visible: alpha over 0.3, as sam_synth's
    return idm, kinds


def render(model, lmx: str, hand: str, seed: int) -> list:
    """[(image, [(kind, mask)], ss)] for each staff Smashcima wrote the line on."""
    rng = random.Random(seed)
    model.rng.seed(seed)
    scene = model(data=copyist.lmx_to_musicxml(lmx), format=".musicxml")
    out = []
    for page in scene.pages:
        for staff in page.staves:
            bb = staff.glyph.get_bbox_in_space(scene.root_space)
            ss_mm = bb.height / 4
            ss = rng.uniform(*copyist.HANDS[hand].ss)
            os_ = 2
            dpi = ss * os_ / ss_mm * 25.4
            rect = Rectangle(bb.left - ss_mm, bb.top - 2.5 * ss_mm, bb.width + 2 * ss_mm, bb.height + 5 * ss_mm)
            layer = scene.compositor.run(ViewBox(space=scene.root_space, rectangle=rect), dpi=dpi)
            bgra = BitmapRenderer().render(layer)
            idm, kinds = owners(scene, rect, dpi, bgra.shape[:2])
            if "barline" not in {k for i, k in enumerate(kinds, 1) if (idm == i).any()}:
                continue  # a staff the line didn't reach (or only a neighbour's ledger notes)
            g = cv2.cvtColor(bgra[..., :3], cv2.COLOR_BGR2GRAY).astype(np.float32)
            H, W = g.shape
            g = cv2.resize(g, (W // os_, H // os_), interpolation=cv2.INTER_AREA)
            idm = cv2.resize(idm.astype(np.float32), (W // os_, H // os_), interpolation=cv2.INTER_NEAREST).astype(np.int32)
            g = cv2.GaussianBlur(g, (0, 0), rng.uniform(0.4, 0.9))
            g += np.random.default_rng(seed).normal(0, 3, g.shape)
            g = np.clip(g / max(np.percentile(g, 90), 1) * 255, 0, 255).astype(np.uint8)
            ok, buf = cv2.imencode(".jpg", g, [cv2.IMWRITE_JPEG_QUALITY, rng.randint(70, 92)])
            img = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
            masks = [(k, idm == i) for i, k in enumerate(kinds, 1)]
            out.append((img, [(k, m) for k, m in masks if m.sum() >= 4], ss))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path, help="an .lmx file, a directory of them, or a text file listing them")
    ap.add_argument("--hand", default="berlin", choices=sorted(copyist.HANDS), help="whose staff-space size to draw at")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--sheet", type=Path)
    ap.add_argument("--n", type=int, default=500, help="lines of music (each may fill more than one staff)")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    if a.src.is_dir():
        files = sorted(a.src.rglob("*.lmx"))
    elif a.src.suffix == ".lmx":
        files = [a.src]
    else:
        files = [Path(l) for l in a.src.read_text().split() if l]
    random.Random(a.seed).shuffle(files)
    model = BaseHandwrittenModel()
    rows, done, staves, tally, nwin, fails = [], 0, 0, {}, 0, 0
    if a.out:
        a.out.mkdir(parents=True, exist_ok=True)
    for i, f in enumerate(files):
        if done >= a.n:
            break
        try:
            drawn = render(model, f.read_text(), a.hand, a.seed + i)
        except Exception:  # lines Smashcima can't read or lay out
            fails += 1
            continue
        done += 1
        for si, (img, masks, ss) in enumerate(drawn):
            staves += 1
            if a.sheet:
                rows += sheet_rows(img, masks) + [np.full((12, img.shape[1], 3), 200, np.uint8)]
            if not a.out:
                continue
            h, w = img.shape
            for wi, (x0, x1) in enumerate(windows(masks, w, ss)):
                kinds, prompts, ms = [], [], []
                for k, m in masks:
                    ys, xs = np.nonzero(m)
                    if xs.min() >= x0 and xs.max() < x1:
                        pr = prompt(k, m)
                        kinds.append(k)
                        prompts.append([pr[0] - x0, pr[1], pr[2] - x0, pr[3]])
                        ms.append(m[:, x0:x1])
                if not kinds:
                    continue
                np.savez_compressed(a.out / f"{f.stem}_{a.seed + i}_s{si}_w{wi}.npz", image=img[:, x0:x1],
                                    kinds=np.array(kinds), prompts=np.array(prompts, np.int32),
                                    masks=np.packbits(np.stack(ms), axis=-1), width=x1 - x0)
                nwin += 1
                for k in kinds:
                    tally[k] = tally.get(k, 0) + 1
    print(f"{done} lines on {staves} staves ({fails} skipped), {nwin} windows",
          json.dumps(dict(sorted(tally.items(), key=lambda kv: -kv[1]))))
    if rows:
        width = max(r.shape[1] for r in rows)
        cv2.imwrite(str(a.sheet), np.vstack([np.hstack([r, np.full((r.shape[0], width - r.shape[1], 3), 255, np.uint8)])
                                             for r in rows]))


if __name__ == "__main__":
    main()
