"""build.py <sets.json> <out.json>: Philhar's site as a list of work sets, with sources and archive status."""
import json, re, sys
sets = json.load(open(sys.argv[1]))
W = "https://web.archive.org/web/2023id_/https://le-concert.pagesperso-orange.fr/"
# index: (scoring, category, source_kind)
A = {
 0: ("vc, bc", "cello and bass", "print"), 1: ("orchestra", "orchestral", "print"), 2: ("orchestra", "orchestral", "print"),
 3: ("vc, b", "cello and bass", "print"), 4: ("2 vl, vc", "string trio", "print+manuscript"), 5: ("vl, va, vc", "string trio", "print"),
 6: ("2 vl, va, vc", "string quartet", "print"), 7: ("2 vl, va, vc", "string quartet", "print"), 8: ("2 vl, va, vc", "string quartet", "print"),
 9: ("2 vl, va, vc", "string quartet", "print"), 10: ("2 vl, va, vc", "string quartet", "print+manuscript"), 11: ("2 vl, va, vc", "string quartet", "manuscript+print"),
 12: ("2 vl, va, vc", "string quartet", "print"), 13: ("orchestra", "orchestral", "print"), 14: ("2 bn/vc/b", "two basses", "print"),
 15: ("vc, bc", "cello and bass", "print"), 16: ("2 bn/vc/b", "two basses", "print"), 17: ("2 bn/vc/b", "two basses", "print"),
 18: ("2 va, vc", "string trio", "not stated"), 19: ("2 vl, va, vc", "string quartet", "print"), 20: ("vc, b", "cello and bass", "print"),
 21: ("2 ob, 2 hn, strings (+fl, bn)", "orchestral", "print"), 22: ("vl, va, b", "string trio", "print"), 23: ("vl, vc", "string duo", "manuscript+print"),
 24: ("vc, bc", "cello and bass", "print"), 25: ("vc, orchestra / vc, pf", "orchestral", "not stated"), 26: ("2 vc", "two basses", "print"),
 27: ("vc, bc", "cello and bass", "print"), 28: ("vl, vc", "string duo", "manuscript"), 29: ("2 vl, va, vc", "string quartet", "print"),
 30: ("fl/vl, vl, va, b", "string quartet", "print"), 31: ("2 vl, va, b", "string quartet", "print"), 32: ("2 ob, 2 hn, strings", "orchestral", "print"),
 33: ("2 ob, 2 hn, strings", "orchestral", "print"), 34: ("orchestra", "orchestral", "print"), 35: ("orchestra", "orchestral", "print"),
 36: ("orchestra", "orchestral", "print"), 37: ("baryton, va, vc", "string trio", "manuscript"), 38: ("2 vl, 2 va, vc", "string quintet", "manuscript"),
 39: ("vl, vc", "string duo", "print"), 40: ("2 vl, vc", "string trio", "print"), 41: ("2 vl, va, vc", "string quartet", "print"),
 42: ("2 vc, b", "string trio", "manuscript"), 43: ("2 vl, va, vc", "string quartet", "print"), 44: ("orchestra", "orchestral", "print"),
 45: ("pf, vc", "piano and cello", "manuscript"), 46: ("2 vl, va, vc", "string quartet", "print"), 47: ("vl, va, vc", "string trio", "print"),
 48: ("3 vc", "string trio", "manuscript"), 49: ("vc, b", "cello and bass", "print"), 50: ("orchestra", "orchestral", "not stated"),
 51: ("2 vc", "two basses", "print"), 52: ("orchestra", "orchestral", "not stated"), 53: ("2 vl, va, vc", "string quartet", "print"),
 54: ("vc, b", "cello and bass", "print"), 55: ("vc, b", "cello and bass", "print"), 56: ("orchestra", "orchestral", "print"),
 57: ("vc, b", "cello and bass", "print"), 58: ("vl, orchestra", "orchestral", "print"), 59: ("orchestra", "orchestral", "print"),
 60: ("vl, vc", "string duo", "print"), 61: ("orchestra", "orchestral", "not stated"), 62: ("orchestra", "orchestral", "not stated"),
 63: ("vl, va, vc", "string trio", "print"),
}
# manuscript sources named by Philhar, resolved (RISM Online, IMSLP, library viewers; checked 2026-10-20)
MS = {
 4: [{"named": "Manuscrit (parties) - n.d.", "library": "US-R (Sibley Music Library, Rochester)", "shelfmark": "M351.B664M", "rism": "130195",
      "date": "1766 (RISM: 1766p); IMSLP: ca. 1775", "format": "3 parts (vl 1, vl 2, vlc), p. 27-63 each", "hand": "unknown copyist",
      "scan": "IMSLP (Sibley scan); not linked from RISM", "identified_by": "IMSLP page for G.83-88; Philhar names no library"},
     {"named": "Manuscrit (score) - n.d.", "library": "probably I-MC (Montecassino), via Internet Culturale", "shelfmark": "1-C-7 g-l", "rism": "852015747 (G.83) and siblings",
      "date": "1750-1799", "format": "score", "scan": "Internet Culturale; IMSLP", "identified_by": "IMSLP lists an Internet Culturale manuscript score; RISM I-MC 1-C-7g is a score; unconfirmed match"}],
 10: [{"named": "Manuscrit, copiste inconnu, ayant appartenu à Pierre Baillot (BNF-Gallica)", "library": "F-Pn", "shelfmark": "Vmb ms. 153", "date": "1775-1800",
       "format": "parts", "scan": "Gallica; already on disk and paired (reports/2026-10-11-philhar-manuscript-sources)", "note": "Philhar's cSource names the Chevardière print as the source; the manuscript gave variants"}],
 11: [{"named": "Manuscrit autographe, 1777 (BNF-Gallica)", "library": "F-Pn", "shelfmark": "MS-1292", "date": "1777", "format": "score (autograph)",
       "scan": "Gallica; already on disk; pairing tried, 29 of 468 staves kept (census report)"}],
 23: [{"named": "Manuscrit - Bremner", "library": "D-B (Staatsbibliothek zu Berlin)", "shelfmark": "Mus.ms. 2861", "rism": "452007625", "date": "ca. 1780",
       "format": "2 parts (vl, vlc), 10 + 10 folios; 41 images", "scan": "SBB digital (PPN626958725, resolver SBB00001DA400000000); IMSLP",
       "identified_by": "IMSLP's only manuscript scan for the set is SBB's 1780 copy", "note": "Encoding mixes the manuscript and Bremner's print (London, ca. 1765); comments mark 'BR:' and 'MS:' readings"}],
 28: [{"named": "Manuscrit (IMSLP)", "library": "not named (IMSLP upload by 'Zelenka', 2010)", "shelfmark": None, "rism": "850810319? (I-Gl M. (3) 22.7, parts, 1760-1780) — unconfirmed",
       "format": "parts", "scan": "IMSLP: 'Duet for Violin and Cello in F major (Giardini, Felice)'"}],
 37: [{"named": "Manuscrit Johann Elssler, ca.1790 (Staatsbibliothek zu Berlin)", "library": "D-B", "shelfmark": "Mus.ms. 10037", "rism": "452005366", "date": "ca. 1790",
       "format": "3 parts (baryton, va, vc) for 72 trios, 635 images; Hob. XI:25-27 are a few pages of each part", "hand": "Johann Elssler (1769-1843) and others",
       "scan": "SBB digital (PPN820525103, resolver SBB0001967C00000000); IMSLP per trio"}],
 38: [{"named": "Manuscrit (ca.1760-99). SLUB-Dresden (IMSLP)", "library": "D-Dl (SLUB Dresden)", "shelfmark": "Mus.3403-P-513", "rism": "210044350", "date": "ca. 1770-1800",
       "format": "5 parts (vl 1, 2, va 1, 2, vlc), 8+8+7+7+7 folios", "scan": "SLUB digital (ppn398103402; returns 403 to scripted requests); IMSLP copy of SLUB's scan",
       "note": "Title names 'von Robinig' crossed out, 'Weizner' added: a Salzburg copy"}],
 42: [{"named": "Manuscrit (D-Eu Esl VIII 405, IMSLP)", "library": "D-Eu (UB Eichstätt-Ingolstadt)", "shelfmark": "Esl VIII 405", "rism": "450300198", "date": "ca. 1800 (1795-1805)",
       "format": "3 parts (vlc 1, vlc 2, b), 2+2+2 folios", "hand": "RISM: Steger, Johann Georg", "scan": "Eichstätt digital (urn:nbn:de:bvb:824-esl-viii-405-6; bot gate, hand download); IMSLP",
       "note": "Same Eichstätt collection as our Op. 2 copies (Esl VIII 351-357, stamped Bibl. Steger)"}],
 45: [{"named": "Manuscrit holographe - HAAB-Weimar (IMSLP)", "library": "D-WRz (HAAB Weimar)", "date": "1824", "format": "autograph score (25 pp) and cello part (9 pp)",
       "scan": "IMSLP (AAB scan)"}],
 48: [{"named": "Manuscrit autographe (Staatsbibliothek zu Berlin, IMSLP)", "library": "D-B", "date": "1925", "format": "autograph", "scan": "IMSLP"}],
}
# period manuscript copies (not Philhar's source) of works he encoded from prints: leads, from RISM Online
LEADS = {
 3: ["D-Eu Esl VIII 407 (G.1, RISM 450200982) and Esl VIII 349 (G.4, RISM 450200979): Eichstätt copies, ca. 1790, digitized"],
 4: ["D-B KHM 620-624 (G.87, 88, 85, 83, 86): parts, copyist Schober (the KHM 577 Op. 32 hand), 4+4+4 pp each, SBB digitized",
     "I-MC 1-C-7 g-l: Montecassino score, digitized", "D-LEm Becker III.11.27-28 (G.88, G.86), ca. 1768, digitized"],
 5: ["D-Eu Esl VIII 21 (G.98): parts vl, va, vc, ca. 1790, 2+2+2 folios, digitized"],
 41: ["D-Eu Esl VIII 395 (G major quartet, ca. 1790), D-LEb Go. S. 215 (3 quartets, A, C, E-flat, ca. 1810): keys not yet matched to op. 14"],
 40: ["D-Eu Esl VIII 430 (trio in G, ca. 1800): not yet matched to op. 22"],
}
out = []
for i, s in enumerate(sets):
    sc, cat, kind = A[i]
    m = re.search(r"\(([^)]*\d{4}[^)]*)\)", s["composer"])
    t = s["text"]
    src = re.findall(r"Sources?\s*(?:\(IMSLP\))?\s*:?\s*(.{0,160}?)(?=Partition|PDF|Fichiers|Orchestration|N°1|n°1|op\.7 n°|$)", t)
    src = sorted({re.sub(r"\s*N°\d.*", "", x).strip() for x in src if x.strip()})
    works = [{"zip": z["href"], "archived": z["archived"], "bytes": z["bytes"],
              "wayback": f"https://web.archive.org/web/{z['archived']}/https://le-concert.pagesperso-orange.fr/{z['href']}" if z["archived"] else None}
             for z in s["zips"] if z["kind"] == "lilypond"]
    out.append({"composer": re.sub(r"\s*\(.*", "", s["composer"]), "composer_dates": m.group(1) if m else None,
                "page": s["page"], "title": s["title"], "scoring": sc, "category": cat,
                "source_kind": kind, "philhar_source": src or None,
                "scan_mentions": sorted(set(re.findall(r"(IMSLP|Gallica|BNF|Staatsbibliothek zu Berlin|SLUB|HAAB)", t))),
                "links": s["links"], "manuscripts": MS.get(i), "manuscript_copy_leads": LEADS.get(i),
                "lilypond": works, "n_works": len(works), "n_archived": sum(1 for w in works if w["archived"])})
json.dump({"site": "https://le-concert.pagesperso-orange.fr/ (Philhar, Editions 'Le Concert')",
           "snapshot": "https://web.archive.org/web/20230929061441/https://le-concert.pagesperso-orange.fr/",
           "crawled": "2026-10-20", "note": "Composer pages fetched from Wayback captures of 2023-09-30 to 2023-10-03 (nearest to 2023-09-29). 'archived' is the first Wayback capture with status 200 and a zip type (CDX). Manuscript details resolved from RISM Online and IMSLP on 2026-10-20.",
           "sets": out}, open(sys.argv[2], "w"), ensure_ascii=False, indent=1)
from collections import Counter
print("composers", len({o["page"] for o in out}), "sets", len(out), "works", sum(o["n_works"] for o in out), "archived", sum(o["n_archived"] for o in out))
print(Counter(o["source_kind"] for o in out))
ms = [o for o in out if "manuscript" in o["source_kind"]]
print("ms sets", len(ms), "ms works", sum(o["n_works"] for o in ms))
print(Counter(o["category"] for o in out))
print("string works 1700-1810:", sum(o["n_works"] for o in out if o["category"] not in ("orchestral", "piano and cello")))
