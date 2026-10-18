# Zeus rebuilt on MuSViT

Can an image encoder pretrained on 9.7 million IMSLP pages (MuSViT, ECCV
2026) read Boccherini's copyists better than Zeus's own small encoder? This
records the work from the first attempt (2026-10-16) to the released reader
(2026-10-18). `BRIEF.md` is the plan and the day-by-day log;
`zeus-score/MODEL_CARD_MUSVIT.md` is the released model's card; `NEXT.md`
is what comes next.

**Result: yes.** The released reader, `musvit-D3`, gets 270 of the clean
test's 347 bars exact (78%) against Zeus J's 225 (65%): +13.0 points, 95%
interval +9.2 to +17.0. It makes 172 wrong events against Zeus J's 412,
and it fixes most of Zeus's known weakness, the viola's broken-chord 32nds
(108 wrong pitches down to 27). It is in zeus-score's registry beside
Zeus J, with a held-out sibling, `musvit-D1`, for experiments.

## What we tried, and what we learned

Each change was judged on a practice exam (held-out movements, symbol
errors) and reported on the clean test (KHM 603 I, bars exact). Points are
bars exact on the clean test.

**What helped**

| change | effect | why we think so |
|---|---|---|
| Two training stages: public staves, then ours | needed: without stage 1, 28% symbol errors on the practice exam against 17% | Without it the decoder memorises a few thousand staves instead of learning to read. |
| MuSViT-Base over MuSViT-light | the light encoder tied Zeus J (225); Base made it 241 | A bigger pretrained encoder sees the page better: pitch improved most. |
| Larger adapters (rank 64, attention and MLP) | +3.2 | More room to adapt the encoder to handwriting. |
| An 8-layer decoder over 4 | +6.6 | Rhythm needs context across the bar: the decoder's job. |
| Bars in two voices kept in training | 497 → 595 Op. 48 staves | Not visible on the clean test (16 two-voice bars), but it teaches double stops instead of leaving them out. |
| Re-pairing Philhar's encodings with a MuSViT reader | 3,219 staves kept against Zeus F's 3,158, none wrong | A better reader pairs more staves: more, cleaner labels. |
| More real staves | 254 at 1,508 staves (a random draw), 263–265 at 2,892, 270 at 3,411 | The one lever that kept paying. |

**What didn't**

| change | result | our reading |
|---|---|---|
| Zeus's augmentation set | worse (practice exam 19.4% against 17.9%) | It was made to turn clean engravings into scans; ours are scans. |
| Unlocking the encoder's top layers | no better than adapters | Adapters already give the encoder what it can use from this little data. |
| Beam search, with or without a bar-length penalty | no better than greedy | Most remaining errors keep the bar's length. |
| Zeus's own decoder design (LSTMs) on MuSViT | 221, the weakest | Transformers attend across the whole staff; LSTMs drift. |
| Continued pretraining on our manuscripts (label-free) | +3.5 alone, nothing with the 8-layer decoder | It sharpens pitch (seeing) but not rhythm (reading). |
| Column memory (Zeus's column packing) | +3.7 alone, nothing with the 8-layer decoder; spurious events near zero | It overlaps with what the deeper decoder fixes. |
| Colour instead of grey (the scans are colour; stage 2 only, D1's recipe) | no change: practice exam 19.1% against 19.0%, clean test 260 against 263 (−0.9 points, −3.7 to +1.7) | Ink against paper carries the music; hue adds little the grey doesn't, at least without colour in stage 1. |
| Combining the gains | they don't stack (C1 265, C4 263, C5 253) | The changes fix the same errors; the rest are of another kind; and the test can't see differences under about 4 points. |

**What we learned about measuring**

- **One movement is a small test.** 347 bars can't separate readers within
  about 4 points, and with this many readers it began choosing between
  close ones. A second clean test is the most useful thing we lack.
- **Knowing the music flatters a reader.** The Madrid copies of Op. 22 are a
  hand no model trained on, but Op. 22's music is in training through other
  copies. A reader trained without Op. 22 and Op. 32 made 24.1% symbol errors
  on Madrid; one with the same number of staves that had seen them, 11.6%.
  So Madrid can't rank readers, and **on a work and a hand it has never seen,
  the reader gets about a quarter of symbols wrong**. For the edition that is
  mostly fine: its sources are copies of works already encoded somewhere.
- **The clean test's hand is in training** (KHM 602 is the same copyist), so
  it measures known hands. New hands are the weak spot and the next target.
- **Fine-tuning specialises.** On the public benchmarks the reader gives up
  much of what stage 1 knew (below).

**What it cost:** $53 of Modal time for all of it (two days, 40-odd
training runs), and the Mac stayed usable throughout.

## What was built first (2026-10-16)

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

## First results

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
errors on 200 Dolores test staves (round 4 scores every model on the full
test sets).

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

## Round 4: re-pairing, Madrid, and the release (2026-10-18)

**Re-pairing.** Every Philhar source was read again by C4 and paired with its
encoding (`read_auto.py`, then autopair): 3,219 of 4,661 staves kept against
Zeus F's 3,158, none wrong on the labelled Op. 48 sources. Gains were largest
where Zeus read worst (F-Pn RES 507 (2): 550 against 509; Vma 1067 (1): 142
against 123); Op. 32 fell (412 against 473), its hand reading worse for the
new reader. Rebuilt with two voices: 2,444 Philhar staves (Zeus F's pairing,
one voice only: 2,246).

**D1 and D2:** C1's and C4's recipes on Op. 48 plus the new staves (2,892).

| reader | practice exam | clean test | Madrid, symbol errors | Madrid, exact staves (372) |
|---|---:|---:|---:|---:|
| Zeus J | | 225 | 17.3% | 30 |
| C1 | 18.6% | 265 | 7.4% | 91 |
| C4 | 20.0% | 263 | 7.3% | 102 |
| **D1** | **18.9%** | 263 (265 on the Mac) | **5.8%** | **114** |
| D2 | 19.8% | 257 | 10.7% | 66 |

**What Madrid measures.** D1's lead on Madrid came with much more Op. 22 in
its training, so two runs on 1,508 staves separated the music from the data:

| reader (1,508 staves) | Madrid | Op. 32 | clean test |
|---|---:|---:|---:|
| H1: no Op. 22 or Op. 32 | 24.1% | 31.7% | 247 |
| R1: a random 1,508, both works in | 11.6% | 9.3% (164 of its staves in training) | 254 |

Every token in the Madrid staves is in H1's training data, so it isn't
vocabulary. Knowing the music roughly halves the errors at equal data.

**The release.** D3 is D1's recipe and pass (24 of 30) with the practice
exam's movements and the Madrid copies added: 3,411 staves, everything but
the clean test. Clean test 270 (78%), the best so far; against Zeus J +13.0
points (+9.2 to +17.0). D1 is kept as the held-out reference. Both are
packaged by `release.py` (195 MB, half precision, adapters folded in, no
MuSViT download or peft needed) and scored through zeus-score by
`tools/musvit_score.py`, which shares everything with `tools/zeus_score.py`
but the model.

**On the Mac.** Reading the clean test's staves: 1.9 s a staff as first
written; 0.40 s with cached decoding (each decoder layer keeps the keys and
values of the image and of the symbols so far, the same readings); 0.28 s
with the adapters folded in and half precision (1 staff of 64 read
differently; the clean test came out at 265 against Modal's 263). Zeus J
reads at 0.05 s, being 15 times smaller. Scoring a reading, as the edition
does, is one pass with no step-by-step decoding: 66 staves in 42 s, the same
as Zeus J.

**The public benchmarks.** MusiCorpus's test staves (Dolores 2,357, OmniOMR
257), every model read the same way and scored the same way (symbol edits
over the reference's length; "cut" scores readings cut at twice the
reference's length, which removes the runaways that loop past the staff's
end). No paper reports a number for Zeus's solo-staff snapshot, so stock
Zeus is scored here too.

| model | Dolores (2,357), on our symbols | as written | OmniOMR (257), on our symbols | as written |
|---|---:|---:|---:|---:|
| stock Zeus (ayce-2026-08-03) | 18.2% | 17.5% | 24.6% | 24.9% |
| Zeus J | 39.2% | 44.3% | 48.7% | 52.3% |
| MuSViT stage 1 (E2-tf8) | **17.2%** | **16.7%** | **22.9%** | **23.2%** |
| musvit-D1 | 34.3% | 40.0% | 38.2% | 43.1% |
| musvit-D3 | 32.8% | 38.8% | 38.8% | 43.6% |

"On our symbols" drops from both sides the tokens our labels never contain
(10% of Dolores's: stem directions, hidden header marks, tremolos, accents),
which a reader fine-tuned on our staves never learns to write. Stage 1
starts a little ahead of stock Zeus; fine-tuning roughly doubles both
readers' errors here (Zeus J gives up more: 39.2% against D3's 32.8%).
These are specialists. The "about 12%" for stock Zeus quoted in earlier
rounds came from no published source: no paper reports the solo snapshot,
and scored this way it makes 17.5% (33.0% before runaways are cut). The
earlier 200-staff Dolores numbers (stage 1 9.4–12.5%, C1 35.7%) were scored
on a subset without cutting runaways and aren't comparable with these.

Readings: `modal_app.read_samples` (MuSViT, on Modal) and Zeus's own
`predict` on the Mac; staves from the musvit-staves volume (`/public/*/
samples.test.txt`).

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

$53 of Modal time in all, metered (the first $30 was Modal's free credit, so
$23 billed): about $12 for the light and full encoders (2026-10-16/17),
about $36 for rounds 2–3, the label-free pretraining, the re-pairing reads
and the overnight run (many L40S runs at once), and about $5 on 2026-10-18
(the held-out pair, D3, the public benchmarks).

## Next

`NEXT.md`: synthetic quartet staves (printed, then handwritten) aimed at new
hands; a second clean test in a new hand; measure and retune the edition's
flags with musvit-D3, then make it the default.
