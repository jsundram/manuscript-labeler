# Philhar's other works, and G. 223 from a print: dataW and dataP (2026-10-21)

Two new groups of manuscripts were paired with an encoding, staff by staff,
to make training staves for the MuSViT reader. Nothing was labelled by
hand. Correctness of each kept staff came first; count second.

- **Group 1, dataW:** fourteen string works on Philhar's archived site
  (Wayback Machine), in their manuscripts: Boccherini's op. 4 trios,
  Campioni's op. 7 duos, the Giardini duet and M. Haydn's MH 411 quintet.
  Scans and LilyPond come from `experiments/philhar-mss/`.
- **Group 2, dataP:** Op. 44 no. 4 (G. 223), whose two manuscripts have no
  encoding. They were paired with the 1952 Bärenreiter print as two OMR
  readers read it, using only the bars where both readers agree
  (`experiments/print-omr/`).

**Result:**
- **dataW: 1,013 staves (7,007 bars) from 9 sources.**
- **dataP: 22 staves (149 bars) from 2 sources.** 14 of the 22 are cut
  after their first bars (below).
- **Montecassino 1-C-7 was skipped** (below).

None of these sources is in any reader's training. So one reader,
musvit-D4 (run D3S-h96), was used, as for G. 213.

## Counts

`counts.py` writes `counts.md`:
- **paired:** the staves `autopair.py` keeps;
- **in the set:** the staves left after `dataset.py`'s checks;
- **bars:** counted in each kept staff's label.

| group | source | works | detected | paired | in the set | bars |
|---|---|---|--:|--:|--:|--:|
| W | D-B KHM 620 (Schober) | G. 87 | 95 | 61 | 44 | 380 |
| W | D-B KHM 621 | G. 88 | 81 | 56 | 40 | 350 |
| W | D-B KHM 622 | G. 85 | 90 | 67 | 54 | 450 |
| W | D-B KHM 623 | G. 83 | 76 | 44 | 41 | 288 |
| W | D-B KHM 624 | G. 86 | 76 | 58 | 53 | 466 |
| W | D-B Mus.ms. 2861 | Campioni op. 7, 1–6 | 494 | 392 | 299 | 1,342 |
| W | D-Dl Mus.3403-P-513 | MH 411 | 586 | 401 | 293 | 2,613 |
| W | US-R M351.B664M (Sibley) | G. 83–88 | 690 | 241 | 185 | 1,089 |
| W | Giardini (IMSLP) | duet in F | 58 | 36 | 4 | 29 |
| W | I-MC 1-C-7 (Montecassino) | G. 83–88 | skipped | | | |
| P | D-B KHM 600 | G. 223 | 122 | 61 | 18 | 134 |
| P | F-Po RES-507 (10), the autograph | G. 223 | 120 | 64 | 4 | 15 |
| | **dataW** | | 2,246 | 1,356 | **1,013** | 7,007 |
| | **dataP** | | 242 | 125 | **22** | 149 |

By part, dataW holds 1,013 staves:
- 395 first violin and 233 second violin;
- 57 viola and 57 second viola (va2), both from MH 411;
- 271 cello.

Sibley's bass part pairs worst: 14 cello staves kept, against 171
violin staves.

## Why staves weren't kept

**Group 1, the pairing** (first reason given, of 890 not kept):

| reason | staves |
|---|--:|
| a measure paired with two bars (a bar line missed, or other barring) | 249 |
| an extra measure (half a bar at a line break, a heading, a scrap) | 146 |
| the staff beside it begins or ends with two bars, an extra measure, or rests | 133 |
| a measure nothing like its bar | 90 |
| beside a bar no staff holds | 90 |
| measures and bar boxes differ, and an end isn't one bar | 68 |
| an end measure shorter (61) or longer (39) than its bar | 100 |
| more bar boxes than measures, the first box narrow (`--head-box`, new) | 14 |

**Group 1, dataset.py** (of 1,356 paired):
- not plain (a bar split across the line, a multi-bar rest): 211
- a measure unlike its bar: 46
- Philhar's clef changes on the staff: 32
- no clef or key drawn (Giardini, not a movement's first staff): 26
- few pitches as the encoding's: 19
- the label failed the read-back check: 3
- notes far off the staff: 2
- durations that don't fill a bar: 2
- two clefs read: 1
- left out by eye: 1

**Group 2, the pairing** (of 117 not kept):
- an extra measure: 46
- a measure paired with two bars: 27
- beside a missed bar: 17
- beside a neighbour's extra or double measure: 10
- end measures too long or short: 12
- unlike: 5

**Group 2, dataset.py** (of 125 paired):
- a bar the print's readers don't agree on, early in the staff: 84
- the reading's key isn't the print's: 9
- the reading wrote another clef, or two: 4
- unlike: 2
- no clef or key drawn: 2
- the time signatures differ: 1
- not plain: 1

By source:
- **Sibley** pairs worst (35% of staves). Its scan is a 150 dpi grey
  image under a 300 dpi black stencil. The levelling detection needs
  (below) thins many bar lines away, so the reader joins bars ("two").
- **Giardini:** the copyist draws clef and key only on a movement's first
  staff. Only those 4 staves are kept.
- **KHM 600 and RES-507 (10):** 61% of the print's measures are agreed. So
  a staff of 12–17 bars rarely has all its bars agreed. The cello loses
  most: its tenor-clef passages and double stops are where the print's
  readers disagree.
- **The key check (RES-507 (10)):** the reader reads the autograph's key
  signature poorly (4 sharps for 1). Most staves it puts out have no key
  drawn at all.
- **KHM 600's Trio:** two of its staves were put out by the key check.
  The copy writes G minor with one flat (−1), where the print has two.

## What changed in the pipeline

Every change is a new option or a new part name. Without them, behaviour
is unchanged. This was checked:
- autopair.py was re-run on A-ST 577 (Philhar) and G213-KHM587
  (MusicXML) with their old options. Both results files are
  byte-identical.
- dataset.py was re-run on SA 3364. Its dataM2 staff list, images and
  labels came out identical.

**Group 1 (Philhar's other works):**
- **`philhar.py`:** `FILES` gains `va2` (`05-A2`, MH 411's second
  viola), and `ROMAN` runs to VIII (MH 411 has seven movements).
- **`va2`** is added wherever the quartet's parts are listed:
  - autopair's `PARTS` (last, so the old order is kept);
  - dataset.py's labelled-source parts, and its viola-and-cello
    far-off-staff check;
  - the part filters of barcheck, clefread and compare.

  The labeler (`labels.py`, `app.js`) wasn't changed. Pairing doesn't
  need it, and the UI and saved labels were left alone.
- **`autodetect.py --score-parts vn1,vn2,vc`:** the parts of a score
  system, for three-staff systems. It was made for Montecassino, which
  was then skipped.
- **`autodetect.py --max-staves N`:** leaves out a parts page where
  detection found more than N staves. Its staves are fragments: 15
  Sibley pages give 17–27 even after levelling.
- **`autodetect.py --leave-out 20:0,...`:** leaves out given staves.
  These are KHM 600's three violin cue staves, above the cello on
  pp. 20, 22 and 23.
- **`autopair.py --head-box`:** puts out a staff when two things hold:
  detection found more bar boxes on it than the reading has measures, and
  its first box is under 0.6 of its median box. A movement's pickup is
  exempt.
  - **Found on KHM 620 cello p2-2.** The staff opens with the second half
    of I 14. The reading of p2-1 stretched the first half to seven
    eighths, read as the whole bar, and the reading of p2-2 dropped the
    second half. Both staves paired one-to-one, and p2-2 was labelled
    I 15–21 without the four eighths it opens with.
  - The rule puts out 24 staves in all. The 9 viewed included correct
    ones (a first bar with few notes): a cost in yield, not in
    correctness.
- **`dataset.py --heads-only`:** keeps only a staff that opens a movement.
  This is for a copy that draws clef and key nowhere else (Giardini),
  where the label's clef and key would not be on the image.
- **The sources' trio order:** Sibley's (G. 83, 86, 84, 85, 87, 88) is
  given to `--quartets`. So were Montecassino's, before it was skipped.

**Group 2 (G. 223 from the print):**
- **`autopair.py --print-bars BA2676-G223.json`:** pairs with the print's
  reading (`print-omr/encode.py`). Every measure is paired, agreed or not,
  so the alignment has all of them to hold on to. A bar is (movement,
  measure number).
- **`dataset.py --print-bars`** (`print_pairs`) labels each staff with the
  print's reading of its bars. A staff is kept only if all of these hold:
  - it is plain and within one movement;
  - every bar is agreed (the OSSQ reader and Audiveris read it the same,
    and it isn't a lone bar rest);
  - no measure is more than 0.5 unlike its bar (barring, or tremolos
    written the other way);
  - the manuscript's reading names at least half the print's pitches, on
    the staff and in every bar of 3 or more notes
    (`--min-pitch 0.5 --min-bar-pitch 0.5`, which catches an octave);
  - the reading wrote one clef, the one chosen, and the print changes no
    clef there;
  - no viola or cello note is more than 9 steps off the middle line;
  - the reading's key signature is the print's;
  - the reading wrote a time signature in the same measures as the print.

  The label is built from the OSSQ reader's tokens for those print
  measures:
  - stems are dropped;
  - the clef is the one chosen, the key is the print's, and the time is
    written where the print's reader wrote one;
  - read back, the label must give the print's events, bar for bar.
- **Whole staves, or cut ones (`--cut-agreed 3`):** the brief allowed a
  staff to be kept for its agreed bars only if the dataset can cut single
  bars cleanly. It can't cut a bar out of the middle: the piece would
  have no clef or key. **So a staff whose bars aren't all agreed is left
  out**, with one exception:
  - when its first 3 or more bars are agreed, and detection's bar boxes on
    it are as many as the reading's measures, the image is cut at the bar
    line ending those bars, 0.3 staff space past it;
  - the cut keeps the staff's own clef and key at its head;
  - 14 of dataP's 22 staves are cut. All were viewed, and each ends
    cleanly at its bar line.
- **`dataset.py --heads-only`** is used for RES-507 (10) too. Boccherini's
  autograph parts draw clef and key only on a movement's or section's
  first staff (the others open with a double stroke). Only staves with a
  time signature in their first measure are kept.

**Contact sheets (`philhar-repair/contact.py`)** gain three options:
- `--lily`: Philhar's folder;
- `--print-bars`: the print's measures as text, marking those not agreed;
- `--labels DIR`: each staff as the staff set has it (cut, if it was cut),
  under it its label bar by bar.

## The sources

| list | file | pages |
|---|---|---|
| D-B_KHM-620 … 624 | `~/Data/manuscript-labeler/philhar-mss/D-B_KHM-62n/D-B_KHM-62n.pdf` | the page maps' `autodetect_pages` |
| D-B_Mus.ms.2861 | `.../D-B_Mus.ms.2861/D-B_Mus.ms.2861.pdf` | `2-19:vn1,22-39:vc` |
| D-Dl_Mus.3403-P-513 | `.../D-Dl_Mus.3403-P-513/D-Dl_Mus.3403-P-513.pdf` | `2-14:vc,16-30:vn1,32-46:vn2,48-59:va,62-73:va2` |
| US-R_M351.B664M | `.../US-R_M351.B664M/US-R_M351.B664M-levels.pdf` (made from the library's PDF, below) | `2-37:vn1,39-74:vn2,76-111:vc`, `--max-staves 12` |
| unknown_IMSLP-PMLP122408 | `.../unknown_IMSLP-PMLP122408/unknown_IMSLP-PMLP122408.pdf` | `2-5:vn1,8-11:vc` |
| G223-KHM600 | `~/Dropbox/Code/boccherini-sources/digitizations/G223/463060000_D-B/463060000_D-B.pdf` (read only) | `2-5:va,8-11:vn1,14-17:vn2,20-23:vc`, `--leave-out 20:0,22:0,23:0` |
| G223-RES507-10 | `.../G223/btv1b525026043/btv1b525026043.pdf` (read only) | `2-4:vn1,6-8:vn2,10-12:va,14-16:vc` |

`sources.txt` holds these, with each source's works in its own order.

Notes on the sources:
- **G. 223's page maps were found by eye** from contact sheets of every
  page.
  - KHM 600: the viola part comes first, with the full title. Each
    part's Trio is on its own page (5, 11, 17, 23). Pages 6, 12, 18 and
    24 are blank; 25 is the colour chart.
  - RES-507 (10): four parts of three pages, each after a title page
    (1, 5, 9, 13).
- **Sibley needed levels.**
  - Detection on the library's PDF found 1,543 "staves", most of them
    half a staff high. The staff lines are grey, about 6 px thick at the
    2,800 px render, and spaced 26 px. Detection took them for twice as
    many lines.
  - The fix: each page rendered at 2,800 px with black at 90 and white at
    150 (`philhar-repair/levels.py`). That leaves thin line cores.
  - Detection then finds 990 staves, and 690 after `--max-staves 12`.
    The estimate was 650.
  - Two settings were tried on two pages first. 110/210 changed nothing.
    60/115 lost half the staves.
- **Montecassino (I-MC 1-C-7) was skipped.** Detection with
  `--score-parts vn1,vn2,vc` and the layouts `9:0-2,3-5,6-8;10:0-2,3-5,6-8|1-3,4-6,7-9`
  found 9 staves on 6 of 8 test pages. But three things defeat it:
  - the images are about 650 × 770 px, so a staff space is about 5 px and
    every crop is blurred;
  - detection cut some staves short (p3, violin I);
  - continuation systems draw no clef or key, so every label would write
    a clef and key that the image lacks.

  It wasn't read, so it cost nothing on Modal.

## Checked by eye

Contact sheets of kept staves, each with its label bar by bar and the
encoding's first and last bar:
- **Viola, va2 and cello, every source:**
  - every third staff for the KHM copies, Giardini and Sibley;
  - every eighth for Mus.ms. 2861 (153 cello staves) and MH 411 (166
    viola, va2 and cello staves);
  - about 70 staves in all.
- **Violins:** every twelfth staff of Sibley, MH 411 and Mus.ms. 2861,
  every fifth of KHM 620, and all of Giardini's.
- **dataP:** all 22 staves, cut and whole, against the print's text.
- **Staves with more bar boxes than measures** (KHM 620, 621): all 11.
  One was wrong, KHM 620 p2-2, which led to `--head-box`. The rest have a
  custos or end marks after the last bar line.
- **Staves `--head-box` put out:** 9 of 24.
- **Not kept:** every 25th Sibley staff (joined bars, where levelling
  thinned the bar lines) and the print path's notes for every staff.

What the checks found and changed:
- **Giardini:** continuation staves have no clef or key, but the labels
  wrote them. Fixed with `--heads-only` (from 23 staves to 4).
- **RES-507 (10):** the same, fixed with `--heads-only` (from 6 staves
  to 4).
- **Mus.ms. 2861 p37-5** opens with a C clef and key before the bass clef
  the label writes alone. It was dropped by eye (`drop/D-B_Mus.ms.2861.txt`).
- **KHM 620 p2-2:** the label was short of the music shown; fixed with
  `--head-box`.

Nothing else viewed was found wrong.

Not fixed, and worth knowing:
- **A clef at a line's end.** Where the copy writes the next line's
  clef at the end of a staff (MH 411 cello p4-6, p13-6), the label
  doesn't have it.
- **Print labels follow the print.** In dataP, slurs, articulation,
  beaming and accidentals are the print's (Upmeyer 1952), as read by the
  OSSQ reader. Only notes, rests, durations, dots, graces and pitches were
  agreed by the two readers and checked against the manuscript's reading.
  dataM's accidentals follow Philhar's engraving the same way.
- **dataM2 has the defect `--heads-only` fixes here.** F-Pn_RES-507-2
  (Op. 33, Boccherini's autograph parts) draws clef and key only on a
  movement's first staff, the same as RES-507 (10). Its dataM2 labels
  write them on every staff: p11-6, for one, has neither drawn. dataM2
  wasn't changed here.
- **Sibley's images in dataW are levelled.** They look nearly bitonal,
  unlike the other sources.

## Cost

- **Modal: about $0.31**, from the billing report for this run's four
  apps:
  - G. 223's two manuscripts, 242 staves: $0.04;
  - KHM 620–624, Mus.ms. 2861 and MH 411, 1,498 staves: $0.23;
  - Giardini, 58 staves: $0.01;
  - Sibley, 690 staves: $0.04.

  These were readings only, on L4, one app at a time.
- **Mac (M1, shared with other work), one heavy process at a time:**
  - bar-line prediction: about 50 minutes, Sibley three times;
  - detection: about 50 minutes;
  - pairing: about 40 minutes, done twice once `--head-box` was added;
  - staff sets: about 15 minutes.

## Where things are

- **Staff sets:**
  - `~/.cache/manuscript-labeler/zeus/dataW/` and `.../dataP/`, one
    `samples.<source>.txt` per source;
  - on Modal at `/dataW` and `/dataP` in `musvit-staves`;
  - registered in `docs/storage.md`.
- **Detections:** `experiments/zeus/auto/<source>.json`.
- **Readings:** `answers/<source>-auto-musvit-D3S-h96.json`.
- **Pairings:**
  `results/autopair-<source>-any-count-neighbours-paired-short-ends-long-ends-head-box-musvit-D3S-h96.json`.
- **This folder:**
  - `sources.txt`, `detect.sh`, `build.sh`, `counts.py`, `counts.md`;
  - `drop/` (staves left out by eye);
  - `logs/` (autodetect, autopair, dataset).

## Rebuild

    E=~/Dropbox/Code/boccherini-opus-48; M=~/Data/manuscript-labeler/philhar-mss
    B=~/Dropbox/Code/boccherini-sources/digitizations/G223
    # Sibley levelled for detection (2,800 px, black 90, white 150)
    uv run experiments/zeus/philhar-repair/levels.py $M/US-R_M351.B664M/US-R_M351.B664M.pdf $M/US-R_M351.B664M/US-R_M351.B664M-levels.pdf 90 150
    uv run --with markdown-it-py tools/predict_barlines.py $E --pdf <each PDF in sources.txt>
    # the bar-line filter cache, as for print-omr: copied, not retrained
    for s in <each source>; do mkdir -p experiments/zeus/auto/cache/$s; cp -R experiments/zeus/auto/cache/Op02-1-SA3364/models experiments/zeus/auto/cache/$s/; done
    zsh experiments/zeus/wayback-print-pairs/detect.sh            # autodetect.py, every source
    uv run experiments/musvit/read_auto.py --run D3S-h96 --file reader.pt <each source>   # Modal, L4
    zsh experiments/zeus/wayback-print-pairs/build.sh pair        # autopair.py
    zsh experiments/zeus/wayback-print-pairs/build.sh data        # dataset.py -> dataW, dataP
    uv run experiments/zeus/wayback-print-pairs/counts.py > experiments/zeus/wayback-print-pairs/counts.md
    cd experiments/zeus   # contact sheets, e.g.:
    uv run philhar-repair/contact.py results/autopair-SRC-...-head-box-musvit-D3S-h96.json /tmp/sheet \
        --list ~/.cache/manuscript-labeler/zeus/dataW/samples.SRC.txt --labels ~/.cache/manuscript-labeler/zeus/dataW \
        --lily ~/Data/manuscript-labeler/philhar-site/lily --part va va2 vc --every 3
    uv run philhar-repair/contact.py results/autopair-G223-KHM600-...json /tmp/sheet --print-bars ../print-omr/G223/BA2676-G223.json \
        --list ~/.cache/manuscript-labeler/zeus/dataP/samples.G223-KHM600.txt --labels ~/.cache/manuscript-labeler/zeus/dataP
    modal volume put musvit-staves ~/.cache/manuscript-labeler/zeus/dataW /dataW
    modal volume put musvit-staves ~/.cache/manuscript-labeler/zeus/dataP /dataP

Writing to `~/.cache` and `~/Data`, and the Modal calls, run outside the
sandbox.
