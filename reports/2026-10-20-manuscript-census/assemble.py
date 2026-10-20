"""Build census.md and census.json from inventory.json and pages.jsonl.

    python3 assemble.py
"""
import collections, json, re, statistics
from pathlib import Path

S = Path(__file__).resolve().parent
ARCH = Path.home() / "Dropbox/Code/boccherini-sources"
DIG = ARCH / "digitizations"
CACHE = ARCH / ".rism-cache"

OPUS = {}
for o in json.loads((ARCH / "opera.json").read_text()):
    for q in o["quartets"]:
        OPUS[str(q["gerard"])] = (o["opus"], q["number"])

# which items have an encoding, and of what kind
DATAM = {"G159/450200974_D-Eu", "G160/450200971_D-Eu", "G161/450200976_D-Eu", "G162/450200978_D-Eu",
         "G163/450200977_D-Eu", "G164/450200972_D-Eu", "G162/550503024_CZ-Pu",
         "G183/463056300_D-B", "G184/463056400_D-B", "G185/463056500_D-B", "G186/463056600_D-B",
         "G187/463056700_D-B", "G188/463056800_D-B", "G184_185_186_188/btv1b52514840q",
         "G201-206/463057700_D-B", "G207/1001161096_D-B", "G208/1001161550_D-B", "G209/1001161569_D-B",
         "G210/1001161583_D-B", "G211/1001161590_D-B", "G212/1001161668_D-B", "G207-212/btv1b52502470f"}
DATAT = {"G183/E-Mc_1-7040-188bis", "G184/E-Mc_1-7040-188", "G185/E-Mc_1-7040-187",
         "G186/E-Mc_1-7040-185", "G188/E-Mc_1-7040-186bis"}
OSSQ = {"G213/463058700_D-B"}
PHILHAR = set(range(159, 213))  # Philhar / IMSLP LilyPond in boccherini-quartet-data/lilypond

ENC_LABEL = {"dataM": "dataM", "dataT": "dataT (Madrid test set)", "OSSQ": "OSSQ",
             "LilyPond, unpaired": "Philhar LilyPond exists, not paired", "none": "none"}

CAL_DARK, CAL_SAT = -1, 0.02  # the black card is not black enough; its colour patches are what show
SKIP_FILES = {"550503024_CZ-Pu.pdf", "CZ-Pu_59_R_23.cover.pdf", "CZ-Pu_59_R_23.title.pdf",
              "CZ-Pu_59_R_23.violin1.pdf", "CZ-Pu_59_R_23.violin2.pdf", "CZ-Pu_59_R_23.viola.pdf",
              "CZ-Pu_59_R_23.cello.pdf"}
NOTES = {
    "G162/550503024_CZ-Pu": "Counted once from CZ-Pu_59_R_23.pdf; 550503024_CZ-Pu.pdf is the same 20 pages, and the cover/title/part PDFs split the same pages.",
    "G184_185_186_188/btv1b52514840q": "Four part files: vc (Gallica) + vn1, vn2, va from an earlier pass.",
    "G250-255/US-Wc_M452-A2-B68-op54": "Not in opera.json; title says 'Tre Quartetti'; G 250-255 is the folder's name, unverified. A Violino Primo part-book.",
    "G159/btv1b10863131t": "19th-century copy; a full score.",
    "G168/btv1b10076417z": "19th-century copy; a full score.",
    "G202_204/225003122_D-LEm": "Full score.",
    "G189-194/btv1b10537292r": "Full score; pairing was tried (29 of 468 staves kept), not in dataM.",
    "G165/650004090_A-ST": "Only one page scanned (vlc f. 1r): a title page with a one-staff incipit, so no music staves counted.",
    "G159/PPN1935497081_D-B": "Shelfmark SA 3364 per the SBB title; not in RISM.",
}
EXCLUDED = {
    "G159-164/190027176_S-Skma": "catalogued as a manuscript, but it is the Hummel print (archive correction)",
    "found/BnF/btv1b7400136t": "marked not-a-quartet",
}


# Pages checked by eye where the counter was wrong (wrong staff spacing, title pages
# drawn on ruled paper, blank ruled pages read as music): {folder/file#page: staves}
PAGE_FIX = {
    "G162/550503024_CZ-Pu/CZ-Pu_59_R_23.pdf#3": 0, "G162/550503024_CZ-Pu/CZ-Pu_59_R_23.pdf#6": 7,
    "G165/650004090_A-ST/650004090_A-ST.pdf#1": 0, "G167/650004089_A-ST/650004089_A-ST.pdf#3": 8,
    "G167/650004089_A-ST/650004089_A-ST.pdf#4": 0,
    "G183/E-Mc_1-7040-188bis/E-Mc_1-7040-188bis.pdf#5": 6, "G183/E-Mc_1-7040-188bis/E-Mc_1-7040-188bis.pdf#7": 0,
    "G184/E-Mc_1-7040-188/E-Mc_1-7040-188.pdf#2": 10, "G184/E-Mc_1-7040-188/E-Mc_1-7040-188.pdf#27": 6,
    "G185/E-Mc_1-7040-187/E-Mc_1-7040-187.pdf#3": 4,
    "G184_185_186_188/btv1b52514840q/btv1b52514840q.pdf#1": 0, "G184_185_186_188/btv1b52514840q/btv1b52514840q.pdf#25": 0,
    "G184_185_186_188/btv1b52514840q/Vmb-Ms-153.violin2.pdf#16": 7, "G184_185_186_188/btv1b52514840q/Vmb-Ms-153.violin2.pdf#34": 8,
    "G184_185_186_188/btv1b52514840q/Vmb-Ms-153.violin2.pdf#38": 0, "G184_185_186_188/btv1b52514840q/Vmb-Ms-153.viola.pdf#5": 0,
    "G186/E-Mc_1-7040-185/E-Mc_1-7040-185.pdf#1": 0,
    "G220/463059600_D-B/463059600_D-B.pdf#1": 8, "G222/463059900_D-B/463059900_D-B.pdf#2": 11,
    "G189-194/btv1b10537292r/btv1b10537292r.pdf#60": 8,
    "G248-249/US-Wc_M452-A2-B68/US-Wc_M452-A2-B68-G249.pdf#15": 10,
    # light-ink music pages the page-ink rule took for title pages, and one page of show-through
    "G184/E-Mc_1-7040-188/E-Mc_1-7040-188.pdf#29": 8, "G237/1001137012_D-B/1001137012_D-B.pdf#15": 4,
    "G189-194/btv1b10537292r/btv1b10537292r.pdf#41": 4, "G216/463059100_D-B/463059100_D-B.pdf#18": 9,
    "G216/btv1b108677212/btv1b108677212.pdf#5": 6, "G160/450200971_D-Eu/D-Eu_Esl_VIII_352.pdf#17": 4,
}
# Whole documents the counter cannot read; staves and music pages estimated by eye.
DOC_FIX = {
    "G168/btv1b10076417z": (11, 244, "Bilevel microfilm of two-page openings; the counter finds almost nothing. Counted by eye: 11 openings of music, 244 staves; image 14 repeats image 13 and is not counted."),
    "G201-206/463057700_D-B": (129, 1060, "Estimate. The counter misses staves on these dense 11-staff pages: a 20-page eye sample gave 132 staves where it found 106 (x1.25), and 4 of the 20 were blank ruled pages."),
    "G207/1001161096_D-B": (18, 140, "Estimate. Faint-ink full score, 2 systems of 4 per page; music pages counted by eye x 8, less partial pages. The counter found about two thirds."),
    "G208/1001161550_D-B": (22, 172, "Estimate, as KHM 579."),
    "G209/1001161569_D-B": (21, 164, "Estimate, as KHM 579."),
    "G210/1001161583_D-B": (14, 108, "Estimate, as KHM 579."),
    "G211/1001161590_D-B": (21, 164, "Estimate, as KHM 579."),
    "G212/1001161668_D-B": (13, 100, "Estimate, as KHM 579."),
    "G250-255/US-Wc_M452-A2-B68-op54": (149, 1350, "Estimate. Every image is a two-page opening; counted half by half, with 24 openings corrected by eye; about 10 staves a full page. 8 title openings (part-books), so likely more than one Violino Primo book. Not in opera.json; G 250-255 is the folder's name, unverified."),
}
PAGE_INK = 0.38  # a page whose staves carry under this share of the document's median ink is a title page


def clean(r, calib):
    """Music staves on a page after three simple rules, measured on the Op. 48
    labels: a scanner calibration target is not music; a page with a single
    inked staff is a title page; a staff with under 0.3 of the page's median
    ink is a heading or 'Segue' line crossing an empty staff."""
    if calib.get(f"{r['pdf']}#{r['page']}"):
        return 0, "calibration"
    inks = [i for i in r["inks"] if i >= 0.01]
    if len(inks) == 1:
        return 0, "single"
    if not inks:
        return 0, ""
    med = statistics.median(inks)
    kept = [i for i in inks if i >= 0.3 * med]
    return len(kept), ("faint" if len(kept) < len(inks) else "")


def scribes(ids):
    out = []
    for sid in ids:
        f = CACHE / f"{sid}.xml"
        if not f.exists():
            continue
        x = f.read_text()
        for df in re.findall(r'<(?:marc:)?datafield tag="700".*?</(?:marc:)?datafield>', x, re.S):
            subs = collections.defaultdict(list)
            for code, val in re.findall(r'code="(\w)">([^<]*)<', df):
                subs[code].append(val)
            if "scr" in subs.get("4", []):
                for a in subs.get("a", []):
                    a = a.replace("Copyist ", "")
                    if a not in out:
                        out.append(a)
    return out


def main():
    calib = {k: v["dark"] > CAL_DARK and v["sat"] > CAL_SAT
             for k, v in json.loads((S / "calib.json").read_text()).items()} if (S / "calib.json").exists() else {}
    dropped = collections.Counter()
    pages = {}
    for line in (S / "pages.jsonl").open():
        r = json.loads(line)
        pages.setdefault(r["pdf"], {})[r["page"]] = r
    inv = json.loads((S / "inventory.json").read_text())
    op48 = {"226", "227", "228", "229", "230", "231"}
    rows, perpage, excluded = [], {}, []
    for it in inv:
        if it["medium"] == "print":
            continue
        g = it["gerard"] if isinstance(it["gerard"], list) else [it["gerard"]] if it["gerard"] else []
        if set(g) & op48:
            continue
        if it["folder"] in EXCLUDED:
            excluded.append((it["folder"], EXCLUDED[it["folder"]]))
            continue
        m = json.loads((DIG / it["folder"] / "metadata.json").read_text())
        auto = it["medium"] == "autograph" or str(m.get("is_autograph")) == "True"
        ids = [m["source_id"]] if m.get("source_id") else []
        rel = m.get("rism_related") or []
        if isinstance(rel, str):
            rel = re.findall(r"sources/(\d+)", rel)
        else:
            rel = [re.sub(r"\D", "", u.rsplit("/", 1)[-1]) for u in rel]
        if m.get("rism_relation") == "copy":
            ids += rel
        sc = scribes(ids)
        hand = "autograph" if auto else ("copyist: " + "; ".join(sc) if sc else "copyist")
        gi = sorted({int(x) for x in g})
        if it["folder"] in OSSQ:
            enc = "OSSQ"
        elif it["folder"] in DATAM:
            enc = "dataM"
        elif it["folder"] in DATAT:
            enc = "dataT"
        elif gi and all(x in PHILHAR for x in gi):
            enc = "LilyPond, unpaired"
        else:
            enc = "none"
        ops = sorted({OPUS[str(x)] for x in gi if str(x) in OPUS}, key=lambda t: (t[0], t[1] or 0))
        if ops:
            by = collections.defaultdict(list)
            for o, n in ops:
                by[o].append(n)
            opus = "; ".join(f"Op. {o}" + (f" no. {','.join(map(str, ns))}" if ns and ns[0] is not None and len(ns) < 6 else "")
                             for o, ns in by.items())
        else:
            opus = "Op. 54 (?)" if "op54" in it["folder"] else "?"
        files = [f for f in it["files"] if f not in SKIP_FILES]
        npg = nmus = nst = nraw = 0
        pp = {}
        for f in files:
            p = str(DIG / it["folder"] / f)
            got = pages.get(p, {})
            npg += it["files"][f]
            docink = [i for r in got.values() for i in r["inks"] if i >= 0.01]
            dmed = statistics.median(docink) if docink else 0
            cl = {}
            for n, r in sorted(got.items()):
                key = f"{it['folder']}/{f}#{n}"
                ink = [i for i in r["inks"] if i >= 0.01]
                if key in PAGE_FIX:
                    cl[n] = (PAGE_FIX[key], "eye")
                elif len(ink) > 1 and statistics.median(ink) < PAGE_INK * dmed and not calib.get(f"{r['pdf']}#{r['page']}"):
                    cl[n] = (0, "title")
                else:
                    cl[n] = clean(r, calib)
            pp[f] = {n: {"staves": cl[n][0], "raw": r["staves"], "ruled": r["ruled"], "rule": cl[n][1]}
                     for n, r in sorted(got.items())}
            nmus += sum(1 for c in cl.values() if c[0] > 0)
            nst += sum(c[0] for c in cl.values())
            nraw += sum(r["staves"] for r in got.values())
            for n, c in cl.items():
                if c[1] and it["folder"] not in DOC_FIX:
                    dropped[c[1]] += got[n]["staves"] - c[0]
            missing = it["files"][f] - len(got)
            if missing:
                print("NOT COUNTED YET:", p, missing, "pages")
        note = NOTES.get(it["folder"], "")
        est = False
        if it["folder"] in DOC_FIX:
            nmus, nst, note = DOC_FIX[it["folder"]]
            est = True
            dropped["estimate"] += nst - nraw
        perpage[it["folder"]] = pp
        shelf = it["shelfmark"] or ("SA 3364" if "PPN1935497081" in it["folder"] else "")
        rows.append(dict(folder=it["folder"], gerard=gi, opus=opus, lib=it["siglum"], shelf=shelf,
                         hand=hand, format="PDF", pages=npg, music=nmus, staves=nst, raw=nraw, enc=enc, est=est,
                         note=note, opus_key=ops[0][0] if ops else 54))

    rows.sort(key=lambda r: (r["gerard"][0] if r["gerard"] else 999, r["lib"], r["shelf"]))
    gfmt = lambda g: (f"{g[0]}–{g[-1]}" if len(g) > 2 and g == list(range(g[0], g[-1] + 1)) else ", ".join(map(str, g)))
    L = ["# Boccherini quartet manuscripts on disk, outside Op. 48: staves and encodings", "",
         "Source: `~/Dropbox/Code/boccherini-sources/digitizations/`: every item the archive classes as a manuscript "
         "or autograph, less Op. 48 (G 226–231). **Staves** are music staves: the labeler's own staff finder "
         "(`detect.find_staves` plus `detect_page`'s empty-staff test, the detection the labeler proposes) on 2800-px renders, then four simple rules: "
         "scanner calibration targets are not music; a page with one inked staff is a title page; a page whose staves carry under 0.38 of the "
         "document's median ink is a title page; a staff with under 0.3 of its page's median ink is a heading or 'Segue' line across an empty staff. "
         "About 60 pages checked by eye were corrected by hand (`PAGE_FIX` in assemble.py). Nine documents the finder cannot read are estimated by eye "
         "(marked ≈; see their notes). **Raw** is the finder's count before all of this. A **music page** has at least one music staff; "
         "the rest (title pages, covers, blank or ruled-only pages, calibration targets) are left out.", "",
         "Encodings: **dataM** = paired with Philhar's LilyPond for training; **dataT** = the Madrid test set, paired the same way; "
         "**OSSQ** = OSSQ-OMR/OpenScore encoding; **Philhar LilyPond, not paired** = an encoding of the work exists in "
         "`boccherini-quartet-data/lilypond` (Op. 2–33, G 159–212) but this source has not been paired with it; **none** = no encoding of the work.", "",
         "| G | Opus | Library, shelfmark | Hand | Format | Pages | Music pages | Staves | Raw | Encoding | Note |",
         "|---|---|---|---|---|--:|--:|--:|--:|---|---|"]
    for r in rows:
        L.append(f"| {gfmt(r['gerard']) if r['gerard'] else '?'} | {r['opus']} | {r['lib']} {r['shelf']} | {r['hand']} | {r['format']} | "
                 f"{r['pages']} | {r['music']} | {'≈' if r['est'] else ''}{r['staves']} | {r['raw']} | {ENC_LABEL[r['enc']]} | {r['note']} |")
    T = lambda key: collections.Counter() if False else None
    tot = collections.Counter()
    enc = collections.defaultdict(lambda: collections.Counter())
    lib = collections.defaultdict(lambda: collections.Counter())
    op = collections.defaultdict(lambda: collections.Counter())
    for r in rows:
        for c, k in ((enc, r["enc"]), (lib, r["lib"]), (op, r["opus_key"])):
            c[k]["items"] += 1
            c[k]["pages"] += r["pages"]
            c[k]["music"] += r["music"]
            c[k]["staves"] += r["staves"]
            c[k]["none" if r["enc"] == "none" else "unpaired" if r["enc"] == "LilyPond, unpaired" else "paired"] += r["staves"]
        tot["items"] += 1
        tot["pages"] += r["pages"]
        tot["music"] += r["music"]
        tot["staves"] += r["staves"]
        tot["raw"] += r["raw"]
    L += ["", f"**All:** {tot['items']} manuscripts, {tot['pages']} pages, {tot['music']} music pages "
          f"({tot['pages'] - tot['music']} left out), **{tot['staves']} staves** "
          f"(finder's raw count {tot['raw']}; the rules removed {dropped['title'] + dropped['faint'] + dropped['single'] + dropped['calibration']}, "
          f"eye corrections removed {dropped['eye']} net, whole-document estimates added {dropped['estimate']}).", "",
          "## By encoding", "", "| Encoding | Manuscripts | Pages | Music pages | Staves |", "|---|--:|--:|--:|--:|"]
    for k in ("none", "LilyPond, unpaired", "dataM", "dataT", "OSSQ"):
        c = enc[k]
        L.append(f"| {ENC_LABEL[k]} | {c['items']} | {c['pages']} | {c['music']} | {c['staves']} |")
    paired = sum(enc[k]["staves"] for k in ("dataM", "dataT", "OSSQ"))
    L += ["", f"No encoding of the work: **{enc['none']['staves']}** staves. "
          f"Work encoded but this source not paired: **{enc['LilyPond, unpaired']['staves']}**. "
          f"Paired with an encoding (dataM, dataT, OSSQ): **{paired}**.", "",
          "## By library", "", "| Library | Manuscripts | Music pages | Staves | no encoding | encoded, unpaired | paired |", "|---|--:|--:|--:|--:|--:|--:|"]
    for k, c in sorted(lib.items(), key=lambda kv: -kv[1]["staves"]):
        L.append(f"| {k} | {c['items']} | {c['music']} | {c['staves']} | {c['none']} | {c['unpaired']} | {c['paired']} |")
    L += ["", "## By opus", "", "| Opus | Manuscripts | Music pages | Staves | no encoding | encoded, unpaired | paired |", "|---|--:|--:|--:|--:|--:|--:|"]
    for k, c in sorted(op.items()):
        L.append(f"| Op. {k}{' (?)' if k == 54 else ''} | {c['items']} | {c['music']} | {c['staves']} | {c['none']} | {c['unpaired']} | {c['paired']} |")
    L += ["", "## Left out", ""] + [f"- `{f}`: {why}" for f, why in excluded] + [
        "- Op. 48 (G 226–231): excluded as asked.",
        "- Prints: every item the archive classes as print.", ""]
    (S / "census.md").write_text("\n".join(L) + "\n")
    (S / "census.json").write_text(json.dumps({"rows": [{k: v for k, v in r.items() if k != "opus_key"} for r in rows],
                                               "pages": perpage}, indent=1))
    print("\n".join(L[-40:]))


if __name__ == "__main__":
    main()
