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
"""How likely the Zeus OMR model finds a given reading of a manuscript's
staves, token by token: for an edition comparing a manuscript with its notes
(the Op. 48 edition's scripts/differences.py).

    uv run ~/Dropbox/Code/manuscript-labeler/tools/zeus_score.py \\
        --pdf M.pdf --structure S.ily --events DIR --out scores.json \\
        [--bars M.bars.json] [--parts vn1 vc] [--movements I II] [--shifts 0 -1 1] [--model M]
    uv run ... tools/zeus_score.py --edition <Op48 edition> --source F-Pn_Vma-ms-1067-1 ...

Reads the manuscript (--pdf), its bar export from the labeler (--bars,
default beside the PDF) and each movement's key and time (--structure: a
Structure.ily, or JSON; see movements()). With --edition and --source those
are found in the Op. 48 edition's layout. The reading is --events DIR, one
file per part and movement, DIR/<part>-<mvt>.json (vn1-I.json ...), in the
format of the edition's `scripts/events.py <quartet> <part> <mvt> --json`
(zeus-score/README.md describes it). Parts and movements default to every
one in the bar export; one with no reading file is left out, and listed.

Each staff is cut as the model was trained on it (experiments/zeus/
compare.py's page_image and staff_crop, saved as dataset.py saves it), and
the reading of its bars written in Zeus's output format (LMX) as
dataset.py's training data is, and checked the same way: read back, it is
the reading. Zeus is then handed it, teacher-forced, one staff at a time,
and gives each token's log-probability, the token it would have written
there and that one's. For every --shifts k, again with every pitch moved k
octaves (a passage written in another register shows as one).

Where dataset.py leaves a staff out, this scores it if it can:
- a bar with two voices is written as one, the upper (notes of both that
  start and last together as one chord), and listed in the staff's
  `approximate`: its scores don't say what the manuscript has there;
- a clef change inside a bar is written where the reading changes clef.
Every staff still left out is listed in `left_out`, with its bars and why.

Output, one JSON file: {format: 1, model: {name, version, sha256},
labeler_commit, zeus_commit, source, movements, staves: [{sid, part, mvt,
bars: [[bar, count]...], tokens, approximate: [bar...], unknown: [token...],
trained, shifts: {"k": {lp, best, best_lp}}}], left_out: [{sid, part, mvt,
bars: [first, last], reason}]}; lp, best and best_lp have one more entry
than tokens, for the end (EOS). `format` goes up with any change a reader
must handle. `sha256` is the weights file's. `trained` is true where the
model was trained on the staff's source and movement (--trained-on, where
["*"] means every movement), false where it wasn't and the source was named
(--source), and null when that isn't known: a model given by path, or a
source named only by its PDF's file name that --trained-on doesn't list.
Trained movements are named on stderr: the model has learned their reading,
so it objects less there.

`read` (a MuSViT reader only) gives the model's own reading of each staff
instead, with each token's probability; with --against, each bar counted
against our notes by compare.py's rules. `compare` counts two sets of our
notes by the same rules. zeus-score/README.md describes both.

--renders is where page renders are written and read (default the
labeler's cache). The zeus-score package (zeus-score/) runs this file with
a registry model's --model-name, --model-version and --trained-on.

--model defaults to run J at epoch 8 (65% of bars exact on the clean test,
KHM 603 movement I; G 62%, I 64%). J was trained on every encoded Op. 48
movement but that one, with the edition's own notes, so on those staves it
leans toward the edition's reading; G-lr1e5-e8 saw the fewest of them. The models derive
from Zeus's CC BY-NC-SA weights: non-commercial use.
"""

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path

LABELER = Path(__file__).resolve().parent.parent
if (LABELER / "experiments" / "zeus" / "compare.py").exists():  # a labeler checkout; in zeus-score they're beside this
    sys.path.insert(0, str(LABELER / "experiments" / "zeus"))
import compare  # noqa: E402
import dataset  # noqa: E402
import structure  # noqa: E402

MODEL = Path.home() / ".cache/manuscript-labeler/models/zeus/sweep/J-lr1e5-e8.model"
PARTS = ("vn1", "vn2", "va", "vc")
PITCH = re.compile(r"([A-G])(\d)")
GLYPH = {"treble": "clefs.G", "alto": "clefs.C", "tenor": "clefs.C", "bass": "clefs.F"}


def shifted(tokens: list[str], by: int) -> list[str]:
    return [f"{m.group(1)}{int(m.group(2)) + by}" if (m := PITCH.fullmatch(t)) else t for t in tokens]


def two_voices(evs: list[dict]) -> bool:
    """dataset.py's test: the bar's notes and rests are in more than one voice."""
    return len({e["voice"] for e in evs if e["grace"] == "0"}) > 1


def top(e: dict) -> int:
    return max((compare.num(n["pitch"]) for n in e["notes"]), default=-1)


def one_voice(evs: list[dict], bar: int, mk: dict) -> list[dict]:
    """A bar of several voices as one: at each onset the upper voice's note
    (a rest only where no voice has a note), with the notes of the other
    voices that start and last with it as one chord; what starts inside a
    note kept is dropped, and grace notes go with the note they lead into."""
    def length(e):
        dur = e["dur"] or ""
        n = dataset.LEN.get(dur.rstrip("."), Fraction(0)) * (2 - Fraction(1, 2 ** dur.count(".")))
        ratio = dataset.mark(mk, bar, e).get("tuplet")
        return n * Fraction(ratio[1], ratio[0]) if ratio else n

    main = [e for e in evs if e["grace"] == "0"]
    kept, until = [], Fraction(-1)
    for on in sorted({Fraction(e["pos"]) for e in main}):
        if on < until:
            continue
        here = [e for e in main if Fraction(e["pos"]) == on]
        # the upper note; where only rests start, the shortest, so no voice's next note is hidden
        first = max(here, key=lambda e: (e["kind"] == "note", top(e), -length(e)))
        e = dict(first)
        heads = list(e["notes"])
        for o in here:
            if o is not first and o["kind"] == first["kind"] == "note" and o["dur"] == first["dur"] and o["tup"] == first["tup"]:
                heads += [h for h in o["notes"] if h["pitch"] not in {x["pitch"] for x in heads}]
        e["notes"] = sorted(heads, key=lambda h: compare.num(h["pitch"]))
        kept.append(e)
        until = on + length(first)
    lead = {(Fraction(e["pos"]), e["voice"]) for e in kept}
    graces = [e for e in evs if e["grace"] != "0" and (Fraction(e["pos"]), e["voice"]) in lead]
    return sorted(graces + kept, key=lambda e: (Fraction(e["pos"]), e["grace"] == "0"))


def clef_places(box: dict, evs: list[dict]) -> dict | None:
    """Where a bar's clef changes inside it, as the reading changes clef:
    {index of the first note in the new clef: the labels' clef}; None if
    the reading doesn't change clef there as often as the manuscript."""
    glyphs = [(i, e["clef"]) for i, e in enumerate(evs) if e["kind"] == "note" and e["clef"]]
    at = [i for (_, a), (i, b) in zip(glyphs, glyphs[1:]) if a != b]
    new = box["clefs"][1:]
    if len(at) != len(new) or any(c not in dataset.CLEF for c in new):
        return None
    return dict(zip(at, new))


def check(lmx: str, boxes: list[dict], per_box: list[list[dict]], changes: dict) -> bool:
    """dataset.py's check: read back as compare.py reads Zeus, the LMX is
    the reading, bar by bar (a bar that changes clef read in its clefs as
    written)."""
    measures, _ = compare.parse(lmx)
    if len(measures) != len(boxes):
        return False
    for k, (b, ms, evs) in enumerate(zip(boxes, measures, per_box)):
        zs = [compare.zeus_event(e, e["zclef"] if k in changes else b["clefs"][0]) for e in ms]
        enc = compare.encoded(evs)
        if not (len(zs) == len(enc) and all(map(compare.same, enc, zs))):
            return False
    return True


def write(boxes, evs, mk, exp, first_of_mvt, split) -> tuple[str | None, list[int], str]:
    """A staff's LMX, its approximate bars, or None and why it's left out."""
    per_box = [dataset.box_events(b, evs, split) for b in boxes]
    for b, be in zip(boxes, per_box):
        if be is None:
            return None, [], f"bar {b['bar']} is split across two staves where its notes can't be cut"
    approximate, changes = [], {}
    for k, b in enumerate(boxes):
        if two_voices(evs.get(str(b["bar"]), [])):
            per_box[k] = one_voice(per_box[k], b["bar"], mk)
            approximate.append(k)
        if len(b["clefs"]) > 1:
            places = clef_places(b, per_box[k])
            if places is None:
                return None, [], f"a clef change inside bar {b['bar']} that the reading doesn't make there"
            changes[k] = places
    xml = dataset.staff_part(boxes, evs, mk, exp, first_of_mvt, split, per_box, changes)
    # dataset.py's bar check, on the bars written as they are
    whole = [b if k not in approximate else {**b, "count": 0} for k, b in enumerate(boxes)]
    if not dataset.fills(xml, whole, exp, split, max(int(k) for k in evs)):
        return None, [], "a bar whose notes don't fill it"
    lmx = dataset.encode(xml)
    if not check(lmx, boxes, per_box, changes):
        return None, [], "its notes didn't survive being written in Zeus's format"
    return lmx, [boxes[k]["bar"] for k in approximate], ""


def staff_image(page, s: dict) -> bytes:
    """The staff as dataset.py saves it for training: a JPEG at quality 95."""
    from PIL import Image
    buf = io.BytesIO()
    Image.open(io.BytesIO(compare.staff_crop(page, s))).convert("L").save(buf, "JPEG", quality=95)
    return buf.getvalue()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def zeus_commit() -> str | None:
    from importlib.metadata import distribution
    try:
        return json.loads(distribution("zeus").read_text("direct_url.json") or "{}").get("vcs_info", {}).get("commit_id", "")[:7] or None
    except Exception:
        return None


class Zeus:
    """Zeus, teacher-forced, one staff at a time (its attention doesn't mask
    a batch's padding): for each reading of a staff, each token's
    log-probability, the token Zeus would have written there and that one's.
    musvit_score.py's Reader is the same for a MuSViT reader."""
    engine = "zeus"
    too_long = ""

    def __init__(self, path: Path):
        import tensorflow as tf
        from zeus import Zeus as Model
        self.weights, self.commit = path / "weights.h5", zeus_commit()
        self.model = Model.load(path)
        self.tm = self.model.token_map

        @tf.function(reduce_retracing=True)
        def logprobs(img, ids):
            enc = self.model.model.encoder(tf.RaggedTensor.from_tensor(img[tf.newaxis], ragged_rank=2), training=False)
            return tf.nn.log_softmax(self.model.model.decoder_training(enc, ids[tf.newaxis]), -1)[0]
        self.logprobs = logprobs

    def unknown(self, toks: list[str]) -> list[str]:
        return sorted({t for t in toks if self.tm.token_to_index(t, allow_unknown_tokens=True) == self.tm.unknown_token_index})

    def score(self, jpeg: bytes, readings: list[list[str]]) -> list[dict]:
        import numpy as np
        import tensorflow as tf
        from zeus.model.preprocess_image import preprocess_image
        # As Zeus's predict prepares a staff: grey, its height, width by aspect up to 1500, no padding.
        img = preprocess_image(tf.constant(jpeg), height=self.model.architecture_options.height, transformations=[],
                               max_image_width=1500)
        out = []
        for toks in readings:
            ids = [self.tm.token_to_index(t, allow_unknown_tokens=True) for t in toks] + [self.tm.eos_token_index]
            lp = self.logprobs(img, tf.constant(ids, tf.int32)).numpy()
            best = lp.argmax(-1)
            out.append({"lp": [round(float(v), 3) for v in lp[np.arange(len(ids)), ids]],
                        "best": [self.tm.index_to_token(int(i)) for i in best],
                        "best_lp": [round(float(lp[k, i]), 3) for k, i in enumerate(best)]})
        return out


def main(backend=None):
    backend = backend or Zeus
    if sys.argv[1:2] == ["read"]:
        return read_main(backend, sys.argv[2:])
    if sys.argv[1:2] == ["compare"]:
        return compare_main(sys.argv[2:])
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pdf", type=Path, help="the manuscript")
    ap.add_argument("--bars", type=Path, help="its bar export from the labeler (default the PDF's .bars.json)")
    ap.add_argument("--structure", type=Path, help="each movement's key and time: a Structure.ily or a .json")
    ap.add_argument("--edition", type=Path, help="the Op. 48 edition: --source then finds the other three")
    ap.add_argument("--source", help="the source's name (default the PDF's); with --edition, its sources/G*/<source>")
    ap.add_argument("--parts", nargs="+", help="default every part in the bar export")
    ap.add_argument("--movements", nargs="+", help="default every movement in the bar export")
    ap.add_argument("--events", type=Path, required=True, help="the reading: DIR/<part>-<mvt>.json")
    ap.add_argument("--shifts", type=int, nargs="+", default=[0], help="octaves to move every pitch by, 0 as given")
    ap.add_argument("--model", type=Path, default=MODEL)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--renders", type=Path, default=compare.RENDERS, help="where page renders are written and read")
    ap.add_argument("--model-name", help="the model's registry name (default its folder's)")
    ap.add_argument("--model-version", help="the model's registry version")
    ap.add_argument("--model-sha256", help="its weights' sha256, if already checked (default computed)")
    ap.add_argument("--trained-on", type=json.loads,
                    help='JSON: {"<source>": ["I", ...]} the model was trained on; ["*"] for every movement')
    ap.add_argument("--labeler-commit", help="the labeler commit this code is from (default this checkout's)")
    a = ap.parse_args()
    compare.RENDERS = a.renders

    named = bool(a.source)
    pdf, export, expected, a.source = inputs(a)
    parts = a.parts or sorted({b["part"] for b in export["bars"]}, key=lambda p: (PARTS.index(p) if p in PARTS else len(PARTS), p))
    if not a.movements:
        a.movements = list(dict.fromkeys(b["movement"] for b in export["bars"] if b["part"] in parts))

    # The staves and their boxes, as dataset.py takes them.
    staves: dict[str, list] = {}
    for b in export["bars"]:
        if b["part"] in parts and b["movement"] in a.movements:
            staves.setdefault(b["system"], []).append(b)
    boxes_per_bar = Counter((b["part"], b["movement"], b["bar"]) for bs in staves.values() for b in bs)
    first_of_mvt, seen = set(), set()
    for b in export["bars"]:
        if (b["part"], b["movement"]) not in seen:
            seen.add((b["part"], b["movement"]))
            first_of_mvt.add((b["part"], b["movement"], b["bar"], b["count"]))

    events, mks, splits = {}, {}, {}
    for part, mvt in sorted({(b["part"], b["movement"]) for bs in staves.values() for b in bs}):
        f = a.events / f"{part}-{mvt}.json"
        if not f.exists():
            continue
        events[(part, mvt)] = json.loads(f.read_text())
        mks[(part, mvt)] = dataset.marks(events[(part, mvt)])
        pick = [Fraction(e["pos"]) for e in events[(part, mvt)].get("0", []) if e["grace"] == "0"]
        cut = min(pick) if pick else False  # the pickup starts where a short bar would end
        splits[(part, mvt)] = {bar: cut for (p, m, bar), n in boxes_per_bar.items() if p == part and m == mvt and n > 1}

    # Each staff written, or left out with the reason.
    todo, left_out = [], []
    for sid, boxes in staves.items():
        part, mvt = boxes[0]["part"], boxes[0]["movement"]
        why = None
        if {b["movement"] for b in boxes} != {mvt}:
            why = "it holds the end of one movement and the start of the next"
        elif (part, mvt) not in events:
            why = f"no reading given for {part} {mvt} ({part}-{mvt}.json)"
        elif mvt not in expected:
            why = f"the structure has no movement {mvt}"
        else:
            lmx, approx, why = dataset_safe(write, boxes, events[(part, mvt)], mks[(part, mvt)], expected[mvt],
                                            first_of_mvt, splits[(part, mvt)])
        if why:
            left_out.append({"sid": sid, "part": part, "mvt": mvt, "bars": [boxes[0]["bar"], boxes[-1]["bar"]],
                             "reason": why})
            continue
        todo.append((sid, boxes, lmx, approx))

    model = backend(a.model)
    rows, page = [], None
    for sid, boxes, lmx, approx in todo:
        s = export["systems"][sid]
        if page is None or page[0] != s["page"]:
            page = (s["page"], compare.page_image(pdf, s["page"]))
        toks = lmx.split()
        scored = model.score(staff_image(page[1], s), [shifted(toks, by) for by in a.shifts])
        if scored is None:
            left_out.append({"sid": sid, "part": boxes[0]["part"], "mvt": boxes[0]["movement"],
                             "bars": [boxes[0]["bar"], boxes[-1]["bar"]], "reason": model.too_long})
            continue
        rows.append({"sid": sid, "part": boxes[0]["part"], "mvt": boxes[0]["movement"],
                     "bars": [[b["bar"], b["count"]] for b in boxes], "tokens": toks, "approximate": approx,
                     "unknown": model.unknown(toks),
                     "trained": trained(a.trained_on, a.source, named, boxes[0]["movement"]),
                     "shifts": {str(by): sc for by, sc in zip(a.shifts, scored)}})

    commit = a.labeler_commit
    if commit is None and (LABELER / "tools" / "zeus_score.py").exists():  # a labeler checkout
        head = subprocess.run(["git", "-C", str(LABELER), "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
        commit = head.stdout.strip() or None
    model_info = {"name": a.model_name or a.model.name.removesuffix(".model"), "version": a.model_version,
                  "sha256": a.model_sha256 or sha256(model.weights), "engine": model.engine}
    learned = sorted({r["mvt"] for r in rows if r["trained"]})
    if learned:
        print(f"zeus_score: {model_info['name']} was trained on {a.source} {' '.join(learned)}: "
              f"it objects less there", file=sys.stderr)
    out = {"format": 1, "model": model_info, "labeler_commit": commit,
           "zeus_commit": model.commit, "source": a.source, "movements": a.movements,
           "staves": rows, "left_out": left_out}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out))
    print(f"{a.source} {' '.join(a.movements)}: scored {len(rows)} staves "
          f"({sum(bool(r['approximate']) for r in rows)} with approximate bars), left out {len(left_out)}")


def source_args(ap) -> None:
    """The manuscript and which of it: scoring's options, less the reading."""
    ap.add_argument("--pdf", type=Path, help="the manuscript")
    ap.add_argument("--bars", type=Path, help="its bar export from the labeler (default the PDF's .bars.json)")
    ap.add_argument("--edition", type=Path, help="the Op. 48 edition: --source then finds the PDF and bar export")
    ap.add_argument("--source", help="the source's name (default the PDF's); with --edition, its sources/G*/<source>")
    ap.add_argument("--parts", nargs="+", help="default every part in the bar export")
    ap.add_argument("--movements", nargs="+", help="default every movement in the bar export")


def chosen_staves(a, export: dict) -> dict:
    """{staff: its bar boxes} for --parts and --movements (every one in the
    bar export by default), as compare.py takes them; sets a.movements."""
    parts = a.parts or sorted({b["part"] for b in export["bars"]}, key=lambda p: (PARTS.index(p) if p in PARTS else len(PARTS), p))
    if not a.movements:
        a.movements = list(dict.fromkeys(b["movement"] for b in export["bars"] if b["part"] in parts))
    staves: dict[str, list] = {}
    for b in export["bars"]:
        if b["part"] in parts and b["movement"] in a.movements:
            staves.setdefault(b["system"], []).append(b)
    return staves


def bar_keys(staves: dict) -> tuple[set, set]:
    """Every bar box's bar, and those with a clef change inside (where it
    falls isn't known), which compare.py leaves uncompared."""
    keys = {(b["part"], b["movement"], b["bar"]) for bs in staves.values() for b in bs}
    return keys, {(b["part"], b["movement"], b["bar"]) for bs in staves.values() for b in bs if len(b["clefs"]) != 1}


def notes_of(folder: Path, staves: dict) -> dict:
    """{(part, movement, bar): encoded events} from DIR/<part>-<mvt>.json
    (scoring's --events), for every part and movement the staves hold that
    has a file."""
    out = {}
    for part, mvt in sorted({(b["part"], b["movement"]) for bs in staves.values() for b in bs}):
        f = folder / f"{part}-{mvt}.json"
        if f.exists():
            for bar, evs in json.loads(f.read_text()).items():
                out[(part, mvt, int(bar))] = compare.encoded(evs)
    return out


def bar_results(scored: dict) -> dict:
    """The tally and rows of compare.score_bars or compare_notes, as written out."""
    rows = [{k: r[k] for k in ("part", "movement", "bar", "exact", "rhythm", "pitch", "exact as written", "errors",
                               "encoded", "zeus")} for r in scored["rows"]]
    for r in rows:
        r["ours"], r["read"] = r.pop("encoded"), r.pop("zeus")
    return {"tally": {g: dict(t) for g, t in scored["tally"].items()}, "bars": rows}


def labeler_commit(given: str | None) -> str | None:
    if given is None and (LABELER / "tools" / "zeus_score.py").exists():  # a labeler checkout
        head = subprocess.run(["git", "-C", str(LABELER), "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
        return head.stdout.strip() or None
    return given


def read_main(backend, argv: list[str]) -> None:
    """`read`: the model's own reading of each staff, with each token's
    probability; with --against, each bar counted against our notes by
    compare.py's rules (the model card's)."""
    ap = argparse.ArgumentParser(prog="zeus-score read", description=read_main.__doc__)
    source_args(ap)
    ap.add_argument("--against", type=Path, help="our notes, DIR/<part>-<mvt>.json (as scoring's --events), to count bars right")
    ap.add_argument("--batch", type=int, default=1,
                    help="staves read together, in order of width (1: each alone, so its reading doesn't depend on the others)")
    ap.add_argument("--model", type=Path, default=MODEL)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--renders", type=Path, default=compare.RENDERS, help="where page renders are written and read")
    ap.add_argument("--model-name")
    ap.add_argument("--model-version")
    ap.add_argument("--model-sha256")
    ap.add_argument("--trained-on", type=json.loads)
    ap.add_argument("--labeler-commit")
    a = ap.parse_args(argv)
    if not hasattr(backend, "read"):
        sys.exit("zeus-score read: needs a MuSViT reader (a registry model whose engine is musvit)")
    compare.RENDERS = a.renders
    named = bool(a.source)
    pdf, export, _, a.source = inputs(a, structure_needed=False)
    staves = chosen_staves(a, export)

    sids, jpegs, page = list(staves), [], None
    for sid in sids:
        s = export["systems"][sid]
        if page is None or page[0] != s["page"]:
            page = (s["page"], compare.page_image(pdf, s["page"]))
        jpegs.append(staff_image(page[1], s))
    model = backend(a.model)
    read, decoding = model.read(jpegs, a.batch)

    ours = notes_of(a.against, staves) if a.against else {}
    scored = compare.score_bars(staves, {sid: " ".join(r["tokens"]) for sid, r in zip(sids, read)}, export, ours)
    rows = []
    for sid, r in zip(sids, read):
        boxes, how = staves[sid], scored["pairing"][sid]
        cuts = [k for k, t in enumerate(r["tokens"]) if t == "measure"]
        measures = [r["tokens"][x:y] for x, y in zip([0] + cuts[1:], cuts[1:] + [len(r["tokens"])])] if cuts else [r["tokens"]]
        lp = r["lp"]
        rows.append({"sid": sid, "part": boxes[0]["part"], "mvt": boxes[0]["movement"],
                     "bars": [[b["bar"], b["count"]] for b in boxes],
                     "trained": trained(a.trained_on, a.source, named, boxes[0]["movement"]),
                     "tokens": r["tokens"], "measures": measures,
                     "paired": how is not None,
                     "pairing": None if how is None else [{"bar": b["bar"], "count": b["count"], "how": kind, "measures": ms}
                                                         for b, (kind, ms) in zip(boxes, how)],
                     "ended": r["ended"], "lp": lp, "runner_up": r["runner_up"], "runner_up_lp": r["runner_up_lp"],
                     "mean_lp": round(sum(lp) / len(lp), 4) if lp else None,
                     "below_half": round(sum(x < -0.6931 for x in lp) / len(lp), 4) if lp else None})

    model_info = {"name": a.model_name or a.model.name.removesuffix(".model"), "version": a.model_version,
                  "sha256": a.model_sha256 or sha256(model.weights), "engine": model.engine}
    out = {"format": 1, "command": "read", "model": model_info, "labeler_commit": labeler_commit(a.labeler_commit),
           "decoding": decoding, "source": a.source, "movements": a.movements, "staves": rows}
    if a.against:
        out["against"] = {"notes": str(a.against), **bar_results(scored)}
    learned = sorted({r["mvt"] for r in rows if r["trained"]})
    if learned:
        print(f"zeus_score: {model_info['name']} was trained on {a.source} {' '.join(learned)}: "
              f"its reading there is of music it learned", file=sys.stderr)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out))
    t = scored["tally"]["all"]
    print(f"{a.source} {' '.join(a.movements)}: read {len(rows)} staves ({decoding['device']}, {decoding['precision']}, "
          f"{decoding['batch']} at a time); {sum(not r['paired'] for r in rows)} whose measures don't pair with their "
          f"bar boxes, {sum(not r['ended'] for r in rows)} that ran out of length"
          + (f"; bars exact {t['bars exact']}/{t['bars']}" if a.against else ""))


def compare_main(argv: list[str]) -> None:
    """`compare`: two sets of our notes counted by compare.py's rules over
    the bars a reading is compared on: --events against --against, taken as
    right."""
    ap = argparse.ArgumentParser(prog="zeus-score compare", description=compare_main.__doc__)
    source_args(ap)
    ap.add_argument("--events", type=Path, required=True, help="the notes to count, DIR/<part>-<mvt>.json")
    ap.add_argument("--against", type=Path, required=True, help="the notes taken as right, DIR/<part>-<mvt>.json")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--labeler-commit")
    a = ap.parse_args(argv)
    _, export, _, a.source = inputs(a, structure_needed=False)
    staves = chosen_staves(a, export)
    keys, skip = bar_keys(staves)
    scored = compare.compare_notes(keys, notes_of(a.events, staves), notes_of(a.against, staves), skip)
    out = {"format": 1, "command": "compare", "labeler_commit": labeler_commit(a.labeler_commit), "source": a.source,
           "movements": a.movements, "events": str(a.events), "against": str(a.against), **bar_results(scored)}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out))
    t = scored["tally"]["all"]
    print(f"{a.source} {' '.join(a.movements)}: bars exact {t['bars exact']}/{t['bars']}, "
          f"{t['bars not compared']} not compared")


def trained(trained_on: dict | None, source: str, named: bool, mvt: str) -> bool | None:
    """Was the model trained on this source's movement? None: not known."""
    if trained_on is None:
        return None
    movements = trained_on.get(source)
    if movements is not None:
        return "*" in movements or mvt in movements
    return False if named else None


def inputs(a, structure_needed: bool = True) -> tuple[Path, dict, dict, str]:
    """The manuscript, its bar export, each movement's key and time, and the
    source's name: from --pdf, --bars and --structure, or, given --edition and
    --source, from the Op. 48 edition's layout (sources/G*/<source>.pdf and
    .bars.json, Op48-<n>/Structure.ily); an explicit file wins. Reading and
    comparing don't need the key and time ({} then)."""
    pdf, bars, struct = a.pdf, a.bars, getattr(a, "structure", None)
    if a.edition:
        if not a.source:
            sys.exit("zeus_score: --edition needs --source")
        pdf = pdf or next(a.edition.glob(f"sources/*/{a.source}.pdf"), None)
        if pdf is None:
            sys.exit(f"zeus_score: no sources/*/{a.source}.pdf in {a.edition}")
    if pdf is None:
        sys.exit("zeus_score: give --pdf (with --structure), or --edition and --source")
    bars = bars or pdf.with_name(pdf.stem + ".bars.json")
    if not bars.exists():
        sys.exit(f"zeus_score: no bar export {bars}")
    export = json.loads(bars.read_text())
    if not structure_needed:
        return pdf, export, {}, a.source or pdf.stem
    if struct is None and a.edition:
        struct = a.edition / f"Op48-{export['source']['gerard'] - 225}" / "Structure.ily"
    if struct is None:
        sys.exit("zeus_score: give --structure (a Structure.ily or a .json of each movement's key and time)")
    return pdf, export, movements(struct), a.source or pdf.stem


def movements(path: Path) -> dict:
    """{movement: {time, key, changes}}: a Structure.ily as the labeler reads
    it, or JSON written that way: {"I": {"time": "6/8", "key": 1, "changes":
    [{"bar": 32, "on_bar_line": false, "key": -2}]}}, key in fifths (sharps
    positive), a change holding from its bar (from the bar's upbeat if not on
    the bar line)."""
    if path.suffix == ".json":
        out = json.loads(path.read_text())
        for m, e in out.items():
            if not (isinstance(e.get("time"), str) and re.fullmatch(r"\d+/\d+", e["time"])
                    and isinstance(e.get("key"), int)):
                sys.exit(f'zeus_score: movement {m} in {path} needs a time ("3/4") and a key (fifths, an integer)')
            e.setdefault("changes", [])
            for c in e["changes"]:
                c.setdefault("on_bar_line", True)
                if not (isinstance(c.get("bar"), int) and ("key" in c or "time" in c)
                        and isinstance(c.get("key", 0), int) and re.fullmatch(r"\d+/\d+", c.get("time", "1/1"))):
                    sys.exit(f"zeus_score: a change in movement {m} of {path} needs a bar (an integer) "
                             f"and a key (an integer) or a time: {c}")
        return out
    return structure.expected(path.read_text())


def dataset_safe(fn, *args):
    """A staff the conversion can't write (a clef or duration it has no
    word for) is left out, not the whole run."""
    try:
        return fn(*args)
    except (KeyError, ValueError, AssertionError) as e:  # the LMX encoder asserts on what it can't write
        return None, [], f"its notes can't be written in Zeus's format ({e})"


if __name__ == "__main__":
    main()
