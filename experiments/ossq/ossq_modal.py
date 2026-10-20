"""Rebuild OSSQ-OMR's scanned quartet staves on Modal CPUs (PLAN.md).

OSSQ-OMR (Kim, Liu, Valero-Mas, Jeong, ISMIR 2026; data CC0, code MIT) ships
no images yet. This rebuilds its scanned part images from what it does ship,
the way its pipeline (MALerLab/omr-data-preprocessor, "omrdp") builds them:

- the scans: IMSLP PDFs, at the direct URLs in ossq-omr's
  data/scores_w_url.yaml (no login), fetched once, one at a time, into the
  `ossq-raw` volume;
- the systems and staves: omrdp's own YOLO detectors (MALerLab/ls-yolo
  releases) and box merging, at the models and thresholds each score's
  sq<id>_yolo_infos.yaml records, on pages rendered at 300 dpi as omrdp does;
- the alignment, as omrdp's: on the pages sq<id>_scanned.csv's first line
  names, the boxes left after yolo_infos' ignores are paired in order with
  the encoding's systems (its system breaks were edited to match the scan);
  a score whose counts differ is skipped. Each system must have four staves,
  and where the csv's notes give every box's bar count, bar counts are
  checked too;
- the labels: each staff's music from the corrected sq<id>_cleaned.musicxml
  (ossq-omr omr-dev 7a17e45), sliced into systems and written with Zeus's LMX
  encoder at Zeus's pin, as our labels are: no stems; key and clef on every
  staff; time where the music has it. Staves with a token our reader's
  vocabulary lacks are left out (a mark is dropped instead), and counted.

Unlike omrdp, the staves are cut from the 300 dpi page, not from systems
shrunk to an 18 px staff, and saved 256 px high (grey JPEG) as our public
staves are. Each staff's id is omrdp's segment id (sq<id>:<page>:<system>:<part>)
written as sq<id>/<page>-<system>-<part>, so their splits apply as they are.

    modal run experiments/ossq/ossq_modal.py::fetch            # the scans, once (polite: one at a time)
    modal run experiments/ossq/ossq_modal.py::cut [--kind scanned|synthetic|manuscript] [--only sq7070781,...]
    modal run experiments/ossq/ossq_modal.py::lists            # samples.*.txt from the manifests

The synthetic renders (MuseScore 3.6.2 on the corrected .mscx, paired in
order as omrdp pairs them) and the three usable manuscripts (TEST ONLY:
paired in order only when the systems found with four staves are exactly
as many as the encoding's) are cut the same way.

Volumes: `ossq-raw` (/raw: pdfs/, logs) is this app's own; staves go to
`musvit-staves` (/staves) under ossq/ only.
"""

import io
import json
import re
import time
from pathlib import Path

import modal

OSSQ_SHA = "7a17e45cddc0b7064fc3a179b62caeb57595e993"   # ossq-omr omr-dev, camera-ready
OMRDP_SHA = "bdea0d1829c9db84480ebd2e0385f6f5fe324274"  # omr-data-preprocessor main, 2026-07-31
LMX_SHA = "87fca1c38bda83bc032596ab00af28412f92941d"    # Zeus's pin of OMR-Research/lmx
RAW = f"https://raw.githubusercontent.com/MALerLab/ossq-omr/{OSSQ_SHA}"
YOLO = {
    "ls-yolo-system-v2.0.0": "system-v2",
    "ls-yolo-system-v3.0.0": "system-v3",
    "ls-yolo-staff-height-v2.0.0": "staff-height-v2",
    "ls-yolo-staff-bbox-v1.0.1": "staff-bbox-v1",
}
HERE = Path(__file__).resolve().parent
VOCAB_FILE = Path.home() / ".cache/manuscript-labeler/models/musvit/musvit-D3@2026-10-18/vocab.json"
UA = "manuscript-labeler/0.1 (OSSQ-OMR rebuild for OMR research; one file at a time)"

app = modal.App("ossq-staves")
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "curl", "libgl1", "libglib2.0-0")
    .uv_pip_install("torch==2.10.0", "torchvision", index_url="https://download.pytorch.org/whl/cpu")
    .uv_pip_install("ultralytics==8.4.14", "opencv-python-headless", "pdfplumber==0.11.9", "pypdfium2==5.4.0",
                    "strictyaml", "requests", "pillow", "numpy", "tqdm",
                    f"linearized-musicxml @ git+https://github.com/OMR-Research/lmx.git@{LMX_SHA}")
    .run_commands(
        f"mkdir -p /opt/omrdp && curl -sfL https://codeload.github.com/MALerLab/omr-data-preprocessor/tar.gz/{OMRDP_SHA}"
        " | tar xz -C /opt/omrdp --strip-components 1",
        "mkdir -p /opt/ckpt && cd /opt/ckpt && " + " && ".join(
            f"curl -sfLO https://github.com/MALerLab/ls-yolo/releases/download/{tag}/{name}.pt"
            for name, tag in YOLO.items()),
        f"mkdir -p /opt/ossq && curl -sfL {RAW}/data/scores_w_url.yaml -o /opt/ossq/scores_w_url.yaml"
        f" && curl -sfL {RAW}/data/scanned_score_types.tsv -o /opt/ossq/scanned_score_types.tsv",
    )
    .env({"PYTHONPATH": "/opt/omrdp", "YOLO_CONFIG_DIR": "/tmp/yolo"})
    # MuseScore 3.6.2, which ossq-omr's README requires for its .mscx files (synthetic renders only)
    .apt_install("libnss3", "libasound2", "libxkbcommon0", "libxkbcommon-x11-0", "libfontconfig1", "libegl1",
                 "libdbus-1-3", "libxrender1", "libxi6", "libsm6", "libice6", "libxcomposite1", "libxcursor1",
                 "libxrandr2", "libxtst6", "libpulse0", "libjack0", "libportaudio2", "libsndfile1", "libxcb-icccm4",
                 "libxcb-image0", "libxcb-keysyms1", "libxcb-render-util0", "libxcb-xinerama0", "libxcb-xkb1",
                 "xvfb")
    .run_commands(
        "mkdir -p /opt/mscore && cd /opt/mscore && curl -sfLo ms.AppImage"
        " https://github.com/musescore/MuseScore/releases/download/v3.6.2/MuseScore-3.6.2.548021370-x86_64.AppImage"
        " && chmod +x ms.AppImage && ./ms.AppImage --appimage-extract > /dev/null && rm ms.AppImage")
    .add_local_file(VOCAB_FILE, "/opt/vocab.json")
)
raw = modal.Volume.from_name("ossq-raw", create_if_missing=True)
staves = modal.Volume.from_name("musvit-staves")


# ---------------------------------------------------------------- metadata

def scores() -> dict[str, dict]:
    """ossq-omr's score list with each scan's URL and type (-1 ignored, 0
    manuscript, 1 scanned, 1` / 1`` double column, 2 engraved, 3 part-books,
    4-7 one part)."""
    import csv
    import strictyaml
    data = strictyaml.load(Path("/opt/ossq/scores_w_url.yaml").read_text()).data
    types = {r["id"]: r["type"] for r in csv.DictReader(open("/opt/ossq/scanned_score_types.tsv"), delimiter="\t")}
    return {k: {**v, "type": types.get(k, "")} for k, v in data.items()}


def fetch_text(rel: str) -> str | None:
    import requests
    from urllib.parse import quote
    r = requests.get(f"{RAW}/{quote(rel)}", timeout=120)
    return r.text if r.status_code == 200 else None


# ---------------------------------------------------------------- the scans

@app.function(image=image, cpu=1, memory=1024, timeout=6 * 3600, volumes={"/raw": raw}, max_containers=1)
def fetch_pdfs(ids: list[str], delay: float = 15.0) -> dict[str, str]:
    """Each scan from IMSLP's direct URL, one at a time, `delay` s apart;
    stops after 3 refusals in a row rather than press on."""
    import requests
    meta = scores()
    out, refused = {}, 0
    (Path("/raw") / "pdfs").mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    s.headers["User-Agent"] = UA
    for k in ids:
        dest = Path("/raw/pdfs") / f"sq{k}.pdf"
        if dest.exists() and dest.read_bytes()[:4] == b"%PDF":
            out[k] = "have"
            continue
        url = meta[k].get("imslp_url")
        if not url:
            out[k] = "no url"
            continue
        try:
            r = s.get(url, timeout=600)
            ok = r.status_code == 200 and r.content[:4] == b"%PDF"
        except Exception as e:
            r, ok = None, False
            out[k] = f"error {type(e).__name__}"
        if ok:
            dest.write_bytes(r.content)
            out[k] = f"got {len(r.content) / 1e6:.1f} MB"
            refused = 0
            raw.commit()
        else:
            if r is not None:
                out[k] = f"refused {r.status_code} {r.headers.get('content-type')}"
            refused += 1
        print(k, out[k], flush=True)
        if refused >= 3:
            print("3 refusals in a row: stopping", flush=True)
            break
        time.sleep(delay)
    Path("/raw/fetch-log.json").write_text(json.dumps(out, indent=1))
    raw.commit()
    return out


# ---------------------------------------------------------------- labels

SOFT = re.compile(r"^(stem:.*|beam:continue|arpeggiate|staff:\d+|tremolo:unmeasured|staccatissimo|spiccato|breath-mark|caesura)$")


def system_labels(xml_text: str, vocab: set[str]):
    """[(bar count, [lmx or None per part], [why per part])] for every system
    of the score, in order, as our labels are written."""
    import xml.etree.ElementTree as ET
    from lmx.musicxml.slice_part_to_systems import slice_part_to_systems
    from lmx.tokenization.Encoder import Encoder
    root = ET.fromstring(xml_text)
    parts = root.findall("part")
    sliced = []
    for p in parts:
        sliced.append([s.part for page in slice_part_to_systems(p) for s in page.systems])
    n = {len(s) for s in sliced}
    if len(n) != 1:
        raise ValueError(f"parts have different system counts {sorted(n)}")
    out = []
    for k in range(n.pop()):
        bars = {len(sl[k].findall("measure")) for sl in sliced}
        lmxs, whys = [], []
        for sl in sliced:
            part = sl[k]
            for note in part.iter("note"):
                for st in note.findall("stem"):
                    note.remove(st)
            err = io.StringIO()
            enc = Encoder(errout=err, fail_on_unknown_tokens=False)
            try:
                enc.process_part(part)
            except Exception as e:
                lmxs.append(None)
                whys.append(f"encoder {type(e).__name__}: {str(e)[:60]}")
                continue
            missing = re.findall(r"Token '([^']+)' not in the vocabulary", err.getvalue())
            hard = [t for t in missing if not SOFT.match(t)]
            toks = enc.output_tokens
            if hard:
                lmxs.append(None)
                whys.append("lmx lacks " + hard[0])
                continue
            if "print-object:no" in toks:
                lmxs.append(None)
                whys.append("a hidden object")
                continue
            unknown = [t for t in toks if t not in vocab]
            hard = [t for t in unknown if not SOFT.match(t)]
            if hard:
                lmxs.append(None)
                whys.append("vocab lacks " + sorted(set(hard))[0])
                continue
            dropped = [t for t in missing if SOFT.match(t)] + unknown
            toks = [t for t in toks if t in vocab]
            if not any(re.match(r"^([A-G]\d)$", t) for t in toks):
                whys.append("only rests" + (f"; dropped {dropped}" if dropped else ""))
            else:
                whys.append(f"dropped {sorted(set(dropped))}" if dropped else "")
            lmxs.append(" ".join(toks))
        out.append((max(bars) if len(bars) == 1 else -1, lmxs, whys))
    return out


# ---------------------------------------------------------------- cutting

def yolo_boxes(model, imgs, with_class=False):
    """omrdp's box lists (lx ly rx ry conf, or cls lx ly rx ry conf) per image, sorted by y then x."""
    res = model(imgs, device="cpu", verbose=False)
    out = []
    for r in res:
        xy = r.boxes.xyxy.int().tolist()
        cf = r.boxes.conf.tolist()
        if with_class:
            cl = r.boxes.cls.tolist()
            bb = sorted([(c, *b, f) for b, c, f in zip(xy, cl, cf)], key=lambda x: (x[2], x[1]))
        else:
            bb = sorted([(*b, f) for b, f in zip(xy, cf)], key=lambda x: (x[1], x[0]))
        out.append(bb)
    return out


def merged(bb, conf, merge, with_class=False):
    """omrdp.utils.bbox.load_bboxs on these boxes (it reads them from a file)."""
    import tempfile
    from omrdp.utils.bbox import load_bboxs
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        for b in bb:
            f.write(" ".join(map(str, b)) + "\n")
    return load_bboxs(f.name, confidence_threshold=conf, merge_threshold=merge, with_class=with_class)


def parse_csv(text: str):
    """sq<id>_scanned.csv: its first line is the page range omrdp cuts
    ("6:8", ":", "2:71"); the rest are alignment notes in several forms."""
    lines = [l.strip() for l in text.splitlines()]
    st, ed = lines[0].split(":")
    rows = [[c.strip() for c in l.split(",") if c.strip()] for l in lines[1:] if l.strip()]
    return (int(st) if st else 1), (int(ed) if ed else None), rows


def csv_bars(rows, n_systems):
    """The bar count of each kept system, when the notes list every box as a
    bar count or x (ignored) and the counts are exactly n_systems; else None."""
    cells = [c for r in rows for c in r]
    if not cells or not all(c == "x" or c.isdigit() for c in cells):
        return None
    bars = [int(c) for c in cells if c != "x"]
    if len(bars) != n_systems or not any(len(r) > 1 for r in rows):
        return None
    return bars


def listed(v) -> set[str]:
    return set(v) if isinstance(v, list) else set()


MS_INFO = {  # omrdp's scanned defaults (ossq_step_001.sh); manuscripts have no yolo_infos
    "system": {"model": "ls-yolo-system-v3.0.0", "confidence_threshold": 0.30, "merge_threshold": 0.7},
    "staff_height": {"model": "ls-yolo-staff-height-v2.0.0", "target_height": 18},
    "staff_bbox": {"model": "ls-yolo-staff-bbox-v1.0.1", "confidence_threshold": 0.7, "merge_threshold": 0.7},
}
MSCORE = "/opt/mscore/squashfs-root/AppRun"


def render_synthetic(sqid: str, path: str) -> Path:
    """The score's own layout rendered by MuseScore 3.6.2 (as omrdp's
    convert_musescore_to_pdf, default style), kept in /raw/synth/."""
    import subprocess
    out = Path("/raw/synth") / f"{sqid}.pdf"
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    mscx = Path("/tmp") / f"{sqid}.mscx"
    mscx.write_text(fetch_text(f"scores/{path}/{sqid}.mscx"))
    # its AppImage has only Qt's xcb platform plugin, so it draws on a virtual X display
    r = subprocess.run(["xvfb-run", "-a", MSCORE, "-r", "300", "-o", str(out), str(mscx)], capture_output=True,
                       text=True, timeout=1800, env={"HOME": "/tmp", "PATH": "/usr/bin:/bin", "XDG_RUNTIME_DIR": "/tmp"})
    if not out.exists():
        raise RuntimeError(f"mscore failed {r.returncode}: {r.stderr[-400:]}")
    raw.commit()
    return out


@app.function(image=image, cpu=4, memory=8192, timeout=3 * 3600, max_containers=4,
              volumes={"/raw": raw, "/staves": staves})
def cut_score(kind: str, k: str) -> dict:
    """Every staff of one score, as images, labels and a manifest, under
    /staves/ossq/<kind>/sq<id>/. kind: scanned (the scan's pages in
    sq<id>_scanned.csv's range, paired in order as omrdp pairs them),
    synthetic (MuseScore's render of the corrected source, likewise), manuscript
    (the IMSLP scan, paired in order only if the systems found with four
    staves are exactly as many as the encoding's; TEST ONLY)."""
    import cv2
    import numpy as np
    import pdfplumber
    import strictyaml
    from ultralytics import YOLO as Y
    t0 = time.time()
    meta = scores()[k]
    sqid, path = f"sq{k}", meta["path"]
    stats = {"sqid": sqid, "kind": kind, "path": path, "type": meta["type"]}
    why = {}
    def count(key, n=1):
        why[key] = why.get(key, 0) + n

    xml_text = fetch_text(f"scores/{path}/{sqid}_cleaned.musicxml")
    if not xml_text:
        return {**stats, "error": "no cleaned musicxml"}
    vocab = set(json.loads(Path("/opt/vocab.json").read_text()))
    try:
        labels = system_labels(xml_text, vocab)
    except Exception as e:
        return {**stats, "error": f"labels: {type(e).__name__} {e}"}
    stats["encoding_systems"] = len(labels)

    rows, st, ed = None, 1, None
    if kind == "manuscript":
        info = MS_INFO
        pdf = Path("/raw/pdfs") / f"{sqid}.pdf"
    else:
        info_text = fetch_text(f"scores/{path}/images/{kind}/{sqid}_yolo_infos.yaml")
        if not info_text:
            return {**stats, "error": "no yolo_infos"}
        info = strictyaml.load(info_text).data
        if kind == "scanned":
            pdf = Path("/raw/pdfs") / f"{sqid}.pdf"
            csv_text = fetch_text(f"scores/{path}/{sqid}_scanned.csv")
            if not csv_text:
                return {**stats, "error": "no scanned csv"}
            st, ed, rows = parse_csv(csv_text)
        else:
            try:
                pdf = render_synthetic(sqid, path)
            except Exception as e:
                return {**stats, "error": f"render: {e}"[:500]}
    if not pdf.exists():
        return {**stats, "error": "no pdf"}
    sysi, hti, sti = info["system"], info["staff_height"], info["staff_bbox"]
    ignores = listed(sysi.get("ignores")) | listed(sti.get("ignores"))
    exceptions = listed(sysi.get("exceptions")) | listed(sti.get("exceptions"))
    m_sys = Y(f"/opt/ckpt/{sysi['model']}.pt")
    m_ht = Y(f"/opt/ckpt/{hti['model']}.pt")
    m_st = Y(f"/opt/ckpt/{sti['model']}.pt")
    target = float(hti.get("target_height") or 18)

    doc = pdfplumber.open(str(pdf))
    pages = list(range(st, min(ed or len(doc.pages), len(doc.pages)) + 1))

    def staves_of(page, box):
        """(staff px, [(cls, x0, y0, x1, y1) in page px] top to bottom) or a reason."""
        lx, ly, rx, ry = box
        crop = page[ly:ry, lx:rx]
        hb = yolo_boxes(m_ht, [crop[:, : crop.shape[1] // 2]])[0]
        if not hb:
            return "no staff height found"
        h = sum(b[3] - b[1] for b in hb) / len(hb)
        ratio = target / h
        small = cv2.resize(crop, (max(1, int(crop.shape[1] * ratio)), max(1, int(crop.shape[0] * ratio))),
                           interpolation=cv2.INTER_AREA)
        sb = merged(yolo_boxes(m_st, [small], with_class=True)[0], float(sti["confidence_threshold"]),
                    float(sti["merge_threshold"]), with_class=True)
        if len(sb) != 4:
            return f"{len(sb)} staves found, not 4"
        return h, [(int(cl), lx + int(a / ratio), ly + int(b / ratio), lx + round(c / ratio), ly + round(d / ratio))
                   for cl, a, b, c, d in sb]

    # 1. every system box on the pages in range, in order, less omrdp's ignores;
    #    paired with the encoding's systems in order, as omrdp pairs them
    found = []  # (pno, j, seg, encoding index, staves or reason)
    images = {}
    for pno in pages:
        pil = doc.pages[pno - 1].to_image(resolution=300).original.convert("RGB")
        page = np.asarray(pil)[:, :, ::-1].copy()  # BGR, as cv2.imread gives omrdp
        boxes = merged(yolo_boxes(m_sys, [page])[0], float(sysi["confidence_threshold"]), float(sysi["merge_threshold"]))
        kept = False
        for j, box in enumerate(boxes):
            seg = f"{sqid}:{pno:04d}:{j + 1:04d}"
            if seg in ignores:
                continue
            stv = staves_of(page, box)
            if kind == "manuscript" and isinstance(stv, str):
                count("manuscript box without four staves (not paired)")
                continue
            found.append((pno, j, seg, None, stv))
            kept = True
        if kept:
            images[pno] = cv2.cvtColor(page, cv2.COLOR_BGR2GRAY)
    stats["systems_found"] = len(found)
    if len(found) != len(labels):  # omrdp skips such a score too
        return {**stats, "error": f"{len(labels)} encoding systems against {len(found)} systems found"}
    found = [(pno, j, seg, n, stv) for n, (pno, j, seg, _, stv) in enumerate(found)]
    # The csv's rows are notes made while aligning (omrdp reads only its page range).
    # Where they list every box's bar count (or x), check each pairing's bar count.
    bars_noted = csv_bars(rows, len(labels)) if rows is not None else None
    stats["bar_check"] = bars_noted is not None
    if bars_noted:
        keep = []
        for f in found:
            if labels[f[3]][0] != bars_noted[f[3]]:
                count("bar count != csv note")
            else:
                keep.append(f)
        found = keep

    # 2. the staves of each paired system
    out_dir = Path("/staves/ossq") / kind / sqid
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for pno, j, seg, idx, stv in found:
        if seg in exceptions:
            count("system excepted by omrdp")
            continue
        if isinstance(stv, str):
            count(stv)
            continue
        bars, lmxs, whys = labels[idx]
        h, sb = stv
        if [c for c, *_ in sb] != [2, 2, 1, 0]:
            count("staff classes not vn vn va vc (kept)")
        grey = images[pno]
        for p, (cl, x0, y0, x1, y1) in enumerate(sb, 1):
            sid = f"{seg}:{p}"
            if sid in ignores or sid in exceptions:
                count("staff excepted by omrdp")
                continue
            if lmxs[p - 1] is None:
                count(whys[p - 1])
                continue
            x0, y0, x1, y1 = max(0, x0), max(0, y0), min(grey.shape[1], x1), min(grey.shape[0], y1)
            if y1 - y0 < 16 or x1 - x0 < 64:
                count("staff box too small")
                continue
            im = grey[y0:y1, x0:x1]
            im = cv2.resize(im, (max(1, round(im.shape[1] * 256 / im.shape[0])), 256), interpolation=cv2.INTER_AREA)
            name = f"{pno:04d}-{j + 1:04d}-{p}"
            cv2.imwrite(str(out_dir / f"{name}.jpg"), im, [cv2.IMWRITE_JPEG_QUALITY, 90])
            (out_dir / f"{name}.lmx").write_text(lmxs[p - 1] + "\n")
            manifest.append({"id": f"{kind}/{sqid}/{name}", "seg": sid, "page": pno, "box": [x0, y0, x1, y1],
                             "staff_px": round(h, 1), "cls": cl, "bars": bars, "note": whys[p - 1]})
            count("written" if not whys[p - 1] else "written, " + whys[p - 1].split(";")[0][:40])
    (out_dir / "manifest.json").write_text(json.dumps({**stats, "why": why, "staves": manifest}, indent=0))
    staves.commit()
    return {**stats, "why": why, "written": len(manifest), "seconds": round(time.time() - t0)}


# ---------------------------------------------------------------- entry points

def scanned_ids() -> list[str]:
    """The scores omrdp cuts from scans: those with a sq<id>_scanned.csv at
    OSSQ_SHA (96; listed from the repo's tree into scanned_ids.txt)."""
    return (HERE / "scanned_ids.txt").read_text().split()


MANUSCRIPTS = ["7313978", "7551068", "8818128", "7577795", "7588853", "7556360"]  # fetched
# Cut only these: Andrée, Maier, Mayer A. Hensel's scan is 1,000 px; Mayer E minor is
# a pencil draft laid out unlike the encoding; Mayer D's manuscript is a piano duet.
MANUSCRIPTS_CUT = ["7313978", "7551068", "8818128"]


@app.local_entrypoint()
def fetch(only: str = "", delay: float = 15.0):
    ids = only.split(",") if only else scanned_ids() + MANUSCRIPTS
    out = fetch_pdfs.remote(ids, delay)
    print(json.dumps(out, indent=1))


@app.local_entrypoint()
def cut(kind: str = "scanned", only: str = "", containers: int = 4):
    """kind: scanned (96 scores), synthetic (122), manuscript (3, TEST ONLY).
    containers: at most this many at once (4 at most: other runs need the quota)."""
    if only:
        ids = [s.removeprefix("sq") for s in only.split(",")]
    else:
        ids = {"scanned": scanned_ids(), "manuscript": MANUSCRIPTS_CUT,
               "synthetic": (HERE / "synthetic_ids.txt").read_text().split()}[kind]
    total, log = 0, []
    fn = cut_score.with_options(max_containers=min(4, containers))
    for r in fn.map([kind] * len(ids), ids, return_exceptions=True):
        if isinstance(r, Exception):
            print("FAILED", repr(r)[:300], flush=True)
            log.append({"error": repr(r)[:300]})
            continue
        total += r.get("written", 0)
        log.append(r)
        print(json.dumps(r), flush=True)
    logf = HERE / f"cut-{kind}.json"
    old = {r["sqid"]: r for r in json.loads(logf.read_text())} if logf.exists() else {}
    old.update({r["sqid"]: r for r in log if "sqid" in r})
    logf.write_text(json.dumps(sorted(old.values(), key=lambda r: r["sqid"]), indent=1))
    print(f"written {total} staves", flush=True)


@app.function(image=image, volumes={"/staves": staves}, timeout=1800)
def write_lists(splits: dict) -> dict:
    """From the manifests: samples.ossq-scanned.txt (every scanned staff),
    samples.ossq-synthetic.txt, samples.ossq-manuscripts-TEST.txt (never for
    training), and a test list of scanned staves for each of their
    score-level folds."""
    root = Path("/staves/ossq")
    def ids_of(kind):
        out = []
        for m in sorted(root.glob(f"{kind}/*/manifest.json")):
            out += [s["id"] for s in json.loads(m.read_text())["staves"]]
        return out
    counts = {}
    for kind, name in [("synthetic", "samples.ossq-synthetic.txt"), ("manuscript", "samples.ossq-manuscripts-TEST.txt")]:
        sel = ids_of(kind)
        if sel:
            (root / name).write_text("\n".join(sel) + "\n")
            counts[name] = len(sel)
    ids = ids_of("scanned")
    (root / "samples.ossq-scanned.txt").write_text("\n".join(ids) + "\n")
    counts["samples.ossq-scanned.txt"] = len(ids)
    for fold, works in splits.items():
        w = set(works["test_scanned"])
        sel = [i for i in ids if i.split("/")[1] in w]
        name = f"samples.ossq-scanned-{fold}-test.txt"
        (root / name).write_text("\n".join(sel) + "\n")
        counts[name] = len(sel)
    (root / "splits.json").write_text(json.dumps(splits, indent=1))
    staves.commit()
    segs = {kind: [i.split("/", 1)[1] for i in ids_of(kind)] for kind in ("scanned", "synthetic")}
    return {"counts": counts, "segs": segs}


@app.local_entrypoint()
def lists():
    splits = json.loads((HERE / "splits.json").read_text())
    r = write_lists.remote(splits)
    (HERE / "staff-ids.json").write_text(json.dumps(r["segs"]))
    print(json.dumps(r["counts"], indent=1))
