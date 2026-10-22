# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "img2pdf", "pypdf"]
# ///
"""The manuscript scans for Philhar's kept string works, one PDF per source.

    uv run experiments/philhar-mss/fetch_scans.py [~/Data/manuscript-labeler/philhar-mss] [source ...]

Each source goes to <root>/<siglum_shelfmark>/<siglum_shelfmark>.pdf with a
SOURCE.json beside it (where from, licence, pages, SHA-256 of the PDF and of
every file it was made from). Downloads go through a cache in $TMPDIR, so a
rerun fetches nothing twice. At most one request every 1.2 s per host.

- SBB Berlin and SLUB Dresden: IIIF manifests, full-size JPEGs, packed
  losslessly with img2pdf.
- Sibley (UR Research): the three "(manuscript)" part PDFs, joined in part
  order. The "(print)" files in the same record are a bound-with print
  (G. 89-94) and are left out, as are the colour covers.
- Montecassino: Internet Culturale's page images for folios 46v-88r
  (trios VII-XII = G. 83-88), the largest size it serves (about 650 x 770).
- IMSLP (Giardini only; the library is not named): the subscriber's session
  in .imslp-cookies.txt, passed to curl and never read here. A response that
  isn't a PDF stops the run (IMSLP's captcha); nothing works around it.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import img2pdf
import requests
from pypdf import PdfReader, PdfWriter

REPO = Path(__file__).resolve().parents[2]
COOKIES = REPO / ".imslp-cookies.txt"
CACHE = Path(os.environ.get("TMPDIR", "/tmp")) / "philhar-mss-cache"
UA = "manuscript-labeler/0.1 (research on 18th-c. string parts; 1 request/s)"
PDM = "Public Domain Mark 1.0"

SBB_TERMS = ("Not stated in the IIIF manifest or METS (owner: SBB-PK). SBB's terms of use put its digitised public-domain holdings under the Public Domain Mark 1.0; not confirmed for this item. Attribute: Staatsbibliothek zu Berlin - PK")

SOURCES = {
    "D-B_Mus.ms.2861": dict(
        kind="iiif", manifest="https://content.staatsbibliothek-berlin.de/dc/PPN626958725/manifest",
        work="Campioni, 6 Duos op. 7 (vl, vc)", library="Staatsbibliothek zu Berlin",
        landing="https://resolver.staatsbibliothek-berlin.de/SBB00001DA400000000",
        rism="452007625", date="ca. 1780", hand="not named in RISM or SBB", licence=SBB_TERMS),
    **{f"D-B_KHM-{k}": dict(
        kind="iiif", manifest=f"https://content.staatsbibliothek-berlin.de/dc/{ppn}/manifest",
        work=f"Boccherini, Trio {g} (op. 4) (2 vl, vc)", library="Staatsbibliothek zu Berlin",
        landing=f"https://resolver.staatsbibliothek-berlin.de/{res}",
        rism=rism, date="ca. 1775-1800", hand="Copyist Schober (RISM); the KHM 577 Op. 32 hand",
        licence=SBB_TERMS)
        for k, g, ppn, res, rism in [
            (620, "G. 87", "PPN1672119073", "SBB000291F800000000", "1001082801"),
            (621, "G. 88", "PPN1672119405", "SBB000291F900000000", "1001082803"),
            (622, "G. 85", "PPN1672119677", "SBB000291FA00000000", "1001082805"),
            (623, "G. 83", "PPN1672120217", "SBB000291FB00000000", "1001082806"),
            (624, "G. 86", "PPN1672120462", "SBB000291FC00000000", "1001082808")]},
    "D-Dl_Mus.3403-P-513": dict(
        kind="iiif", manifest="https://iiif.slub-dresden.de/iiif/2/398103402/manifest.json",
        image_size="original",
        work="M. Haydn, Quintet in F, MH 411 (2 vl, 2 va, vc)", library="SLUB Dresden",
        landing="https://digital.slub-dresden.de/id398103402", rism="210044350",
        date="ca. 1770-1800 (SLUB: 1799)", hand="not named; a Salzburg copy (title: 'von Robinig', later 'Weizner')",
        licence=f"{PDM} (SLUB's manifest: Rechteinformationen)"),
    "US-R_M351.B664M": dict(
        kind="pdfs", files=[
            ("vn1", "https://urresearch.rochester.edu/fileDownloadForInstitutionalItem.action?itemId=11019&itemFileId=25038"),
            ("vn2", "https://urresearch.rochester.edu/fileDownloadForInstitutionalItem.action?itemId=11019&itemFileId=25043"),
            ("vc", "https://urresearch.rochester.edu/fileDownloadForInstitutionalItem.action?itemId=11019&itemFileId=25046")],
        work="Boccherini, 6 Trios op. 4, G. 83-88 (2 vl, vc)", library="Sibley Music Library, Eastman School (UR Research)",
        landing="http://hdl.handle.net/1802/11394", rism="130195",
        date="RISM: 1766 (1766p); Sibley: ca. 1775", hand="unknown copyist (Sibley)",
        licence="Public domain (UR Research: 'This item is in the public domain')"),
    "I-MC_1-C-7": dict(
        kind="ic", ic_id="oai:www.internetculturale.sbn.it/Teca:20:NT0000:FR0084-01C07_A-W",
        folios=("46v", "88r"),
        work="Boccherini, Trios G. 83-88 as trios VII-XII of 23 (score)",
        library="Biblioteca statale del Monumento nazionale di Montecassino (Internet Culturale)",
        landing="http://www.internetculturale.it/opencms/opencms/it/viewItemMag.jsp?id=oai%3Awww.internetculturale.sbn.it%2FTeca%3A20%3ANT0000%3AFR0084-01C07_A-W",
        rism="852015740 (set); 852015747-852015752 (1-C-7 g-l)", date="1750-1799 (second half of the 18th c.)",
        hand="not named", licence="Internet Culturale (MiC/ICCU) terms: free for study and research; "
        "reproduction for other uses needs the library's permission. IMSLP lists the same scans as public domain"),
    "unknown_IMSLP-PMLP122408": dict(
        kind="imslp", files=[("parts", "https://imslp.org/images/3/3a/PMLP122408-Giardini_Duetto_a_Violino_e_Violoncello.pdf",
                              "a355732ff3bb6d0510a108beb2d85f2e0bfaa81e")],
        work="Giardini, Duet in F (vl, vc)", library="not named (IMSLP upload by Zelenka, 2010)",
        landing="https://imslp.org/wiki/Duet_for_Violin_and_Cello_in_F_major_(Giardini,_Felice)",
        rism="none found (I-Gl M. (3) 22.7 has a different title)", date="not given", hand="not named",
        licence="Public domain per IMSLP; downloaded with a subscriber's session"),
}

_last: dict[str, float] = {}
S = requests.Session()
S.headers["User-Agent"] = UA


def polite(url: str):
    host = re.match(r"https?://([^/]+)", url)[1]
    wait = 1.2 - (time.time() - _last.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    _last[host] = time.time()


def cached(url: str, name: str) -> Path:
    f = CACHE / name
    if f.exists() and f.stat().st_size:
        return f
    f.parent.mkdir(parents=True, exist_ok=True)
    polite(url)
    for attempt in range(3):
        r = S.get(url, timeout=180)
        if r.status_code == 200:
            break
        time.sleep(5 * (attempt + 1))
    r.raise_for_status()
    f.write_bytes(r.content)
    return f


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def iiif(name: str, src: dict) -> tuple[list[Path], list[str], dict]:
    m = json.loads(cached(src["manifest"], f"{name}/manifest.json").read_text())
    imgs, labels = [], []
    for i, c in enumerate(m["sequences"][0]["canvases"], 1):
        svc = c["images"][0]["resource"]["service"]["@id"]
        if src.get("image_size") == "original":          # SLUB: the .medium.jpg derivative -> .original.jpg
            svc = svc.replace(".medium.jpg", ".original.jpg")
        url = f"{svc}/full/full/0/default.jpg"
        imgs.append(cached(url, f"{name}/{i:04d}.jpg"))
        labels.append(str(c.get("label", i)))
    meta = {"manifest": src["manifest"], "canvases": len(imgs),
            "structures": [s.get("label") for s in m.get("structures", [])]}
    return imgs, labels, meta


def ic(name: str, src: dict) -> tuple[list[Path], list[str], dict]:
    url = ("https://www.internetculturale.it/jmms/magparser?id=" + requests.utils.quote(src["ic_id"], safe="")
           + "&teca=MagTeca+-+ICCU&mode=all&fulltext=0")
    xml = cached(url, f"{name}/mag.xml").read_text()
    pages = re.findall(r'<page [^>]*?idx="(\d+)"\s+name="([^"]*)"\s+src="([^"]*)"', xml, re.S)
    names = [n for _, n, _ in pages]
    a, b = (f"c. {f[:-1]} {f[-1]}" for f in src["folios"])
    lo, hi = names.index(a), names.index(b)
    imgs, labels = [], []
    for idx, n, s in pages[lo:hi + 1]:
        imgs.append(cached("https://www.internetculturale.it/jmms/" + s, f"{name}/{int(idx):04d}.jpg"))
        labels.append(n)
    return imgs, labels, {"mag": url, "pages_in_volume": len(pages), "range": [a, b]}


def imslp_get(url: str, want_sha1: str, name: str) -> Path:
    f = CACHE / name
    if not (f.exists() and f.read_bytes()[:5] == b"%PDF-"):
        f.parent.mkdir(parents=True, exist_ok=True)
        polite(url)
        subprocess.run(["curl", "-s", "-L", "-b", str(COOKIES), "-A", UA, "-o", str(f), url], check=True)
    if f.read_bytes()[:5] != b"%PDF-":
        sys.exit(f"IMSLP returned something other than a PDF for {url} (captcha?). Stopping.")
    if want_sha1 and hashlib.sha1(f.read_bytes()).hexdigest() != want_sha1:
        sys.exit(f"SHA-1 mismatch for {url}")
    return f


def main():
    args = sys.argv[1:]
    root = Path(args.pop(0) if args and "/" in args[0] else "~/Data/manuscript-labeler/philhar-mss").expanduser()
    for name, src in SOURCES.items():
        if args and name not in args:
            continue
        out = root / name
        out.mkdir(parents=True, exist_ok=True)
        pdf = out / f"{name}.pdf"
        inputs, extra = [], {}
        if src["kind"] in ("iiif", "ic"):
            imgs, labels, extra = (iiif if src["kind"] == "iiif" else ic)(name, src)
            pdf.write_bytes(img2pdf.convert([str(p) for p in imgs]))
            inputs = [{"page": i, "label": l, "sha256": sha(p)} for i, (p, l) in enumerate(zip(imgs, labels), 1)]
        else:
            w = PdfWriter()
            for part, url, *rest in src["files"]:
                f = (imslp_get(url, rest[0], f"{name}/{part}.pdf") if src["kind"] == "imslp"
                     else cached(url, f"{name}/{part}.pdf"))
                if f.read_bytes()[:5] != b"%PDF-":
                    sys.exit(f"not a PDF: {url}")
                start = len(w.pages)
                for page in PdfReader(f).pages:
                    w.add_page(page)
                inputs.append({"part": part, "url": url, "sha256": sha(f), "pages": [start + 1, len(w.pages)]})
            with open(pdf, "wb") as fh:
                w.write(fh)
        n = len(PdfReader(pdf).pages)
        info = {k: v for k, v in src.items() if k not in ("files",)}
        info.update(source=name, pdf=pdf.name, pages=n, bytes=pdf.stat().st_size, sha256=sha(pdf),
                    fetched=time.strftime("%Y-%m-%d"), made_from=inputs, **extra)
        (out / "SOURCE.json").write_text(json.dumps(info, indent=1, ensure_ascii=False) + "\n")
        print(f"{name:28s} {n:4d} pages {pdf.stat().st_size / 1e6:7.1f} MB", flush=True)


if __name__ == "__main__":
    main()
