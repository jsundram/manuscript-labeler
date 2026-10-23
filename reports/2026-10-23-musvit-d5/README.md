# musvit-D5: as good on notes, far better at beams; and D4's bar counts were luck

2026-10-23. Follow-ups to [Boccherini 6k](../2026-10-22-boccherini-6k/),
whose reader tied D4 on the clean test and miscounted bars on a new hand.
Six more runs (three variants, a repeat of D4's own recipe, two seeds of
the best) settle it: the new data didn't make the reader worse, D4's few
miscounted staves were one lucky run, and the best variant, Boccherini 6k
with Op. 48 weighted three times on D4's drawn stage, is as good as D4 on
notes, much better at beams, and better at the edition's flags. Released
as **musvit-D5** (run D5-B6k-d11-op48x3-s1).

## Every reader on both tests

Clean test: KHM 603 I, 347 bars, read on the Mac (compare.py). Dresden:
Mus.3403 (M. Haydn's MH 411), 353 staves, 3,157 bars, labelled by pairing
and left out of every training set, scored bar by bar in notes and rhythm
(experiments/musvit/held_out.py; markings apart).

| reader | drawn stage | Boccherini stage | clean test | Dresden bars exact | staves miscounted | beam errors | slur errors |
|---|---|---|--:|--:|--:|--:|--:|
| musvit-D3 (128 px, Public 9k only) | none | 3k | 270 | 78.8% | 20 | 4,324 | 967 |
| musvit-D4 | Drawn 11k | 3k | 277 | 83.7% | 8 | 3,990 | 932 |
| D4's recipe again (D3S-h96-r2) | Drawn 11k | 3k | 274 | 81.6% | 20 | 3,921 | 931 |
| the clef run (D3S-h96-clef) | Drawn 15k | 3k | 277 | 75.5% | 27 | 4,153 | 985 |
| Boccherini 6k (D5-B6k) | Drawn 15k | 6k | 277 | 76.0% | 29 | 798 | 863 |
| fewer passes (D5-B6k-s13: 13 of 16) | Drawn 15k | 6k | 279 | 75.0% | 30 | 868 | 985 |
| Op. 48 ×3 (D5-B6k-op48x3) | Drawn 15k | 6k, Op. 48 ×3 | 279 | 79.3% | 19 | 816 | 869 |
| from Drawn 11k (D5-B6k-d11) | Drawn 11k | 6k | 283 | 78.9% | 22 | 863 | 993 |
| Op. 48 ×3 from Drawn 11k, seed 0 | Drawn 11k | 6k, Op. 48 ×3 | 277 | 80.7% | 19 | 849 | 760 |
| **musvit-D5**: the same, seed 1 | Drawn 11k | 6k, Op. 48 ×3 | **283** | 80.2% | **17** | **796** | 786 |

Every run is Public 9k at 96 px (D3 at 128) and D4's last-stage recipe:
24 passes of a 30-pass schedule, lr 1e-4, LoRA rank 64 on attention and
MLP; Boccherini 6k is 6,275 staves, 7,465 with Op. 48 ×3
(experiments/musvit/drivers/train_b6k.py, whose options name each run).

## What the runs say

- **D4's 8 miscounted staves were luck.** Its own recipe, run again, miscounts
  20, as D3 does and as the new readers do (17–22 on Drawn 11k). Two runs of
  one recipe differ by 2 points on Dresden and 12 staves: a single run can't
  rank readers this close. (proto.py now takes --seed; before, every run
  seeded 0.)
- **The clean test can't separate them**: 270 to 283, all within its noise
  (about ±10 bars).
- **The new data's gain is beams, and it repeats**: every reader trained on
  Boccherini 6k makes 800–870 beam errors on Dresden, against 3,900–4,300
  for D3 and D4 (which read this copyist's beams as slurs:
  reports/2026-10-22-boccherini-6k, p49-3).
- **Drawn 15k without Op. 48 weighted up miscounts most** (27–30, three
  runs); on Drawn 11k, 17–22. Op. 48 ×3 helps on either.
- **Fewer passes** (D4's number of steps on twice the data) changed nothing.

## musvit-D5

Chosen from the two seeds of Op. 48 ×3 from Drawn 11k, which agree within
a point on Dresden: seed 1 for its clean test (283 against 277) and fewer
miscounted staves (17 against 19), though 0.5 points lower on Dresden;
inside the noise either way.

**Flags for the edition** (the edition's scripts/flag_test.py on Op. 48
No. 2 I, with the reader from a local build):

| floor | reader | flagged | wrong | false | caught |
|---:|---|--:|--:|--:|---|
| 2 | musvit-D5 | 108 | 95 | 13 | 95 of 107 |
| 2 | musvit-D4 | 110 | 94 | 16 | 94 of 107 |
| **3** | **musvit-D5** | **106** | **95** | **11** | **95 of 107** |
| **3** | **musvit-D4** | **108** | **94** | **14** | **94 of 107** |
| 4 | musvit-D5 | 103 | 95 | 8 | 95 of 107 |
| 4 | musvit-D4 | 107 | 94 | 13 | 94 of 107 |
| 6 | musvit-D5 | 100 | 93 | 7 | 93 of 107 |
| 6 | musvit-D4 | 102 | 93 | 9 | 93 of 107 |
| 8 | musvit-D5 | 98 | 92 | 6 | 92 of 107 |
| 8 | musvit-D4 | 99 | 92 | 7 | 92 of 107 |

At the floor of 3 it catches the one error D4 misses (vn1 59) and misses
none D4 catches. As good or better at every floor.

**Release**: musvit-D5-2026-10-23 (experiments/musvit/release.py), reader.safetensors
sha256 aa5e681bc94e4ca0ed4a1697855746b4a0f3d589b7e59fd985a4e564275dc203,
archive 4ae9750b6892fbb46ee06e04e63d0349b34c979c8defeebc2f8b542f2c5b0e96.
It reads 40 of 40 Dresden staves exactly as the training run did. zeus-score
1.4.0 makes it the default (D4, D3 and D1 stay listed). The pairing and Try
pairing still read with D4 (as D3S-h96): their readings are cached under
that name, and changing the reader would re-read every paired source.

## Next

1. Re-pair with musvit-D5: its beams may pair more staves (a Modal read of
   the 57 sources, about $1, then the parallel pairer).
2. Readers compared on two runs each, by held_out.py and the clean test.
3. A second held-out hand beside Dresden.

## Reproduce

```
uv run experiments/musvit/drivers/train_b6k.py --name D5-B6k-d11-op48x3-s1 --init SF1-h96 --op48 3 --seed 1
uv run experiments/musvit/drivers/train_b6k.py --name D3S-h96-r2 --init SF1-h96 --data b3k    # D4's recipe again
modal volume get musvit runs/<run> ~/.cache/manuscript-labeler/musvit/runs/
uv run experiments/musvit/read.py ~/Dropbox/Code/boccherini-opus-48 --run <run> --file reader.pt --device mps
uv run experiments/musvit/held_out.py <dataW4>/samples.D-Dl_Mus.3403-P-513.txt --runs D3-tf8-all D3S-h96 ... <run>
uv run experiments/musvit/release.py D5-B6k-d11-op48x3-s1 reader.pt musvit-D5 2026-10-23 --out <dir> --licence <LICENSE> --notice <NOTICE.md>
uv run reports/2026-10-20-clef-change-staves/flag_test_local.py <dir>/musvit-D5@2026-10-23 musvit-D5@2026-10-23 \
  aa5e681bc94e4ca0ed4a1697855746b4a0f3d589b7e59fd985a4e564275dc203 -- musvit-D5@2026-10-23 musvit-D4@2026-10-20
```

The other runs' options are in train_b6k.py's docstring; their training
logs are in `training-logs/`, their clean-test readings in
experiments/zeus/results/ (`D-B_KHM-603-I-musvit-<run>-mps.json`).

## Cost

- **Modal:** $4.96 for the six runs here (`modal billing report`, by
  app): Op. 48 ×3 $1.37, from Drawn 11k $1.14, the two seeds $0.82 each,
  D4's recipe again $0.43, fewer passes $0.38. With Boccherini 6k's first
  run ($0.93), $5.89.
- **Mac (M1):** the clean test and Dresden for each reader, the flag test,
  the release and its check, about 1 h.
