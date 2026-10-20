# /// script
# dependencies = ["pillow"]
# ///
"""Shrink pos_data staves to 256 px high in place, their places and staff space scaled with them."""
import json, sys
from pathlib import Path
from PIL import Image
for d in sys.argv[1:]:
    n = 0
    for f in Path(d).glob("*.pos.json"):
        p = json.loads(f.read_text())
        if p["h"] <= 256:
            continue
        k = 256 / p["h"]
        jpg = f.with_name(f.name[: -len(".pos.json")] + ".jpg")
        im = Image.open(jpg).convert("L")
        w = max(1, round(p["w"] * k))
        im.resize((w, 256), Image.LANCZOS).save(jpg, quality=92)
        p["targets"] = [[t, kind, round(x * w / p["w"], 1), round(y * k, 1)] for t, kind, x, y in p["targets"]]
        p["ss"] *= k
        if "lines" in p:
            p["lines"] = [round(r * k, 1) for r in p["lines"]]
        p["w"], p["h"] = w, 256
        f.write_text(json.dumps(p))
        n += 1
    print(d, n, "shrunk")
