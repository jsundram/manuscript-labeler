# Zeus rebuilt on MuSViT: first results

Can an image encoder pretrained on 9.7 million IMSLP pages (MuSViT, ECCV
2026) read Boccherini's copyists better than Zeus's own small encoder? This
records the first attempt (2026-10-16/17). `BRIEF.md` is the plan and the
day-by-day log.

**Result: with the full encoder, it beats Zeus J on the clean test at the
note level** (a third fewer wrong events, clearly beyond chance; pitch
better by 4.6 points of bars, also beyond chance). Bars exact is 67%
against J's 65%: better, but within what one movement can tell apart.
It trained without KHM 602 II, which J had. The first attempt, with the
light encoder, tied J.

## What was built

- **Encoder:** MuSViT-light (a ViT, 22M parameters, 16 px patches), with
  LoRA adapters on its attention (4.8M trainable parameters with the
  decoder). Staves are read at 128 px high and their own width.
- **Decoder:** a 4-layer transformer (torch.nn, d 256) writing Zeus's
  output, LMX, one token at a time, attending to the encoder's patches. Not
  MuSViT's own CTC head: half our staves have more LMX tokens than the
  encoder has columns.
- **Training,** as Zeus was trained: stage 1 on the public staves Zeus's
  stock model learned from (Dolores train + validation, OmniOMR train +
  validation: 8,765 staves); stage 2 on run J's Boccherini staves.
- **On Modal** (an L4 GPU): `modal_app.py` runs `proto.py`; the staves are
  in the `musvit-staves` volume, weights and runs in `musvit`. Training on
  the Mac's GPU didn't work: the Mac became unresponsive at normal
  priority, and stalled at background priority.
- **Scored as Zeus is:** `read.py` cuts the clean test's staves with
  compare.py's own crop (the one the training staves were cut with), has
  the model read them on Modal, and puts the readings in compare.py's
  cache; compare.py then scores them without loading Zeus.

```
modal run experiments/musvit/modal_app.py --args "NAME --train ... --dev ..." [--gpu L4]
uv run experiments/musvit/read.py ~/Dropbox/Code/boccherini-opus-48 --run NAME
```

## Results

The clean test, KHM 603 movement I (347 bars), by compare.py:

| | bars exact | rhythm | pitch | extra events |
|---|---|---|---|---|
| Zeus J | 225 (65%) | 257 | 256 | 36 |
| MuSViT, J's staves less KHM 602 II (`stage2-602II`) | **225 (65%)** | **266** | 252 | **17** |
| MuSViT, all of J's staves (`stage2-J`) | 223 (64%) | 260 | 251 | 46 |
| **MuSViT full encoder**, J's staves less KHM 602 II (`stage2-full-602II`, best) | **233 (67%)** | 259 | **272** | 47 |
| **MuSViT full encoder, all of J's staves** (`stage2-full-J`, pass 12 as chosen on KHM 602 II) | **241 (69%)** | **272** | **279** | 32 |

The full-encoder reader against Zeus J, bar by bar (10,000 paired
resamples of the 347 bars):

- bars exact: +2.3 points, 95% interval −1.4 to +6.1 (not yet beyond chance);
- bars right in pitch: +4.6 points, +0.6 to +8.9;
- wrong events: 270 against J's 412, 167 fewer per resample on average
  (95% interval 92 to 245). Events right: 87% against 80%.
- by part, bars exact (J, new): vn1 47, 45; vn2 46, 55; va 53, 55; vc
  79, 78. The viola's events right: 401, 474.
- the viola's broken-chord 32nds (bars 26–31 and 61–67, J's known
  weakness): wrong pitches 83 → 28; still 1 bar of 13 exact (groups
  dropped or added).

One movement can't separate two models within about 4 points, so both are
ties. On the held-out movement (KHM 602 II, 32 staves, symbol error rate),
`stage2-602II` made 17–18% against Zeus run G's 19% (G is Zeus's run on
much the same staves without KHM 602 II).

How it got there, on the held-out movement:

| | symbol errors, KHM 602 II |
|---|---|
| no stage 1 (J's staves only) | 28% |
| stage 1, then stage 2 (3 passes) | 20% |
| stage 1, then stage 2 (best, pass 9) | 17% |
| Zeus's first fine-tune / run G | 22% / 19% |

Without the public staves the decoder memorised J's 2,500 staves instead
of learning to read: stage 1 is needed. Stage 1 alone reached 17% symbol
errors on 200 Dolores test staves (stock Zeus reported about 12% there, by
its own evaluation).

## The full encoder (2026-10-17)

MuSViT (89M) instead of MuSViT-light, with bfloat16 arithmetic on an L40S
GPU, and training until the held-out score stopped improving:

- stage 1 (public staves): 60 passes (the cap), about 97 s each; on 200
  Dolores test staves 9.4% symbol errors at best (light: 17%; stock Zeus
  reported about 12%), 47–51 exact.
- stage 2 (J's staves less KHM 602 II): stopped at pass 21; best at pass
  12, 12.8% on KHM 602 II (light: 17%; Zeus G: 19%).

## Tuning round 2: data and adapters (2026-10-17)

The practice exam grew to 114 staves: KHM 602 II plus Op. 48/5 I in both
sources (RES 507 (17); Vma 1067 (3), its slurs dropped, as the encoding's
follow RES 507 (17)). Op. 48/5 II in both sources joined training (93
staves; 2,629 in all). Four stage-2 variants from `stage1-full`, run at
once on L40S GPUs, each stopping when the exam stopped improving:

| variant | best symbol errors, practice exam | clean test, bars exact |
|---|---|---|
| B0 baseline (LoRA rank 16 on attention) | 17.9% (pass 15) | 240 (69%) |
| **B1 larger adapters** (stage 1's folded in; rank 64 on attention and MLP) | **15.8%** (pass 30, still improving) | **251 (72%)** |
| B2 top 4 encoder layers unlocked (a tenth of the learning rate) | 17.6% (pass 24) | |
| B3 Zeus's full augmentation set | 19.4% (pass 24) | |

Paired resampling on the clean test: B1 against Zeus J, bars exact **+7.5
points (95% interval +3.7 to +11.5)** and 246 fewer wrong events; B1
against B0, +3.2 points (−0.3 to +6.6) and 45 fewer wrong events (6 to 85
fewer). Adding Op. 48/5 II (B0 against `stage2-full-602II`): +2.0 points
(−0.9 to +4.9). Both B models are held-out models: neither saw KHM 602 II
or Op. 48/5 I. Zeus's augmentation, made to turn clean engravings into
scans, hurt on real scans. Beam search, with or without a penalty for bars
that don't add up to the time signature, did no better than reading one
symbol at a time (KHM 602 II: 245 bars exact greedy, 239–240 with beams):
most remaining errors keep the bar's length.

## Round 3: two voices, decoder size (2026-10-17)

Two voices: dataset.py now writes a bar where the encoding has two voices
(double stops) as Zeus's data does, line 1, a <backup>, line 2 (voices
regrouped into lines by where they overlap; LilyPond numbers temporary
voices per passage). Op. 48 staves kept rose from 497 to 593; the practice
exam (KHM 602 II, Op. 48/5 I in both sources) is now 145 staves, two-voice
ones included, so its scores aren't comparable with round 2's.

| second stage on the two-voice data, larger adapters | practice exam (145) | clean test, bars exact |
|---|---|---|
| C0: from the 4-layer stage 1 (`stage1-full`) | 19.2% | 242 (70%) |
| **C1: from an 8-layer stage 1 (`E2-tf8`)** | **18.6%** | **265 (76%)** |
| C2: from the 4-layer stage 1 on the pretrained encoder (`stage1-bocch`) | 18.4% | 254 (73%) |
| C3: from a 4-layer stage 1 with column memory (`F1-columns`) | 18.9% | 255 (73%) |
| C4: pretrained encoder and 8-layer decoder (`G1-bocch-tf8`, 8.9% on Dolores, the best stage 1) | 20.0% | 263 (76%); rhythm 290, pitch 298, 11 missed |
| C5: pretrained encoder, 8-layer decoder and column memory (`G2-bocch-tf8-cols`) | 20.4% | 253 (73%); 4 extra events |
| C6: Zeus's own decoder design (`ZeusHead`: LSTMs, attention fed back) on column memory (`F2-zeus`) | 21.4% | 221 (64%) |

On the public staves the 8-layer decoder had done worse (12.4% at best,
stopping at pass 40, against the 4-layer's 9.4%), yet on the clean test it
is the best reader so far: against Zeus J **+11.5 points of bars exact
(95% interval +7.2 to +15.9)**, rhythm 287 and pitch 293 of 347, events
right 91%; against B1 +4.0 (+0.6 to +7.5); against C0 +6.6 (+2.9 to +10.4).
The practice exam put C1 and C0 within a point of each other, so the
clean test is now deciding between models, which spends it: a gain this
size should be confirmed on another held-out movement before it is
trusted. Pretraining on our manuscripts without labels (`pretrain.py`: 8,872 staves
from 1,714 pages, the four held-out manuscripts left out; 20 passes, about
30 minutes, rebuild loss 0.035 to 0.0081) helps a little on our staves: C2
against C0, the same recipe on the original encoder, +3.5 points (0.0 to
+6.9). On the public staves it did slightly worse (10.5% against 9.4%),
as an encoder tuned to our hands might. Column memory (each column's 8 patches joined into one vector for the
decoder, as Zeus packs a column's height) tied patches on the public
staves (9.4% each) and helps on ours: C3 against C0 +3.7 points (0.0 to
+7.5), with 6 extra events against C0's 64. Pretraining, the 8-layer
decoder and column memory each change a different part, so their
combinations are the next runs (`G1-bocch-tf8`, `G2-bocch-tf8-cols`).

A faithful copy of Zeus's decoder on MuSViT's column memory (`ZeusHead`,
trained a symbol at a time, batches of 32 then 16) learned fastest per
training step on the public staves but settled at 13.1% there, and on ours
it is the weakest reader of the round (221 bars, behind Zeus J's 225; 175
wrong pitches and 175 wrong durations). The transformer decoders keep the
lead.

The three gains don't stack. With the 8-layer decoder in place, adding
pretraining (C4) gives 263 against C1's 265, and adding column memory as well
(C5) gives 253: −3.5 points against C1 (−7.5 to +0.3). Readers C1, C4, C3, C2
and C5 span 253–265 bars, which one movement can't separate; the gap they
share over Zeus J (+8 to +11.5 points) is the result. Column memory keeps
spurious events near zero in every model that has it (4–6, against 15–64).
Next gains look more likely to come from data than from architecture.

Fine-tuning on our staves costs the public benchmark: C1 scores 35.7% SER on
the 200 Dolores test staves, against 12.5% for its stage-1 model `E2-tf8`
(Zeus's own fine-tunes went from 12% to 15%). To measure properly on the
final model. The clean test has 16 two-voice bars, so two-voice training
can't show much there (C0 against B1: −2.6, −5.8 to +0.9).

## Why the light reader and Zeus scored alike

They miss mostly the same bars, but not the same way. Of 347 bars:

- both right: 207; both wrong: 104; only Zeus J right: 18; only MuSViT
  right: 18.
- Of the 104 both miss, they read only 5 the same way.

The bars both miss are dense ones: 32nd-note broken chords in the viola,
violin passagework, 10–16 events where one slip makes the bar wrong. Both
models learn from the same few thousand staves, so the same bars are hard
for both; the data, not the architecture, sets the ceiling. MuSViT's slips
there are often smaller (a dropped group of four, a rest a 16th instead of
a 32nd), which bars exact doesn't reward. Because their mistakes differ, a
bar where the two disagree is worth a look: they agree on 212 bars, of
which 207 are right.

## Cost

About $12 of Modal time in all (estimate): about $7 for the light-encoder
work (tests, the run without stage 1, stage 1 for 2.6 hours, two stage-2
runs, readings) and about $5 for the full encoder (stage 1 for 1.7 hours
on an L40S, stage 2, readings).

## Next

- Stage 2 on all of J's staves, with the full encoder; and a second test
  movement, to tell gains of a few points apart.
- Continued MuSViT pretraining on all the manuscripts (about 2,300 pages,
  most never matched to an encoding), without labels.
- Use the two readers together: flag the bars where they disagree.
- The licences: MuSViT's and Zeus's weights are CC BY-NC-SA, and so is
  anything trained from them.
