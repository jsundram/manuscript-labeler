# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow"]
# ///
"""Contact sheets of bars, for looking at the print: each row a detected
staff of BA 2676 (as autodetect found it), captioned.

    uv run experiments/print-omr/crops.py OUT.png part:page:staff:caption ...
    uv run experiments/print-omr/crops.py OUT.png --rows rows.json    [{"part","page","staff","caption"}]
"""

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ZEUS = Path(__file__).resolve().parent.parent / "zeus"
PAGES = Path.home() / "Data/manuscript-labeler/experiments/print-omr/pages"


def staff_image(part: str, page: int, staff: int, width: int = 1800) -> Image.Image:
    auto = json.loads((ZEUS / "auto" / f"BA2676-{part}.json").read_text())
    s = sorted(auto["pages"][str(page)]["systems"], key=lambda s: s["top"])[staff]
    im = Image.open(PAGES / part / f"p-{page:02d}.png").convert("L")
    W, H = im.size
    h = s["bottom"] - s["top"]
    box = (int(max(0, s["left"] - 0.01) * W), int(max(0, s["top"] - 0.9 * h) * H),
           int(min(1, s["right"] + 0.01) * W), int(min(1, s["bottom"] + 0.9 * h) * H))
    c = im.crop(box)
    return c.resize((width, int(c.height * width / c.width)))


def sheet(rows: list[dict], out: Path, width: int = 1800):
    ims = []
    font = ImageFont.load_default(size=22)
    for r in rows:
        st = staff_image(r["part"], int(r["page"]), int(r["staff"]), width)
        cap = r.get("caption", "")
        lines = [cap[i:i + 150] for i in range(0, len(cap), 150)] or [""]
        tile = Image.new("L", (width, st.height + 28 * len(lines) + 6), 255)
        d = ImageDraw.Draw(tile)
        for k, line in enumerate(lines):
            d.text((6, 4 + 28 * k), line, fill=0, font=font)
        tile.paste(st, (0, 28 * len(lines) + 6))
        ims.append(tile)
    H = sum(i.height for i in ims) + 8 * len(ims)
    page = Image.new("L", (width, H), 200)
    y = 0
    for i in ims:
        page.paste(i, (0, y))
        y += i.height + 8
    page.save(out)


def main():
    out = Path(sys.argv[1])
    if sys.argv[2] == "--rows":
        rows = json.loads(Path(sys.argv[3]).read_text())
    else:
        rows = []
        for a in sys.argv[2:]:
            part, page, staff, *cap = a.split(":", 3)
            rows.append({"part": part, "page": page, "staff": staff, "caption": cap[0] if cap else f"{part} p{page} staff {staff}"})
    sheet(rows, out)


if __name__ == "__main__":
    main()
