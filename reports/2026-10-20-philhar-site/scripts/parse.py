# /// script
# requires-python = ">=3.11"
# dependencies = ["beautifulsoup4"]
# ///
"""parse.py <pagesdir> <cdx200.txt> <out.json>: one entry per work set (h2) with its LilyPond zips."""
import sys, pathlib, re, json
from bs4 import BeautifulSoup
pages, cdxf, out = map(pathlib.Path, sys.argv[1:4])
arch = {}
for line in cdxf.read_text().splitlines():
    url, ts, st, mime, ln = line.split()[:5]
    p = re.sub(r"^https?://le-concert\.pagesperso-orange\.fr(:\d+)?/", "", url)
    if mime in ("application/zip", "application/x-zip-compressed", "application/octet-stream", "application/pdf"):
        arch.setdefault(p.lower(), (ts, mime, int(ln) if ln.isdigit() else None))
sets = []
for f in sorted(pages.glob("*.html")):
    s = BeautifulSoup(f.read_bytes(), "html.parser", from_encoding="latin1")
    h1 = s.find("h1")
    if not h1: continue
    comp = h1.get_text(" ", strip=True)
    body = s.body
    # walk the document in order, splitting at h2 with text
    cur = None
    for el in body.descendants:
        if getattr(el, "name", None) == "h2" and el.get_text(strip=True):
            cur = {"page": f.name, "composer": comp, "title": re.sub(r"\s+", " ", el.get_text(" ", strip=True)),
                   "text": "", "zips": [], "links": [], "pdfs": 0}
            sets.append(cur)
        elif cur is not None and getattr(el, "name", None) == "a" and el.get("href"):
            h = el["href"]
            if h.lower().endswith(".zip"):
                low = h.lower()
                kind = "parts-pdf" if re.search(r"parti|parts|pdf-", low) and "lily" not in low and "lys" not in low else "lilypond"
                a = arch.get(low)
                cur["zips"].append({"href": h, "kind": kind, "archived": a[0] if a else None, "bytes": a[2] if a else None})
            elif h.lower().endswith(".pdf"):
                cur["pdfs"] += 1
            elif h.startswith("http") and "lilypond.org" not in h and "creativecommons" not in h:
                if h not in cur["links"]: cur["links"].append(h)
        elif cur is not None and isinstance(el, str):
            cur["text"] += el
    for c in sets:
        if c["page"] == f.name:
            t = re.sub(r"\s+", " ", c["text"]).strip()
            t = t.split('Editions "Le Concert"')[0]
            c["text"] = t
json.dump(sets, out.open("w"), ensure_ascii=False, indent=1)
n_ly = sum(1 for c in sets for z in c["zips"] if z["kind"] == "lilypond")
n_ar = sum(1 for c in sets for z in c["zips"] if z["kind"] == "lilypond" and z["archived"])
print(len(sets), "sets;", n_ly, "lilypond zips;", n_ar, "archived")
for c in sets:
    lz = [z for z in c["zips"] if z["kind"] == "lilypond"]
    print(f'{c["page"]:20} {len(lz):2} ly, {sum(1 for z in lz if z["archived"]):2} arch | {c["title"][:70]}')
