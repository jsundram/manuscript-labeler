"""OSSQ's 1750-1800 scanned staves, re-cropped to our convention, for MuSViT's
stage 1 (PLAN.md, "Period staves for stage 1").

The works: Haydn Op. 1, 9, 20, 64, 74, 76; Mozart K. 80 to K. 590; Beethoven
Op. 18 (42 scanned scores, 13,253 staves). Each staff is re-cut from its JPEG
in /staves/ossq/scanned/ (256 px high, the YOLO staff box), as
compare.staff_crop cuts ours:
- the five lines found by horizontal ink projection, in vertical strips, so
  a slightly tilted staff is found and straightened;
- from 2.5 spaces above the top line to 2.5 below the bottom one (9 spaces);
- the box's width plus a space of white at each end (the JPEG has no more of
  the page; the box ends where the staff does);
- the paper brightened to white by its 90th percentile; grey JPEG 256 px high.
Staves whose lines aren't found are skipped and counted.

    modal run experiments/ossq/period.py::recrop                    # -> /staves/ossq-period/
    modal run experiments/ossq/period.py::sheet                     # contact sheet, ours beside OSSQ's
    modal run experiments/ossq/period.py::check                     # pairing check with musvit-D4
    modal run experiments/ossq/period.py::clean [--exclude sqX,...] # samples.ossq-period(-clean).txt

Writes only under /staves/ossq-period/ in the musvit-staves volume.
"""

import json
import sys
from pathlib import Path

import modal

HERE = Path(__file__).resolve().parent
OUT = "/staves/ossq-period"

app = modal.App("ossq-period")
image = modal.Image.debian_slim(python_version="3.12").uv_pip_install("numpy", "pillow")
staves = modal.Volume.from_name("musvit-staves")

if modal.is_local():  # the reader (musvit-zeus's read_samples), run within this app for the check
    sys.path.insert(0, str(HERE.parent / "musvit"))
    import modal_app as musvit
    app.include(musvit.app)


def period(path: str) -> bool:
    """Haydn's Op. 1, 9, 20, 64, 74, 76 and Mozart's K. 80-590 are all of their
    scanned works in OSSQ; of Beethoven's, only Op. 18."""
    c = path.split("/")[0]
    return c.startswith("Haydn") or c.startswith("Mozart") or (c.startswith("Beethoven") and "Op.18" in path)


def selected() -> list[str]:
    return [r["sqid"] for r in json.loads((HERE / "cut-scanned.json").read_text())
            if r.get("written") and period(r["path"])]


# ---------------------------------------------------------------- finding the staff

def comb(p, s_exp: float):
    """The best five-line comb in a darkness profile p: (y0, space, contrast),
    contrast being the faintest line's darkness less the spaces' mean."""
    import numpy as np
    h = len(p)
    pm = np.maximum(np.maximum(p, np.roll(p, 1)), np.roll(p, -1))  # a line may straddle rows
    pm[0], pm[-1] = p[0], p[-1]
    best = (0, 0.0, -1.0)
    for s in np.arange(0.8 * s_exp, 1.2 * s_exp + 1e-6, 0.1):
        y0 = np.arange(0, h - 4 * s - 1)
        if not len(y0):
            continue
        lines = np.stack([pm[np.round(y0 + k * s).astype(int)] for k in range(5)])
        gaps = np.stack([p[np.round(y0 + (k + .5) * s).astype(int)] for k in range(4)])
        score = lines.min(0) - gaps.mean(0)
        # the box is centred on its staff: a comb far off centre is a neighbour's ledger lines or text
        centre = y0 + 2 * s
        score = np.where(np.abs(centre - h / 2) < 0.3 * h, score, -1)
        i = int(score.argmax())
        if score[i] > best[2]:
            best = (float(y0[i]), float(s), float(score[i]))
    return best


def find_staff(a, s_exp: float):
    """The staff in a strip (grey array, paper ~1): (top at x=0, slope, space,
    strips agreeing, strips) or a reason. Each ~300 px strip gets its own
    comb; a line is fitted through the combs that agree."""
    import numpy as np
    h, w = a.shape
    d = 1 - a
    n = max(3, w // 300)
    edges = np.linspace(0, w, n + 1).astype(int)
    found = []
    for x0, x1 in zip(edges[:-1], edges[1:]):
        y0, s, c = comb(d[:, x0:x1].mean(1), s_exp)
        if c > 0.15:
            found.append(((x0 + x1) / 2, y0, s))
    if len(found) < max(2, n // 3):
        return f"lines found in {len(found)} of {n} strips"
    f = np.array(found)
    s = float(np.median(f[:, 2]))
    keep = np.abs(f[:, 1] - np.median(f[:, 1])) < 0.6 * s  # the combs on one staff
    for _ in range(2):
        if keep.sum() < max(2, n // 3):
            return f"strips disagree ({int(keep.sum())} of {n} agree)"
        if keep.sum() >= 3:
            b, a0 = np.polyfit(f[keep, 0], f[keep, 1], 1)
        else:
            b, a0 = 0.0, float(np.mean(f[keep, 1]))
        keep = np.abs(f[:, 1] - (a0 + b * f[:, 0])) < 0.4 * s
    if keep.sum() < max(2, n // 3):
        return f"strips disagree ({int(keep.sum())} of {n} agree)"
    s = float(np.median(f[keep, 2]))
    if abs(b) * w > 5 * s:  # a skewed scan is straightened; past this the box has cut the staff
        return f"tilted {abs(b) * w / s:.1f} spaces"
    return float(a0), float(b), s, int(keep.sum()), n


def recut(jpg: bytes, s_exp: float):
    """(JPEG bytes, geometry) of the staff cut to our convention, or (None, reason)."""
    import io
    import numpy as np
    from PIL import Image
    im = Image.open(io.BytesIO(jpg)).convert("L")
    a = np.asarray(im, dtype=np.float32)
    a = np.clip(a / max(np.percentile(a, 90), 1), 0, 1)  # paper to white, as staff_crop does
    r = find_staff(a, s_exp)
    if isinstance(r, str):
        return None, r
    top, slope, s, agree, n = r
    h, w = a.shape
    pad = round(s)
    W, Hh = w + 2 * pad, round(9 * s)
    # output (u, v) <- input (u - pad, top + slope * (u - pad) - 2.5 s + v): straightened along the staff
    src = Image.fromarray((a * 255).astype(np.uint8))
    out = src.transform((W, Hh), Image.AFFINE, (1, 0, -pad, slope, 1, top - 2.5 * s - slope * pad),
                        resample=Image.BICUBIC, fillcolor=255)
    out = out.resize((max(1, round(W * 256 / Hh)), 256), Image.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=92)
    ends = [top - 2.5 * s, top + slope * w - 2.5 * s]
    geo = {"top": round(top, 1), "slope": round(slope, 5), "space": round(s, 2), "expected": round(s_exp, 2),
           "strips": f"{agree}/{n}", "white_above": round(max(0, -min(ends)) / s, 2),
           "white_below": round(max(0, max(e + 9 * s for e in ends) - h) / s, 2)}
    return buf.getvalue(), geo


# ---------------------------------------------------------------- on Modal

@app.function(image=image, cpu=2, memory=4096, timeout=1800, max_containers=4, volumes={"/staves": staves})
def recrop_score(sqid: str) -> dict:
    """Every staff of one score, re-cut to /staves/ossq-period/<sqid>/, with its label."""
    from concurrent.futures import ThreadPoolExecutor
    src = Path("/staves/ossq/scanned") / sqid
    dst = Path(OUT) / sqid
    dst.mkdir(parents=True, exist_ok=True)
    m = json.loads((src / "manifest.json").read_text())

    def one(st):
        name = st["id"].rsplit("/", 1)[1]
        x0, y0, x1, y1 = st["box"]
        s_exp = st["staff_px"] * 256 / (y1 - y0) / 4  # the staff's space in the 256 px JPEG
        jpg, geo = recut((src / f"{name}.jpg").read_bytes(), s_exp)
        if jpg is None:
            return name, None, geo
        (dst / f"{name}.jpg").write_bytes(jpg)
        (dst / f"{name}.lmx").write_bytes((src / f"{name}.lmx").read_bytes())
        return name, geo, None

    with ThreadPoolExecutor(32) as ex:  # each file's first read off the volume is slow
        res = list(ex.map(one, m["staves"]))
    written = [{"name": n, "seg": st["seg"], "bars": st["bars"], **g}
               for (n, g, _), st in zip(res, m["staves"]) if g]
    skipped = {n: why for n, _, why in res if why}
    (dst / "manifest.json").write_text(json.dumps({"sqid": sqid, "path": m["path"], "written": written,
                                                   "skipped": skipped}, indent=0))
    staves.commit()
    return {"sqid": sqid, "path": m["path"], "staves": len(m["staves"]), "written": len(written), "skipped": skipped,
            "padded_1space": sum(1 for g in written if g["white_above"] > 1 or g["white_below"] > 1)}


@app.function(image=image, volumes={"/staves": staves}, timeout=900)
def write_list(name: str, keys: list[str]) -> int:
    """A samples list under /staves/ossq-period/ (keys relative to it)."""
    staves.reload()
    (Path(OUT) / name).write_text("\n".join(keys) + "\n")
    staves.commit()
    return len(keys)


@app.function(image=image, volumes={"/staves": staves}, timeout=900)
def manifests() -> dict:
    staves.reload()
    return {p.parent.name: json.loads(p.read_text()) for p in sorted(Path(OUT).glob("sq*/manifest.json"))}


@app.function(image=image, volumes={"/staves": staves}, timeout=900)
def files(paths: list[str]) -> dict:
    """The bytes of these files on the volume."""
    from concurrent.futures import ThreadPoolExecutor
    staves.reload()
    with ThreadPoolExecutor(32) as ex:
        return dict(zip(paths, ex.map(lambda p: Path(p).read_bytes() if Path(p).exists() else None, paths)))


@app.function(image=image, volumes={"/staves": staves}, timeout=900)
def listing(folder: str, pattern: str, n: int) -> list[str]:
    import random
    fs = sorted(str(p) for p in Path(folder).glob(pattern))
    random.Random(0).shuffle(fs)
    return fs[:n]


# ---------------------------------------------------------------- entry points

@app.local_entrypoint()
def recrop(only: str = ""):
    ids = only.split(",") if only else selected()
    log, total = [], 0
    for r in recrop_score.map(ids, return_exceptions=True):
        if isinstance(r, Exception):
            print("FAILED", repr(r)[:300], flush=True)
            continue
        log.append(r)
        total += r["written"]
        print(r["sqid"], r["written"], "of", r["staves"], "skipped", len(r["skipped"]), flush=True)
    logf = HERE / "period-recrop.json"
    old = {r["sqid"]: r for r in json.loads(logf.read_text())} if logf.exists() else {}
    old.update({r["sqid"]: r for r in log})
    logf.write_text(json.dumps(sorted(old.values(), key=lambda r: r["sqid"]), indent=1))
    if not only:
        ms = manifests.remote()
        keys = [f"{k}/{g['name']}" for k in sorted(ms) for g in ms[k]["written"]]
        print("samples.ossq-period.txt", write_list.remote("samples.ossq-period.txt", keys), flush=True)
    print("written", total, flush=True)


def tile(ims, labels, width=1600, h=110):
    """Rows of staves, each h px high, cut (not squeezed) to width, labelled."""
    from PIL import Image, ImageDraw
    rows = []
    for im, lab in zip(ims, labels):
        im = im.convert("L")
        im = im.resize((max(1, round(im.width * h / im.height)), h), Image.LANCZOS).crop((0, 0, width, h))
        row = Image.new("RGB", (width, h + 16), "white")
        row.paste(im, (0, 16))
        ImageDraw.Draw(row).text((4, 2), lab, fill=(200, 0, 0))
        rows.append(row)
    sheet = Image.new("RGB", (width, sum(r.height for r in rows) + 4 * len(rows)), (90, 90, 90))
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.height + 4
    return sheet


@app.function(image=image, volumes={"/staves": staves}, timeout=900)
def compose(ours: dict, paths: list[str], labels: list[str], width: int = 1600, h: int = 110) -> bytes:
    """The sheet as PNG: our local staves (bytes by label), then these volume files."""
    import io
    from PIL import Image
    staves.reload()
    ims = [Image.open(io.BytesIO(b)) for b in ours.values()] + [Image.open(p) for p in paths]
    buf = io.BytesIO()
    tile(ims, list(ours) + labels, width, h).save(buf, "PNG")
    return buf.getvalue()


@app.local_entrypoint()
def sheet(out: str = "", n: int = 24, seed: int = 1, keys: str = "", width: int = 1600, h: int = 110):
    """A contact sheet: n re-cropped OSSQ staves (random scores, or these
    keys) below our own training staves (dataL2 locally, dolores on the volume)."""
    import random
    ms = manifests.remote()
    rng = random.Random(seed)
    if keys:
        pick = [tuple(k.split("/")) for k in keys.split(",")]
    else:
        pick = [(k, rng.choice(ms[k]["written"])["name"]) for k in rng.sample(sorted(ms), min(n, len(ms)))]
    dol = listing.remote("/staves/public/dolores", "**/*.jpg", 6) if not keys else []
    local = sorted(Path.home().glob(".cache/manuscript-labeler/zeus/dataL2/*/*.jpg"))
    rng.shuffle(local)
    ours = {f"OURS dataL2 {f.parent.name}/{f.stem}": f.read_bytes() for f in (local[:6] if not keys else [])}
    paths = dol + [f"{OUT}/{k}/{nm}.jpg" for k, nm in pick]
    labels = [f"OURS dolores {Path(p).name}" for p in dol] + [f"OSSQ-period {k}/{nm}" for k, nm in pick]
    out = out or str(HERE / "period-sheet.png")
    Path(out).write_bytes(compose.remote(ours, paths, labels, width, h))
    print(out)


DUR = {"breve", "whole", "half", "quarter", "eighth", "16th", "32nd", "64th", "long"}


def measures(lmx: str) -> list[list[str]]:
    """Each measure's rhythm: its events' durations (dots, grace, rest), a
    chord's other heads left out."""
    out, ev, chord = [], None, False
    for t in lmx.split():
        if t == "measure":
            out.append([])
            ev = None
            continue
        if not out:
            out.append([])
        if t == "chord":
            chord = True
        elif t == "rest" or (len(t) == 2 and t[0] in "ABCDEFG" and t[1].isdigit()):
            ev = None if chord else ["r" if t == "rest" else "n"]
            if ev is not None:
                out[-1].append(ev)
            chord = False
        elif t in ("grace", "grace:slash") and out[-1] and ev is not None:
            ev.append("g")
        elif ev is not None and (t in DUR or t == "dot" or t == "rest:measure" or "in" in t and t[0].isdigit()):
            ev.append(t)
    return [[" ".join(e) for e in m] for m in out]


@app.local_entrypoint()
def check(per: int = 25, run: str = "D3S-h96", file: str = "reader.pt", suspect: float = 0.5):
    """Read `per` staves of every score (evenly spaced through it) with the
    reader; compare measure counts and leading rhythms with the labels."""
    ms = manifests.remote()
    sample = []
    for k in sorted(ms):
        w = ms[k]["written"]
        idx = sorted({round(i * (len(w) - 1) / max(1, per - 1)) for i in range(per)})
        sample += [f"{k}/{w[i]['name']}" for i in idx]
    write_list.remote("samples.ossq-period-check.txt", sample)
    labels = files.remote([f"{OUT}/{key}.lmx" for key in sample])
    reads = musvit.read_samples.remote(run, file, f"{OUT}/samples.ossq-period-check.txt")
    rows = []
    for key in sample:
        lab, got = labels[f"{OUT}/{key}.lmx"].decode().strip(), reads.get(key, "")
        a, b = measures(lab), measures(got)
        lead = 0
        for x, y in zip(a, b):
            if x != y:
                break
            lead += 1
        rows.append({"key": key, "label_measures": lab.split().count("measure"),
                     "read_measures": got.split().count("measure"), "leading_rhythm_match": lead, "read": got})
    per_score = {}
    for r in rows:
        k = r["key"].split("/")[0]
        d = per_score.setdefault(k, {"path": ms[k]["path"], "n": 0, "measure_count_differs": 0, "lead": 0,
                                     "measures": 0, "first_measure_rhythm_matches": 0})
        d["n"] += 1
        d["measure_count_differs"] += r["label_measures"] != r["read_measures"]
        d["lead"] += r["leading_rhythm_match"]
        d["measures"] += r["label_measures"]
        d["first_measure_rhythm_matches"] += r["leading_rhythm_match"] > 0
    for k, d in per_score.items():
        d["share_differs"] = round(d["measure_count_differs"] / d["n"], 2)
        d["lead_share"] = round(d["lead"] / max(1, d["measures"]), 2)
        d["suspect"] = d["share_differs"] >= suspect
    (HERE / "period-pairing.json").write_text(json.dumps({"per_score": per_score, "staves": rows}, indent=1))
    bad = sorted(k for k, d in per_score.items() if d["suspect"])
    for k, d in sorted(per_score.items(), key=lambda t: -t[1]["share_differs"]):
        print(f"{k:12} {d['share_differs']:.2f} differ  lead {d['lead_share']:.2f}  first {d['first_measure_rhythm_matches']}/{d['n']}  "
              f"{d['path'].split('/')[1][:60]}", flush=True)
    print("suspect:", bad, flush=True)


@app.local_entrypoint()
def clean(exclude: str = ""):
    """samples.ossq-period.txt (every staff re-cut) and samples.ossq-period-clean.txt
    (less these scores)."""
    bad = set(exclude.split(",")) - {""}
    ms = manifests.remote()
    every = [f"{k}/{g['name']}" for k in sorted(ms) for g in ms[k]["written"]]
    print("samples.ossq-period.txt", write_list.remote("samples.ossq-period.txt", every))
    keys = [f"{k}/{g['name']}" for k in sorted(ms) if k not in bad for g in ms[k]["written"]]
    print("samples.ossq-period-clean.txt", write_list.remote("samples.ossq-period-clean.txt", keys))
