# D3's recipe with a synthetic stage, at 128 and 96 px (2026-10-20)

**Verdict: the best reader so far, but not proven better.** D3's recipe,
started from a synthetic stage and read at 96 px high, read 277 of the
clean test's 347 bars exact (80%). The released musvit-D3 reads 270. The
gain (+7 bars, 95% interval −5 to +19) is inside the noise, as is the
gain over the best 128 px run (+5, −6 to +15). It is also about 30% faster
to read.

The two changes only help together:
- **At 128 px, the synthetic stage did nothing:** 270 against 272 (−2, −13
  to +9).
- **At 96 px without it, reading got worse:** 260 against 272 (−12, −23
  to −1).
- **At 96 px with it, the synthetic stage helped clearly:** 277 against
  260 (+17, +7 to +27).

One run of each, so the pattern may be partly noise.

## What we tried

Every run is D3's recipe: stage 2 on everything but the clean test (Op.
48's training and practice-exam movements, the re-paired Philhar staves,
the Madrid copies; 3,411 staves), 24 passes of a 30-pass schedule, from a
stage-1 reader. The runs differ in two ways:

- **Strip height:** 128 px (as D3) or 96 px. At 96 px stage 1 was
  retrained at 96 too (E2-h96, 2026-10-18).
- **Synthetic stage:** none (start from stage 1), or a synthetic stage
  first: dataS3's 10,790 copyist-drawn staves alone, from stage 1, the
  best pass picked on the practice exam (SF1 at 128 px; SF1-h96 at 96 px,
  best 0.229 at pass 6, as SF1's 0.228).

All four use dataL2 (Op. 48's staves with every beam); D3 used dataL.

## Results

Clean test (KHM 603 I, 347 bars), read on the Mac (`read.py --device
mps`), scored by compare.py.

| run | height | synthetic stage | bars exact | rhythm right | pitch right |
|---|---:|---|---:|---:|---:|
| musvit-D3 (released) | 128 | none | 270 (78%) | 288 | 297 |
| D3L2-tf8-all | 128 | none | 272 (78%) | 302 | 301 |
| D3S-synth-all | 128 | SF1 | 270 (78%) | 295 | 303 |
| D3L2-h96 | 96 | none | 260 (75%) | 284 | 302 |
| **D3S-h96** | 96 | SF1-h96 | **277 (80%)** | 300 | **311** |

**Paired bootstrap over the 347 bars, 95%:**

| comparison | bars | interval |
|---|---:|---:|
| synthetic stage, at 128 px (D3S against D3L2) | −2 | −13 to +9 |
| synthetic stage, at 96 px (D3S-h96 against D3L2-h96) | +17 | +7 to +27 |
| 96 px, no synthetic stage (D3L2-h96 against D3L2) | −12 | −23 to −1 |
| 96 px, with it (D3S-h96 against D3S) | +7 | −4 to +18 |
| the best against the best 128 px run (D3S-h96 against D3L2) | +5 | −6 to +15 |
| the best against the released D3 | +7 | −5 to +19 |

## What it means

- **The synthetic stage's earlier gain (+12 to +14 with D1's recipe,
  reports/2026-10-19-synthetic-first) didn't carry to D3's recipe at
  128 px.** D3's recipe has 18% more real staves (3,411 against 2,892),
  including the practice exam's movements and the Madrid copies. More
  real data may leave less for synthetic staves to add, or the earlier
  gain was partly noise.
- **At 96 px the reader needs the synthetic stage.** Without it, 96 px
  lost 12 bars, beyond the noise. With it, 96 px gave the best reading so
  far. One reading: at 96 px, closer to the staff size MuSViT was
  pretrained at, the encoder has more to relearn, and 10,790 extra staves
  give it room.
- **Pitch is where 96 px gains:** 311 bars right in pitch, the most of any
  reader, against 297 to 303 for the others.

## Caveats

- **One run of each.** The bootstrap covers which bars were drawn, not
  run-to-run noise, and the interaction rests on single runs.
- **The clean test has been consulted many times.** Only one comparison
  here clears zero by a margin (+17 at 96 px).
- **No unseen-hand test:** D3's recipe trains on the Madrid copies and
  Op. 32, so only the clean test is held out.
- The copyist-drawn staves carry some practice-exam pixels (see the
  synthetic-first report); the practice exam picked SF1's and SF1-h96's
  passes, not stage 2's, and the clean test isn't affected.

## Next

1. **Done, 2026-10-20:** D3S-h96 released as musvit-D4, zeus-score 1.3.0's
   default, as accurate and 30% faster (GitHub release
   `musvit-D4-2026-10-20`). The release reads 40 of 40 test staves exactly
   as the run did.
2. A second run of D3S-h96 and of D3L2 (about $1.40), in the next round of
   training, to see if 277 against 272 holds.
3. Measure the staff size MuSViT saw in pretraining, to choose between 96
   px and smaller.

## Cost

- **Modal, L40S:** five runs (four stage-2 runs and SF1-h96), about 1.7
  GPU-hours, **$3.49** billed on 2026-10-20 (measured, `modal billing
  report`, apps for the five runs, CPU and memory included).
- **Mac (Mac mini, M1, 16 GB):** reading the clean test, under a minute a
  run.

## Reproduce

The runs were launched directly with `modal run
experiments/musvit/modal_app.py::main --gpu L40S --args "NAME --init INIT
--init-file best.pt --amp --train ... --dev ... --epochs 30 --stop-at 24
--eval-every 30 --lr 1e-4 --lora-r 64 --lora-mlp"`, with the training
lists of `experiments/musvit/drivers/train_d3.py` on dataL2 (Op. 48 from
`drivers/train-L.txt` and `dev-L.txt`, plus dataM and dataT). INIT is
E2-tf8 (D3L2), SF1-synth (D3S), E2-h96 (D3L2-h96) or SF1-h96 (D3S-h96).
SF1-h96 is `drivers/synth_first.py`'s stage A from E2-h96. Readings and
scores: `experiments/zeus/answers/` and `results/`,
`*-musvit-<run>-mps.json`; models on the Modal volume `musvit`,
`runs/<run>`.
