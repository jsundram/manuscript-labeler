# G. 213 (Op. 39, A major): training staves from OSSQ's encoding (2026-10-20)

Three copies of Boccherini's quartet G. 213, each paired staff by staff and
bar by bar with OSSQ-OMR's corrected encoding, to make training staves for
the MuSViT reader. Nothing was labelled by hand. Correctness of each kept
staff came first; count second.

## Sources

| name | copy | file | page map (PDF pages) |
|---|---|---|---|
| G213-Sibley | Pleyel, plate 125 (Le Duc title, Pleyel stamp). IMSLP 78818, Sibley Library. OSSQ corrected the encoding to this scan. | `~/Data/manuscript-labeler/zeus/g213/IMSLP78818-PMLP159484-Opus-39.pdf` (17 pp., only G. 213; fetched once from s9.imslp.org) | `1-5:vn1,6-9:vn2,10-13:va,14-17:vc` |
| G213-DB-Pleyel | The same edition, Berlin DMS 51778, livraison 3 (G. 213 is Quartetto II) | `~/Dropbox/Code/boccherini-sources/digitizations/G213_232_235/990005884_D-B_livr3/D-B_DMS_51778.pdf` (read only) | `11-13:vn1,15-16:vn1,29-32:vn2,43-46:va,57-60:vc`. Page 14 is in the brief's range 11-16, but it is a plate with no music: the vn1 part runs 11, 12, 13, 15, 16 |
| G213-KHM587 | Manuscript parts, Berlin KHM 587, dated November 1787 (RISM 463058700) | `~/Dropbox/Code/boccherini-sources/digitizations/G213/463058700_D-B/463058700_D-B.pdf` (41 pp.; read only) | `2-9:va,14-19:vn1,22-31:vn2,34-39:vc`. Found by eye: each part opens with its title, the viola with the long "Mese di Novembre. 1787" title. Confirmed by the pairing: every page's kept staves pair to its part, in order |

The 42-page `boccherini-quartet-data/manuscripts/Boccherini G.213 - Opus 39 - Manuscript.pdf`
is a different file: A4 pages, a jsPDF export from February 2026. Its
thumbnails show the same manuscript. It was not used.

**Encoding:** OSSQ-OMR `sq8454356_cleaned.musicxml`, ossq-omr commit
7a17e45 (omr-dev). It is an OpenScore transcription of IMSLP 78818. It
is saved at `~/Data/manuscript-labeler/zeus/g213/`, because the sandbox
can't write to `~/.cache`. G. 213 is only in OSSQ's synthetic list, not its
scanned list, so no OSSQ scanned staff is a copy of these pages.

Two things about the encoding matter here:
- **The cello has no clef changes.** It is bass clef throughout, while the
  print and the manuscript move to tenor clef often. The viola has none
  either.
- **Tremolo abbreviations.** In places the score writes out repeated
  notes where the print uses a tremolo (vc I 52–54), and the reverse.

## Same plates: Sibley and Berlin

The Sibley and Berlin copies are pulls from the same plates. `twins.py`
compares staff ink profiles:
- every Berlin page's best Sibley match is its expected page (0.56–0.79,
  against at most 0.26 for any other page);
- every page has the same number of staves in both copies;
- every staff's best match is the staff at its place, except six page-top
  staves, where titles and headings skew the profile;
- on all 188 staves that both copies paired by their own readings, the
  bars agree exactly.

No staff showed a difference in the music between the two issues.

## The pipeline

1. `tools/predict_barlines.py --pdf` (cached bar-line detectors), then
   `autodetect.py --pdf --name --pages` (one filter cache copied across the
   three names).
2. `experiments/musvit/read_auto.py --run D3S-h96 --file reader.pt` (musvit-D4, Modal L4).
3. `autopair.py --musicxml SCORE --model /nonexistent/musvit-D3S-h96 --any-count --neighbours --short-ends`.
4. `g213/merge.py`: kept staves, cross-checked against the twin (Sibley↔Berlin).
5. `dataset.py --pairs SRC --musicxml SCORE --results results/autopair-SRC-final.json --clef chosen --max-unlike 0.5`.

## What the Sibley test found, and what was fixed

Sibley was the pipeline's test. Each problem it showed was traced and fixed:

- **Detection:** page 1's paper edge was found inside the page (a dark
  band), which cut every staff at 89% of the page width. Fix:
  `autodetect.py --whole-page 1`.
- **Adapter:** MuseScore writes a bar split by a repeat as two measures
  (X1, X2 …), and the reader reads them as one. Fix: a "join" step
  (`mxl.movements`, `autopair.musicxml_encoding`).
- **Pairing, a bar short:** a staff can pair one-to-one but a bar short
  when the staff beside it ends with a measure for two bars, or a bar rest
  for several, and takes that bar (viola p10-5). The bar was a rest at the
  end of the line that the reading dropped. Fix: `--neighbours`.
- **Pairing, half a bar:** a bar split across a line break could be taken
  for the whole bar, with the other half counted as an extra measure.
  Fixes: `--short-ends` (an end measure under 3/4 of its bar), the extra
  case in `--neighbours`, and `merge.py` dropping two whole-bar staves that
  share a bar.
- **Labels, hidden rests:** OSSQ fills second voices with hidden rests
  (print-object=no). They became `forward`.
- **Labels, mid-bar key change:** IV has a key change inside a bar (X2)
  where the print draws no bar line. Staves holding it are left out.
- **Labels, cello clefs:** the encoding's cello clef is wrong for the
  tenor-clef staves. The clef autopair chose from the reader's notes is
  written in its place, only where the reader wrote that clef and no
  other. Viola and cello staves with a note more than 9 steps from the
  middle line (a clef change inside the staff) are left out.
- **Labels, tremolos:** staves where the print abbreviates what the score
  writes out (or the reverse) are left out (`--max-unlike 0.5`).

Existing behaviour is unchanged. `--musicxml`, `--neighbours` and
`--short-ends` are new options, and so is `--whole-page`. The kept-staff
records gain fields ("steps", "bar_clefs", "read_clefs", "worst"), and the
results gain a "not kept" list with reasons.

## Counts

| | Sibley | Berlin print | KHM 587 |
|---|---|---|---|
| staves detected | 236 | 236 | 240 |
| paired (merge.py) | 207 | 211 | 148 |
| in the staff set | **166** | **166** | **99** |
| bars in the set | 834 | 867 | 582 |
| reader exact on those bars (rhythm) | 79% (88%) | 81% (87%) | 73% (86%) |

The Sibley and Berlin sets agree. 165 staves are in both, with the same
bars. Sibley p13-12 is in only its set: its Berlin twin p46-12 was cut
short by detection. Berlin p43-6 is in only its set: its Sibley twin's end
was detected elsewhere.

### The Berlin print: why each staff that isn't in the set was left out

Not one is a difference in the music.

- **25 not paired.** Reading or detection, the same on the same plate: in
  20 of the 25 the Sibley twin fails too.
  - Two bars read as one: a missed bar line. vn1 p13-4 (II 36–37), va
    p43-3 (I 17–18) with p43-4 beside it, va p46-12 (IV 137–138), vc
    p60-0 (IV 58–59) with p59-12 beside it.
  - An extra measure, or half a bar at a line break: vn1 p15-10, p16-11
    (IV 129) with p15-9 and p16-12 beside them, vc p59-1, vn2 p29-8 (I 37).
  - An end measure shorter than its bar: half a bar at a line break, or a
    movement's pickup read as a full bar. vn1 p11-3 (I 12), p13-9 (III 10);
    va p44-3 (I 73), p45-5 (IV 0), p46-4 (IV 99); vc p59-6 (IV 0).
  - Measures and bar boxes disagree, and an end is not one bar: vn1
    p11-1, p12-8; vc p58-0, p60-12.
  - Beside a multi-bar rest: va p44-12 (II 46–55).
  - Tremolo abbreviation (the print writes half notes where the score
    writes 16ths): vc p57-10 (I 53–55).
  - Paired, but unconfirmed: va p44-8 (II 0–10).
- **24 paired but not plain.** Half a bar at a line break, or a
  multi-bar rest: dataset.py can't cut half a MusicXML bar. vn1 p11-0,
  p11-2, p11-6–9, p12-9–11; vn2 p29-13–14, p30-13, p31-1–2, p32-5–6;
  va p44-11, p45-0, p45-1, p45-3; vc p58-1, p59-0, p60-1, p60-11.
- **3 hold the IV key-change bar (X2).**
- **5 have a measure unlike its bar.** Tremolos written two ways: vn2
  p29-7, p32-10; va p44-6; vc p57-3, p57-8.
- **6 where the cello clef is uncertain.** The reader wrote bass but its
  notes fit tenor, or it wrote both: vc p57-2, p57-4, p58-2, p58-6, p59-7,
  p59-11.
- **7 with notes far off the staff.** A clef change inside the staff,
  which the score doesn't have: vc p57-5, p57-9, p57-11, p58-3, p58-11,
  p59-5, p59-9.

### KHM 587

92 staves were not paired, and the copy's notation is the main cause.
Failures by bar, the score's text against the reading:
- **The barring differs in movement I's fast passages.** The manuscript
  often has one bar line where the print has two: vn1 I 10–11, 22–23,
  29–30, 42–43, 48–65, 75–76; vc I 17–18; vc IV 94–95.
- **Tremolos written out, or abbreviated, the other way from the print:**
  - vn2 I 27, 32–33, 50–54: the manuscript writes 32nds, the score has
    quarters and halves;
  - vn2 IV 30–33 and IV 113–116: written-out 16ths against quarters;
  - va I 18, 26, 32–33, 79–87: 32nds against quarters;
  - va IV 97 and IV 112–115: quarters with tremolo strokes against
    written-out 16ths;
  - vc I 11, 39, 50, 64–65, 71: 16ths against halves.
- **III 10–11 (vn1):** two bars read as one, where the manuscript
  continues the line differently.

Pages 3 (va) and 23 (vn2) yield nothing: 5 and 3 staves were detected
there.

The reader is exact on 73% of the kept bars here, against 81% on the
Berlin print. That gap is handwriting, or a pitch the manuscript has
differently that the pairing, which works mostly from rhythm, can't see.
The KHM 587 set should be treated as less certain than the two prints.

## Checked by eye

- **Contact sheets** (`contact.py`) of every staff in the Berlin staff
  set, with its bars and the encoding's first and last bar, including all
  viola and cello staves. The Sibley set equals the Berlin set staff for
  staff (165 of 166), so it was checked through its twins.
- **Not paired:** every Berlin staff, and the Sibley staves that differ
  from their twins.
- **Not confirmed by bar boxes or twin:** nine staves were viewed and
  passed: Berlin p43-5, p43-6, p44-2, p44-11, p30-10 and Sibley p1-11,
  p2-1, p13-12, p15-12. Berlin p30-10 (vn2 II 0–10) holds the whole of
  II 8, where Sibley p7-10 splits it across the line break.
- **KHM 587:** the first sheet of the set (12 viola staves), and the
  failures above.

## Where things are

- **Staff sets** (dataM's layout, JPEG plus LMX):
  `~/.cache/manuscript-labeler/zeus/dataG213/`, with `samples.G213-Sibley.txt`,
  `samples.G213-DB-Pleyel.txt` and `samples.G213-KHM587.txt`. Not uploaded
  to Modal.
- **Detections:** `experiments/zeus/auto/G213-*.json`.
- **Readings:** `experiments/zeus/answers/G213-*-auto-musvit-D3S-h96.json`.
- **Pairings:** `experiments/zeus/results/autopair-G213-*-any-count-neighbours-short-ends-musvit-D3S-h96.json`,
  and the final ones, `autopair-G213-*-final.json`.
- **Staff twins:** `g213/twins-DB-Sibley.json`.

**Cost:** about $0.10 on Modal (one L4 reading of 712 staves), plus about
30 minutes of local CPU on the Mac mini M1 (detection, pairing, staff sets).

## Rebuild

    E=~/Dropbox/Code/boccherini-opus-48; D=~/Data/manuscript-labeler/zeus/g213; X=$D/sq8454356_cleaned.musicxml
    B=~/Dropbox/Code/boccherini-sources/digitizations
    SIB=$D/IMSLP78818-PMLP159484-Opus-39.pdf; DB=$B/G213_232_235/990005884_D-B_livr3/D-B_DMS_51778.pdf; KHM=$B/G213/463058700_D-B/463058700_D-B.pdf
    uv run --with markdown-it-py tools/predict_barlines.py $E --pdf $SIB --pdf $DB --pdf $KHM
    uv run --with markdown-it-py experiments/zeus/autodetect.py $E --pdf $SIB --name G213-Sibley --pages 1-5:vn1,6-9:vn2,10-13:va,14-17:vc --whole-page 1
    uv run --with markdown-it-py experiments/zeus/autodetect.py $E --pdf $DB --name G213-DB-Pleyel --pages 11-13:vn1,15-16:vn1,29-32:vn2,43-46:va,57-60:vc
    uv run --with markdown-it-py experiments/zeus/autodetect.py $E --pdf $KHM --name G213-KHM587 --pages 2-9:va,14-19:vn1,22-31:vn2,34-39:vc
    uv run experiments/musvit/read_auto.py --run D3S-h96 --file reader.pt G213-Sibley G213-DB-Pleyel G213-KHM587
    cd experiments/zeus
    for s in G213-Sibley G213-DB-Pleyel G213-KHM587; do
      UV_PYTHON_INSTALL_DIR=~/.cache/manuscript-labeler/zeus/py uv run --python-preference only-managed autopair.py $E \
        --source $s --musicxml $X --model /nonexistent/musvit-D3S-h96 --any-count --neighbours --short-ends
    done
    P=11:1,12:2,13:3,15:4,16:5,29:6,30:7,31:8,32:9,43:10,44:11,45:12,46:13,57:14,58:15,59:16,60:17
    Q=$(echo $P | tr ',' '\n' | awk -F: '{print $2":"$1}' | paste -sd, -)
    EB=p43-5,p43-6,p44-2,p44-11,p30-10; ES=p1-11,p2-1,p13-12,p15-12     # checked by eye
    uv run g213/merge.py G213-DB-Pleyel G213-Sibley --pages $P --eyed $EB --twin-eyed $ES
    uv run g213/merge.py G213-Sibley G213-DB-Pleyel --pages $Q --eyed $ES --twin-eyed $EB
    uv run g213/merge.py G213-KHM587 -
    for s in G213-Sibley G213-DB-Pleyel G213-KHM587; do
      UV_PYTHON_INSTALL_DIR=~/.cache/manuscript-labeler/zeus/py uv run --python-preference only-managed dataset.py $E \
        --pairs $s --musicxml $X --results results/autopair-$s-final.json --clef chosen --max-unlike 0.5 \
        --out ~/.cache/manuscript-labeler/zeus/dataG213
    done
    uv run g213/twins.py G213-DB-Pleyel G213-Sibley --out g213/twins-DB-Sibley.json   # the same-plates check
    uv run g213/contact.py results/autopair-G213-DB-Pleyel-final.json $X /tmp/sheet   # contact sheets

Writing to `~/.cache` and `~/Data`, and the Modal call, run outside the sandbox.
