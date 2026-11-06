"""The page-omr test's pages: those of the two held-out sets (KHM 603 I, the
clean test; RES 507 (16) Op48-4 I) whose every staff is a held-out staff.
Per page a folder: page.png (the labeler's render), truth.lmx (its staves'
labels, in page order) and D6's readings of the same staves (D6.lmx, and
D6-key.lmx, read with the key given).

    uv run --with numpy --with pillow python pages.py OUT
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "experiments/zeus"))
import compare  # noqa: E402
from PIL import Image  # noqa: E402

E = Path.home() / "Dropbox/Code/boccherini-opus-48"
Z = Path.home() / ".cache/manuscript-labeler/zeus"
A = ROOT / "experiments/zeus/answers"
SETS = {"D-B_KHM-603": Z / "test-clean/samples.D-B_KHM-603-I.txt", "F-Po_RES-507-16": Z / "dataL4/samples.F-Po_RES-507-16-I.txt"}
READERS = {"D-B_KHM-603": {"D6": "D6-A-mps"}, "F-Po_RES-507-16": {"D6": "D6-A-mps", "D6-key": "D6-A-mps-key"}}
OUT = Path(sys.argv[1])
for src, samples in SETS.items():
    staves = [samples.parent / s for s in samples.read_text().split()]
    pdf = next(E.glob(f"sources/*/{src}.pdf"))
    export = json.loads(pdf.with_name(pdf.stem + ".bars.json").read_text())
    pages: dict[int, int] = {}
    for s in export["systems"].values():
        pages[s["page"]] = pages.get(s["page"], 0) + 1
    for page, n in sorted(pages.items()):
        mine = sorted((s for s in staves if s.name.startswith(f"p{page}s")), key=lambda s: int(s.name.split("s")[1]))
        if not mine or len(mine) != n:
            continue
        d = OUT / f"{src}-p{page}"
        d.mkdir(parents=True, exist_ok=True)
        compare.page_image(pdf, page)  # renders it
        Image.open(compare.render_dir(pdf) / f"p{page:03d}.png").convert("RGB").save(d / "page.png")
        (d / "truth.lmx").write_text(" ".join(s.with_suffix(".lmx").read_text().strip() for s in mine))
        for name, run in READERS[src].items():
            cache = {k.split(":")[0]: v for k, v in json.loads((A / f"{src}-musvit-{run}.json").read_text()).items()}
            (d / f"{name}.lmx").write_text(" ".join(cache[s.name] for s in mine))
        print(src, page, len(mine), "staves")
