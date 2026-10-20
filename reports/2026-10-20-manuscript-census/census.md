# Boccherini quartet manuscripts on disk, outside Op. 48: staves and encodings

Source: `~/Dropbox/Code/boccherini-sources/digitizations/`: every item the archive classes as a manuscript or autograph, less Op. 48 (G 226–231). **Staves** are music staves: the labeler's own staff finder (`detect.find_staves` plus `detect_page`'s empty-staff test, the detection the labeler proposes) on 2800-px renders, then four simple rules: scanner calibration targets are not music; a page with one inked staff is a title page; a page whose staves carry under 0.38 of the document's median ink is a title page; a staff with under 0.3 of its page's median ink is a heading or 'Segue' line across an empty staff. About 60 pages checked by eye were corrected by hand (`PAGE_FIX` in assemble.py). Nine documents the finder cannot read are estimated by eye (marked ≈; see their notes). **Raw** is the finder's count before all of this. A **music page** has at least one music staff; the rest (title pages, covers, blank or ruled-only pages, calibration targets) are left out.

Encodings: **dataM** = paired with Philhar's LilyPond for training; **dataT** = the Madrid test set, paired the same way; **OSSQ** = OSSQ-OMR/OpenScore encoding; **Philhar LilyPond, not paired** = an encoding of the work exists in `boccherini-quartet-data/lilypond` (Op. 2–33, G 159–212) but this source has not been paired with it; **none** = no encoding of the work.

| G | Opus | Library, shelfmark | Hand | Format | Pages | Music pages | Staves | Raw | Encoding | Note |
|---|---|---|---|---|--:|--:|--:|--:|---|---|
| 159 | Op. 2 no. 1 | D-B SA 3364 | copyist | PDF | 21 | 16 | 200 | 212 | Philhar LilyPond exists, not paired | Shelfmark SA 3364 per the SBB title; not in RISM. |
| 159 | Op. 2 no. 1 | D-Eu Esl VIII 351 | copyist | PDF | 29 | 27 | 211 | 227 | dataM |  |
| 159 | Op. 2 no. 1 | F-Pn MS-202 | copyist | PDF | 33 | 29 | 321 | 325 | Philhar LilyPond exists, not paired | 19th-century copy; a full score. |
| 160 | Op. 2 no. 2 | D-Eu Esl VIII 352 | copyist | PDF | 17 | 15 | 125 | 140 | dataM |  |
| 161 | Op. 2 no. 3 | D-Eu Esl VIII 353 | copyist | PDF | 17 | 12 | 102 | 116 | dataM |  |
| 162 | Op. 2 no. 4 | CZ-Pu 59 R 23 | copyist | PDF | 20 | 15 | 117 | 133 | dataM | Counted once from CZ-Pu_59_R_23.pdf; 550503024_CZ-Pu.pdf is the same 20 pages, and the cover/title/part PDFs split the same pages. |
| 162 | Op. 2 no. 4 | D-Eu Esl VIII 354 | copyist | PDF | 17 | 14 | 111 | 130 | dataM |  |
| 163 | Op. 2 no. 5 | D-Eu Esl VIII 355 | copyist | PDF | 17 | 13 | 113 | 127 | dataM |  |
| 164 | Op. 2 no. 6 | D-Eu Esl VIII 357 | copyist | PDF | 17 | 13 | 100 | 108 | dataM |  |
| 165 | Op. 8 no. 1 | A-ST Mus.ms. 576 | copyist: A-ST 120 | PDF | 1 | 0 | 0 | 6 | Philhar LilyPond exists, not paired | Only one page scanned (vlc f. 1r): a title page with a one-staff incipit, so no music staves counted. |
| 167 | Op. 8 no. 3 | A-ST Mus.ms. 577 | copyist: A-ST 120 | PDF | 4 | 3 | 24 | 48 | Philhar LilyPond exists, not paired |  |
| 168 | Op. 8 no. 4 | F-Pn MS-200 | copyist | PDF | 16 | 11 | ≈244 | 2 | Philhar LilyPond exists, not paired | Bilevel microfilm of two-page openings; the counter finds almost nothing. Counted by eye: 11 openings of music, 244 staves; image 14 repeats image 13 and is not counted. |
| 183 | Op. 22 no. 1 | D-B KHM 563 | copyist: Font, Francisco | PDF | 33 | 16 | 130 | 136 | dataM |  |
| 183 | Op. 22 no. 1 | E-Mc 1/7040-188 bis | copyist | PDF | 40 | 20 | 162 | 235 | dataT (Madrid test set) |  |
| 184 | Op. 22 no. 2 | D-B KHM 564 | copyist: Font, Francisco | PDF | 33 | 16 | 125 | 134 | dataM |  |
| 184 | Op. 22 no. 2 | E-Mc 1/7040-188 | copyist | PDF | 40 | 20 | 157 | 211 | dataT (Madrid test set) |  |
| 184, 185, 186, 188 | Op. 22 no. 2,3,4,6 | F-Pn VMB MS-153 | copyist | PDF | 168 | 89 | 664 | 807 | dataM | Four part files: vc (Gallica) + vn1, vn2, va from an earlier pass. |
| 185 | Op. 22 no. 3 | D-B KHM 565 | copyist: Font, Francisco | PDF | 33 | 24 | 163 | 164 | dataM |  |
| 185 | Op. 22 no. 3 | E-Mc 1/7040-187 | copyist | PDF | 32 | 24 | 168 | 209 | dataT (Madrid test set) |  |
| 186 | Op. 22 no. 4 | D-B KHM 566 | copyist: Font, Francisco | PDF | 33 | 16 | 124 | 134 | dataM |  |
| 186 | Op. 22 no. 4 | E-Mc 1/7040-185 | copyist | PDF | 16 | 8 | 62 | 72 | dataT (Madrid test set) |  |
| 187 | Op. 22 no. 5 | D-B KHM 567 | copyist: Font, Francisco | PDF | 33 | 16 | 128 | 134 | dataM |  |
| 188 | Op. 22 no. 6 | D-B KHM 568 | copyist: Font, Francisco | PDF | 33 | 16 | 126 | 131 | dataM |  |
| 188 | Op. 22 no. 6 | E-Mc 1/7040-186 bis | copyist | PDF | 32 | 16 | 129 | 147 | dataT (Madrid test set) |  |
| 189–194 | Op. 24 | F-Pn MS-1292 | autograph | PDF | 118 | 109 | 775 | 778 | Philhar LilyPond exists, not paired | Full score; pairing was tried (29 of 468 staves kept), not in dataM. |
| 201–206 | Op. 32 | D-B KHM 577 | copyist: Schober | PDF | 161 | 129 | ≈1060 | 925 | dataM | Estimate. The counter misses staves on these dense 11-staff pages: a 20-page eye sample gave 132 staves where it found 106 (x1.25), and 4 of the 20 were blank ruled pages. |
| 202, 204 | Op. 32 no. 2,4 | D-LEm Becker III.12.4 | copyist: Kindscher, Johann Ludwig Gottfried | PDF | 28 | 19 | 301 | 306 | Philhar LilyPond exists, not paired | Full score. |
| 207 | Op. 33 no. 1 | D-B KHM 579 | copyist | PDF | 21 | 18 | ≈140 | 126 | dataM | Estimate. Faint-ink full score, 2 systems of 4 per page; music pages counted by eye x 8, less partial pages. The counter found about two thirds. |
| 207–212 | Op. 33 | F-Po RES-507 (2) | autograph | PDF | 104 | 92 | 637 | 652 | dataM |  |
| 208 | Op. 33 no. 2 | D-B KHM 580 | copyist | PDF | 25 | 22 | ≈172 | 122 | dataM | Estimate, as KHM 579. |
| 209 | Op. 33 no. 3 | D-B KHM 581 | copyist | PDF | 25 | 21 | ≈164 | 113 | dataM | Estimate, as KHM 579. |
| 210 | Op. 33 no. 4 | D-B KHM 582 | copyist | PDF | 17 | 14 | ≈108 | 99 | dataM | Estimate, as KHM 579. |
| 211 | Op. 33 no. 5 | D-B KHM 583 | copyist | PDF | 25 | 21 | ≈164 | 131 | dataM | Estimate, as KHM 579. |
| 212 | Op. 33 no. 6 | D-B KHM 584 | copyist | PDF | 17 | 13 | ≈100 | 89 | dataM | Estimate, as KHM 579. |
| 213 | Op. 39 | D-B KHM 587 | copyist: Schober | PDF | 41 | 30 | 236 | 244 | OSSQ |  |
| 216 | Op. 42 no. 1 | D-B KHM 591 | copyist: Berlin27 (GraunWV) | PDF | 21 | 12 | 103 | 103 | none |  |
| 216 | Op. 42 no. 1 | F-Pn D-11157 | copyist: Picquot, Louis | PDF | 20 | 15 | 99 | 102 | none |  |
| 217 | Op. 42 no. 2 | D-B KHM 593 | copyist: KH 8 (Drosopoulou) | PDF | 21 | 16 | 113 | 116 | none |  |
| 217 | Op. 42 no. 2 | F-Pn D-11158 | copyist: Picquot, Louis | PDF | 22 | 13 | 76 | 82 | none |  |
| 218 | Op. 43 no. 1 | D-B KHM 594 | copyist: Schober | PDF | 27 | 16 | 113 | 120 | none |  |
| 219 | Op. 43 no. 2 | D-B KHM 595 | copyist: Schober | PDF | 33 | 16 | 117 | 121 | none |  |
| 220 | Op. 44 no. 1 | D-B KHM 596 | autograph | PDF | 9 | 8 | 92 | 101 | none |  |
| 220 | Op. 44 no. 1 | D-B KHM 597 | copyist: Schober | PDF | 25 | 16 | 136 | 143 | none |  |
| 221 | Op. 44 no. 2 | D-B KHM 598 | copyist: Schober | PDF | 33 | 24 | 143 | 150 | none |  |
| 222 | Op. 44 no. 3 | D-B KHM 599 | copyist: Schober | PDF | 25 | 16 | 115 | 126 | none |  |
| 223 | Op. 44 no. 4 | D-B KHM 600 | copyist: Schober | PDF | 25 | 16 | 123 | 128 | none |  |
| 223 | Op. 44 no. 4 | F-Po RES-507 (10) | autograph | PDF | 16 | 12 | 115 | 123 | none |  |
| 224 | Op. 44 no. 5 | F-Po RES-507 (11) | autograph | PDF | 18 | 13 | 109 | 114 | none |  |
| 225 | Op. 44 no. 6 | D-B KHM 601 | copyist: Schober | PDF | 25 | 16 | 115 | 120 | none |  |
| 237 | Op. 53 no. 2 | D-B KHM 610 | copyist: Schober | PDF | 17 | 15 | 110 | 116 | none |  |
| 248 | Op. 64 no. 1 | F-Pn Vma ms 1067 (5) | copyist | PDF | 32 | 24 | 331 | 341 | none |  |
| 248, 249 | Op. 64 no. 1,2 | US-Wc M452.A2 B68 Case | copyist | PDF | 48 | 40 | 336 | 337 | none |  |
| 249 | Op. 64 no. 2 | F-Pn Vma ms 1067 (6) | copyist | PDF | 21 | 13 | 130 | 136 | none |  |
| 250–255 | Op. 54 (?) | US-Wc M452.A2 B68 op. 54 Case | copyist | PDF | 85 | 149 | ≈1350 | 549 | none | Estimate. Every image is a two-page opening; counted half by half, with 24 openings corrected by eye; about 10 staves a full page. 8 title openings (part-books), so likely more than one Violino Primo book. Not in opera.json; G 250-255 is the folder's name, unverified. |

**All:** 54 manuscripts, 1840 pages, 1387 music pages (453 left out), **11489 staves** (finder's raw count 10801; the rules removed 396, eye corrections removed 262 net, whole-document estimates added 1346).

## By encoding

| Encoding | Manuscripts | Pages | Music pages | Staves |
|---|--:|--:|--:|--:|
| none | 19 | 523 | 450 | 3826 |
| Philhar LilyPond exists, not paired | 7 | 221 | 187 | 1865 |
| dataM | 22 | 895 | 632 | 4884 |
| dataT (Madrid test set) | 5 | 160 | 88 | 678 |
| OSSQ | 1 | 41 | 30 | 236 |

No encoding of the work: **3826** staves. Work encoded but this source not paired: **1865**. Paired with an encoding (dataM, dataT, OSSQ): **5798**.

## By library

| Library | Manuscripts | Music pages | Staves | no encoding | encoded, unpaired | paired |
|---|--:|--:|--:|--:|--:|--:|
| D-B | 26 | 559 | 4420 | 1280 | 200 | 2940 |
| F-Pn | 8 | 303 | 2640 | 636 | 1340 | 664 |
| US-Wc | 2 | 189 | 1686 | 1686 | 0 | 0 |
| F-Po | 3 | 117 | 861 | 224 | 0 | 637 |
| D-Eu | 6 | 94 | 762 | 0 | 0 | 762 |
| E-Mc | 5 | 88 | 678 | 0 | 0 | 678 |
| D-LEm | 1 | 19 | 301 | 0 | 301 | 0 |
| CZ-Pu | 1 | 15 | 117 | 0 | 0 | 117 |
| A-ST | 2 | 3 | 24 | 0 | 24 | 0 |

## By opus

| Opus | Manuscripts | Music pages | Staves | no encoding | encoded, unpaired | paired |
|---|--:|--:|--:|--:|--:|--:|
| Op. 2 | 9 | 154 | 1400 | 0 | 521 | 879 |
| Op. 8 | 3 | 14 | 268 | 0 | 268 | 0 |
| Op. 22 | 12 | 281 | 2138 | 0 | 0 | 2138 |
| Op. 24 | 1 | 109 | 775 | 0 | 775 | 0 |
| Op. 32 | 2 | 148 | 1361 | 0 | 301 | 1060 |
| Op. 33 | 7 | 201 | 1485 | 0 | 0 | 1485 |
| Op. 39 | 1 | 30 | 236 | 0 | 0 | 236 |
| Op. 42 | 4 | 56 | 391 | 391 | 0 | 0 |
| Op. 43 | 2 | 32 | 230 | 230 | 0 | 0 |
| Op. 44 | 8 | 121 | 948 | 948 | 0 | 0 |
| Op. 53 | 1 | 15 | 110 | 110 | 0 | 0 |
| Op. 54 (?) | 1 | 149 | 1350 | 1350 | 0 | 0 |
| Op. 64 | 3 | 77 | 797 | 797 | 0 | 0 |

## Left out

- `G159-164/190027176_S-Skma`: catalogued as a manuscript, but it is the Hummel print (archive correction)
- `found/BnF/btv1b7400136t`: marked not-a-quartet
- Op. 48 (G 226–231): excluded as asked.
- Prints: every item the archive classes as print.

