# /// script
# requires-python = "==3.10.*"
# dependencies = [
#   "zeus @ git+https://github.com/OmniOMR/zeus.git@c8569eb1c8b5bb24511de6a5e53ef2450de6206c",
#   "tensorflow-macos==2.12.0; sys_platform == 'darwin' and platform_machine == 'arm64'",
#   "numpy", "pillow",
# ]
# [tool.uv]
# override-dependencies = ["tensorflow; sys_platform != 'darwin' or platform_machine != 'arm64'"]
# ///
"""Zeus models on the Dolores and OmniOMR test staves, scored as proto.score scores (symbol edits over reference length)."""
import io, json, time
from pathlib import Path
from PIL import Image
S = Path(__file__).parent / "bench"
M = Path.home() / ".cache/manuscript-labeler/models/zeus"

def edits(a, b):
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]

from zeus import InferenceOptions, Zeus
out = []
for name, path in (("stock Zeus (ayce-2026-08-03)", M / "ayce-2026-08-03.model"), ("Zeus J", M / "J-lr1e5-e8@2026-10-16")):
    model = Zeus.load(path)
    for test in ("dolores", "omniomr"):
        lines = (S / f"{test}-test.txt").read_text().split()
        imgs, refs = [], []
        for l in lines:
            p = S / test / l
            buf = io.BytesIO(); Image.open(p.with_suffix(".jpg")).convert("L").save(buf, "PNG"); imgs.append(buf.getvalue())
            refs.append(p.with_suffix(".lmx").read_text().split())
        t0 = time.time()
        got = [g.split() for g in model.predict(imgs, InferenceOptions(batch_size=8))]
        e = sum(edits(g, r) for g, r in zip(got, refs)); n = sum(len(r) for r in refs)
        cut = sum(edits(g[: 2 * len(r)], r) for g, r in zip(got, refs))
        ex = sum(g == r for g, r in zip(got, refs))
        out.append(f"{test} {name}: SER {e / n:.3f}, exact {ex}/{len(refs)}, SER cut at 2x {cut / n:.3f} ({time.time() - t0:.0f} s)")
        print(out[-1], flush=True)
        (S / f"{test}-{path.name}.json").write_text(json.dumps({l: " ".join(g) for l, g in zip(lines, got)}))
(S / "zeus-summary.txt").write_text("\n".join(out) + "\n")
