# /// script
# dependencies = ["pypdf"]
# ///
"""Split two-page openings into single pages (CropBox halves): left then right, per opening."""
import sys
from pypdf import PdfReader, PdfWriter
src, dest, first, last = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
r = PdfReader(src); w = PdfWriter()
for n in range(first, last + 1):
    for half in (0, 1):
        w.add_page(r.pages[n - 1])
        page = w.pages[-1]
        x0, y0, x1, y1 = map(float, r.pages[n - 1].mediabox)
        mid = (x0 + x1) / 2
        box = (x0, y0, mid, y1) if half == 0 else (mid, y0, x1, y1)
        page.mediabox.lower_left, page.mediabox.upper_right = box[:2], box[2:]
        page.cropbox.lower_left, page.cropbox.upper_right = box[:2], box[2:]
w.write(dest)
print("wrote", dest, len(w.pages), "pages")
