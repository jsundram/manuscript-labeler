# Philhar's string manuscripts: scans and LilyPond, ready to pair (2026-10-20)

The survey (`reports/2026-10-20-philhar-site/`) found 18 works on Philhar's
archived site that he encoded from manuscript string parts with a scan
online. This folder fetches the ones for violin, viola and cello only, gets
their scans from the libraries, makes his LilyPond readable by
`experiments/zeus/philhar.py`, and maps every page. Nothing is paired yet:
the pairing code is being changed by another job. The last section says what
pairing these sources needs.

**In short:** 14 works kept, 4 left out. 10 manuscript sources fetched,
386 pages, about 2,050 staves of parts plus a 750-staff score. All 14
encodings read: bar events for every part and movement (134 readings).
314 MB of scans, 16 MB of LilyPond.

## Works kept and left out

| Works | Scoring | Kept? |
|---|---|---|
| Boccherini, 6 Trios op. 4, G. 83-88 | 2 vl, vc | **kept** (6) |
| Campioni, 6 Duos op. 7 | vl, vc | **kept** (6) |
| Giardini, Duet in F | vl, vc | **kept** (1) |
| M. Haydn, Quintet in F, MH 411 | 2 vl, 2 va, vc | **kept** (1) |
| J. Haydn, Baryton Trios Hob. XI:25-27 | baryton, va, vc | left out (3): the baryton |
| L. Hofmann, Divertimento in D | 2 vc, b | left out (1): a bass part ("Basse"; RISM: b) |

- **Manuscript only.** Op. 4 also names two prints (Venier 1768, Hummel
  1783) and Campioni names Bremner's print: no print was fetched. Sibley's
  record of the op. 4 parts also holds a bound-with print (G. 89-94); its
  "(print)" files are left out.
- **The op. 4 bass part** in the Sibley copy is headed "Basso". It is the
  cello part (RISM: vlc; Philhar: Violoncelle), so it stays.
- Op. 22 and op. 24 (the survey's other manuscript sets) are already ours.

## Sources

Each is one PDF in `~/Data/manuscript-labeler/philhar-mss/<source>/`, with a
`SOURCE.json` (URLs, licence, SHA-256 of the PDF and of each input). Staves
are counted by eye from contact sheets (about ±15%).

| Source | Works | Kind | Hand, date | Pages | Staves | Link | Licence or terms |
|---|---|---|---|---:|---:|---|---|
| D-B KHM 620 | G. 87 | parts | Copyist Schober; ca. 1775-1800 | 13 | 94 | [SBB](https://resolver.staatsbibliothek-berlin.de/SBB000291F800000000) | SBB¹ |
| D-B KHM 621 | G. 88 | parts | Schober | 13 | 80 | [SBB](https://resolver.staatsbibliothek-berlin.de/SBB000291F900000000) | SBB¹ |
| D-B KHM 622 | G. 85 | parts | Schober | 13 | 84 | [SBB](https://resolver.staatsbibliothek-berlin.de/SBB000291FA00000000) | SBB¹ |
| D-B KHM 623 | G. 83 | parts | Schober | 13 | 76 | [SBB](https://resolver.staatsbibliothek-berlin.de/SBB000291FB00000000) | SBB¹ |
| D-B KHM 624 | G. 86 | parts | Schober | 13 | 75 | [SBB](https://resolver.staatsbibliothek-berlin.de/SBB000291FC00000000) | SBB¹ |
| D-B Mus.ms. 2861 | Campioni op. 7, 1-6 | parts | not named; ca. 1780 | 41 | 410 | [SBB](https://resolver.staatsbibliothek-berlin.de/SBB00001DA400000000) | SBB¹ |
| D-Dl Mus.3403-P-513 | MH 411 | parts | not named, a Salzburg copy; ca. 1770-1800 (SLUB: 1799) | 74 | 525 | [SLUB](https://digital.slub-dresden.de/id398103402) | Public Domain Mark 1.0 |
| US-R M351.B664M | G. 83-88 | parts | unknown copyist; 1766 (RISM) or ca. 1775 (Sibley) | 111 | 650 | [UR Research](http://hdl.handle.net/1802/11394) | public domain (UR Research) |
| I-MC 1-C-7 g-l | G. 83-88 | **score** | not named; 1750-1799 | 84 | 750 | [Internet Culturale](http://www.internetculturale.it/opencms/opencms/it/viewItemMag.jsp?id=oai%3Awww.internetculturale.sbn.it%2FTeca%3A20%3ANT0000%3AFR0084-01C07_A-W) | study and research² |
| unknown (IMSLP) | Giardini duet | parts | not named; no date | 11 | 61 | [IMSLP](https://imslp.org/wiki/Duet_for_Violin_and_Cello_in_F_major_(Giardini,_Felice)) | public domain per IMSLP |

¹ Neither SBB's IIIF manifest nor its METS states a licence. SBB's terms
of use put digitised public-domain holdings under the Public Domain Mark;
not confirmed per item. Attribute the Staatsbibliothek zu Berlin - PK.
² Internet Culturale (MiC/ICCU): free for study and research; other reuse
needs the library's permission. IMSLP lists the same scans as public domain.

- **Six hands:** Schober (Berlin, our KHM 577 Op. 32 hand), the
  Campioni copyist, the Salzburg MH 411 copyist, the Sibley op. 4 copyist,
  the Montecassino scorer, and the Giardini copyist.
- **Op. 4 three times over.** G. 83, 85, 86, 87 and 88 exist in three
  manuscripts (Sibley parts, Schober's parts, the Montecassino score), G. 84
  in two. One encoding pairs with all of them.
- **Not one library's own copy:** only Giardini. Its library is unknown;
  RISM's I-Gl M. (3) 22.7 has a different title, so it isn't that. It came
  from IMSLP with the subscriber's session: one file, no captcha, SHA-1
  matched IMSLP's.
- **Image quality.** SBB and SLUB: full-size colour (about 2,500 x 4,100 and
  3,900 x 2,800 px). Sibley: 150 dpi grey with a 300 dpi mask. Giardini: 150
  dpi grey, cropped tight. Montecassino: Internet Culturale serves only
  about 650 x 770 px (some 80 dpi), each page photographed open with the
  facing page's edge in frame. It is the weakest source by far.

## LilyPond

`fetch_lily.py` downloaded the 7 zips not already on disk from the Wayback
Machine (raw `id_` captures, 1.1 s apart) and copied the 7 the survey had
fetched. Each work is in `~/Data/manuscript-labeler/philhar-site/<work>/`
(zip, `unpacked/`, `SOURCE.json` with capture URL and SHA-256).

`adapt.py` builds `philhar-site/lily/<work>/` in philhar.py's layout and
reads every part and movement:

- Renames Philhar's per-work files (`11018-1-V1-1.ily`,
  `13021-1-Cello-1.ily`, `12005-04-Alto2-3.ily`) to `Trame.ily`,
  `Global.ily`, `01-V1-M.ily`, `02-V2-M.ily`, `03-A-M.ily`, `04-Vc-M.ily`,
  and `05-A2-M.ily` for MH 411's second viola. A duo's violin is `01-V1`.
- Makes line endings LF (the op. 4 skeletons are old-Mac CR only).
- Runs `convert-ly` on every file (they are 2.16 to 2.24) up to 2.26.
- Drops `\paper` and `\header` from Global.ily (MH 411's fails in 2.26), and
  turns op. 4's `(add-script m "staccato")` into a symbol.
- Doesn't edit philhar.py. It imports it, widens `FILES` (adds `va2`) and
  `ROMAN` (to VIII) for its own run, and calls `read()`.

**Result:** all 134 part-movement readings give bar events, and every
part covers its movement's bars as the skeleton counts them, with one
exception. Campioni duos 4 and 6, movement III, end with a quarter-note
spacer holding the "Da Capo" text: the skeleton counts it as a bar
(53, 45) and no part plays it. `philhar-site/lily/<work>/check.json` has
each reading; `lily-check.json` the summary.

| Works | Parts | Movements | Bars (skeleton) |
|---|---|---|---:|
| G. 83, 84, 85, 86, 87, 88 | vn1, vn2, vc | 3, 3, 4, 3, 3, 3 | 1,565 |
| Campioni op. 7, 1-6 | vn1, vc | 3 each | 1,061 |
| Giardini | vn1, vc | 3 | 219 |
| MH 411 | vn1, vn2, va, va2, vc | 7 | 923 |

## Page maps

`pagemaps/<source>.json` (made by `pagemaps.py`) gives, by PDF page: which
part each page holds, title and blank pages, where each movement starts
(page, and staff from the top counting staves with music; for the score,
also the system), the hand and date, the works in the source's order, and
the `--pages` string autodetect.py takes. Where SBB and SLUB divide the
parts in their manifests, the part ranges agree. Summary:

| Source | autodetect `--pages` | Notes |
|---|---|---|
| D-B KHM 620 | `2-4:vc,5-8:vn1,9-12:vn2` | p1 cover with a 2-staff incipit; p13 colour chart (all five KHM copies) |
| D-B KHM 621 | `2-4:vc,5-7:vn1,9-11:vn2` | pp8, 12 blank |
| D-B KHM 622 | `2-4:vc,5-8:vn1,9-12:vn2` | |
| D-B KHM 623 | `2-4:vc,6-8:vn1,10-12:vn2` | pp5, 9 part titles; cello's slow movement headed Adagio assai, violins' Largo assai |
| D-B KHM 624 | `2-4:vc,6-8:vn1,10-12:vn2` | pp5, 9 part titles |
| D-B Mus.ms. 2861 | `2-19:vn1,22-39:vc` | each duet starts a page; p20, p40 blank, p41 colour chart |
| D-Dl Mus.3403-P-513 | `2-14:vc,16-30:vn1,32-46:vn2,48-59:va,62-73:va2` | movements in Philhar's order I-VII; title page before each part |
| US-R M351.B664M | `2-37:vn1,39-74:vn2,76-111:vc` | trios in the copy's order G. 83, 86, 84, 85, 87, 88; every movement starts a page but G. 85's finale (staff 8 in vn1 and bass) |
| I-MC 1-C-7 | `1-84:score` | systems of 3 staves; trios VII-XII = G. 83, 86, 87, 84, 88, 85; G. 87 ends and G. 84 starts on f. 66v (p41, systems 2 and 3) |
| Giardini | `2-5:vn1,8-11:vc` | p6 blank; the cello's Adagio heading is cropped off (p9, staff 2) |

## What pairing will need

Nothing below has been changed: it touches philhar.py, autodetect.py,
autopair.py and dataset.py, which another job is editing.

1. **philhar.py**, which autopair calls as a command for every part and
   movement:
   - `FILES` needs `"va2": "05-A2"` (MH 411's second viola).
   - `ROMAN` stops at IV, so `movements()` fails on MH 411's V-VII. It
     needs to go to VII at least.
   - Nothing else: the renamed files are what it expects.
2. **Part names.** Only one is new: `va2`. Duos use vn1 and vc, trios vn1,
   vn2 and vc. autopair already skips a part with no staves, so trios and
   duos fit. `va2` has to be added wherever the four parts are listed:
   - autopair `PARTS`, autodetect `PARTS`;
   - the filters in barcheck, clefread and compare;
   - dataset.py's `parts` (line 739: the labelled-source path only);
   - to review the pairs in the labeler, labels.py `PARTS`, and app.js
     `PARTS` and `DEFAULT_CLEF` (va2: alto).
3. **autodetect, parts:** works as it is, with `--pdf`, `--name <source>`
   and the `--pages` strings above.
4. **autodetect, score (Montecassino):** score mode keeps only 4-staff
   systems and deals parts as `PARTS[k % 4]`. This score's systems have 3
   staves (vn1, vn2, vc). It needs the system's parts as an option. The
   scan is also low-resolution and shows the facing page's edge, so
   detection may need its corners checked. Pair it last, or leave it out.
5. **autopair:** `--philhar ~/Data/manuscript-labeler/philhar-site/lily`.
   Give `--quartets` in each source's order:
   - Sibley: `boccherini-G83,boccherini-G86,boccherini-G84,boccherini-G85,boccherini-G87,boccherini-G88`;
   - Montecassino: `boccherini-G83,boccherini-G86,boccherini-G87,boccherini-G84,boccherini-G88,boccherini-G85`;
   - each KHM copy: its one trio; Mus.ms. 2861: `campioni-op7-1,...,campioni-op7-6`;
   - SLUB: `haydn-m-MH411`; Giardini: `giardini-duo-F`.
6. **Expect disagreements.** Philhar's op. 4 names two prints and two
   manuscripts without saying which his notes follow. His Campioni mixes
   this copy with Bremner's print (`BR:`/`MS:` comments). Bars that differ
   will be dropped, at a cost in yield.
7. **Small traps:**
   - The "Da Capo" spacer bar at the end of Campioni 4/III and 6/III may
     read as a missed bar at the end of the last staff.
   - The KHM covers' 2-staff incipits and the SBB colour charts are left
     out by the page maps; keep them out.
   - The cello parts change clef (bass, tenor, treble); MH 411 has two alto
     clef parts.

**Leads not fetched:** Leipzig Becker III.11.27-28 (G. 88, G. 86, ca. 1768,
digitised), and the Eichstätt and Leipzig copies listed in the survey.

## Files

- `fetch_lily.py`: Philhar's zips from the Wayback Machine, one folder per work.
- `adapt.py`: philhar.py's layout in `philhar-site/lily/`, and the reading check.
- `fetch_scans.py`: the scans, one PDF per source, with SOURCE.json.
- `pagemaps.py`: writes `pagemaps/*.json`.
- `lily-check.json`: the reading check's summary.

Rebuild: `uv run experiments/philhar-mss/fetch_lily.py && uv run experiments/philhar-mss/adapt.py && uv run experiments/philhar-mss/fetch_scans.py && uv run experiments/philhar-mss/pagemaps.py`
(writing to `~/Data` and the network need the sandbox off; hosts:
web.archive.org, content.staatsbibliothek-berlin.de, iiif.slub-dresden.de,
images.iiif.slub-dresden.de, urresearch.rochester.edu, www.internetculturale.it,
imslp.org).

## Cost

Mac (M1) CPU only, no GPU. About 2 hours of wall time: 20 minutes of
downloads (most of it SBB's server, about 8 s an image), the rest reading
pages by eye for the maps. 330 MB downloaded, under the 2 GB limit.
