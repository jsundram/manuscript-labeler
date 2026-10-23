# Boccherini 6k: twice the data, a new hand much better read

2026-10-22. musvit-D4's chain with its last stage on the re-detected,
re-paired sets: **Public 9k → Drawn 15k → Boccherini 6k** (run D5-B6k),
against D4's Public 9k → Drawn 11k → Boccherini 3k.

**Verdict: no better on the Berlin hand, much better on a hand it never
saw.**
- **The clean test** (KHM 603 I, Berlin): 277 of 347 bars exact, the
  same as D4 (+0; 13 bars better, 13 worse; 95% interval −10 to +10).
- **A held-out manuscript in a new hand** (Dresden Mus.3403, M. Haydn's
  MH 411 quintet, 353 staves its pairing labelled, left out of training):
  symbol errors 16.2% → **10.3%**, staves exact 23 → **48**. The same
  chain with Boccherini 3k (the clef run) reads it worse than D4 (18.2%,
  14), so the gain is the new data, not Drawn 15k.
- **Flags for the edition** (Op48-2 I, floor 3): the same 94 of 107
  errors caught; 17 false flags against D4's 14.
- **Cost:** $0.93 on Modal (L40S $0.82, CPU $0.10); 24 passes of 46–47 s.

Not released. The Berlin hand is what the edition reads now, and there it
ties D4 with three more false flags; on new hands it is clearly better.

## The stages

| stage | what it trains on | staves |
|---|---|--:|
| Public 9k | MusiCorpus's Dolores and OmniOMR (E2-h96) | 8,765 |
| Drawn 15k | drawn staves in our copyists' hands, with the clef-change ones (dataS3, dataS4; SF1-h96-clef, from the clef run) | 14,760 |
| **Boccherini 6k** | Op. 48's training and practice-exam movements (dataL2: 595), Philhar's quartets with the Madrid copies (dataM5: 4,371), Philhar's other works but Dresden (dataW4: 853), the print's agreed bars (dataP4: 21), G. 213's copies (dataG213-4: 435) | **6,275** |

Boccherini 3k was dataL2, dataM and dataT (3,411). The new sets come from
the [redetection](../2026-10-22-redetection/),
[bars that cross a line](../2026-10-22-split-bars/) and
[bar lines the reading missed](../2026-10-22-missed-bar-lines/); the Madrid
copies, dataT before, are in dataM5. Campioni's Op. 7 (Berlin, 338
staves) is in too, so the stage isn't Boccherini's alone. No Op. 48 source
is in the new sets, so the clean test's music isn't either; every token
in them is in Drawn 15k's vocabulary.

The recipe is D4's Boccherini stage: 24 passes of a 30-pass schedule, lr
1e-4, LoRA rank 64 on attention and MLP, bfloat16. New: the batches built
by 4 worker processes on 5 reserved cores (proto.py --workers): a pass
took 46–47 s for 6,275 staves, as D4's took 47 s for 3,411, about twice
the staves a second.

## Results

**Clean test** (KHM 603 I; read on the Mac, `-mps`):

| reader | bars exact | rhythm | pitch | clef errors |
|---|--:|--:|--:|--:|
| musvit-D4 (Drawn 11k, Boccherini 3k) | 277 | 300 | 311 | 4 |
| with Drawn 15k (clef run) | 277 | 297 | 316 | 1 |
| **Boccherini 6k** | **277** | 296 | 316 | 1 |

By part, bars exact (D4, clef run, Boccherini 6k): violin I 63, 58, 60;
violin II 62, 62, 58; viola 74, 80, 79; cello 78, 77, 80. Violin II's
duration errors rose (47, 33, 64).

**Held out, Dresden Mus.3403** (proto.py --epochs 0, the 353 staves as
dataset.py labelled them from the pairing, checked bar for bar against
the encoding):

| reader | symbol errors | staves exact |
|---|--:|--:|
| musvit-D4 | 16.2% | 23 |
| with Drawn 15k (clef run) | 18.2% | 14 |
| **Boccherini 6k** | **10.3%** | **48** |

**Flags for the edition** (the edition's flag_test.py on Op48-2 I, with
the reader from a local test build, as in the clef run):

| floor | reader | flagged | wrong | false | caught |
|---:|---|--:|--:|--:|---|
| 2 | Boccherini 6k | 112 | 95 | 17 | 95 of 107 |
| 2 | musvit-D4 | 110 | 94 | 16 | 94 of 107 |
| **3** | **Boccherini 6k** | **111** | **94** | **17** | **94 of 107** |
| **3** | **musvit-D4** | **108** | **94** | **14** | **94 of 107** |
| 6 | Boccherini 6k | 102 | 93 | 9 | 93 of 107 |
| 6 | musvit-D4 | 102 | 93 | 9 | 93 of 107 |

## What it means

The scaling guess (from 1,508, 2,892 and 3,411 staves: about +10 bars of
the clean test for each doubling) didn't hold on the clean test. The
earlier gains came from more of the Berlin and Paris hands; the new staves
are mostly other copyists' (Op. 32's, the Madrid and Dresden copyists',
Campioni's). They show where they should: on a hand none of the training
had, symbol errors fell by about a third. The clean test alone can no
longer tell which reader is better; the held-out manuscript is the second
measure the next comparisons need.

## Next

1. Decide whether to release it: better for new manuscripts, a tie (three
   more false flags) for the edition's Berlin copies.
2. A second held-out hand, to know the Dresden gain isn't one copyist's.
3. Violin II's durations on the clean test: what the new reader misreads.

## Reproduce

```
modal volume put musvit-staves ~/.cache/manuscript-labeler/zeus/dataM5 /dataM5   # and dataW4, dataP4, dataG213-4
uv run experiments/musvit/drivers/train_b6k.py
modal volume get musvit runs/D5-B6k ~/.cache/manuscript-labeler/musvit/runs/
uv run experiments/musvit/read.py ~/Dropbox/Code/boccherini-opus-48 --run D5-B6k --file reader.pt --device mps
uv run experiments/musvit/proto.py held --init D5-B6k --init-file reader.pt --epochs 0 \
  --train <dataW4>/samples.D-Dl_Mus.3403-P-513.txt --dev <the same> --device mps
uv run experiments/musvit/release.py D5-B6k reader.pt musvit-D5b6k test --out <dir> --licence <LICENSE> --notice <NOTICE.md>
uv run reports/2026-10-20-clef-change-staves/flag_test_local.py <dir>/musvit-D5b6k@test musvit-D5b6k@test \
  e5604fd0c6e27457c36dd9afaba9bff9c749f18b3d08572f42284b04e26e1494 -- musvit-D5b6k@test musvit-D4@2026-10-20
```

The model is on the Modal volume `musvit`, `runs/D5-B6k`; the training
log is `training-log.txt` here.

## Cost

- **Modal:** $0.93 (`modal billing report --for today`): L40S $0.82, CPU
  $0.10 (5 cores), memory $0.01. Uploads free.
- **Mac (M1):** the clean test, the held-out test (three readers) and the
  flag test, about 15 min.
