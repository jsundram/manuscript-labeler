# OSSQ-OMR's quartet staves, rebuilt for MuSViT (2026-10-20)

OSSQ-OMR (Kim, Liu, Valero-Mas, Jeong, ISMIR 2026) pairs 96 printed quartet
scores from IMSLP with corrected encodings: 45,212 scanned staff images in
the paper. The images aren't published yet (the Zenodo and Hugging Face
links are still TODO). This rebuilds them on Modal from what is published,
as staff strips with our LMX, for stage 1 or replay. See
`docs/ismir2026-papers.md` (P13-3) for why.

## How the scans are obtained

- **The scans aren't in any repo.** `ossq-omr` tracks the MuseScore sources,
  the corrected MusicXML and per-score metadata only.
- **omrdp downloads them from IMSLP.** Its `crawl_imslp.py` first scraped
  each score's direct PDF URL from IMSLP's wiki. It then downloaded them
  with plain `requests`, sleeping 30–60 s between files and switching
  NordVPN country every 10 files to dodge IMSLP's download limits.
- **The URLs it found are published.** `data/scores_w_url.yaml` (ossq-omr)
  has a direct mirror URL for every score
  (`vmirror.imslp.org`, `s9.imslp.org`, `ks15.imslp.org`, ...).
- **Those URLs need no login, cookies or browser check.** They served PDFs
  to a Modal container with an honest User-Agent (2026-10-20). The wiki and
  `api.php` are what sit behind IMSLP's browser check (`ossq_fetch.py`), not
  the file mirrors.
- **We fetch each file once,** one at a time, 15 s apart, into our own
  `ossq-raw` volume. The fetch stops after three refusals in a row. No VPN.

## How omrdp pairs encodings with scans, and cuts staves

- **Pages:** each PDF rendered at 300 dpi (pdfplumber). Only the pages that
  `sq<id>_scanned.csv`'s first line names (for example `6:8`).
- **Systems:** a YOLO detector, `ls-yolo-system-v3.0.0`
  ([MALerLab/ls-yolo](https://github.com/MALerLab/ls-yolo) releases), then
  omrdp's box merging. Thresholds are per score, in
  `images/scanned/sq<id>_yolo_infos.yaml` (usually confidence 0.30, merge 0.7).
- **Staves:** a second YOLO finds the staff height on the left half of each
  system. The system is shrunk so a staff is 18 px. A third YOLO
  (`ls-yolo-staff-bbox-v1.0.1`) finds the four staves and labels them
  violin, violin, viola, cello.
- **Pairing:** by order. The encoding's system breaks were edited to match
  the scan. So once the boxes listed in `yolo_infos`' `ignores` are dropped,
  system *k* of the encoding is the *k*-th box left. If the counts differ,
  omrdp skips the score. The CSV's rows are notes made while aligning, in
  several forms (bar counts with `x` for an ignored box, systems per page,
  `n`, `a`); omrdp reads only its first line.
- **Labels:** their LMXE, per system and per part.
- **Headless on Linux?** Yes for the scans: nothing in that path needs
  MuseScore. The synthetic renders need MuseScore 3.6.2 (ossq-omr's README
  insists on that version). Its Linux AppImage runs once extracted, under
  Xvfb, because it ships only Qt's xcb plugin.

## What we build differently

1. **Staves at full resolution.** omrdp's part images are cut from systems
   shrunk to an 18 px staff: 57–73 px tall. We use their boxes but cut each
   staff from the 300 dpi page. We save it 256 px high, grey JPEG, like our
   public staves.
2. **Pairing as omrdp does it, plus what checks we can make.** The score is
   skipped unless we find exactly as many systems as the encoding has. Each
   system must have exactly four staves. Where a CSV's notes list every box
   as a bar count or `x` (10 scores), each system's bar count is checked
   against them too. Failures are dropped and counted.
3. **Our LMX, not their LMXE.** Each part's systems are sliced from the
   corrected `sq<id>_cleaned.musicxml` (omr-dev 7a17e45; it was updated
   after the last `.mscx` edit). They are encoded with Zeus's LMX encoder at
   Zeus's pin, as `experiments/zeus/dataset.py` writes our labels:
   - no stems;
   - key and clef on every staff;
   - time only where the music has it.

   Tokens our reader's vocabulary (musvit-D3's 137) lacks are handled two
   ways. A mark (articulation, stem, beam:continue, ...) is dropped and the
   staff kept. Anything that changes pitch or rhythm (a key of six sharps,
   5/4, an unknown tuplet) drops the staff. Staves with hidden objects are
   dropped too. All of this is counted in each manifest.
4. **The ids are theirs.** Their segment `sq7070781:0006:0003:1` is our
   `scanned/sq7070781/0006-0003-1`, so their splits apply as they are.

## Output (volume `musvit-staves`, under `/staves/ossq/` only)

- `scanned/sq<id>/<page>-<system>-<part>.jpg` and `.lmx`, plus
  `manifest.json`. The manifest has, per staff, its page box at 300 dpi, the
  staff height in px, its class, bar count and any dropped marks. It also
  has every drop reason, counted.
- `synthetic/sq<id>/...` in the same layout: MuseScore's render of the
  corrected `.mscx`, paired by order as omrdp pairs it. Kept separate; it
  may not be used.
- `manuscript/sq<id>/...`: **TEST ONLY**, and empty for now. omrdp never
  cut the manuscripts (there is no CSV or `yolo_infos` for them).
  - Only Andrée, Maier and Mayer A were tried. Hensel's scan is 1,000 px.
    Mayer E minor is a pencil draft laid out unlike the encoding. Mayer D's
    manuscript is a piano duet.
  - They're paired by order only if the systems found with four staves are
    exactly as many as the encoding's.
  - omrdp's print-trained detectors found 154 of Andrée's 161 systems, 14
    of Maier's 50 and 8 of Mayer's 127. So nothing was written, and there
    is no `samples.ossq-manuscripts-TEST.txt` yet.
  - `experiments/zeus/ossq` (the labeler's detection, then dynamic
    programming) is the way to pair them.
- Lists, one key per line (`<dir>/<id>`, relative to `/staves/ossq/`), as
  `proto.py`'s `staves()` reads them:
  - `samples.ossq-scanned.txt`: every scanned staff (training);
  - `samples.ossq-synthetic.txt`: the synthetic renders;
  - `samples.ossq-manuscripts-TEST.txt`: the manuscripts, when they are
    paired (not yet). **Never put it in a training list.**
  - `samples.ossq-scanned-fold{0..4}-test.txt`: the scanned staves of each
    of their score-level test splits.
- `splits.json` (also `experiments/ossq/splits.json`): the works in each
  fold's train, valid, test_scanned and test_synth sets. The data comes
  from sqomr's `metadata/comp_ossq_v2.4.1_unique_vocabs_256_fold*_partwise`.
  - There are five folds. The paper speaks of four; fold0 is the default
    split (`ossq_v2.4.1_256_fold0` in sqomr's README).
  - The five scanned test sets don't overlap: 10, 6, 9, 10 and 12 works.

The raw PDFs (scans in `pdfs/`, MuseScore renders in `synth/`) stay in the
`ossq-raw` volume. Re-cutting them, for example to our 2.5-space crop,
needs no new download.

## Where it runs, and what it costs

- **Modal CPU containers only:** app `ossq-staves`, 4 CPUs and 8 GB each,
  at most 4 at a time. No GPUs.
- **Estimated beforehand:** $1–3. **Spent:** about $0.95 in all (2026-10-20).
  - The fetch: 101 of 102 PDFs, about an hour on one CPU.
  - The synthetic set: 122 scores, about 30 min on 3 containers.
  - The scanned set: 96 scores, about 15 min on 4 containers (3,580
    container-seconds).

## Result (2026-10-20)

| set | scores | staves | the paper's |
|---|---:|---:|---:|
| scanned | 83 of 96 | 37,751 | 45,212 |
| synthetic | 122 of 122 | 51,810 | 52,960 |
| manuscripts | 0 of 3 | 0 | (not given per staff) |

**The scanned set is short by 13 scores:**
- Beach Op. 89: its only scan is behind imslp.eu's disclaimer page, so
  nothing could be fetched.
- Three double-column scans (sq7555331, sq9790696, sq10517302): far fewer
  systems were found than the encoding has. omrdp evidently had these
  pages split first.
- Nine scores are one system off (one too many or one too few). The
  detector runs on CPU here and on GPU there, and the renders may differ
  slightly. Their segment lists (sqomr's TSVs) name the boxes they kept,
  so these could be recovered page by page later.

**The detection agrees with theirs.** Of the 32,676 scanned staves sqomr's
splits list, 27,443 have our exact ids (page, system, part). Nearly all of
the 5,233 others are in the 13 skipped scores. Our 10,308 extra ids are
staves their splits leave out (they keep labels of at most 256 tokens).
Spot checks of labels against images match.

**Why staves were dropped** (scanned / synthetic):
- a hidden object: 364 / 459;
- a token our vocabulary lacks: 9/8 time 167 / 183, six sharps or flats
  124 / 172, 5/4 55 / 68;
- tuplets we don't have: about 110 / 140;
- a percussion clef, which lmx can't encode: 58 / 58;
- not four staves found: 13 / 8.

**Kept but noted:**
- an arpeggio sign dropped (the staff kept): 44 / 94;
- only rests: 258 / 374.

Each score's numbers are in `cut-scanned.json`, `cut-synthetic.json` and
`cut-manuscript.json`. `staff-ids.json` lists every staff written.

**Fold test lists** (scanned staves):
- fold0 3,370
- fold1 5,286
- fold2 4,301
- fold3 5,342
- fold4 4,056

## Commands

```
modal run experiments/ossq/ossq_modal.py::fetch                       # scans, once
modal run experiments/ossq/ossq_modal.py::cut --kind scanned           # or synthetic, manuscript
modal run experiments/ossq/ossq_modal.py::lists                       # samples.*.txt + splits.json
```

`cut-<kind>.json` here records each score's result: staves written, and
what was dropped and why.

## Before training on it

- **Check the overlap with our test material.** Boccherini G.213 (Op. 39) is
  in OSSQ's synthetic set only (it has no scan). Leave it out of anything
  meant to test Boccherini.
- **The crops differ from ours.** Their staff boxes are taller than our
  2.5-space crop: the staff is about a quarter of the strip's height rather
  than 4/9. So the reader sees OSSQ staves smaller at 128 px. The manifest's
  boxes and staff heights allow re-cropping without re-detecting.
- **Training copies only what it uses.** `modal_app.py`'s `train` copies
  only the top folders its sample lists name (2026-10-20), so `ossq/` is
  copied only by a run that trains on it.
- **Check the pairing.** Systems are paired with the encoding by order, so a
  missed system and a spurious one would cancel and shift every label after
  them. Before training, read a sample with musvit-D4 and flag staves whose
  bar count differs from their label's.

## Which staves to use (2026-10-20)

Music from Boccherini's lifetime, ideally 1750–1800, rather than a random
draw. The scanned set's works composed then (dates by catalogue number;
OSSQ doesn't record them):

| composer | works | composed | staves |
|---|---|---|---:|
| Haydn | Op. 1, 9, 20, 64, 74, 76 (24 quartets) | c. 1757–1797 | 7,540 |
| Mozart | K. 80 to K. 590 (12 quartets) | 1770–1790 | 3,344 |
| Beethoven | Op. 18 Nos. 1–6 | 1798–1800 | 2,369 |
| **1750–1800** | | | **13,253** |

That is half again stage 1's 8,765 MusiCorpus staves, so all of it can go
into stage 1, pooled or balanced one to one per pass. The other 24,498
(Beethoven's Op. 59 and late quartets, Cherubini 1814, Arriaga 1823,
Schubert and later) stay out for now. The editions scanned are mostly
19th- and 20th-century engravings: period music, modern print. And it is
the OpenScore corpus our synthetic stage already draws from, so the images
are new to the reader but the music isn't.

## Period staves for stage 1 (2026-10-20)

The 1750–1800 works above, re-cropped to our convention and checked for
label slips. Data only; nothing was trained. Code: `period.py` (app
`ossq-period`, CPU only, at most 4 containers, plus musvit-zeus's
`read_samples` for the check).

**Selected:** 42 scanned scores, 13,253 staves:
- Haydn: all 24 scanned (Op. 1, 9, 20, 64, 74, 76), 7,540 staves.
- Mozart: all 15 scanned, K. 80 to K. 590, 3,344 staves. K. 464 is four
  scores, one per movement.
- Beethoven: Op. 18 Nos. 1–6, 2,369 staves.

**Re-cropped** from the 256 px JPEGs in `ossq/scanned/`, without going
back to the PDFs:
- **Finding the lines:** each strip is split into ~300 px columns. In each
  column, the darkness profile is searched for the best five-line comb
  near the expected space (`staff_px` scaled to the JPEG). The comb must lie
  near the box's middle, and its faintest line must be at least 0.15 darker
  than the spaces between.
- **Straightening:** a line is fitted through the columns that agree, so a
  skewed scan is straightened along the staff, as `staff_crop` does.
- **Crop:** 2.5 spaces above the top line to 2.5 below the bottom one (9
  spaces), so the staff is 4/9 of the height.
  - The box's full width plus one space of white at each end: the JPEG holds
    nothing beyond the box, and the box ends where the staff does.
  - Paper brightened to white by its 90th percentile. Grey JPEG, 256 px high.
- **Result:** 13,241 written, 12 skipped:
  - 9 where too few columns showed five lines;
  - 3 where the columns disagreed.
  - Seven of the 12 are in Haydn Op. 9 No. 1 (sq9961690). The other five
    are one or two per score in four scores. They weren't looked at.
- **Tilt:** 15 staves are tilted 3–4 spaces across their width (skewed
  pages in sq10307350, sq7249986, sq9199617, sq7103818, sq7302710). They
  are kept, straightened. Past 5 spaces a staff would be skipped; none is.
- **White fill:** 192 staves have more than a space of white filled in above
  or below, where the YOLO box stopped short of 2.5 spaces.
- Each score's numbers are in `period-recrop.json`. Each staff's geometry
  (top line, slope, space, columns agreeing, white fill) is in
  `/staves/ossq-period/sq<id>/manifest.json`.

**The crops look like ours.** The contact sheet (`period.py::sheet`) shows
24 re-cropped staves under 6 of dataL2's and 6 of dolores':
- the staff centred at about 4/9 of the height, as in dataL2;
- 2.5 spaces of neighbouring ink (dynamics, ledger notes, slurs) above and
  below, and nothing of the staff cut off;
- the clef, or the system's brace, at the left edge.

The tilted staves come out straight. dolores is a public set cut its own
way, so dataL2 is the fair comparison.

**Pairing check:** 25 staves per score, evenly spaced through it (1,050
staves). They were read by musvit-D4 (run D3S-h96, `reader.pt`, 96 px).
- **Measure counts:** the reading's count matched the label's on 938 staves
  (89%). On 104 the reader found fewer measures, on 8 more.
- **First measure:** its rhythm matched the label's on 90% of staves.
- **Per score:** the share whose measure count differs ranges from 0 to 36%.
  The highest are Beethoven Op. 18 No. 2 (36%), K. 590 and one of K. 464's
  movements (sq7078259, 28%), and Haydn Op. 64 No. 2 and K. 465 (24%).
  Sixteen scores are at 4% or below.
- **No score is suspect.** In every score:
  - the mismatches are scattered through it, not a run from some point to
    its end (which is what a slipped system would leave);
  - the first measure's rhythm matches on at least 18 of 25 staves. A
    shifted label would almost never match.
- **The misses are the reader's.** Of the 104 readings short of the label,
  only 16 lose just the last measure. The rest drop or merge one in the
  middle, mostly on long staves (median 10 measures, against 7 overall).
- **Disagreements looked at,** image against label against reading:
  - K. 465's cello, last system: 13 bars, read as 12; a repeated bar dropped.
  - K. 590's first violin: tied half notes read as dotted halves, and 16th
    figures read as triplets.
  - Op. 18 No. 2: a run of 16th triplets.
  - The opening of Op. 76 No. 1: the print has a barline the encoding lacks.

  Each label matched its image.
- Every reading, with its counts, is in `period-pairing.json`.

**Lists** (`musvit-staves`, keys relative to `/staves/ossq-period/`):
- `samples.ossq-period.txt`: all 13,241.
- `samples.ossq-period-clean.txt`: also 13,241, since no score was excluded.
- `samples.ossq-period-check.txt`: the 1,050 read for the check.

**Cost:** about $0.30. The re-crop was $0.19 (CPU, about 25 min on 4
containers; reads off the volume are slow), and the check $0.11 (an L4 for
a few minutes).

```
modal run experiments/ossq/period.py::recrop               # re-crop the 42 scores -> /staves/ossq-period/
modal run experiments/ossq/period.py::sheet                # contact sheet (--keys sqX/name,... for chosen staves)
modal run experiments/ossq/period.py::check                # pairing check with musvit-D4
modal run experiments/ossq/period.py::clean [--exclude sqX,...]   # both lists
```
