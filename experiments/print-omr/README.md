# A printed edition as a source of labels (2026-10-20)

Can an engraved edition, read by OMR, supply labels for Boccherini
manuscripts that have no encoding? The plan: read the print, pair the
manuscripts with that reading, keep only the bars where both agree. This
tests the first half on quartets whose notes we already know.

**Answer: yes, when two different readers agree.** Where the OSSQ reader
(MuSViT) and Audiveris read a bar the same way, the reading is right
**99.2%** of the time, by the print, on 2,480 bars: **60%** of the test bed's
4,140 encoded part-bars. musvit-D4 with Audiveris is 99.0% on 56%; all three
together 99.2% on 55%. The two MuSViT readers agreeing are not enough (about
96.5%): they share their mistakes. No reader alone comes near: the best,
the OSSQ reader, has 82.5% of bars exact.

G. 223 (Op. 44/4) is read and saved for pairing (`G223/BA2676-G223.json`):
854 of its 1,404 part-measures (61%) pass the rule.

## The edition

Bärenreiter BA 2676, Boccherini, *Ausgewählte Streichquartette*, ed. Walter
Upmeyer (1952). IMSLP #370564–370567 (violin I, violin II, viola, cello) and
#370568 (covers, German foreword), in
`~/Data/manuscript-labeler/imslp/barenreiter-ba2676/`, registered in
`~/Data/registry.toml` (public domain per IMSLP; a subscriber's browser
download, because of a captcha). Engraved parts, scanned at 300 dpi, 1-bit,
with the scanner's black surround.

The print's own labels differ from Gérard's: G. 159 is "op. 1 Nr. 1", G. 189
"op. 24 Nr. 5", G. 228 "op. 48 Nr. 2", G. 243 "op. 58 Nr. 2". G. 189's opening
matches Philhar's Op24-1, and G. 228's the Op. 48 edition's Op48-3.

### Page map

`pagemap.json` (written by `make_pagemap.py`), read by eye from contact
sheets of every page. PDF page *n* is printed page *n*+1 in every part; page 1
is the part's cover. Every quartet starts at a page top; movements start
mid-page.

| quartet | movement | vn1 | vn2 | va | vc |
|---|---|---|---|---|---|
| I: G. 159 | I Allegro commodo | 2 | 2 | 2 | 2 |
|  | II Largo | 3 | 3 | 3 | 3 |
|  | III Allegro | 3–4 | 3–4 | 3–4 | 3–4 |
| II: G. 189 | I Moderato | 5–6 | 5–6 | 5–6 | 5–6 |
|  | II Grave | 7 | 7 | 7 | 6 |
|  | III Allegro assai | 8 | 7–8 | 7–8 | 7 |
| III: G. 214 | I Prestissimo | 9–11 | 9–10 | 9–10 | 8–10 |
|  | II Tempo di Minuetto (Trio) | 11–12 | 11 | 11 | 10 |
|  | III Flebile | 12 | 11–12 | 11 | 11 |
|  | IV Prestissimo | 12–13 | 12 | 12 | 11–12 |
| IV: G. 213 | I Allegro moderato | 14–16 | 13–14 | 13–14 | 13–14 |
|  | II Minuetto. Allegro (Trio) | 16 | 14 | 14 | 14 |
|  | III Grave | 17 | 15 | 15 | 15 |
|  | IV Allegro giusto | 17–18 | 15–16 | 15–16 | 15–16 |
| V: G. 215 | I Allegretto moderato | 19–20 | 17–18 | 17–18 | 17–18 |
|  | II Minuetto. Allegro (Trio) | 21–22 | 18 | 18 | 18 |
|  | III Larghetto affettuoso | 22 | 19 | 19 | 19 |
|  | IV Rondeau. Allegro moderato | 23–24 | 19–20 | 19–20 | 19–20 |
| VI: G. 223 | I Presto | 25–26 | 21–22 | 21–22 | 21–22 |
|  | II Tempo di Minuetto (Trio) | 27 | 23 | 23 | 23 |
| VII: G. 228 | I Allegretto moderato | 28–30 | 24–26 | 24–26 | 24–26 |
|  | II Minuetto. Con moto (Trio) | 30 | 26 | 26 | 26 |
| VIII: G. 243 | I Allegretto lento | 31–32 | 27–28 | 27–28 | 27–28 |
|  | II Minuetto. Allegro (Trio) | 32–33 | 28–29 | 28 | 28 |
|  | III Larghetto | 33 | 29 | 29 | 29 |
|  | IV Finale. Allegro vivo assai | 34–35 | 30–31 | 29–30 | 29–30 |

## The test bed

Four quartets, every movement, all four parts (`truth.py` → `truth/G*.json`,
each bar's events as compare.py compares them):

| quartet | encoding | bars per part |
|---|---|---:|
| G. 159 (Op. 2/1) | Philhar's LilyPond, `boccherini-quartet-data/lilypond/Op02-1` (philhar.py) | 332 |
| G. 189 (Op. 24/1) | Philhar's LilyPond, `Op24-1` | 198 |
| G. 213 (Op. 39) | OSSQ's corrected MusicXML, `sq8454356_cleaned.musicxml` (ossq/mxl.py) | 318 |
| G. 228 (Op. 48/3) | the Op. 48 edition's own, `Op48-3` (scripts/events.py), both movements: both are encoded and checked | 187 |

4,140 part-bars in all. A multi-bar rest is written out as one bar rest per
bar (events.py lists only its first bar).

## The candidates

| reader | what | how it ran | licence |
|---|---|---|---|
| **musvit-D4** | our MuSViT reader, run D3S-h96, `reader.pt` | `autodetect.py` (staves), then `read_auto.py`, Modal L4 | ours |
| **OSSQ reader** | run D3S-h96-ossq: D4's chain with OSSQ's 13,241 period print staves in the public stage | the same | ours |
| **Audiveris 5.11.0** | open-source OMR for engraved music, MusicXML out | Modal (below) | AGPL-3.0 |

**Installing Audiveris.** The macOS arm64 release (`.dmg`, with its own
Java) was unpacked to `~/Data/manuscript-labeler/tools/audiveris-5.11.0/`
and runs in batch. But on the Mac every page stalled: a step (BEAMS,
LEDGERS, HEADS) ran past its timeout, 10 minutes and more on one page. Two
causes: the scans' black surround (fixed by `clean_pages.py`, which whitens
everything dark touching the image edge and crops to the paper), and the
Mac's load (a load average near 100 from other work, which a heavy Java
step can't run under). So it runs on Modal (`audiveris_modal.py`): the
Ubuntu 24.04 `.deb` unpacked into the image (its post-install script fails
in a container; it needs GTK 3 for a native call at start-up), an L4
container per the project's rule, 8 CPUs, 16 GB; about 35 s a page.

**Not tried:** oemer (it depends on `onnxruntime-gpu`, which has no Mac
wheel); homr (AGPL-3.0, onnxruntime) would have run, but Audiveris already
gave the second, independent reader the test needed.

## How readings are scored (`score.py`)

**Pairing a reading with the encoding.** For each quartet and part, the
reader's measures on the quartet's pages, in order, are aligned with the
encoding's bars (all movements, in order) by dynamic programming: one
measure to one bar (cost: an edit distance over events, a rhythm-right
event costing half), two measures to one bar (a bar a repeat splits), one
to two, one bar rest to a run of bar rests (a multi-bar rest), or a
measure or bar left out. The encoding is used only to pair.

**Terms**, compare.py's, over every encoded bar: **bar exact** (the same
events in order: notes, rests, durations, dots, graces, each note's letter
and octave, at the pitches the reader wrote, in its own clefs), **right in
rhythm**, **right in pitch**. A bar left out or paired with part of a
measure is wrong. Accidentals are apart, as in compare.py. Two
conventions the print doesn't share are evened out:
- a unison written as two voices (`<< d8 \\ d >>`) is one note;
- **tremolos either way** (`canon()`): the print writes out repeated notes
  that Philhar (`e2.:8`) and OSSQ often abbreviate, so a run of equal notes
  lasting one note value equals that note, on both sides.

**Agreement.** Two readings are aligned with each other the same way,
**without the encoding**, as the pairing would have to on an unencoded
quartet. A bar is *agreed* when a measure of one is paired one-to-one with
a measure of the other and their events are identical. It is *right* when
that measure is paired with an encoded bar and is exact (tremolos either
way).

**Looking at the print.** The encodings follow other sources, so the scorer
counts some right readings wrong. Every agreed bar it counted wrong was
looked at in the print (`crops.py` contact sheets, zoomed where needed):
all 86 of the three-way set, and the pairs' others (all for the two
Audiveris pairs, a random 24 of 146 for the MuSViT pair). Verdicts in
`adjudication.json`; `adjusted.py` applies them. "Edition" means the print
has what the readers wrote; anything unclear was counted as an OMR error.

## Scores

**Each reader alone**, against the encodings (`results/score.txt`):

| reader | bars | exact | exact, tremolos either way | rhythm right | pitch right |
|---|---:|---:|---:|---:|---:|
| musvit-D4 | 4,055 | 77.3% | 79.1% | 84.5% | 79.4% |
| OSSQ reader | 4,058 | **82.5%** | **84.7%** | **87.9%** | **84.5%** |
| Audiveris | 4,103 | 61.0% | 62.7% | 63.5% | 67.4% |

By quartet, bar exact (D4 / OSSQ reader / Audiveris): G. 159 83.9 / 89.3 /
60.0%; G. 189 62.0 / 67.8 / 54.4%; G. 213 70.6 / 77.7 / 57.1%; G. 228 93.5 /
94.8 / 76.4%. About 85 bars of each are inside multi-bar rests and not
scored. These counts include the edition's differences from the
encodings, which are many in G. 189 (its whole viola I is an octave below
Philhar's) and G. 213 (OSSQ follows the Pleyel print, which differs in
rests, rhythms and tremolos).

**Agreement**, the filter the pairing would use:

| readers agreeing | agreed bars (share of 4,140) | right, by the scorer | right, after looking at the print |
|---|---:|---:|---:|
| musvit-D4 + OSSQ reader | 3,342 (80.7%) | 93.1% | about 96.5% (sampled) |
| musvit-D4 + Audiveris | 2,326 (56.2%) | 95.7% | **99.0%** |
| OSSQ reader + Audiveris | 2,480 (59.9%) | 95.9% | **99.2%** |
| all three | 2,265 (54.7%) | 96.2% | **99.2%** |

The three-way set's 86 scorer-wrong bars: 68 are the print (28 the G. 189
viola octave, 6 tremolos written out, 26 rhythms, rests, pitches, chords or
graces the print has otherwise, 7 the scorer pairing a right measure with
the wrong bar next to a split bar, 1 a misprint the readers read
faithfully: a 2/4 bar whose quarter rest overfills it), and **18 are OMR
errors**: 9 multi-bar rests read as a single bar rest
(the count isn't read), 4 unclear, 5 real misreadings (16ths for 32nds, a
quarter for an 8th, a measure cut short, a misread clef at an upbeat). The
multi-bar rests are easy to drop: the rule below leaves out any agreed
measure that is a lone bar rest, which takes the three-way set to about
99.6%.

A "fills the bar" check (the measure as long as most on its staff, from the
readers' own durations) adds little: 96.2% → 96.8% on the three-way set, by
the scorer.

## Typical errors

- **MuSViT misses tenor clef** in the cello (both readers, the same way):
  `examples/omr-tenor-clef.png`, G. 213 vc I 24–25 read in bass clef. This
  is why the MuSViT pair alone fails: their errors are shared. Audiveris
  reads the clef.
- **Multi-bar rests** (all three): one bar rest for "5",
  `examples/omr-multirest.png`.
- **Grace-note values** (MuSViT): a 16th grace read as an 8th,
  `examples/omr-grace-duration.png`. **Audiveris drops grace notes**
  altogether (`examples/audiveris-graces.png`), its main reason for low
  "bar exact"; it also drops notes in dense 32nd passages, and reads few
  double stops.
- **Not OMR errors:** `examples/edition-viola-octave.png` (G. 189 va I an
  octave below Philhar), `examples/edition-tremolo.png` (written-out notes
  where Philhar has tremolos), `examples/edition-rests.png` (8th + 16th rest
  where Philhar has a dotted 8th).

## Verdict

**Use the agreement of a MuSViT reader and Audiveris**, and leave out any
agreed measure that is a lone bar rest. On the test bed that keeps about 60%
of bars at 99% right by the print, above the 98% aim. The OSSQ reader is the
better MuSViT partner (more bars, 99.2%); adding musvit-D4 as a third vote
costs 5% of the bars and gains nothing measurable.

Two cautions:
- **The print is not the manuscript.** BA 2676 differs from the encodings
  in many places (octaves, rests, rhythms, tremolos written out), so it
  will differ from the manuscripts too. The pairing's own agreement test
  (print reading against the manuscript reading) must do that filtering;
  this study only says the print reading itself can be trusted.
- The 99% rests on one look at about 150 bars in the print (the 28 octave
  bars by one crop and a check that nothing but the octave differs), with
  unclear ones counted against the readers. The MuSViT pair's 96.5% is
  extrapolated from 24 of its 146 bars outside the three-way set (16 of the
  24 were OMR errors).

### G. 223 (Op. 44/4), ready for pairing

`encode.py 223` → `G223/BA2676-G223.json`: every measure the OSSQ reader
read on G. 223's pages, by part and movement (I Presto, II Tempo di
Minuetto), each with its page, staff (as `auto/BA2676-<part>.json` orders
them) and measure index, its events (as compare.py compares them, pitches as
written), which readers agree, and `"use"`: Audiveris agrees and it isn't
a lone bar rest. 1,404 measures, **854 to use** (61%); all three agree on
830. By part, I / II: vn1 218/287, 35/66; vn2 153/279, 52/69; va 225/287,
44/68; vc 84/280, 43/68 (the cello's tenor-clef passages and double stops
lose the most). Measures are numbered in reading order, not by the print's
bar numbers (a split bar counts twice, a multi-bar rest once). The OSSQ
reader's LMX for every staff is in
`experiments/zeus/answers/BA2676-<part>-auto-musvit-D3S-h96-ossq.json`, and
Audiveris's MusicXML per page in
`~/Data/manuscript-labeler/experiments/print-omr/audiveris/`. Not paired with
KHM 600 or F-Po RES-507 (10) yet.

## Cost

- **Modal: $1.16** (billing report): MuSViT readings of all 1,498 staves,
  twice, $0.24; Audiveris on 68 pages (the test bed and G. 223), $0.87, plus
  $0.05 of test runs and image builds. L4 only, at most two at once.
- **Mac:** bar-line detectors and staff detection on 122 pages, about 25
  minutes; each scoring run about 15 minutes (one process, under heavy
  load from other work).

## Rerun

    E=~/Dropbox/Code/boccherini-opus-48; D=~/Data/manuscript-labeler/imslp/barenreiter-ba2676
    P=experiments/print-omr
    uv run $P/make_pagemap.py
    uv run $P/truth.py                                     # the encodings -> truth/
    # staves, MuSViT readings
    uv run --with markdown-it-py tools/predict_barlines.py $E --pdf $D/IMSLP370564*.pdf --pdf $D/IMSLP370565*.pdf --pdf $D/IMSLP370566*.pdf --pdf $D/IMSLP370567*.pdf
    uv run --with markdown-it-py experiments/zeus/autodetect.py $E --pdf $D/IMSLP370564*Vl1.pdf --name BA2676-vn1 --pages 2-35:vn1
    #   ... the same for vn2 (370565, 2-31), va (370566, 2-30), vc (370567, 2-30)
    uv run experiments/musvit/read_auto.py --run D3S-h96 --file reader.pt BA2676-vn1 BA2676-vn2 BA2676-va BA2676-vc
    uv run experiments/musvit/read_auto.py --run D3S-h96-ossq --file reader.pt BA2676-vn1 BA2676-vn2 BA2676-va BA2676-vc
    # Audiveris
    for p in vn1:370564 vn2:370565 va:370566 vc:370567; do mkdir -p ~/Data/manuscript-labeler/experiments/print-omr/pages/${p%%:*}
      pdftoppm -r 300 -gray -png -f 2 $D/IMSLP${p##*:}*.pdf ~/Data/manuscript-labeler/experiments/print-omr/pages/${p%%:*}/p; done
    uv run $P/clean_pages.py
    modal run $P/audiveris_modal.py --pages "vn1:2-8 vn1:14-18 vn1:25-30 vn2:2-8 vn2:13-16 vn2:21-26 va:2-8 va:13-16 va:21-26 vc:2-7 vc:13-16 vc:21-26"
    # scores, agreement, the print's verdicts, G. 223
    uv run $P/score.py musvit:D3S-h96 musvit:D3S-h96-ossq mxl:audiveris > $P/results/score.txt
    python3 $P/adjusted.py
    uv run $P/encode.py 223
    uv run $P/crops.py OUT.png vc:13:5:caption        # a staff of the print, for looking

Modal commands, and writes to `~/.cache` and `~/Data`, run outside the
sandbox. The autodetect filter cache was copied from another unlabelled
source's (`auto/cache/*/models`), so it wasn't retrained.

## Files

- `pagemap.json`, `make_pagemap.py`: the page map.
- `truth.py`, `truth/`: the encodings, bar by bar.
- `readings.py`: each reader's measures (MuSViT LMX, MusicXML).
- `score.py`: pairing, scores, agreement; `results/score.json`,
  `results/score.txt`, `results/bars.json` (every bar's verdict, and the
  agreed bars counted wrong).
- `adjudication.json`, `adjusted.py`: the print's verdicts.
- `clean_pages.py`, `audiveris_modal.py`: Audiveris.
- `encode.py`, `G223/BA2676-G223.json`: G. 223 for pairing.
- `crops.py`, `examples/`: staves of the print.
- Outside the repo: `~/Data/manuscript-labeler/experiments/print-omr/`
  (pages, cleaned pages, Audiveris output),
  `~/Data/manuscript-labeler/tools/audiveris-5.11.0/`;
  `experiments/zeus/auto/BA2676-*.json` and
  `experiments/zeus/answers/BA2676-*` (detections and readings) are in the
  repo.
