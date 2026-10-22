# Philhar's encodings, paired again: dataM2 (2026-10-20)

Philhar's LilyPond covers Op. 2–33 (G 159–212). dataM and dataT were made
by pairing manuscripts with it, before the G. 213 work improved the
pipeline. This is that pairing done again with the current pipeline and
the musvit-D4 reader, plus the seven sources the census found encoded
but never paired. Nothing was labelled by hand. Correctness of each kept
staff came first; count second.

**Result:** `dataM2` holds **3,624 staves (20,838 bars)**, against 2,816
staves (16,892 bars) in dataM and dataT. That is +808 staves, +29%.
- The re-paired old sources give fewer staves than before: 2,466
  against 2,774. The new rules and a second reader put out staves
  whose labels were wrong, and many that were right.
- The full scores and new copies give 1,158, where dataM had 42: the six
  Op. 33 scores (KHM 579–584) 522, Op. 24 (MS-1292) 282, Op. 2/1 (SA
  3364 134, MS-202 131), Op. 32 (D-LEm) 69, Op. 8 (MS-200 18, A-ST 577
  2).

## Sources

| list | source | file | pages |
|---|---|---|---|
| F-Pn_RES-507-2 … Op32-G201-206, Op22-*-EMc | dataM's and dataT's sources | as before (`auto/<source>.json`) | as before |
| Op33-n-G20x-score | D-B KHM 579–584, Op. 33 full scores | `boccherini-quartet-data/manuscripts/Boccherini G.20x - Opus 33 Number n - Manuscript.pdf` | as before, now `:score` with `--score-layout "10:0-3,5-8\|1-4,6-9"` |
| F-Pn_MS-1292-score | F-Pn MS-1292, Op. 24 autograph, full score | `boccherini-quartet-data/manuscripts/Boccherini G.189-194 - Opus 24 Number 1-6 - Manuscript - France.pdf` (the archive's btv1b10537292r) | `2-118:score`, layout `10:0-3,5-8\|1-4,6-9` |
| Op32-DLEm | D-LEm Becker III.12.4, Op. 32 nos. 2 and 4, full score | `digitizations/G202_204/225003122_D-LEm/225003122_D-LEm.pdf` | `6-14:score,16-25:score`, layout `16:0-3,4-7,8-11,12-15`, `--score-margin 0.07` |
| Op02-1-MS202 | F-Pn MS-202, Op. 2 no. 1, full score | `digitizations/G159/btv1b10863131t/btv1b10863131t.pdf` | `5-32:score`, layout `14:0-3,5-8,10-13;15:1-4,6-9,11-14\|0-3,5-8,10-13` |
| Op02-1-SA3364 | D-B SA 3364, Op. 2 no. 1, parts | `digitizations/G159/PPN1935497081_D-B/PPN1935497081_D-B.pdf` | `3-6:vn1,7-10:vn2,11-14:va,15-18:vc` (found by eye; p21 repeats p4 under a colour chart, left out) |
| Op08-3-AST577 | A-ST Mus.ms. 577, Op. 8 no. 3 | `digitizations/G167/650004089_A-ST/650004089_A-ST.pdf` | `2-3:va` |
| Op08-4-MS200 | F-Pn MS-200, Op. 8 no. 4, full score, microfilm of two-page openings | `~/Data/manuscript-labeler/zeus/ms200/F-Pn_MS-200-levels.pdf` (made from `digitizations/G168/btv1b10076417z`, below) | `1-22:score`, layout `12:0-3,4-7,8-11;8:0-3,4-7` |

Some notes on these sources:
- **MS-1292 holds Op. 24 nos. 1, 3, 4, 5 and 6, in that order.** No. 2
  isn't in it. Page 51 is headed "Quartetto 4°"; the movement starts the
  reading found (key, metre, tempo words) fix the rest. Paired in the
  order Op. 2/1–6, it kept 183 staves; in this order, 371.
- **A-ST 577:** page 4 is the cello's title page. Pages 2–3 are
  Op. 8/3's Largo, Allegro and Minuetto, in a C clef. Page 1 is an
  Allegro that Op. 8/3 doesn't have, so it was left out. **A-ST 576** is
  one title page, with no music.
- **MS-200:** each image is a two-page opening. Openings 3–13 were cut in
  half with a PDF CropBox, giving 22 pages. Each page was then rendered
  at 2,800 px with its levels set (black 170, white 225). The film's
  paper is grey, about 230. Its staff lines, about 200, are lighter than
  detection's dark threshold of 175, so it found no staves at all.
  After levelling, 9 of the 22 pages show exactly 12 ruled staves. The
  others show 11 or fewer: a staff is missed. So detection is still
  unreliable on this film. Its 18 staves are kept, but treat them as
  less certain.

## What changed in the pipeline

Every change is a new option. Without it, behaviour is unchanged.

- **`autodetect.py --score-layout`** groups score pages by their ruling.
  - **The problem:** detection's empty-staff test drops sparse staves (a
    few rests, about 0.1–0.7% ink between the lines). That left a system
    with three staves, and the old grouping by gaps then lost all four.
    It found 272 of the six Op. 33 scores' roughly 850 staves, and 468
    of MS-1292's 856.
  - **What it does:** on score pages, the empty-staff test is off, so
    every ruled staff is found. The layout then names which ruled staves
    make each system, for a page with a given number of them. The staves
    left over must be empty (under 1% ink). Of the layouts that pass,
    the one with the least ink on its leftover staves is taken. Any
    other page is left out and logged.
  - **What it drops:** a staff mostly outside the page's median left and
    right ends (the facing page); a stub under a tenth of that width (a
    title); and, with `--score-margin`, a "staff" at the image's top or
    bottom edge (D-LEm's library heading and footer band).
  - **Gain:** Op. 33's six scores now give 864 staves, and MS-1292 856.
- **`autopair.py --neighbours-paired`.** `--neighbours` put out a staff
  when the staff beside it began or ended with an extra measure. Most of
  the staves it put out stood beside an empty staff with a heading
  ("Minuetto", "Violino Primo", "Siegue Menuetto") or a scrap of
  detection, read as one extra measure. With this option, a neighbour
  none of whose measures paired puts no staff out. On the old sources it
  brought back 127 staves of the old sets with the same bars (30 sources;
  Op. 32 wasn't measured without it).
- **`autopair.py --long-ends`.** A staff is put out when its first or
  last measure, paired with a whole bar, reads over 5/4 of that bar's
  length. That is the mirror of `--short-ends`: part of a bar split by
  the line break, read into the next measure.
- **`philhar-repair/both.py`: two readers for the old sources.** musvit-D4
  was trained on dataM and dataT, so its reading of an old staff can
  repeat the old label, right or wrong. Op. 2/2 (D-Eu) p8-5 shows it:
  - the staff ends with half of III 8, and p8-6 opens with the other
    half;
  - dataM had p8-5 holding all of III 8;
  - D4 "read" the whole bar there and dropped the half on p8-6;
  - C4 (`C4-bocch-tf8-L`, trained on Op. 48 alone) read the half on p8-6
    as an extra measure, and the rules put both staves out.

  So for the old sources, a staff is kept only where D4's and C4's
  pairings both keep it, with the same bars and clef. The new sources
  were never trained on, and D4's pairing alone is used there, as for
  G. 213.
- **`dataset.py` (with `--philhar`):**
  - `--clef-checks` leaves out a staff whose clef may change on it.
    That is when Philhar's clef changes within its bars (130 staves),
    the reading wrote two clefs (none), or a viola or cello note lies
    more than 9 steps from the middle line (21). dataM wrote one clef
    on such staves.
  - `--max-unlike 0.5`, as for G. 213.
  - `--min-pitch 0.5` leaves out a staff where the reading names under
    half of the encoding's notes right in the clef chosen. Rhythm alone
    can place a lone bar elsewhere: CZ-Pu cello p2-7, one bar, was paired
    with II 34, but the page shows II 28.
  - `--drop` reads a list of staves to leave out, as for G. 213.
- **`philhar-repair/contact.py`:** contact sheets for Philhar pairings:
  the staff, its bars, and Philhar's first and last bar as text.

## Counts

`counts.py` produces the table below:
- **before:** the staff set the source was in (dataM, or dataT for
  `-EMc`), with the bars of the pairing it was built from;
- **paired:** the staves the pairing keeps (both readers, for old
  sources);
- **dataM2:** after dataset.py's checks.

| source | detected | paired | before: staves | before: bars | dataM2: staves | dataM2: bars | gain |
|---|--:|--:|--:|--:|--:|--:|--:|
| F-Pn_RES-507-2 | 692 | 505 | 448 | 2970 | 401 | 2694 | -47 |
| Op02-1-G159 | 193 | 119 | 116 | 908 | 103 | 824 | -13 |
| Op02-2-G160 | 135 | 96 | 90 | 607 | 75 | 505 | -15 |
| Op02-3-G161 | 107 | 82 | 79 | 588 | 72 | 540 | -7 |
| Op02-4-G162 | 120 | 87 | 86 | 573 | 84 | 562 | -2 |
| Op02-5-G163 | 121 | 100 | 97 | 736 | 82 | 630 | -15 |
| Op02-6-G164 | 100 | 70 | 63 | 520 | 56 | 463 | -7 |
| Op02-4-CZ-Pu-va | 31 | 9 | 14 | 88 | 9 | 55 | -5 |
| Op02-4-CZ-Pu-vc | 25 | 5 | 3 | 17 | 2 | 16 | -1 |
| Op02-4-CZ-Pu-vn1 | 32 | 6 | 8 | 41 | 5 | 25 | -3 |
| Op02-4-CZ-Pu-vn2 | 31 | 14 | 14 | 90 | 11 | 72 | -3 |
| Op22-1-G183 | 131 | 108 | 95 | 468 | 89 | 438 | -6 |
| Op22-2-G184 | 125 | 106 | 80 | 305 | 78 | 295 | -2 |
| Op22-3-G185 | 157 | 136 | 129 | 642 | 115 | 578 | -14 |
| Op22-4-G186 | 125 | 123 | 114 | 562 | 111 | 551 | -3 |
| Op22-5-G187 | 124 | 100 | 94 | 585 | 88 | 559 | -6 |
| Op22-6-G188 | 126 | 109 | 100 | 636 | 99 | 630 | -1 |
| Op22-6-Vmbr153-va | 31 | 18 | 17 | 114 | 15 | 100 | -2 |
| Op22-6-Vmbr153-vc | 51 | 10 | 16 | 87 | 7 | 48 | -9 |
| Op22-6-Vmbr153-vn1 | 34 | 21 | 20 | 112 | 17 | 89 | -3 |
| Op22-6-Vmbr153-vn2 | 53 | 19 | 28 | 144 | 18 | 91 | -10 |
| Op22-Paris-va | 120 | 70 | 64 | 358 | 57 | 328 | -7 |
| Op22-Paris-vc | 144 | 96 | 91 | 480 | 74 | 401 | -17 |
| Op22-Paris-vn1 | 148 | 103 | 92 | 429 | 85 | 403 | -7 |
| Op22-Paris-vn2 | 138 | 90 | 87 | 437 | 80 | 410 | -7 |
| Op32-G201-206 | 931 | 321 | 357 | 2345 | 269 | 1834 | -88 |
| Op33-1-G207-score | 144 | 106 | 11 | 60 | 81 | 382 | +70 |
| Op33-2-G208-score | 176 | 131 | 0 | 0 | 119 | 569 | +119 |
| Op33-3-G209-score | 168 | 119 | 3 | 12 | 105 | 508 | +102 |
| Op33-4-G210-score | 112 | 72 | 4 | 20 | 51 | 253 | +47 |
| Op33-5-G211-score | 160 | 106 | 20 | 96 | 91 | 481 | +71 |
| Op33-6-G212-score | 104 | 82 | 4 | 16 | 75 | 304 | +71 |
| Op22-1-EMc | 156 | 96 | 85 | 412 | 84 | 407 | -1 |
| Op22-2-EMc | 148 | 95 | 71 | 265 | 69 | 262 | -2 |
| Op22-3-EMc | 197 | 139 | 123 | 612 | 116 | 591 | -7 |
| Op22-4-EMc | 32 | 26 | 18 | 97 | 22 | 113 | +4 |
| Op22-6-EMc | 98 | 83 | 75 | 460 | 73 | 451 | -2 |
| F-Pn_MS-1292-score | 856 | 371 | 0 | 0 | 282 | 1503 | +282 |
| Op32-DLEm | 256 | 96 | 0 | 0 | 69 | 404 | +69 |
| Op02-1-MS202 | 264 | 145 | 0 | 0 | 131 | 528 | +131 |
| Op02-1-SA3364 | 201 | 161 | 0 | 0 | 134 | 824 | +134 |
| Op08-4-MS200 | 108 | 21 | 0 | 0 | 18 | 102 | +18 |
| Op08-3-AST577 | 22 | 2 | 0 | 0 | 2 | 15 | +2 |
| **all** | 7227 | 4374 | 2816 | 16892 | **3624** | 20838 | +808 |

The Op. 33 scores' "before" figures are dataM's lists from the old
detection (`Op33-n-G20x`), which `-score` replaces.

The Madrid copies keep dataT's role. They are separate lists,
`samples.Op22-*-EMc.txt`, so a driver can use or hold them out as it
did dataT. No training list was changed. Op. 48 isn't in dataM2, so the
clean test stays out.

## The old staves, before and after

`before_after.py -both` writes `before-after.json`. Of the 2,774 staves
in dataM and dataT (less the old Op. 33 score lists):
- **2,555** are kept by the new pairing with **the same bars**;
- **none** is kept with other bars;
- **219** aren't kept. Most were put out by a neighbour rule (`--neighbours`, 145 with
  D4 or C4), C4's end-length rules (36), or a slip in the pairing.

dataset.py's clef checks then leave out a further 115 old staves.

Of those that changed, these were checked by eye:
- **The old label was wrong, and the new pipeline leaves the staff out:**
  - Op. 2/1 (D-Eu) p10-4 claims all of I 23. Its line ends with the
    first half, and p10-5 opens with the rest (B4 C5 C5 C5).
  - Op. 2/2 p8-5 ends with half of III 8 (above).
  - Op. 32 (KHM 577) p60-5 is an empty staff under "Dal Capo sino al
    Segno e Fine", labelled as I 48.
  - Op. 32 p53-6 is a scrap of detection, a clef and key only,
    labelled as two bars.
  - Op. 32 p77-5 shows repeated eighth-note double stops where Philhar
    writes half notes.
  - Op. 22/3 (KHM 565) cello p3-3 and p3-4 show written-out 16ths where
    the copy abbreviates.
- **The old label was right, and the new pairing slipped but kept
  nothing wrong:**
  - Op. 22 Paris viola p22-6 and p23-0: the new pairing took the last
    measure for two bars, and didn't keep them.
  - CZ-Pu cello p2-7: the new pairing gave II 34, but it is II 28.
    `--max-unlike` and C4's disagreement both leave it out.
- **The other 9 Op. 32 staves whose bars changed** are all not kept now.
  The new pairing slipped there: missed bars around staves detection
  didn't find.

## Why staves weren't kept

The pairing-level reasons, counted by the first reason given, over all
43 sources (2,853 detected staves not kept):

| reason | staves |
|---|--:|
| a measure paired with two bars (a bar line missed, or barring that differs) | 604 |
| an extra measure (half a bar at a line break, a heading, a scrap) | 498 |
| a measure nothing like its bar (the pairing slipped; abbreviations written two ways) | 483 |
| beside a bar no staff holds (a staff detection missed, or a page left out) | 453 |
| measures and bar boxes differ, and an end isn't one bar | 201 |
| the staff beside it begins or ends with two bars, an extra measure, or rests | 402 |
| an end measure shorter (130) or longer (67) than its bar | 197 |
| the second reader chose another clef, or paired other bars | 14 |

Then dataset.py's checks, on the paired staves:
- **not plain** (a bar split across the line, a multi-bar rest): 512;
- **Philhar's clef changes on the staff:** 130;
- **a measure unlike its bar:** 53;
- **few pitches as the encoding's:** 27;
- **notes far off the staff:** 21;
- **durations that don't fill a bar:** 7.

By source:
- **Op. 24 (MS-1292):** most of no. 1's first movement fails as
  "two" and "unlike". Philhar's barring or text differs from the
  autograph there. Nos. 1 (II, III) and 6 pair best.
- **D-LEm:** four pages are left out by the layout (15 or 17 ruled
  staves). The staves beside the bars they hold then fail as "beside a
  missed bar".
- **CZ-Pu:** this copy's movement II has about half as many bars as
  Philhar's ("two" throughout).

## Checked by eye

Contact sheets (`contact.py`) were made of every sample below, each staff
with its bars and Philhar's first and last bar:
- **The Op. 33 scores:** every third viola and cello staff of each of the
  six, about 60 staves. Sheets for nos. 1, 2 and 4 were read staff by
  staff. All agree with their bars. Many of these systems have no clef
  drawn, so the reader's clef is a guess there. The clef written is the
  one under which the notes name Philhar's pitches.
- **MS-1292:** every sixth viola and cello staff (24). All agree with
  their bars. One (p108-6) has a blotted, crossed-out bar.
- **D-LEm:** every third viola and cello staff (12). All agree. The dense
  4×4 pages put a neighbour's ink at the crop edges.
- **MS-202:** every third viola and cello staff (24). All agree.
- **SA 3364:** every fourth viola and cello staff (14). All agree. At the
  sheet's scale, stems look like bar lines; the full page (p15) shows
  five bars of eight eighths, as paired.
- **MS-200:** all 18 staves, and **A-ST 577:** both. They look right at
  the sheet's scale, but the levelled film is hard to read closely.
- **Old staves dropped by the new rules:**
  - 12 beside an "extra" neighbour. Nearly all were right, which led to
    `--neighbours-paired`.
  - 7 that C4 found short-ended. Five were right (a movement's pickup
    bar that C4 read short). Two were abbreviation mismatches.
  - the 13 Op. 32 staves whose bars changed;
  - the changed staves listed above.

Nothing in dataM2 was found wrong, so nothing is dropped by eye
(`--drop`).

Not fixed:
- **Tremolo abbreviations.** Strokes through a stem, as in Op. 33 and
  MS-1292's repeated notes, aren't in Philhar's text. Those staves are
  labelled with the notes as drawn, without the strokes.
- **Clefs that aren't drawn.** Where a system has no clef, the label
  still writes one.

## Cost

- **Modal:** two reading runs on L4 (`read_auto.py --run D3S-h96 --file
  reader.pt`), 4,563 and 2,361 staves. Metered cost went from $101.95 to
  $103.95 (+$2.00) over the run. Other agents' Modal apps (print-omr,
  musvit) ran at the same time. At G. 213's rate (712 staves for about
  $0.10), these readings cost about $1.
- **Local CPU (Mac mini M1, shared with other work):**
  - detection: about 1 hour;
  - pairing: D4 and C4 on 31 old sources, about 25 minutes each pass;
  - staff sets: about 30 minutes.

## Where things are

- **Staff set:** `~/.cache/manuscript-labeler/zeus/dataM2/`, one
  `samples.<source>.txt` per source. On Modal at `/dataM2` in
  `musvit-staves`.
- **Detections:** `experiments/zeus/auto/<source>.json` (new:
  `*-score`, `Op32-DLEm`, `Op02-1-MS202`, `Op02-1-SA3364`,
  `Op08-4-MS200`, `Op08-3-AST577`).
- **Readings:** `answers/<source>-auto-musvit-D3S-h96.json`.
- **Pairings:**
  `results/autopair-<source>-any-count-neighbours-paired-short-ends-long-ends-<reader>.json`.
  Two-reader merges are `results/autopair-<source>-both.json`.
- **dataset.py logs:** `philhar-repair/logs/`.
- **Counts:** `counts.md`.

## Rebuild

    E=~/Dropbox/Code/boccherini-opus-48; Q=~/Dropbox/Code/boccherini-quartet-data/manuscripts
    B=~/Dropbox/Code/boccherini-sources/digitizations; M=~/Data/manuscript-labeler/zeus/ms200
    # MS-200: openings 3-13 cut in half (a pypdf CropBox), then levelled (rendered at 2800 px, black 170, white 225)
    uv run experiments/zeus/philhar-repair/halves.py $B/G168/btv1b10076417z/btv1b10076417z.pdf $M/F-Pn_MS-200-pages.pdf 3 13
    uv run experiments/zeus/philhar-repair/levels.py $M/F-Pn_MS-200-pages.pdf $M/F-Pn_MS-200-levels.pdf 170 225
    uv run --with markdown-it-py tools/predict_barlines.py $E --pdf <each new PDF>
    K="10:0-3,5-8|1-4,6-9"
    uv run --with markdown-it-py experiments/zeus/autodetect.py $E --pdf "$Q/Boccherini G.207 - Opus 33 Number 1 - Manuscript.pdf" \
        --name Op33-1-G207-score --pages 3-20:score --score-layout $K          # likewise G208 3-24, G209 3-23, G210 3-16, G211 3-23, G212 3-15
    uv run --with markdown-it-py experiments/zeus/autodetect.py $E --pdf "$Q/Boccherini G.189-194 - Opus 24 Number 1-6 - Manuscript - France.pdf" \
        --name F-Pn_MS-1292-score --pages 2-118:score --score-layout $K
    uv run --with markdown-it-py experiments/zeus/autodetect.py $E --pdf $B/G202_204/225003122_D-LEm/225003122_D-LEm.pdf \
        --name Op32-DLEm --pages 6-14:score,16-25:score --score-layout "16:0-3,4-7,8-11,12-15" --score-margin 0.07
    uv run --with markdown-it-py experiments/zeus/autodetect.py $E --pdf $B/G159/btv1b10863131t/btv1b10863131t.pdf \
        --name Op02-1-MS202 --pages 5-32:score --score-layout "14:0-3,5-8,10-13;15:1-4,6-9,11-14|0-3,5-8,10-13"
    uv run --with markdown-it-py experiments/zeus/autodetect.py $E --pdf $B/G159/PPN1935497081_D-B/PPN1935497081_D-B.pdf \
        --name Op02-1-SA3364 --pages 3-6:vn1,7-10:vn2,11-14:va,15-18:vc
    uv run --with markdown-it-py experiments/zeus/autodetect.py $E --pdf $M/F-Pn_MS-200-levels.pdf \
        --name Op08-4-MS200 --pages 1-22:score --score-layout "12:0-3,4-7,8-11;8:0-3,4-7"
    uv run --with markdown-it-py experiments/zeus/autodetect.py $E --pdf $B/G167/650004089_A-ST/650004089_A-ST.pdf \
        --name Op08-3-AST577 --pages 2-3:va
    uv run experiments/musvit/read_auto.py --run D3S-h96 --file reader.pt <every source in sources.txt>   # Modal, L4
    cd experiments/zeus
    # each source of sources.txt ("source quartets ..."), with D4; and the old ones (third column not "-",
    # not -score) also with C4 (its readings: answers/<source>-auto-musvit-C4-bocch-tf8-L-best.json)
    for reader in musvit-D3S-h96 musvit-C4-bocch-tf8-L-best; do
      UV_PYTHON_INSTALL_DIR=~/.cache/manuscript-labeler/zeus/py uv run --python-preference only-managed autopair.py $E \
        --source SRC --philhar ~/Dropbox/Code/boccherini-quartet-data/lilypond --quartets QUARTETS --model /nonexistent/$reader \
        --any-count --neighbours --neighbours-paired --short-ends --long-ends
    done
    uv run philhar-repair/both.py <the old sources>
    zsh philhar-repair/build.sh                     # dataset.py for every source -> dataM2
    uv run philhar-repair/counts.py > philhar-repair/counts.md
    uv run philhar-repair/before_after.py -both <the old sources>
    uv run philhar-repair/contact.py results/autopair-SRC-...json /tmp/sheet --list ~/.cache/.../dataM2/samples.SRC.txt --part va vc --every 3
    modal volume put musvit-staves ~/.cache/manuscript-labeler/zeus/dataM2 /dataM2

Writing to `~/.cache` and `~/Data`, and the Modal calls, run outside the
sandbox.
