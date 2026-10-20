# /// script
# requires-python = ">=3.11"
# dependencies = ["torch", "transformers", "peft", "pillow", "numpy"]
# ///
"""Time a MuSViT reader on the Mac on the clean test's staves, against its Modal readings.
    uv run bench.py RUN FILE [--device mps] [--n 64] [--bs 8]"""
import argparse, hashlib, io, json, pickle, sys, time
from pathlib import Path
from PIL import Image
LAB = Path("/Users/jsundram/Dropbox/Code/manuscript-labeler")
sys.path[:0] = [str(LAB / "experiments/zeus"), str(LAB / "experiments/musvit")]
S = Path(__file__).parent
E = Path.home() / "Dropbox/Code/boccherini-opus-48"

def crops():
    f = S / "bench-crops.pkl"
    if f.exists():
        return pickle.loads(f.read_bytes())
    import compare
    pdf = next(E.glob("sources/*/D-B_KHM-603.pdf"))
    export = json.loads(pdf.with_name(pdf.stem + ".bars.json").read_text())
    sids = list(dict.fromkeys(b["system"] for b in export["bars"] if b["part"] in ("vn1", "vn2", "va", "vc") and b["movement"] == "I"))
    out, page = {}, (None, None)
    for sid in sids:
        s = export["systems"][sid]
        if page[0] != s["page"]:
            page = (s["page"], compare.page_image(pdf, s["page"]))
        png = compare.staff_crop(page[1], s)
        buf = io.BytesIO()
        Image.open(io.BytesIO(png)).convert("L").save(buf, "JPEG", quality=95)
        out[f"{sid}:{hashlib.sha1(png).hexdigest()[:10]}"] = buf.getvalue()
    f.write_bytes(pickle.dumps(out))
    return out

ap = argparse.ArgumentParser()
ap.add_argument("run"); ap.add_argument("file")
ap.add_argument("--device", default="mps"); ap.add_argument("--n", type=int, default=0); ap.add_argument("--bs", type=int, default=8)
a = ap.parse_args()
import torch, proto
c = crops()
keys = sorted(c)[: a.n or None]
want = json.loads((LAB / f"experiments/zeus/answers/D-B_KHM-603-musvit-{a.run}-{Path(a.file).stem}.json").read_text())
t0 = time.time()
got = proto.read_crops(a.run, a.file, {k: c[k] for k in keys}, a.device, a.bs)
secs = time.time() - t0
same = sum(got[k] == want.get(k) for k in keys)
toks = sum(len(got[k].split()) for k in keys)
print(f"{a.device} bs {a.bs}: {len(keys)} staves in {secs:.1f} s ({secs / len(keys):.2f} s a staff, {toks / secs:.0f} tokens/s); "
      f"same as Modal {same}/{len(keys)}")
