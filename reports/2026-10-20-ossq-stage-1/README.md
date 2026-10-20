# OSSQ's period staves in the public stage (2026-10-20)

The reader is trained in stages, each named for what it trains on and its
size in staves. All are at 96 px:

| stage | what it trains on | staves |
|---|---|---:|
| **Public 9k** | the public datasets, MusiCorpus's Dolores and OmniOMR (E2-h96) | 8,765 |
| **Public 22k** | the same, plus OSSQ-OMR's scanned 1750–1800 quartet staves (E3-h96-ossq) | 22,006 |
| **Drawn 11k** | OpenScore's quartets and our own training music, drawn in our copyists' hands (dataS3) | 10,790 |
| **Boccherini 3k** | everything of Boccherini's but the clean test: Op. 48's movements, the re-paired Philhar staves, the Madrid copies (dataL2, dataM, dataT) | 3,411 |

musvit-D4 is Public 9k → Drawn 11k → Boccherini 3k. The reader here is
Public 22k → Drawn 11k → Boccherini 3k.

**Verdict: no gain on our manuscripts.** Adding OSSQ-OMR's 13,241 scanned
staves of 1750–1800 quartets to the public stage, then D4's other two
stages unchanged, read 268 of the clean test's 347 bars exact (77%), against
musvit-D4's 277 (−9, 95% interval −21 to +3). D4 stays the default. Eight
of the lost bars come from four cello clef changes, where the OSSQ reader
left out the clef sign but wrote the notes' real pitches; without them it's
a tie.

Public 22k itself was better than Public 9k, on handwriting it was never
trained on: OmniOMR's symbol errors fell from 22.9% to 18.3%, and
Dolores's from 11.7% to 11.2%. That gain didn't survive the next two
stages.

## What we tried

D4's chain, with one change in the public stage:

1. **Public 22k (E3-h96-ossq):** Public 9k's recipe (MusiCorpus's Dolores
   and OmniOMR train and validation staves, 96 px, full encoder, 60 passes
   at most), plus OSSQ's period staves: 22,006 staves in all, against
   Public 9k's 8,765. The period staves are Haydn Op. 1 to 76, Mozart K. 80
   to 590 and Beethoven Op. 18, re-cropped to our convention (see
   `experiments/ossq/PLAN.md`, "Period staves for stage 1").
2. **Drawn 11k (SF1-h96-ossq):** D4's drawn stage from it: the 10,790
   drawn staves alone, best pass on the practice exam.
3. **Boccherini 3k (D3S-h96-ossq):** D4's Boccherini stage from that:
   3,411 staves, 24 passes of a 30-pass schedule.

## Results

**Each stage, against D4's chain.** Symbol error rate (lower is better).

| stage | D4's chain | with OSSQ |
|---|---:|---:|
| public stage, Dolores test (2,357 staves) | 0.117 (637 exact) | **0.112** (692 exact) |
| public stage, OmniOMR test (257) | 0.229 (9 exact) | **0.183** (12 exact) |
| public stage, its own check (200 Dolores staves) | 0.100, pass 55 | **0.090**, pass 60 |
| Drawn 11k, practice exam (147) | 0.229, pass 6 | **0.213**, pass 10 |

The public stage is Public 9k in D4's chain and Public 22k with OSSQ.

**Clean test** (KHM 603 I, 347 bars), read on the Mac (`read.py --device
mps`), scored by compare.py.

| reader | bars exact | rhythm right | pitch right |
|---|---:|---:|---:|
| musvit-D4 (D3S-h96) | **277 (80%)** | 300 | **311** |
| with OSSQ (D3S-h96-ossq) | 268 (77%) | 298 | 302 |

By part, bars exact (D4, then with OSSQ): violin I 63 and 59, violin II 62
and 58, viola 74 and 80, cello 78 and 71.

**Paired bootstrap over the 347 bars** (10,000 resamples, 95%):
- with OSSQ against D4: −9 (−21 to +3);
- with OSSQ against D3L2-h96 (Public 9k → Boccherini 3k, no drawn
  stage): +8 (−5 to +21).

## Where the bars went

The OSSQ reader lost 23 bars D4 read exactly, and gained 14. The 14 are
scattered small fixes (a note, a duration). Of the 23, **8 are cello bars
whose every note is a 13th off**, as if bass clef were read as treble or
the reverse. They come from four staves (p20s8, p20s9, p21s4, p21s5: two
passages, each played twice, bars 42–48 and 78–86), each at a clef change
inside the staff:

- **On p21s5, at the change back to bass clef, the OSSQ reader wrote
  `key:fifths:1` (a key change) where D4 wrote `clef:F4`.** Its notes are
  the same as D4's (A2, D3, E3, E2).
- **On the other three, neither reader wrote the clef change.** D4 wrote
  the notes where they sit on the staff in the clef before it (F2 to F3 in
  bass; F4, B3 … in treble on p20s9). The OSSQ reader wrote the notes' real pitches (D4 to D5, as the
  encoding has them), as if it had applied the clef but left its sign out.

compare.py places each note by its staff position, from the clefs the
reading writes, and judges that against the labels. So a clef change left
out costs nothing if the notes are written where they sit (D4), and a
13th on every note if they are written at their real pitch (the OSSQ
reader). Scored on pitch, it's the reverse on the three staves where both
left the clef out: the OSSQ reader's notes are the encoding's (D4 E4 F4 …
D5; D2 D3 E3 E2), and D4's are wrong (F2 where the cello plays D4). Only
p21s5 (bars 84–86) is the OSSQ reader's own mistake.

**OSSQ's labels are not the cause.** A check of all 13,241 period labels
(`experiments/ossq/clef-check.md`): they follow the clefs drawn in the
scans. About 130 staves were checked by eye where a wrong clef was likeliest,
and none contradicts its image. Their cello staves change clef inside the
staff less often than ours (2.8% against dataL2's 9.3%).

Without these 8 bars the two readers are within a bar or two of each
other: Public 22k neither helped nor clearly hurt on the clean test.

**Scored with the clef apart** (compare.py, from 2026-10-20: each run of
bars read in the wrong clef is one clef error, and the bars are judged by
place or by the pitches written):

| reader | bars exact (as before) | right, clef apart | exact as written | clef errors |
|---|---:|---:|---:|---:|
| musvit-D4 | **277** | **277** | 272 | 4 |
| with OSSQ | 268 | 275 | **275** | 4 |
| musvit-D3 | 270 | 270 | 264 | 4 |

Every reader makes the same 4 clef errors, all in the cello. With the clef
apart, OSSQ against D4 is 275 against 277; on the notes as written (what
the edition would get) the OSSQ reader is best.

## What it means

- **Print staves made the public stage a better reader of unseen hands.**
  The OmniOMR gain (−4.6 points) is large for a public stage; Dolores
  moved less.
- **The gain washed out in Boccherini 3k.** By the clean test it was
  gone. Boccherini 3k trains the reader on 3,411 staves of the hands it
  will read, and what the public stage knew about other hands seems not
  to matter much after it. The loss in pitch (302 against 311) is mostly the clef
  changes above.
- **Clef changes inside a staff are a weak spot for both readers.** Both
  left out a clef sign the copyist drew. D4's reading then has the notes'
  places but wrong pitches, the OSSQ reader's the right pitches under the
  wrong clef. The scorer judges places, so it credits D4; for the edition's
  music, the OSSQ reader's reading is the right one. Either way the clef
  sign should be written.
- **Not worth the money as is.** Public 22k cost $10.30, three times
  Public 9k's, for no gain at the end.

## Caveats

- **One run of each.** D4's 277 is itself one run; the second runs are
  still owed. The difference is inside the noise.
- **Public 22k ran all 60 passes.** It was still improving on its own
  check at pass 60 (0.094, 0.090), so a longer public stage might do more.
- **The public scores are proto.py's**, on the reader's own symbols, read
  on Modal. They are not the public table's numbers
  (`~/Data/manuscript-labeler/experiments/benchmarks/public-table.md`),
  which come from a different scorer.
- **G. 213's notes are in Drawn 11k** (OpenScore's quartets), as for D4. OSSQ's period staves don't include it.

## Next

1. Not adopted. If OSSQ is tried again, try it where it should matter: a
   test of print, such as G. 213's Berlin print staves (paired the same
   day, `experiments/zeus/g213/README.md`), or as a share of the Boccherini
   stage instead of the public stage.
2. The second runs of D4 and D3L2-h96, still owed.
3. Clef changes inside a staff: count how often each reader leaves out a
   drawn clef change across the labelled sources, not just here.

## Cost

- **Modal, L40S:** Public 22k about 5 GPU-hours, **$10.30**; Drawn 11k
  $0.63; Boccherini 3k $0.69. Total **$11.62** (`modal billing report`,
  2026-10-20, by app, CPU and memory included).
- **Modal, default GPU:** the four public-test readings, not yet billed
  (estimate ~$0.50).
- **Mac (Mac mini, M1, 16 GB):** reading the clean test, under a minute.

## Reproduce

Public 22k:

```
modal run experiments/musvit/modal_app.py::main --gpu L40S --args "E3-h96-ossq
  --encoder full --amp --train /staves/public/dolores/samples.train.txt
  /staves/public/dolores/samples.validation.txt
  /staves/public/omniomr/samples.train.txt
  /staves/public/omniomr/samples.validation.txt
  /staves/ossq-period/samples.ossq-period.txt --vocab-extra <E2-h96's lists>
  --dev /staves/public/dolores/samples.test400.txt --dev-limit 200
  --epochs 60 --eval-every 5 --patience 3 --layers 8 --height 96"
```

Drawn 11k and Boccherini 3k are SF1-h96's and D3S-h96's commands
(reports/2026-10-20-synthetic-and-strip-height, Reproduce) with `--init
E3-h96-ossq` and `--init SF1-h96-ossq`. Public readings: `--init <run>
--init-file best.pt --epochs 0 --train <test list> --dev <test list>`.
Readings and scores: `experiments/zeus/answers/` and `results/`,
`*-musvit-D3S-h96-ossq-mps.json`; models on the Modal volume `musvit`,
`runs/<run>`.
