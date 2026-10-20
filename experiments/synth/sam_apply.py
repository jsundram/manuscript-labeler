# /// script
# requires-python = ">=3.11"
# dependencies = ["torch==2.14.1", "torchvision", "transformers==5.20.1", "pillow", "numpy", "opencv-python-headless==4.10.0.84"]
# ///
"""Segment Anything (fine-tuned decoder, or untrained) over whole mapped staves: a point for every head and stem the map
has, a box for every symbol the segmenter sorted (words, the staff's opening and unsorted pieces aside); each symbol
predicted in the two-bar window where it sits most centrally. Scored by the share of ink no mask claims, beside the
classical pass's unsorted share; drawn one colour per kind.

    uv run experiments/synth/sam_apply.py KEY [...] --maps DIR [--decoder decoder.pt] [--sheet OUT.png]
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import torch

import align
import sam_train
import segment
from sam_data import windows

# one colour per kind, in families (BGR): the parts of a note in blues, rests green, accidentals orange, marks above
# the staff in reds, bar lines brown; magenta is kept for ink nothing claims (no greys or golds: they vanish into paper)
COLORS = {"head": (200, 60, 0), "stem": (235, 170, 40), "flag": (210, 210, 0), "beam": (140, 140, 0), "dot": (220, 40, 90),
          "rest": (60, 170, 0), "accidental": (0, 100, 240), "slur": (30, 30, 200), "tuplet": (90, 90, 235),
          "trill": (90, 90, 235), "barline": (20, 70, 140)}
UNCLAIMED = (255, 0, 255)


def find_dot(ink: np.ndarray, x: int, y: int, ss: float):
    """The box of a dotted note's dot: the smallest compact speck of ink a half to two spaces right of the head, at
    its height or a little above (the lifted staff lines leave a dot on a line in pieces; any piece will do)."""
    h, w = ink.shape
    x0, x1 = min(w, int(x + 0.5 * ss)), min(w, int(x + 2.2 * ss))
    y0, y1 = max(0, int(y - 0.8 * ss)), min(h, int(y + 0.5 * ss))
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    n, _, st, cen = cv2.connectedComponentsWithStats(ink[y0:y1, x0:x1].astype(np.uint8), 8)
    best = None
    for i in range(1, n):
        bx, by, bw, bh, area = st[i]
        if not (0.03 * ss * ss <= area <= 0.5 * ss * ss and bw <= 0.7 * ss and bh <= 0.7 * ss):
            continue
        d = abs(cen[i][0] + x0 - (x + 1.1 * ss)) + abs(cen[i][1] + y0 - y)
        if best is None or d < best[0]:
            best = (d, [x0 + bx - 2, y0 + by - 2, x0 + bx + bw + 2, y0 + by + bh + 2])
    return best[1] if best else None


def prompts(key, m, g, ink):
    """(kind, x0, y0, x1, y1, is_point) for the staff's symbols: the map's heads and stems (a grace head by a box,
    as the fine-tuned decoder never saw one by a point), each dotted note's dot, and the segmenter's other symbols."""
    ss = m["ss"]
    out = []
    for b in m["bars"]:
        for n in b["symbols"]:
            if n.get("rest") or n.get("outside"):
                continue
            if n.get("grace"):
                r = 0.45 * ss
                out.append(("head", int(n["x"] - r), int(n["y"] - 0.8 * r), int(n["x"] + r), int(n["y"] + 0.8 * r), False))
            else:
                out.append(("head", n["x"], n["y"], n["x"], n["y"], True))
            if n.get("dots"):
                d = find_dot(ink, n["x"], n["y"], ss)
                if d:
                    out.append(("dot", *d, False))
            st = n.get("stem")
            if st:
                mx, my = (st["x0"] + st["x1"]) // 2, (n["y"] + st["end"]) // 2
                out.append(("stem", mx, my, mx, my, True))
    seg = segment.segment(key, m, g)
    for s in seg["symbols"]:
        k = s["kind"]
        if k in ("margin", "other", "dot-mark", "start"):
            continue
        out.append((k.split("-")[0], *s["box"], False))
    return out, seg


def grow(labels: np.ndarray, ink: np.ndarray, steps: int) -> np.ndarray:
    """Spread each claim (labels >= 0) over the unclaimed ink it touches, a pixel ring at a time, for up to `steps`
    rings: there is almost no stray ink, so ink touching a symbol is that symbol's."""
    lab = labels.astype(np.int32) + 1  # 0 = unclaimed
    k = np.ones((3, 3), np.uint8)
    for _ in range(steps):
        free = ink & (lab == 0)
        if not free.any():
            break
        reach = cv2.dilate(lab.astype(np.float32), k).astype(np.int32)  # a neighbour's claim (the highest, on ties)
        take = free & (reach > 0)
        if not take.any():
            break
        lab[take] = reach[take]
    return lab - 1


def line_residue(ink: np.ndarray, ss: float, th: int, lines: list) -> np.ndarray:
    """What's left of the staff and ledger lines after lifting: ink near a line's row (or a ledger line's) in
    horizontal runs no thicker than a line (heads, beams and the rest are thicker), wherever the lines bow away
    from their rows. Only near the rows, so a thin slur above the staff is kept."""
    u8 = ink.astype(np.uint8)
    long_ = cv2.morphologyEx(u8, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(3, int(0.35 * ss)), 1))) > 0
    tall = max(2 * th + 1, int(0.33 * ss) | 1)  # the measured thickness undercounts grey, bowed lines; beams are thicker
    thick = cv2.morphologyEx(u8, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, tall))) > 0
    near = np.zeros_like(ink)
    sp = (lines[-1] - lines[0]) / 4
    for r in [lines[0] - k * sp for k in (2, 1)] + list(lines) + [lines[-1] + k * sp for k in (1, 2)]:
        near[max(0, int(r - 0.3 * ss)):max(0, int(r + 0.3 * ss) + 1)] = True
    return long_ & ~thick & near


def kind_of(name: str) -> str:
    base = name.split("-")[0]
    return base if base in COLORS else "dot"


def paint(g: np.ndarray, kind: np.ndarray, mask: np.ndarray, unclaimed: np.ndarray, kinds: list) -> np.ndarray:
    """The staff with each claimed pixel in its kind's colour, a darker edge where one mask meets another, and
    unclaimed ink in magenta."""
    vis = cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)
    for i, k in enumerate(kinds):
        sel = kind == i
        vis[sel] = (0.25 * vis[sel] + 0.75 * np.array(COLORS[k])).astype(np.uint8)
    edge = np.zeros_like(unclaimed)
    edge[:, 1:] |= (mask[:, 1:] != mask[:, :-1]) & (mask[:, 1:] >= 0) & (mask[:, :-1] >= 0)
    edge[1:, :] |= (mask[1:, :] != mask[:-1, :]) & (mask[1:, :] >= 0) & (mask[:-1, :] >= 0)
    vis[edge] = (0.45 * vis[edge]).astype(np.uint8)
    vis[unclaimed] = UNCLAIMED
    return vis


def legend(w: int, kinds: list) -> np.ndarray:
    out = np.full((26, w, 3), 255, np.uint8)
    x = 6
    for k, col in [(k, COLORS[k]) for k in kinds] + [("unclaimed", UNCLAIMED)]:
        cv2.rectangle(out, (x, 7), (x + 14, 19), col, -1)
        cv2.putText(out, k, (x + 18, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (40, 40, 40), 1, cv2.LINE_AA)
        x += 26 + 9 * len(k)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="+")
    ap.add_argument("--maps", type=Path, required=True)
    ap.add_argument("--data", type=Path, default=align.ZEUS / "dataL2")
    ap.add_argument("--decoder", type=Path)
    ap.add_argument("--sheet", type=Path)
    ap.add_argument("--mask-colours", action="store_true", help="draw the original, then Segment Anything's masks and "
                    "the classical pass's symbols in each kind's colour, edged where masks meet, unclaimed ink magenta")
    ap.add_argument("--grow", type=float, default=0, help="spread both passes' claims over touching ink, up to this "
                    "many staff spaces (0: off)")
    a = ap.parse_args()
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    from transformers import Sam2Model
    model = Sam2Model.from_pretrained("facebook/sam2.1-hiera-small").to(dev).eval()
    if a.decoder:
        model.load_state_dict(torch.load(a.decoder, map_location="cpu"), strict=False)
    rows, totals = [], [0, 0, 0]
    for key in a.keys:
        stem_key = key.replace("/", "_")
        m = json.loads((a.maps / f"{stem_key}.json").read_text())
        g = cv2.imread(str(a.data / f"{key}.jpg"), cv2.IMREAD_GRAYSCALE)
        h, w = g.shape
        ss = m["ss"]
        inkf, _, th = align.ink_map(g, ss)
        ink = inkf > 0.4
        resid = line_residue(ink, ss, th, m["lines"])
        ps, seg = prompts(key, m, g, ink & ~resid)
        wins = windows(m, w, ss)
        claimed = np.zeros((h, w), np.int16) - 1  # the kind index claiming each pixel
        each = np.zeros((h, w), np.int32) - 1      # the mask claiming each pixel
        nmask, owners = 0, []
        kinds = sorted(COLORS)
        for wi, (x0, x1) in enumerate(wins):
            mine = []
            for p in ps:
                cx = (p[1] + p[3]) / 2
                centres = [abs(cx - (a0 + a1) / 2) if a0 <= p[1] and p[3] < a1 else 1e9 for a0, a1 in wins]
                if int(np.argmin(centres)) == wi and centres[wi] < 1e9:
                    mine.append(p)
            if not mine:
                continue
            img = g[:, x0:x1]
            s = max(img.shape)
            top, left = (s - h) // 2, (s - img.shape[1]) // 2
            sq = np.full((s, s), 255, np.uint8)
            sq[top:top + h, left:left + img.shape[1]] = img
            with torch.no_grad():
                emb = model.get_image_embeddings(sam_train.pixels(sq, dev))
                for is_point in (True, False):
                    sel = [p for p in mine if p[5] == is_point]
                    if not sel:
                        continue
                    pr = torch.tensor([[(p[1] - x0 + left) * 1024 / s, (p[2] + top) * 1024 / s,
                                        (p[3] - x0 + left) * 1024 / s, (p[4] + top) * 1024 / s] for p in sel], dtype=torch.float32, device=dev)
                    if is_point:
                        out = model(image_embeddings=emb, input_points=pr[None, :, None, :2],
                                    input_labels=torch.ones(1, len(sel), 1, dtype=torch.long, device=dev), multimask_output=False)
                    else:
                        out = model(image_embeddings=emb, input_boxes=pr[None], multimask_output=False)
                    lo = out.pred_masks[0, :, 0].float()
                    full = torch.nn.functional.interpolate(lo[None], size=(s, s), mode="bilinear", align_corners=False)[0] > 0
                    full = full[:, top:top + h, left:left + img.shape[1]].cpu().numpy()
                    for p, mk in zip(sel, full):
                        k = kind_of(p[0])
                        region = claimed[:, x0:x1]
                        free = mk & ink[:, x0:x1] & ~resid[:, x0:x1] & (region < 0)
                        region[free] = kinds.index(k)
                        each[:, x0:x1][free] = nmask
                        owners.append(p)
                        nmask += 1
        lab = seg["lab"]
        margin = np.isin(lab, [c for s_ in seg["symbols"] if s_["kind"] in ("margin", "start") for c in s_["comps"]])
        # one footing for both: ink in pieces bigger than a speck (lifted staff lines leave specks)
        n, cl, st_, _ = cv2.connectedComponentsWithStats(ink.astype(np.uint8), 8)
        big = np.isin(cl, [i for i in range(1, n) if st_[i][4] >= 0.2 * ss * ss])
        on_lines = np.zeros_like(ink)
        for r in m["lines"]:
            on_lines[max(0, r - 2):r + 3] = True  # what's left of the staff lines after lifting: neither's to sort
        counted = ink & big & ~margin & ~on_lines & ~resid
        # the classical pass by kind: its symbols, and the heads and stems it lifted (heads where the map's ellipses are)
        cls_kind = np.zeros((h, w), np.int32) - 1
        cls_mask = np.zeros((h, w), np.int32) - 1
        taken = seg["taken"] > 0
        heads = np.zeros((h, w), np.uint8)
        for b in m["bars"]:
            for n_ in b["symbols"]:
                if not n_.get("rest") and not n_.get("outside"):
                    cv2.ellipse(heads, (n_["x"], n_["y"]), (int(0.72 * ss), int(0.56 * ss)), -25, 0, 360, 1, -1)
        cls_kind[taken & ink & (heads > 0)] = kinds.index("head")
        cls_kind[taken & ink & (heads == 0)] = kinds.index("stem")
        for i, s_ in enumerate(seg["symbols"]):
            if s_["kind"] in ("other", "margin", "start", "dot-mark"):
                continue
            sel = np.isin(lab, s_["comps"]) & (cls_kind < 0)
            cls_kind[sel] = kinds.index(kind_of(s_["kind"]))
            cls_mask[sel] = i
        cls_kind[resid] = -1
        if a.grow:  # not along the staff lines: what's left of them touches every symbol
            steps, room = max(1, round(a.grow * ss)), ink & ~on_lines & ~resid
            claimed = grow(claimed, room, steps)
            each = grow(each, room, steps)
            cls_mask = grow(np.where(cls_mask >= 0, cls_mask, np.where(cls_kind >= 0, len(seg["symbols"]), -1)), room, steps)
            cls_kind = grow(cls_kind, room, steps)
        sorted_cls = cls_kind >= 0
        for i, s_ in enumerate(seg["symbols"]):  # how many masks share each rest, and whose
            if s_["kind"].startswith("rest") and a.sheet:
                ids = np.unique(each[np.isin(lab, s_["comps"]) & ink])
                ids = [int(j) for j in ids if j >= 0]
                if len(ids) > 1:
                    print(f"  {key} {s_['kind']} at x={s_['box'][0]}: {len(ids)} masks, from prompts",
                          [(owners[j][0], owners[j][1]) for j in ids], flush=True)
        un_sam = int((counted & (claimed < 0)).sum())
        un_cls = int((counted & ~sorted_cls).sum())
        ink = counted
        totals[0] += int(ink.sum())
        totals[1] += un_sam
        totals[2] += un_cls
        print(f"{key}: unclaimed ink, Segment Anything {un_sam / ink.sum():.1%}; classical {un_cls / ink.sum():.1%}", flush=True)
        if a.sheet and a.mask_colours:
            vis = paint(g, claimed, each, ink & (claimed < 0), kinds)
            cls = paint(g, cls_kind, cls_mask, ink & ~sorted_cls, kinds)
            gap = np.full((6, w, 3), 255, np.uint8)
            if not rows:
                rows.append(legend(w, kinds))
            rows += [cv2.cvtColor(g, cv2.COLOR_GRAY2BGR), gap, vis, gap, cls, np.full((16, w, 3), 200, np.uint8)]
        elif a.sheet:
            vis = cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)
            for i, k in enumerate(kinds):
                sel = claimed == i
                vis[sel] = (0.4 * vis[sel] + 0.6 * np.array(COLORS[k])).astype(np.uint8)
            red = ink & (claimed < 0)
            vis[red] = (0.4 * vis[red] + 0.6 * np.array([0, 0, 230])).astype(np.uint8)
            rows.append(vis)
    print(f"all: unclaimed ink, Segment Anything {totals[1] / max(1, totals[0]):.1%}; classical {totals[2] / max(1, totals[0]):.1%}")
    if rows:
        width = max(r.shape[1] for r in rows)
        cv2.imwrite(str(a.sheet), np.vstack([np.hstack([r, np.full((r.shape[0], width - r.shape[1], 3), 255, np.uint8)]) for r in rows]))


if __name__ == "__main__":
    main()
