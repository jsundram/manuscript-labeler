# Do OSSQ's period labels ignore the scans' clef changes? (2026-10-20)

**No.** In OSSQ-OMR's 13,241 period staves, the label's clefs follow the
print. About 130 staves were checked by eye, picked where a wrong clef was
most likely, and not one label contradicts its image. The cello labels do
carry the print's clef changes: treble and tenor passages, inside a staff
and at its start. The viola and violin labels never change clef, and the
prints don't either: every viola staff with high notes seen was in alto
clef in the ink, with ledger lines.

G. 213 (README in `experiments/zeus/g213/`) is a different case. Its
encoding is in OSSQ's synthetic list only, rendered from the encoding
itself, so the image and label agree there by construction. None of its
staves is in the period set.

## Labels by part, against our Boccherini staves

Share of staves (`clef_check.py analyze`, all in `clef-check.json`):

| part | OSSQ period: staves | clef change inside the staff | any clef not the part's usual one | notes past 2 ledger lines in the label's clef |
|---|---:|---:|---:|---:|
| vn1 | 3,255 | 0 | 0 | 53 (1.6%)\* |
| vn2 | 3,330 | 0 | 0 | 0 |
| va | 3,319 | 0 | 0 | 37 (1.1%) |
| vc | 3,337 | 94 (2.8%) | 105 (3.1%) | 146 (4.4%) |

| part | dataL2 (hand-labelled): staves | change inside | not usual | far notes |
|---|---:|---:|---:|---:|
| vn1 | 160 | 0 | 0 | 4\* |
| vn2 | 158 | 0 | 0 | 0 |
| va | 148 | 0 | 0 | 0 |
| vc | 129 | 12 (9.3%) | 13 (10.1%) | 10 (7.8%) |

\* Violins: more than 13 steps from the middle line (past 4 ledger lines).

dataM is no baseline for changes: it keeps one clef per staff, chosen by
autopair from the reading. Even so, 91 of its 614 cello staves (14.8%) are
not in bass clef.

OSSQ's cello clef sequences: bass 3,232; treble to bass 34; bass to treble
33; bass, treble, bass 15; treble 9; bass, tenor, bass 6; other tenor
sequences 7; treble, bass, treble 1. Boccherini's cellos change clef about three times as often,
more often to tenor. In the editions OSSQ scanned, a high cello passage
mostly stays in bass clef with ledger lines (up to A4) or moves to treble.
Tenor clef is rare.

## musvit-D4 against the labels (the 1,050 check staves)

| part | staves | clefs differ | label changes clef | D4 changes clef |
|---|---:|---:|---:|---:|
| vn1 | 280 | 1 | 0 | 0 |
| vn2 | 230 | 1 | 0 | 0 |
| va | 272 | 2 | 0 | 0 |
| vc | 268 | 6 | 5 | 0 |

**D4 never writes a clef change inside a staff**, on any of the 1,050. All
10 disagreements are D4's errors; the label matches the ink each time:
- **The label's change, which D4 left out:** `sq15049456/0004-0004-4`
  (bass, treble, bass: D4 reads bars 2–3 a 13th low), `sq15730717/0003-0001-4`,
  `sq16138966/0007-0004-4`, `sq8071278/0003-0001-4`, `sq9719026/0009-0002-4`
  (treble in bars 1–2: D4 reads bars 3–5 in treble, a 13th high).
- **A wrong opening clef:** `sq7294793/0008-0003-4` (high bass-clef notes
  read as tenor), `sq7353137/0011-0004-3` (alto read as treble),
  `sq8907120/0012-0001-3` (alto read as tenor), `sq7078259/0011-0005-2`
  and `sq9396439/0002-0001-1` (violins in treble read as alto).

So D4 can't find what this question looks for. It misses the changes the
labels have, and it can't see a change the label lacks.

## Checked by eye

Contact sheets (`clef_check.py sheets`, then `::sheet`) of:
- the 10 disagreements;
- all 37 viola staves with notes past 2 ledger lines: all alto clef in the
  ink (for example `sq15624112/0011-0002-3`, `sq7284122/0003-0002-3`,
  `sq8088531/0005-0002-3`);
- 35 of the 146 cello staves with such notes, 24 of them from the scores
  with the most (Haydn Op. 20 Nos. 2–4, K. 575, K. 589, K. 590, Op. 18 Nos. 2–3).
  All are bass clef in the ink, with 3 ledger lines (for example
  `sq8088531/0003-0004-4`, `sq8455808/0021-0001-4`, `sq8907120/0019-0005-4`);
- 12 cello staves whose label changes clef, and 12 that open in treble.
  Every change is in the ink at that bar (for example
  `sq7471661/0007-0002-4`: bass, tenor in bar 2, bass in bar 4);
- 24 random cello staves where D4 and the label agree on one clef: all
  bass clef in the ink, with no change.

## How sure

- **Opening clefs and treble passages:** sure. A cello passage in treble
  clef that the label kept in bass would put notes past 2 ledger lines, and
  every such staff seen is right. Of 268 random cello staves (the check
  set), none has an opening clef or a treble passage that contradicts the
  ink. The 95% upper bound is about 1%.
- **A short tenor passage in the middle range** would get past the
  ledger-line screen, and D4 can't find it either. Only the 24 random cello
  staves cover this case. But these editions rarely use tenor clef: 13
  labels have it, and the one seen agrees with its ink.
- **Estimate:** the share of staves whose label clef contradicts the ink
  is about 0% for violins and viola, and well under 1% for cello.

## What to do

- **Drop nothing from the period set for clef reasons.**
- **D4 is the wrong tool for a full sweep.** Reading all 13,241 staves
  would cost about $1.40 (an L4, at the check's $0.11 per 1,050). It would
  mostly turn up D4's own errors, and none of the changes it misses. The
  label-only screen (notes far off the staff in the label's clef) covers
  every staff for nothing. It is already run, and its flags checked out
  clean.
- **D3S-h96-ossq's cello 13ths have some other cause.** On KHM 603 I, its
  cello bars that differ from D4's by a 13th (`p20s8` bar 6, `p20s9` bars
  5–6, `p21s4` bars 5–6) come with no clef token in either reading. It
  moved the notes as though the clef changed, but wrote no change. One
  guess, not tested: OSSQ adds 94 cello staves that jump between treble
  and bass inside the staff. The labels are right, but they may make the
  reader readier to jump.

Cost: about $0.02 of Modal CPU (fetching the labels and drawing the
contact sheets). No GPU was used.
