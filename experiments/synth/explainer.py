# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "verovio==6.3.0", "resvg-py==0.5.0", "opencv-python-headless==4.10.0.84", "numpy", "lxml", "pillow",
#   "linearized-musicxml==1.0.0",
# ]
# ///
"""The page that shows how copyist.py draws a staff: its stages on one staff,
what comes from the real staves (measured against the synthetic ones, per
hand), real staves beside drawings of the same music at the same length,
close-ups, one staff in every hand, new music, and the checks.

    uv run experiments/synth/explainer.py OUT.html [--synth DIR] [--osq-list FILE] [--seed 0]

Everything is drawn afresh from the current copyist.py (and its harvested
clefs); the synthetic statistics come from a generated folder (gen.py's,
default dataS3), with each staff's hand from its hands file.
"""
import argparse
import base64
import json
import random
import re
import sys
from collections import defaultdict
from dataclasses import fields
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import copyist  # noqa: E402
import gen  # noqa: E402

ZEUS = Path.home() / ".cache/manuscript-labeler/zeus"
LABELS = Path.home() / "Dropbox/Code/manuscript-labeler/data/boccherini-opus-48/sources"
EVENT = re.compile(r"^([A-G]\d|rest)$")

SOURCES = {  # source: (Gérard number, quartet, library and shelfmark)
    "D-B_KHM-602": ("G226", "Op. 48 No. 1 (G. 226)", "Berlin, Staatsbibliothek, KHM 602"),
    "D-B_KHM-603": ("G227", "Op. 48 No. 2 (G. 227)", "Berlin, Staatsbibliothek, KHM 603"),
    "F-Po_RES-507-14": ("G228", "Op. 48 No. 3 (G. 228)", "Paris, Bibliothèque-musée de l'Opéra, RES 507 (14)"),
    "F-Pn_Vma-ms-1067-1": ("G228", "Op. 48 No. 3 (G. 228)", "Paris, Bibliothèque nationale, Vma ms 1067 (1)"),
    "F-Po_RES-507-17": ("G230", "Op. 48 No. 5 (G. 230)", "Paris, Bibliothèque-musée de l'Opéra, RES 507 (17)"),
    "F-Pn_Vma-ms-1067-3": ("G230", "Op. 48 No. 5 (G. 230)", "Paris, Bibliothèque nationale, Vma ms 1067 (3)"),
}
PART = {"vn1": "first violin", "vn2": "second violin", "va": "viola", "vc": "cello"}
HAND_NAMES = {
    "berlin": ("Berlin", "KHM 602 and 603: one copyist, all four parts, 1794"),
    "parisA": ("Paris A", "RES 507 (14) and (17): first violin and cello"),
    "parisB": ("Paris B", "RES 507 (14) and (17): second violin and viola; RISM calls RES 507 (14) autograph, and Gérard "
                          "says only its first violin and cello are not in Boccherini's hand"),
    "vma": ("Vma", "Vma ms 1067 (1) and (3): one copyist, all four parts, 1810–40"),
    "generic": ("Generic", "wide ranges of every habit, for hands we haven't seen"),
}
# the staves shown, by hand: (source, part); one of each is drawn from the source's staves of that part
GALLERY = {
    "berlin": [("D-B_KHM-602", "vn1"), ("D-B_KHM-602", "va"), ("D-B_KHM-603", "vc")],
    "parisA": [("F-Po_RES-507-14", "vn1"), ("F-Po_RES-507-17", "vc"), ("F-Po_RES-507-17", "vn1")],
    "parisB": [("F-Po_RES-507-14", "va"), ("F-Po_RES-507-17", "vn2"), ("F-Po_RES-507-14", "vn2")],
    "vma": [("F-Pn_Vma-ms-1067-1", "vn1"), ("F-Pn_Vma-ms-1067-3", "va"), ("F-Pn_Vma-ms-1067-1", "vc")],
}
HOW = {  # how each habit's range was set
    "font": ("chosen", "the SMuFL font the glyphs start from (Petaluma, a handwritten face, twice as often)"),
    "ss": ("measured", "staff space in pixels: the ranges bracket each source's measured median"),
    "width": ("measured", "staff length in staff spaces, when the music isn't a real staff's (a real staff's music is "
                          "drawn at exactly that staff's length)"),
    "slant": ("by eye", "how far stems and bar lines lean right (a shear about the staff's middle)"),
    "nh_w": ("by eye", "notehead half-width, in staff spaces"),
    "nh_h": ("by eye", "notehead half-height"),
    "nh_tilt": ("by eye", "notehead tilt, degrees"),
    "stem_w": ("by eye", "stem width, staff spaces"),
    "stem_len": ("by eye", "stem length against the engraved one"),
    "beam_th": ("by eye", "beam thickness, staff spaces (engraved 0.5)"),
    "beam_wobble": ("by eye", "how far a beam's ends wander, staff spaces"),
    "line_w": ("by eye", "staff-line width"),
    "line_wave": ("by eye", "staff-line waviness"),
    "line_ink": ("by eye", "staff lines' darkness against the notes'"),
    "glyph_jit": ("by eye", "how far each glyph strays from its place"),
    "glyph_rot": ("by eye", "how far each glyph turns, degrees"),
    "glyph_scale": ("by eye", "glyph size against the font's"),
    "warp": ("by eye", "smooth warp of every stroke, staff spaces"),
    "ink": ("by eye", "ink grey (0 black, 255 paper)"),
    "blur": ("by eye", "pen softness, pixels"),
    "hide_tuplet": ("by eye", "chance a staff's tuplet numbers are left out, as copyists often do"),
    "bare_start": ("observed", "chance the staff starts with no clef or key: Paris B's continuation lines"),
    "real_clef": ("copied", "chance the opening clef is one of the copyist's own, cut from their staves"),
}


def jpg(img: np.ndarray, q: int = 82) -> str:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()


def png(img: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", img)
    return "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode()


def real_staves(data: Path) -> list[dict]:
    """Every labelled Op. 48 staff in the folder, with its source, movement, part and hand."""
    parts = {}
    for src, (g, _, _) in SOURCES.items():
        pages = json.loads((LABELS / g / f"{src}.labels.json").read_text())["pages"]
        parts[src] = {k: p.get("part") for k, p in pages.items()}
    out, seen = [], set()
    for f in sorted(data.glob("samples.*.txt")):
        m = re.match(r"samples\.(.+)-(I+|IV|V|VI)\.txt", f.name)
        if not m or "noslur" in m.group(1):
            continue
        src, mvt = m.group(1), m.group(2)
        if src not in SOURCES:
            continue
        for key in f.read_text().split():
            if key in seen:
                continue
            seen.add(key)
            staff = key.split("/")[1]
            part = parts[src].get(re.match(r"p(\d+)", staff).group(1))
            if part not in PART:
                continue
            hand = ("berlin" if src.startswith("D-B") else "vma" if "Vma" in src
                    else "parisA" if part in ("vn1", "vc") else "parisB")
            out.append({"key": key, "source": src, "movement": mvt, "part": part, "hand": hand})
    return out


def stats_of(img_shape, lmx: str) -> dict:
    h, w = img_shape
    toks = lmx.split()
    return {"ss": h / 9, "length": w / h * 9 - 2,
            "events": sum(1 for t in toks if EVENT.match(t)) - toks.count("chord"), "bars": toks.count("measure")}


def summary(vals: list[float]) -> dict:
    v = np.array(vals, dtype=float)
    return {"n": len(v), "p5": float(np.percentile(v, 5)), "p25": float(np.percentile(v, 25)),
            "p50": float(np.percentile(v, 50)), "p75": float(np.percentile(v, 75)), "p95": float(np.percentile(v, 95))}


def synth_hands(folder: Path, group: str, seed: int) -> dict[str, str]:
    """gen.py's hand for each drawn staff: from its hands file, or (older folders) from its seed."""
    if (folder / f"hands.{group}.json").exists():
        return json.loads((folder / f"hands.{group}.json").read_text())
    out = {}
    for line in (folder / f"samples.{group}.txt").read_text().split():
        m = re.match(rf"{group}/s(\d+)-(\d+)$", line)
        i, k = int(m.group(1)), int(m.group(2))
        out[line] = random.Random(seed * 1_000_003 + i * 31 + k).choice(gen.HANDS)
    return out


def measure(data: Path, synth: Path, reals: list[dict]) -> dict:
    """Per hand, real against synthetic: staff space, staff length, notes and rests, bars (5th to 95th percentile)."""
    real = defaultdict(lambda: defaultdict(list))
    for r in reals:
        g = cv2.imread(str(data / f"{r['key']}.jpg"), cv2.IMREAD_GRAYSCALE)
        for k, v in stats_of(g.shape, (data / f"{r['key']}.lmx").read_text()).items():
            real[r["hand"]][k].append(v)
    syn = defaultdict(lambda: defaultdict(list))
    for group, seed in (("S-osq", 3), ("S-own", 4)):
        if not (synth / f"samples.{group}.txt").exists():
            continue
        for line, hand in synth_hands(synth, group, seed).items():
            g = cv2.imread(str(synth / f"{line}.jpg"), cv2.IMREAD_GRAYSCALE)
            for k, v in stats_of(g.shape, (synth / f"{line}.lmx").read_text()).items():
                syn[hand][k].append(v)
    out = {}
    for hand in ["berlin", "parisA", "parisB", "vma", "generic"]:
        out[hand] = {k: {"real": summary(real[hand][k]) if real[hand][k] else None,
                         "synth": summary(syn[hand][k]) if syn[hand][k] else None}
                     for k in ("ss", "length", "events", "bars")}
    return out


def caption(r: dict) -> dict:
    g, quartet, ms = SOURCES[r["source"]]
    return {"work": f"Boccherini, String Quartet {quartet}, movement {r['movement']}",
            "manuscript": ms, "part": PART[r["part"]], "staff": r["key"]}


def params_note(p: dict) -> str:
    return f"{p['font']} · {p['ss']:.1f} px a space · slant {p['slant']:.0f}°"


def draw_pair(data: Path, r: dict, seeds) -> dict:
    real = cv2.imread(str(data / f"{r['key']}.jpg"), cv2.IMREAD_GRAYSCALE)
    lmx = (data / f"{r['key']}.lmx").read_text()
    width = real.shape[1] / real.shape[0] * 9 - 2
    drawn = []
    for s in seeds:
        img, p = copyist.draw(lmx, r["hand"], seed=s, width=width, return_params=True)
        drawn.append({"img": jpg(img), "note": params_note(p)})
    return {"real": jpg(real), "drawn": drawn, **caption(r), "hand": r["hand"],
            "tokens": len(lmx.split()), "events": stats_of(real.shape, lmx)["events"]}


def closeup(img: np.ndarray, frac=0.0, spaces=34) -> np.ndarray:
    """A stretch of a staff at its own resolution, `spaces` staff spaces long from `frac` of the way along."""
    h, w = img.shape
    ss = h / 9
    n = int(spaces * ss)
    x = int(min(max(0, frac * w), max(0, w - n)))
    return img[:, x:x + n]


def rebuild_section(d: Path, data: Path) -> dict:
    """The rebuilding checkpoint: a map over a staff, its symbols sorted, the harvested glyphs, rebuilds beside originals."""
    out = {"overlay": jpg(cv2.imread(str(d / "overlay.png")), 88), "segments": jpg(cv2.imread(str(d / "segments.png")), 85),
           "glyphs": png(cv2.imread(str(d / "glyphs.png"), cv2.IMREAD_GRAYSCALE)), "pairs": []}
    reals = {x["key"]: x for x in real_staves(data)}
    for f in sorted(d.glob("*.rebuilt.jpg")):
        key = "/".join(f.name[: -len(".rebuilt.jpg")].rsplit("_", 1))
        r = reals.get(key, {"key": key, "source": key.split("/")[0], "movement": "", "part": "vn1", "hand": "berlin"})
        out["pairs"].append({"real": jpg(cv2.imread(str(data / f"{key}.jpg"), cv2.IMREAD_GRAYSCALE)),
                             "rebuilt": jpg(cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)), **caption(r)})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--data", type=Path, default=ZEUS / "dataL2")
    ap.add_argument("--synth", type=Path, default=ZEUS / "dataS3")
    ap.add_argument("--osq-list", type=Path, required=True, help="score_to_lmx.py's LMX files, one path a line")
    ap.add_argument("--template", type=Path, default=HERE / "explainer.html")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--rebuild-dir", type=Path, help="overlay.png, segments.png, glyphs.png and KEY.rebuilt.jpg files "
                                                     "(align.py, segment.py, rebuild.py) for the rebuilding section")
    ap.add_argument("--rebuild-only", type=Path, help="with --rebuild-dir: take the rest of the data from this built page")
    a = ap.parse_args()
    if a.rebuild_only:
        data = json.loads(a.rebuild_only.read_text().split("const D = ", 1)[1].split(";\nconst $", 1)[0])
        data["rebuild"] = rebuild_section(a.rebuild_dir, a.data)
        a.out.write_text(a.template.read_text().replace("/*DATA*/null", json.dumps(data)))
        print(a.out)
        return
    rng = random.Random(a.seed)
    reals = real_staves(a.data)
    by = defaultdict(list)
    for r in reals:
        by[(r["source"], r["part"])].append(r)

    def pick(src, part, rng):
        cands = [r for r in by[(src, part)] if 18 <= stats_of((9, 100), (a.data / f"{r['key']}.lmx").read_text())["events"] <= 60]
        return rng.choice(cands or by[(src, part)])

    data = {"hands": {h: {"name": n, "about": d} for h, (n, d) in HAND_NAMES.items()}}

    # the stages, on one Berlin staff
    r = next(x for x in reals if x["key"] == "D-B_KHM-602/p10s4")
    lmx = (a.data / f"{r['key']}.lmx").read_text()
    real = cv2.imread(str(a.data / f"{r['key']}.jpg"), cv2.IMREAD_GRAYSCALE)
    st = {}
    final, p = copyist.draw(lmx, "berlin", seed=11, width=real.shape[1] / real.shape[0] * 9 - 2, return_params=True,
                            stages=st)
    data["stages"] = {"tokens": lmx.split(), "real": jpg(real), "final": jpg(final), "note": params_note(p),
                      **{k: jpg(v, 88) for k, v in st.items()}, **caption(r)}
    print("stages", flush=True)

    # the hands' habits
    data["params"] = [{"name": f.name, "how": HOW.get(f.name, ("", ""))[0], "what": HOW.get(f.name, ("", ""))[1],
                       "ranges": {h: getattr(copyist.HANDS[h], f.name) for h in copyist.HANDS}}
                      for f in fields(copyist.Hand)]
    data["measure"] = measure(a.data, a.synth, reals)
    print("measured", flush=True)

    # the copyists' clefs
    clefs = {}
    for hand in ["berlin", "parisA", "vma"]:
        row = []
        for kind in ("G2", "C3", "F4"):
            ims = [255 - (i * 255).astype(np.uint8) for i in copyist.clef_library(hand, kind)[:7]]
            if ims:
                row.append({"kind": kind, "imgs": [png(cv2.resize(i, (int(i.shape[1] * 80 / i.shape[0]), 80),
                                                              interpolation=cv2.INTER_AREA)) for i in ims]})
        clefs[hand] = row
    data["clefs"] = clefs

    # the gallery: real staves and two drawings each, at the same length
    data["gallery"] = {}
    for hand, picks in GALLERY.items():
        data["gallery"][hand] = [draw_pair(a.data, pick(src, part, rng), (rng.randrange(1 << 20), rng.randrange(1 << 20)))
                                 for src, part in picks]
        print("gallery", hand, flush=True)

    # close-ups, a third of the way along
    data["closeups"] = []
    for hand, picks in GALLERY.items():
        r = pick(*picks[0], random.Random(sum(map(ord, hand))))
        real = cv2.imread(str(a.data / f"{r['key']}.jpg"), cv2.IMREAD_GRAYSCALE)
        lmx = (a.data / f"{r['key']}.lmx").read_text()
        drawn = copyist.draw(lmx, hand, seed=rng.randrange(1 << 20), width=real.shape[1] / real.shape[0] * 9 - 2)
        data["closeups"].append({"hand": hand, "real": jpg(closeup(real, 0.0), 90), "drawn": jpg(closeup(drawn, 0.0), 90),
                                 **caption(r)})

    # one staff, every hand
    r = next(x for x in reals if x["key"] == "D-B_KHM-602/p2s3")
    lmx = (a.data / f"{r['key']}.lmx").read_text()
    data["every"] = {"real": jpg(cv2.imread(str(a.data / f"{r['key']}.jpg"), cv2.IMREAD_GRAYSCALE)), **caption(r),
                     "drawn": []}
    for k, hand in enumerate(["berlin", "parisA", "parisB", "vma", "generic"]):
        img, p = copyist.draw(lmx, hand, seed=500 + k, return_params=True)
        data["every"]["drawn"].append({"hand": hand, "img": jpg(img), "note": params_note(p)})
    print("every hand", flush=True)

    # new music
    files = [Path(l) for l in a.osq_list.read_text().split()]
    rng.shuffle(files)
    data["osq"] = []
    want = ["berlin", "parisA", "parisB", "vma", "generic"] * 2
    for f in files:
        if not want:
            break
        lmx = f.read_text()
        if not 20 <= stats_of((9, 100), lmx)["events"] <= 60:
            continue
        composer, _, work = f.parent.name.partition("__")
        work = re.sub(r"__sq\d+$", "", work).replace("__", ", ").replace("_", " ").strip(" ,")
        try:
            img, p = copyist.draw(lmx, want[0], seed=rng.randrange(1 << 20), return_params=True)
        except ValueError:
            continue
        if img.shape[1] / img.shape[0] > gen.MAX_ASPECT:
            continue
        part = ["first violin", "second violin", "viola", "cello"][int(f.stem[1])] if f.stem[1].isdigit() else ""
        data["osq"].append({"hand": want.pop(0), "img": jpg(img), "note": params_note(p),
                            "work": f"{composer}, {work}", "part": part})
    print("new music", flush=True)

    # a quiz: which is real?
    data["quiz"] = []
    for hand in ["berlin", "parisA", "parisB", "vma"]:
        r = pick(*GALLERY[hand][1], random.Random(31 + len(hand)))
        real = cv2.imread(str(a.data / f"{r['key']}.jpg"), cv2.IMREAD_GRAYSCALE)
        lmx = (a.data / f"{r['key']}.lmx").read_text()
        drawn = copyist.draw(lmx, hand, seed=rng.randrange(1 << 20), width=real.shape[1] / real.shape[0] * 9 - 2)
        frac = rng.uniform(0.2, 0.5)
        pair = [{"img": jpg(closeup(real, frac, 40), 90), "real": True},
                {"img": jpg(closeup(drawn, frac, 40), 90), "real": False}]
        rng.shuffle(pair)
        data["quiz"].append({"hand": hand, "pair": pair, **caption(r)})

    if a.rebuild_dir:
        data["rebuild"] = rebuild_section(a.rebuild_dir, a.data)
    html = a.template.read_text().replace("/*DATA*/null", json.dumps(data))
    a.out.write_text(html)
    print(a.out, f"{len(html) / 1e6:.1f} MB", flush=True)


if __name__ == "__main__":
    main()
