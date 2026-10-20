"""Fetch Dolores's staff-level symbol annotations (compacted), the systems' semantic links and the pages' metadata
from the MusiCorpus zip by range requests."""
import json, re, sys, os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from remotezip import RemoteZip
url = "https://lindat.mff.cuni.cz/repository/server/api/core/bitstreams/fdf9ba56-1854-45fc-a8d2-311dfb3ad8c3/content"
out = Path(sys.argv[1]); listing = sys.argv[2]
names = []
for line in open(listing):
    f = line.split("\t")[0]
    if re.search(r"CVC\.Dolores/[^/]+/(Staves/\d+/coco-object-detection\.json|Systems/\d+/coco-to-semantic\.json|metadata\.json)$", f):
        dst = out / (f.split("CVC.Dolores/")[1])
        if not dst.exists():
            names.append(f)
print(len(names), "to fetch", flush=True)

def centroid(poly):
    xs, ys = poly[0::2], poly[1::2]
    a = cx = cy = 0.0
    for i in range(len(xs)):
        j = (i + 1) % len(xs)
        c = xs[i] * ys[j] - xs[j] * ys[i]
        a += c; cx += (xs[i] + xs[j]) * c; cy += (ys[i] + ys[j]) * c
    if abs(a) < 1e-6:
        return sum(xs) / len(xs), sum(ys) / len(ys)
    return cx / (3 * a), cy / (3 * a)

def work(chunk):
    import time
    z = RemoteZip(url)
    for f in chunk:
            dst = out / (f.split("CVC.Dolores/")[1])
            dst.parent.mkdir(parents=True, exist_ok=True)
            for attempt in range(8):
                try:
                    b = z.read(f)
                    break
                except Exception:
                    time.sleep(10 * (attempt + 1))
                    try:
                        z = RemoteZip(url)
                    except Exception:
                        pass
            else:
                continue
            if f.endswith("coco-object-detection.json"):
                d = json.loads(b)
                cats = {c["id"]: c["name"] for c in d["categories"]}
                im = d["images"][0]
                anns = []
                for a in d["annotations"]:
                    seg = a.get("segmentation") or []
                    poly = max(seg, key=len) if seg and isinstance(seg, list) and isinstance(seg[0], list) else None
                    cx, cy = centroid(poly) if poly and len(poly) >= 6 else (a["bbox"][0] + a["bbox"][2] / 2, a["bbox"][1] + a["bbox"][3] / 2)
                    anns.append([a["id"], cats[a["category_id"]], a["bbox"], round(cx, 1), round(cy, 1), poly])
                dst.write_text(json.dumps({"file": im["file_name"], "w": im["width"], "h": im["height"], "anns": anns}))
            else:
                dst.write_bytes(b)

k = int(sys.argv[3]) if len(sys.argv) > 3 else 6
chunks = [names[i::k] for i in range(k)]
with ThreadPoolExecutor(k) as ex:
    list(ex.map(work, chunks))
print("done", flush=True)
