# /// script
# requires-python = ">=3.11"
# ///
"""Page maps for the Philhar manuscript sources, made by eye from the scans.

    uv run experiments/philhar-mss/pagemaps.py [~/Data/manuscript-labeler/philhar-mss]

Writes pagemaps/<source>.json: which part each PDF page holds, where each
movement starts (page, and staff counted from the top of the page, 1 =
the first staff with music), the hand and date the catalogue gives, and
the --pages string autodetect.py takes. PDF pages are 1-based, as in the
PDF fetch_scans.py made. "work" names the folder in
~/Data/manuscript-labeler/philhar-site/lily/.

Where the Berlin and Dresden manifests divide the parts (IIIF structures),
the parts' page ranges agree with them; the movement starts are by eye.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def starts(work, part, *spec):
    """("I", 2, 1), ("II", 3, 1) ... -> movement starts."""
    return [{"work": work, "part": part, "mvt": m, "page": p, "staff": s} for m, p, s in spec]


SCHOBER = "Copyist Schober (RISM); the hand of KHM 577 (Op. 32)"

MAPS = {
    "D-B_KHM-620": dict(
        staves_estimate=94,
        layout="parts", hand=SCHOBER, date="ca. 1775-1800 (RISM)", works={"boccherini-G87": "G. 87 in D"},
        pages=[([1], None, "cover and title (with an incipit on two staves)"),
               ([2, 4], "vc", None), ([5, 8], "vn1", None), ([9, 12], "vn2", None),
               ([13], None, "the vn1 cover with SBB's colour chart")],
        movements=starts("boccherini-G87", "vc", ("I", 2, 1), ("II", 3, 1), ("III", 4, 1))
        + starts("boccherini-G87", "vn1", ("I", 5, 1), ("II", 7, 1), ("III", 7, 7))
        + starts("boccherini-G87", "vn2", ("I", 9, 1), ("II", 10, 2), ("III", 11, 1))),
    "D-B_KHM-621": dict(
        staves_estimate=80,
        layout="parts", hand=SCHOBER, date="ca. 1775-1800 (RISM)", works={"boccherini-G88": "G. 88 in F"},
        pages=[([1], None, "cover and title (incipit on two staves)"),
               ([2, 4], "vc", None), ([5, 7], "vn1", None), ([8], None, "blank ruled page"),
               ([9, 11], "vn2", None), ([12], None, "blank ruled page"),
               ([13], None, "the vn1 cover with SBB's colour chart")],
        movements=starts("boccherini-G88", "vc", ("I", 2, 1), ("II", 2, 6), ("III", 4, 1))
        + starts("boccherini-G88", "vn1", ("I", 5, 1), ("II", 6, 1), ("III", 7, 2))
        + starts("boccherini-G88", "vn2", ("I", 9, 1), ("II", 10, 1), ("III", 11, 1))),
    "D-B_KHM-622": dict(
        staves_estimate=84,
        layout="parts", hand=SCHOBER, date="ca. 1775-1800 (RISM)", works={"boccherini-G85": "G. 85 in E"},
        pages=[([1], None, "cover and title (incipit on two staves)"),
               ([2, 4], "vc", None), ([5, 8], "vn1", None), ([9, 12], "vn2", None),
               ([13], None, "the vn1 cover with SBB's colour chart")],
        movements=starts("boccherini-G85", "vc", ("I", 2, 1), ("II", 2, 9), ("III", 3, 4), ("IV", 4, 1))
        + starts("boccherini-G85", "vn1", ("I", 5, 1), ("II", 6, 1), ("III", 7, 1), ("IV", 8, 1))
        + starts("boccherini-G85", "vn2", ("I", 9, 1), ("II", 10, 1), ("III", 11, 1), ("IV", 12, 1))),
    "D-B_KHM-623": dict(
        staves_estimate=76,
        layout="parts", hand=SCHOBER, date="ca. 1775-1800 (RISM)", works={"boccherini-G83": "G. 83 in E flat"},
        pages=[([1], None, "cover and title (incipit on two staves)"),
               ([2, 4], "vc", None), ([5], None, "vn1 title page"), ([6, 8], "vn1", None),
               ([9], None, "vn2 title page"), ([10, 12], "vn2", None),
               ([13], None, "the vn1 cover with SBB's colour chart")],
        movements=starts("boccherini-G83", "vc", ("I", 2, 1), ("II", 3, 4), ("III", 4, 1))
        + starts("boccherini-G83", "vn1", ("I", 6, 1), ("II", 7, 4), ("III", 8, 1))
        + starts("boccherini-G83", "vn2", ("I", 10, 1), ("II", 11, 4), ("III", 12, 1)),
        notes="The cello's slow movement is headed 'Adagio assai', the violins' 'Largo assai' (Philhar: Largo assai)."),
    "D-B_KHM-624": dict(
        staves_estimate=75,
        layout="parts", hand=SCHOBER, date="ca. 1775-1800 (RISM)", works={"boccherini-G86": "G. 86 in F minor"},
        pages=[([1], None, "cover and title (incipit on two staves)"),
               ([2, 4], "vc", None), ([5], None, "vn1 title page"), ([6, 8], "vn1", None),
               ([9], None, "vn2 title page"), ([10, 12], "vn2", None),
               ([13], None, "the vn1 cover with SBB's colour chart")],
        movements=starts("boccherini-G86", "vc", ("I", 2, 1), ("II", 2, 6), ("III", 4, 1))
        + starts("boccherini-G86", "vn1", ("I", 6, 1), ("II", 6, 6), ("III", 8, 1))
        + starts("boccherini-G86", "vn2", ("I", 10, 1), ("II", 10, 5), ("III", 12, 1))),
    "D-B_Mus.ms.2861": dict(
        staves_estimate=410,
        layout="parts", hand="not named (RISM, SBB)", date="ca. 1780 (RISM)",
        works={f"campioni-op7-{n}": f"Duetto {r}" for n, r in zip(range(1, 7), ["I", "II", "III", "IV", "V", "VI"])},
        pages=[([1], None, "violin cover: 'Sei Duetti à Violino e Violoncello del Sig. Campioni'"),
               ([2, 19], "vn1", None), ([20], None, "blank ruled page"),
               ([21], None, "cello cover"), ([22, 39], "vc", None), ([40], None, "blank ruled page"),
               ([41], None, "SBB's colour chart")],
        movements=[m for n, (vl, vc) in enumerate([
            ([("I", 2, 1), ("II", 3, 1), ("III", 4, 1)], [("I", 22, 1), ("II", 23, 1), ("III", 24, 1)]),
            ([("I", 5, 1), ("II", 6, 1), ("III", 7, 2)], [("I", 25, 1), ("II", 26, 1), ("III", 27, 1)]),
            ([("I", 8, 1), ("II", 9, 1), ("III", 10, 1)], [("I", 28, 1), ("II", 29, 1), ("III", 30, 1)]),
            ([("I", 11, 1), ("II", 12, 1), ("III", 13, 1)], [("I", 31, 1), ("II", 32, 1), ("III", 33, 1)]),
            ([("I", 14, 1), ("II", 15, 1), ("III", 16, 1)], [("I", 34, 1), ("II", 35, 1), ("III", 36, 1)]),
            ([("I", 17, 1), ("II", 18, 1), ("III", 19, 7)], [("I", 37, 1), ("II", 38, 1), ("III", 39, 3)]),
        ], 1) for m in starts(f"campioni-op7-{n}", "vn1", *vl) + starts(f"campioni-op7-{n}", "vc", *vc)],
        notes="Each duet starts on a new page, headed 'Duetto I' ... 'VI'. Philhar's encoding mixes this copy "
              "with Bremner's print (London, ca. 1765); his comments mark 'BR:' and 'MS:' readings."),
    "D-Dl_Mus.3403-P-513": dict(
        staves_estimate=525,
        layout="parts", hand="not named; a Salzburg copy (title: 'von Robinig' crossed out, 'Weizner' added)",
        date="ca. 1770-1800 (RISM); 1799 (SLUB)", works={"haydn-m-MH411": "Quintetto in F, MH 411"},
        pages=[([1], None, "cover: 'Quintetto a 2 Violini 2 Viole e Violoncello Del Sigr Michele Haydn'"),
               ([2, 14], "vc", None), ([15], None, "vn1 title page"), ([16, 30], "vn1", None),
               ([31], None, "vn2 title page"), ([32, 46], "vn2", None),
               ([47], None, "va1 title page"), ([48, 59], "va", None), ([60], None, "blank ruled page"),
               ([61], None, "va2 title page"), ([62, 73], "va2", None), ([74], None, "blank ruled page")],
        movements=starts("haydn-m-MH411", "vc", ("I", 2, 1), ("II", 4, 1), ("III", 5, 1), ("IV", 6, 1),
                         ("V", 8, 1), ("VI", 10, 1), ("VII", 14, 1))
        + starts("haydn-m-MH411", "vn1", ("I", 16, 1), ("II", 20, 1), ("III", 22, 1), ("IV", 23, 3),
                 ("V", 24, 1), ("VI", 26, 1), ("VII", 30, 1))
        + starts("haydn-m-MH411", "vn2", ("I", 32, 1), ("II", 36, 1), ("III", 38, 1), ("IV", 39, 2),
                 ("V", 40, 1), ("VI", 42, 1), ("VII", 46, 1))
        + starts("haydn-m-MH411", "va", ("I", 48, 1), ("II", 50, 1), ("III", 52, 1), ("IV", 53, 3),
                 ("V", 54, 1), ("VI", 56, 1), ("VII", 59, 4))
        + starts("haydn-m-MH411", "va2", ("I", 62, 1), ("II", 64, 1), ("III", 66, 1), ("IV", 67, 1),
                 ("V", 68, 1), ("VI", 70, 1), ("VII", 73, 5)),
        notes="Movements in Philhar's order: I Allegro aperto, II Menuetto-Trio, III Andante, IV Menuetto "
              "(Allegretto)-Trio, V Un poco allegretto with six variations, VI Finale: Rondo (Vivace assai), "
              "VII Marcia (Andantino). The parts agree with SLUB's manifest (vc 1-14, vn1 15-30, vn2 31-46, "
              "va1 47-60, va2 61-74). Single oblong pages, about 10 staves each. va = viola 1, va2 = viola 2."),
    "US-R_M351.B664M": dict(
        staves_estimate=650,
        layout="parts", hand="unknown copyist (Sibley)", date="1766 (RISM: 1766p); ca. 1775 (Sibley, IMSLP)",
        works={"boccherini-G83": "Trio I", "boccherini-G86": "Trio II", "boccherini-G84": "Trio III",
               "boccherini-G85": "Trio IV", "boccherini-G87": "Trio V", "boccherini-G88": "Trio VI"},
        order=["boccherini-G83", "boccherini-G86", "boccherini-G84", "boccherini-G85", "boccherini-G87",
               "boccherini-G88"],
        pages=[([1], None, "vn1 title: 'Violino Primo. Trij VI a Due Violini e Basso Del Sig. Luiggi Boccherini. Muta 2da'"),
               ([2, 37], "vn1", None), ([38], None, "vn2 title page"), ([39, 74], "vn2", None),
               ([75], None, "bass title page ('Basso')"), ([76, 111], "vc", None)],
        movements=[m for part, off in (("vn1", 0), ("vn2", 37), ("vc", 74)) for m in
                   starts("boccherini-G83", part, ("I", 2 + off, 1), ("II", 4 + off, 1), ("III", 6 + off, 1))
                   + starts("boccherini-G86", part, ("I", 8 + off, 1), ("II", 10 + off, 1), ("III", 12 + off, 1))
                   + starts("boccherini-G84", part, ("I", 14 + off, 1), ("II", 16 + off, 1), ("III", 18 + off, 1))
                   + starts("boccherini-G85", part, ("I", 20 + off, 1), ("II", 22 + off, 1), ("III", 24 + off, 1),
                            ("IV", 62, 1) if part == "vn2" else ("IV", 24 + off, 8))
                   + starts("boccherini-G87", part, ("I", 26 + off, 1), ("II", 28 + off, 1), ("III", 30 + off, 1))
                   + starts("boccherini-G88", part, ("I", 32 + off, 1), ("II", 34 + off, 1), ("III", 36 + off, 1))],
        notes="The three 'manuscript' PDFs of UR Research's record, joined vn1, vn2, bass. The trios run in the "
              "copy's order (G. 83, 86, 84, 85, 87, 88), not Gerard's: give autopair --quartets in this order. "
              "Every movement starts a page, except G. 85's finale (Allegro), which starts on the minuet's page "
              "(staff 8) in vn1 and the bass. The bass part is headed 'Basso' and is the cello part (RISM: vlc; "
              "Philhar: Violoncelle); it mixes bass and tenor clef. Left out: the record's '(print)' files (the "
              "bound-with Venice print of G. 89-94) and colour covers. Some pages begin with empty ruled staves: "
              "staff numbers count staves with music."),
    "I-MC_1-C-7": dict(
        staves_estimate=750,
        layout="score (systems of 3 staves: vn1, vn2, vc)", hand="not named", date="1750-1799 (RISM)",
        works={"boccherini-G83": "Trio VII (1-C-7g)", "boccherini-G86": "Trio VIII (1-C-7h)",
               "boccherini-G87": "Trio IX (1-C-7i)", "boccherini-G84": "Trio X (1-C-7j)",
               "boccherini-G88": "Trio XI (1-C-7k)", "boccherini-G85": "Trio XII (1-C-7l)"},
        order=["boccherini-G83", "boccherini-G86", "boccherini-G87", "boccherini-G84", "boccherini-G88",
               "boccherini-G85"],
        pages=[([1, 11], "score", "Trio VII, G. 83 (f. 46v-51v)"), ([12, 23], "score", "Trio VIII, G. 86 (f. 52r-57v)"),
               ([24, 41], "score", "Trio IX, G. 87 (f. 58r-66v, system 2)"),
               ([41, 58], "score", "Trio X, G. 84 (f. 66v system 3 - 75r)"),
               ([59, 69], "score", "Trio XI, G. 88 (f. 75v-80v)"), ([70, 84], "score", "Trio XII, G. 85 (f. 81r-88r)")],
        movements=[{**m, "system": s} for m, s in [
            *zip(starts("boccherini-G83", "score", ("I", 1, 1), ("II", 7, 1), ("III", 8, 4)), (1, 1, 2)),
            *zip(starts("boccherini-G86", "score", ("I", 12, 1), ("II", 15, 1), ("III", 21, 1)), (1, 1, 1)),
            *zip(starts("boccherini-G87", "score", ("I", 24, 1), ("II", 31, 1), ("III", 35, 1)), (1, 1, 1)),
            *zip(starts("boccherini-G84", "score", ("I", 41, 7), ("II", 47, 7), ("III", 50, 4)), (3, 3, 2)),
            *zip(starts("boccherini-G88", "score", ("I", 59, 1), ("II", 61, 7), ("III", 67, 4)), (1, 3, 2)),
            *zip(starts("boccherini-G85", "score", ("I", 70, 1), ("II", 75, 1), ("III", 78, 1), ("IV", 81, 1)),
                 (1, 1, 1, 1))]],
        autodetect_pages="1-84:score",
        notes="A score, three systems of three staves a page (about 9 staves). Internet Culturale serves it only "
              "at about 650 x 770 px (some 80 dpi), photographed open with the facing page's edge in frame. "
              "PDF page n is the volume's folio label in SOURCE.json. RISM's folio ranges hold, except that "
              "G. 87 ends and G. 84 begins on f. 66v (systems 2 and 3). G. 88's II and III starts are less sure "
              "(read at low resolution). autodetect's score mode takes systems of 4 staves only."),
    "unknown_IMSLP-PMLP122408": dict(
        staves_estimate=61,
        layout="parts", hand="not named", date="not given (IMSLP: manuscript)",
        works={"giardini-duo-F": "Duetto in F"},
        pages=[([1], None, "violin title page ('Violino')"), ([2, 5], "vn1", None), ([6], None, "blank ruled page"),
               ([7], None, "cello title page: 'Duetto a Violoncello e Violino Del Sigr Felice Giardini, Violoncello'"),
               ([8, 11], "vc", None)],
        movements=starts("giardini-duo-F", "vn1", ("I", 2, 1), ("II", 3, 2), ("III", 4, 1))
        + starts("giardini-duo-F", "vc", ("I", 8, 1), ("II", 9, 2), ("III", 10, 1)),
        notes="A grey 150 dpi scan, cropped tight: the cello's 'Adagio' heading is cut off at the left edge (p. 9)."),
}


def autodetect_pages(pages) -> str:
    out = []
    for rng, part, _ in pages:
        if part:
            out.append(f"{rng[0]}-{rng[-1]}:{part}" if len(rng) > 1 else f"{rng[0]}:{part}")
    return ",".join(out)


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "~/Data/manuscript-labeler/philhar-mss").expanduser()
    out = HERE / "pagemaps"
    out.mkdir(exist_ok=True)
    for name, m in MAPS.items():
        src = json.loads((root / name / "SOURCE.json").read_text()) if (root / name / "SOURCE.json").exists() else {}
        doc = {
            "source": name, "pdf": f"~/Data/manuscript-labeler/philhar-mss/{name}/{name}.pdf",
            "pdf_sha256": src.get("sha256"), "pdf_pages": src.get("pages"),
            "library": src.get("library"), "rism": src.get("rism"),
            "layout": m["layout"], "hand": m["hand"], "date": m["date"], "works": m["works"],
            "order": m.get("order", list(m["works"])),
            "staves_estimate": m["staves_estimate"], "staves_estimate_how": "counted by eye from contact sheets, +-15%",
            "pages": [{"pages": f"{r[0]}-{r[-1]}" if len(r) > 1 else str(r[0]), "part": p, **({"what": w} if w else {})}
                      for r, p, w in m["pages"]],
            "movements": m["movements"],
            "autodetect_pages": autodetect_pages(m["pages"]) if m["layout"] == "parts" else m.get("autodetect_pages"),
            **({"notes": m["notes"]} if m.get("notes") else {}),
        }
        last = max(r[-1] for r, _, _ in m["pages"])
        if src and last != src.get("pages"):
            print(f"WARNING {name}: map covers {last} pages, PDF has {src.get('pages')}")
        (out / f"{name}.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
        print(name, doc["autodetect_pages"])


if __name__ == "__main__":
    main()
