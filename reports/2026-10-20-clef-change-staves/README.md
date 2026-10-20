# Drawn staves with clef changes (2026-10-20)

The reader is trained in stages, each named for what it trains on and its
size in staves (see [the stages](../README.md#the-readers-training-stages)):

| stage | what it trains on | staves |
|---|---|---:|
| **Public 9k** | the public datasets, MusiCorpus's Dolores and OmniOMR (E2-h96) | 8,765 |
| **Drawn 15k** | Drawn 11k's staves (dataS3), plus 3,970 drawn staves with clef changes inside the staff (dataS4) | 14,760 |
| **Boccherini 3k** | everything of Boccherini's but the clean test (dataL2, dataM, dataT) | 3,411 |

musvit-D4 is Public 9k → Drawn 11k → Boccherini 3k. This run is Public 9k →
Drawn 15k → Boccherini 3k: the same chain with the clef-change staves added
to the drawn stage, and nothing else changed.

**Verdict: the clef changes are mostly fixed; overall a tie with D4.**
- **Bars exact:** 277 of the clean test's 347, the same as D4 (+0, 95%
  interval −11 to +11).
- **Clef errors:** 1, against 4 for D4, D3 and the OSSQ reader. Three of
  the four cello clef changes are now read with the clef sign.
- **Pitch right:** 316 bars against 311 (+5, −3 to +13). The notes as
  written (what the edition would get): 277 against 272 (+5, −6 to +16).
- **Flags for the edition** (Op48-2 I, floor 3): 105 flagged, 94 wrong,
  11 false, against D4's 108, 94, 14. The same errors caught, three fewer
  false flags. The cello's clef-passage false flags (bars 43, 79, 82) are
  still there.

Not adopted yet: every gain is inside the noise, and D4's 277 is one run.

## What we tried

The clef-change staves (dataS4, `experiments/synth/gen_clefs.py`, see
`experiments/synth/README.md`, "Clef changes inside the staff"):
- Real OpenScore quartet staves, with a stretch moved to the clef a copyist
  would use where the music sits high. Pitches are kept; only the clef, and
  so where the notes sit, changes.
- Cello, bass to treble (1,106) or tenor (875), mostly changing back, and
  477 opening in tenor or treble; viola, alto to treble (678), and 199
  opening in treble; 237 OpenScore staves that already change clef, as they
  are; 398 violin staves unchanged, for balance.
- 76% of the changes fall at a bar line, 24% inside a bar, labelled as our
  hand labels do.
- No Op. 48 music. Paper and clefs come only from D1's training staves,
  never KHM 603 I.

Then D4's chain with Drawn 15k in place of Drawn 11k:
1. **Drawn 15k (SF1-h96-clef):** from Public 9k (E2-h96), 10 passes at most,
   best pass on the practice exam: 0.240 at pass 10, against Drawn 11k's
   0.229 at pass 6.
2. **Boccherini 3k (D3S-h96-clef):** D4's command, from Drawn 15k: 24
   passes of a 30-pass schedule.

## Results

**Clean test** (KHM 603 I, 347 bars), read on the Mac, scored by
compare.py with the clef scored apart.

| reader | bars exact | rhythm right | pitch right | exact as written | right, clef apart | clef errors |
|---|---:|---:|---:|---:|---:|---:|
| musvit-D4 (Drawn 11k) | **277** | **300** | 311 | 272 | **277** | 4 |
| with Drawn 15k | **277** | 297 | **316** | **277** | **277** | **1** |
| with Public 22k (OSSQ) | 268 | 298 | 302 | 275 | 275 | 4 |
| musvit-D3 | 270 | 288 | 297 | 264 | 270 | 4 |

By part, bars exact (D4, then with Drawn 15k): violin I 63 and 58, violin
II 62 and 62, viola 74 and 80, cello 78 and 77.

**Paired bootstrap over the 347 bars** (10,000 resamples, 95%), with
Drawn 15k against:
- musvit-D4: bars exact +0 (−11 to +11); as written +5 (−6 to +16); pitch
  +5 (−3 to +13);
- the OSSQ reader: bars exact +9 (−2 to +20); pitch +14 (+5 to +24);
- musvit-D3: bars exact +7 (−7 to +21); pitch +19 (+8 to +31).

**The cello's clef passages** (bars 42–48 and 78–87, two passages each
played twice):
- Bars 47–48 and 79: D4 left the clef out and wrote wrong pitches the
  scorer counted right. The new reader writes the clef and the right
  pitches.
- Bars 42 and 78: D4 was "exact" only by staff position. The new reader has
  the clef right but slips inside the 32nd-note run (a duration, a
  repeated A4), so they now count wrong.
- Bar 82: the one clef change still missed, by every reader so far.

It gained 16 bars D4 missed (8 in the viola) and lost 16 (8 in violin I,
bars 25–29 and 61–66). The violin I losses look like ordinary variation,
not clefs.

**Flags for the edition**, by the edition's `scripts/flag_test.py` on
Op48-2 I (the clean test's movement, so a second measure, not a second
test). The new reader isn't in zeus-score's registry, so
`flag_test_local.py` (saved here) runs the same test with it from a local
release folder. D4's numbers came out as before.

| floor | reader | flagged | wrong | false | caught |
|---:|---|---:|---:|---:|---|
| 2 | with Drawn 15k | 108 | 95 | 13 | 95 of 107 |
| 2 | musvit-D4 | 110 | 94 | 16 | 94 of 107 |
| **3** | **with Drawn 15k** | **105** | **94** | **11** | **94 of 107** |
| **3** | **musvit-D4** | **108** | **94** | **14** | **94 of 107** |
| 4 | with Drawn 15k | 104 | 94 | 10 | 94 of 107 |
| 4 | musvit-D4 | 107 | 94 | 13 | 94 of 107 |
| 6 | with Drawn 15k | 102 | 93 | 9 | 93 of 107 |
| 6 | musvit-D4 | 102 | 93 | 9 | 93 of 107 |
| 8 | with Drawn 15k | 102 | 93 | 9 | 93 of 107 |
| 8 | musvit-D4 | 99 | 92 | 7 | 92 of 107 |

At floor 3, the encode.py floor, the new reader catches vn1 59 and misses
vc 5; D4 the reverse. Its false flags: vn1 25, 28; vn2 11, 29, 31, 65, 88;
va 32; vc 43, 79, 82. D4's add vn1 62, va 27, 31 and vc 87, and lack vn1
25.

## What it means

- **Drawn staves can teach a specific skill.** The clef changes were the
  one weakness all readers shared, and 3,970 drawn staves fixed three of
  four without hurting the rest overall.
- **The scorer now sees it.** With the clef scored apart (compare.py since
  2026-10-20), the fix shows as clef errors 4 → 1 and the notes as written
  277 against 272. The old position-only score couldn't see it.
- **The edition's flags gain a little.** Three fewer false flags at the
  same catch. The clef-passage false flags remain, so they don't come from
  the reader missing the clef.

## Caveats

- **One run of each.** The second runs of D4 and D3L2-h96 are still owed;
  until then ±11 bars is noise.
- **Four clef passages in the test.** Clef errors 4 → 1 is a count of
  four, not a rate.
- **The practice exam got worse** (0.240 against 0.229) in the drawn stage,
  though the clean test didn't. The practice exam is three Op. 48
  movements; the drawn stage's best pass is picked on it.

## Next

1. If adopted, release it as a new musvit version and repeat the flag test
   from the registry.
2. The second runs, to tell small gains from luck.
3. Bar 82 and the clef-passage false flags: look at what the scorer
   objects to there.

## Cost

- **Modal, L40S:** Drawn 15k 0.62 GPU-hours, $1.24 (10 passes, ~200 s
  each); Boccherini 3k 0.34 GPU-hours, $0.68 (24 passes, ~47 s each).
  **$1.92** in all (`modal billing report`, 2026-10-20, by app).
- **Mac (Mac mini, M1, 16 GB):** building dataS4 and checking it by eye,
  CPU only, about an hour; reading the clean test, under a minute; the flag
  test, a few minutes.
- **Upload of dataS4 to Modal:** no GPU.

## Reproduce

```
modal run experiments/musvit/modal_app.py::main --gpu L40S --args "SF1-h96-clef
  --init E2-h96 --init-file best.pt --amp
  --train /staves/dataS3/samples.S-osq.txt /staves/dataS3/samples.S-own.txt
  /staves/dataS4/samples.S4-clef.txt
  --dev <the three practice-exam lists> --epochs 10 --lr 1e-4
  --eval-every 2 --patience 2 --lora-r 64 --lora-mlp"
```

Boccherini 3k is D4's command (reports/2026-10-20-synthetic-and-strip-height,
Reproduce) with `--init SF1-h96-clef`, named D3S-h96-clef. Then:

```
uv run experiments/musvit/read.py ~/Dropbox/Code/boccherini-opus-48 --run D3S-h96-clef --file reader.pt --device mps
uv run experiments/musvit/release.py D3S-h96-clef reader.pt musvit-D4clef test --out <dir> --licence <LICENSE> --notice <NOTICE.md>
uv run reports/2026-10-20-clef-change-staves/flag_test_local.py <dir>/musvit-D4clef@test musvit-D4clef@test <sha256> -- musvit-D4clef@test musvit-D4@2026-10-20
```

Scores: `experiments/zeus/results/D-B_KHM-603-I-musvit-D3S-h96-clef-mps.json`.
Training log: `training-log.txt`. Model: Modal volume `musvit`,
`runs/D3S-h96-clef`.
