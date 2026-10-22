# /// script
# requires-python = ">=3.11"
# ///
"""Write pagemap.json: Bärenreiter BA 2676's quartets and movements, by PDF
page, in each part. Read by eye from the scans (2026-10-20). PDF page n is
printed page n+1 in every part (PDF 1 is the part's cover). A movement's
range runs from the page it starts on to the page it ends on; a page can
hold the end of one movement and the start of the next."""
import json
from pathlib import Path

D = "~/Data/manuscript-labeler/imslp/barenreiter-ba2676/"
PDF = {"vn1": "IMSLP370564-PMLP598459-Boccherini_Str._Qu._op.2.1_Vl1.pdf",
       "vn2": "IMSLP370565-PMLP598459-Boccherini_Str._Qu._op.2.1_Vl2.pdf",
       "va": "IMSLP370566-PMLP598459-Boccherini_Str._Qu._op.2.1_Vla.pdf",
       "vc": "IMSLP370567-PMLP598459-Boccherini_Str._Qu._op.2.1_Vc.pdf"}
QUARTETS = [  # (no., G., print's heading and opus line, movement titles)
    ("I", 159, "Quartetto c-moll, op. 1 Nr. 1 (1761)", ["Allegro commodo", "Largo", "Allegro"]),
    ("II", 189, "Quartetto D-dur, op. 24 Nr. 5 (1778)", ["Moderato", "Grave", "Allegro assai"]),
    ("III", 214, "Quartetto c-moll, op. 41 (1788)", ["Prestissimo", "Tempo di Minuetto (Trio)", "Flebile", "Prestissimo"]),
    ("IV", 213, "Quartetto A-dur, op. 39 (1787)", ["Allegro moderato", "Minuetto. Allegro (Trio)", "Grave", "Allegro giusto"]),
    ("V", 215, "Quartetto C-dur, op. 41 (1788)", ["Allegretto moderato", "Minuetto. Allegro (Trio)", "Larghetto affettuoso", "Rondeau. Allegro moderato"]),
    ("VI", 223, "Quartettino G-dur \"La Tiranna Spagnola\", op. 44 Nr. 4 (1792)", ["Presto", "Tempo di Minuetto (Trio)"]),
    ("VII", 228, "Quartettino h-moll, op. 48 Nr. 2 (1794)", ["Allegretto moderato", "Minuetto. Con moto (Trio)"]),
    ("VIII", 243, "Quartetto Es-dur, op. 58 Nr. 2 (1799)", ["Allegretto lento", "Minuetto. Allegro (Trio)", "Larghetto", "Finale. Allegro vivo assai"]),
]
# per part, per quartet: each movement's first and last PDF page
PAGES = {
    "vn1": [[(2, 2), (3, 3), (3, 4)], [(5, 6), (7, 7), (8, 8)], [(9, 11), (11, 12), (12, 12), (12, 13)],
            [(14, 16), (16, 16), (17, 17), (17, 18)], [(19, 20), (21, 22), (22, 22), (23, 24)],
            [(25, 26), (27, 27)], [(28, 30), (30, 30)], [(31, 32), (32, 33), (33, 33), (34, 35)]],
    "vn2": [[(2, 2), (3, 3), (3, 4)], [(5, 6), (7, 7), (7, 8)], [(9, 10), (11, 11), (11, 12), (12, 12)],
            [(13, 14), (14, 14), (15, 15), (15, 16)], [(17, 18), (18, 18), (19, 19), (19, 20)],
            [(21, 22), (23, 23)], [(24, 26), (26, 26)], [(27, 28), (28, 29), (29, 29), (30, 31)]],
    "va":  [[(2, 2), (3, 3), (3, 4)], [(5, 6), (7, 7), (7, 8)], [(9, 10), (11, 11), (11, 11), (12, 12)],
            [(13, 14), (14, 14), (15, 15), (15, 16)], [(17, 18), (18, 18), (19, 19), (19, 20)],
            [(21, 22), (23, 23)], [(24, 26), (26, 26)], [(27, 28), (28, 28), (29, 29), (29, 30)]],
    "vc":  [[(2, 2), (3, 3), (3, 4)], [(5, 6), (6, 6), (7, 7)], [(8, 10), (10, 10), (11, 11), (11, 12)],
            [(13, 14), (14, 14), (15, 15), (15, 16)], [(17, 18), (18, 18), (19, 19), (19, 20)],
            [(21, 22), (23, 23)], [(24, 26), (26, 26)], [(27, 28), (28, 28), (29, 29), (29, 30)]],
}
ROMAN = ["I", "II", "III", "IV"]
N = {"vn1": 35, "vn2": 31, "va": 30, "vc": 30}  # pdfinfo
out = {"edition": "Bärenreiter BA 2676, Boccherini, Ausgewählte Streichquartette, ed. Walter Upmeyer (1952)",
       "source": "IMSLP #370564-370568", "folder": D, "note": __doc__.split("\n\n")[0].replace("\n", " "),
       "covers": "IMSLP370568-PMLP598459-Boccherini_Selected_String_Quartets_Covers.pdf (covers, German foreword)",
       "parts": {p: {"pdf": PDF[p], "pdf_pages": N[p]} for p in PDF}, "quartets": []}
for k, (no, g, title, mvts) in enumerate(QUARTETS):
    q = {"no": no, "G": g, "title": title, "parts": {}}
    for p in PDF:
        ranges = PAGES[p][k]
        assert len(ranges) == len(mvts), (p, no)
        q["parts"][p] = {"pages": [ranges[0][0], ranges[-1][1]],
                         "movements": {ROMAN[i]: {"title": mvts[i], "pages": list(r)} for i, r in enumerate(ranges)}}
    out["quartets"].append(q)
(Path(__file__).parent / "pagemap.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
print("wrote pagemap.json")
