# MuSViT reader D3 (musvit-D3, 2026-10-18)

A reader for Boccherini's copyists built on MuSViT, an image encoder
pretrained on 9.7 million pages of printed music. It reads one staff at a time
and writes out its notes in Zeus's output format, so the edition and
[zeus-score](README.md) can use it in Zeus's place. On the clean test it
gets 270 of 347 bars exact against Zeus J's 225. It is in the registry
beside Zeus J; Zeus J stays the default until the edition's flag threshold
is retuned for it.

> **Licence: CC BY-NC-SA 4.0. Non-commercial use only; adaptations shared
> alike.** The encoder adapts MuSViT's weights (PRAIG, University of
> Alicante, https://github.com/OMR-PRAIG-UA-ES/MuSViT), which carry that
> licence, and the reader was first trained on MusiCorpus (OmniOMR), which
> does too. Attribution: PRAIG (MuSViT); OmniOMR (MusiCorpus, Zeus's LMX
> format and tools); Philhar (the quartet encodings); Jason Sundram (the
> reader, its training and training data).

A second model, **musvit-D1**, is the same recipe without the Madrid copies,
KHM 602 II and Op. 48 No. 5 I. Those can still test it, so it is the
reference for experiments; D3 is the one to use.

## The model

| | |
|---|---|
| Architecture | MuSViT's encoder (a ViT-Base: 12 layers, width 768, 16 px patches, 89M parameters) reads a staff image 128 px high at its own width (up to 2,688 px), as 8 rows of patches. An 8-layer transformer decoder (width 256, 8 heads) attends to every patch and writes the staff as tokens. 98M parameters in all; 15 times Zeus's size. |
| Output | Linearized MusicXML (LMX), Zeus's format: 137 tokens in all (the public staves' and ours), including two voices written as Zeus's data writes them (line 1, `<backup>`, line 2). |
| Starting weights | MuSViT (PRAIG/musvit on Hugging Face, ECCV 2026), MAE-pretrained on IMSLP pages |
| This model | D3-tf8-all, pass 24 of a 30-pass schedule. 195 MB (half precision, its adapters folded into the encoder). sha256 of reader.safetensors in the registry. |
| Input | The staff Zeus is given: compare.py's crop from the bar export (a staff space beyond each end, 2.5 above and below, straightened, the paper brightened), saved as JPEG at quality 95, then resized to 128 px high. |
| Environment | Python 3.10–3.12, PyTorch, transformers, safetensors. No MuSViT download and no peft: the archive holds the whole reader. On a Mac it reads on the GPU (mps) in half precision. |
| Training | On Modal's GPUs: stage 1 about an hour on an L40S, stage 2 about 22 minutes. |
| Code | The labeler's `experiments/musvit/`: `proto.py` (the reader, training, reading), `modal_app.py` (Modal), `read.py` (the clean test), `release.py` (this archive); `tools/musvit_score.py` (scoring, as `tools/zeus_score.py`). |

## Training data

**Stage 1:** MusiCorpus's public staves, as Zeus's stock model learned them:
Dolores train and validation and OmniOMR train and validation, 8,765 staves.

**Stage 2:** 3,411 Boccherini staves. Every staff's truth is checked: read
back through the scoring code, it must match its encoding exactly. Unlike
Zeus J's data, bars in two voices (double stops) are kept.

| source | work | staves | its truth |
|---|---|---:|---|
| D-B KHM 602 | Op. 48 No. 1, I and II | 70 + 34 | the edition's checked encoding |
| D-B KHM 603 | Op. 48 No. 2, II | 42 | the same |
| F-Po RES 507 (14) | Op. 48 No. 3, I and II | 63 + 35 | the same |
| F-Pn Vma ms 1067 (1) | Op. 48 No. 3, I and II | 88 + 55 | the same |
| F-Po RES 507 (17) | Op. 48 No. 5, I and II | 44 + 33 | the same |
| F-Pn Vma ms 1067 (3) | Op. 48 No. 5, I and II | 69 + 62 | the same, its slurs left out (the encoding's follow RES 507 (17)) |
| **Op. 48, from the edition** | | **595** | |
| Op. 2, G. 159–164, and the Prague parts of No. 4 | parts | 570 | Philhar's encodings, from Boccherini's autographs, paired automatically |
| Op. 22, G. 183–188 | Berlin parts | 612 | the same |
| Op. 22, Paris part-books and the No. 6 parts (Vmbr 153) | | 415 | the same |
| Op. 22, Madrid copies (E-Mc) | Nos. 1–4, 6 | 372 | the same |
| Op. 32, G. 201–206 | parts | 357 | the same |
| Op. 33: F-Pn RES 507 (2) and G. 207–212 | parts | 490 | the same |
| **Philhar** | | **2,816** | |

"Paired automatically": each staff was detected, read by an earlier MuSViT
reader (C4) and aligned bar by bar with the encoding, and kept only if every
measure paired cleanly. That reader kept 3,219 of 4,661 staves (Zeus F had
kept 3,158) and none wrong on the labelled Op. 48 sources.

- **Held out:** KHM 603 movement I (Op. 48 No. 2 I), the clean test, kept
  out of every run since it was encoded.
- **musvit-D1** also leaves out KHM 602 II, Op. 48 No. 5 I (both sources)
  and the Madrid copies: 2,892 staves.

## How it was trained

- **Stage 1** (run E2-tf8): the decoder and rank-16 LoRA adapters on the
  encoder's attention, trained on the public staves; best pass chosen on
  Dolores staves.
- **Stage 2:** stage 1's adapters folded into the encoder and fresh rank-64
  adapters on its attention and MLP layers. Learning rate 1e-4 with warm-up
  and cosine decay over 30 passes, batch 8, bfloat16, a sideways shift of up
  to 8 px. D1 was scored every 3 passes on a practice exam (KHM 602 II and
  Op. 48 No. 5 I in both sources, 147 staves); its best was pass 24. D3
  repeats the recipe with the practice exam in training and stops at pass 24.
- **What mattered** (each on the clean test): the full MuSViT over the light
  one; larger adapters (+3.2 points); an 8-layer decoder over a 4-layer one
  (+6.6); Boccherini's other copyists' staves. **What didn't:** Zeus's
  augmentation, unlocking the encoder's top layers, beam search, LSTM and
  Zeus-style decoders, column memory, and continued pretraining on our
  manuscripts. The last two helped alone but not together with the 8-layer
  decoder.

## Results on the clean test

KHM 603 movement I, 347 bars, scored by compare.py as Zeus is. A bar is exact
when every event matches the encoding in pitch and duration.

| model | bars exact | rhythm right | pitch right | events right | vn1 | vn2 | va | vc |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Zeus J | 225 (65%) | 257 | 256 | 80% | 47 | 46 | 53 | 79 |
| musvit-D1 | 265 (76%) | 296 | 289 | 92% | 64 | 60 | 64 | 77 |
| **musvit-D3** | **270 (78%)** | 288 | **297** | 92% | 66 | 56 | 68 | 80 |

- **Against Zeus J,** bar by bar (4,000 paired resamples): D3 +13.0 points
  of bars exact (95% interval +9.2 to +17.0); D1 +11.5 (+7.5 to +15.6).
- **Its wrong events** (172 of 2,045; one can be wrong in more than one way): 78 in duration, 45 in pitch, 29 missed, 29 in
  chord size, 16 extra, 1 an octave out (Zeus J: 412). Where it reads the
  note right, it shows the accidental as encoded 99% of the time.
- **The viola's broken-chord 32nds** (Zeus J's known weakness): wrong pitches
  fall from 108 to 27.
- **Rhythm** is where it gains least, and D3 is a little behind D1 there:
  the second violin's dense passages lose a group or gain a dot.

## Unseen hands and unseen music

The clean test's copyist is in training (KHM 602, the same hand), so it
can't say how the reader does on a hand it has never seen. The Madrid copies
of Op. 22 (372 staves paired automatically) are such a hand. But Op. 22's
music is in training through other copies, and that matters more than
expected. Symbol error rate (edits over the reference's length):

| reader (training staves) | Madrid | Op. 32 set | clean test, bars exact |
|---|---:|---:|---:|
| Zeus J (saw Op. 22 and Op. 32) | 17.3% | | 225 |
| D1 (2,892; saw both works) | 5.8% | (trained on it) | 265 |
| D1's recipe on a random 1,508 (saw both works) | 11.6% | (partly trained on it) | 254 |
| D1's recipe on 1,508, no Op. 22 or Op. 32 | **24.1%** | **31.7%** | 247 |

- **Knowing the music halves the errors** at equal data (11.6% against 24.1%).
  A reader leans on the notes it has learned. Every Madrid number above, Zeus
  J's included, is flattered by it.
- **On a work and a hand it has never seen, expect about a quarter of symbols
  wrong.** No missing vocabulary explains it: every Madrid token is in that
  reader's training data.
- For the edition this is mostly good news: most sources are copies of works
  already encoded somewhere, which is the Madrid case.

## What fine-tuning gave up: the public benchmarks

MusiCorpus's test staves, which no model trained on: Dolores (2,357 staves)
and OmniOMR (257). Every model read
them the same way and was scored the same way: symbol edits over the
reference's length, readings cut at twice the reference's length (Zeus
loops past a staff's end on a few). "On our symbols" leaves out of both
sides the tokens our labels never contain (about 10%: stem directions, hidden
header marks, tremolos, accents), which a reader trained on our staves
can't learn to write. No paper reports a number for Zeus's solo-staff
snapshot, so stock Zeus is scored here too.

| model | Dolores, on our symbols | as written | OmniOMR, on our symbols | as written |
|---|---:|---:|---:|---:|
| stock Zeus (ayce-2026-08-03) | 18.2% | 17.5% | 24.6% | 24.9% |
| Zeus J | 39.2% | 44.3% | 48.7% | 52.3% |
| MuSViT stage 1 (E2-tf8), before our staves | **17.2%** | **16.7%** | **22.9%** | **23.2%** |
| musvit-D1 | 34.3% | 40.0% | 38.2% | 43.1% |
| **musvit-D3** | 32.8% | 38.8% | 38.8% | 43.6% |

- **Before fine-tuning, the MuSViT reader starts where stock Zeus does,** a
  little ahead (17.2% against 18.2% on Dolores).
- **Fine-tuning on Boccherini costs both a lot** on these staves: their
  errors roughly double. Both learned our copyists' habits (an alto clef
  expected, Boccherini's figures) and drift on other music. Zeus's own
  fine-tunes did the same.
- **D3 gives up less than Zeus J:** 32.8% against 39.2% on Dolores, 38.8%
  against 48.7% on OmniOMR. It is better than Zeus J on its own task and
  forgets less of the general one.
- For general handwritten music, use stock Zeus or a stage-1 reader, not
  these.

## Speed

On an Apple-silicon Mac (the labeler's), the clean test's staves:

| | per staff |
|---|---:|
| Zeus J, reading (tensorflow-macos) | 0.05 s |
| this reader, reading, as first written (GPU, full precision) | 1.9 s |
| with cached decoding (each layer keeps its keys and values) | 0.40 s |
| and adapters folded in, half precision (the release) | 0.28 s |
| scoring a reading (zeus-score: one pass, no step-by-step decoding) | about 0.5 s with page rendering; 66 staves in 42 s, the same as Zeus J |

Cached decoding gives the same readings; half precision changed 1 staff of
64, and the clean test came out at 265 bars on the Mac against 263 on
Modal's GPU. The encoder is now near the Mac GPU's limit (about 0.16 s a
staff): the reader is 5½ times slower than Zeus J at reading, because it is
15 times bigger. For scoring it doesn't matter.

## As the edition's second reader

Not yet measured. Scoring Op. 48 No. 2 I's encoding, it objects (by more
than 3 in log-probability) at 240 tokens, Zeus J at 238, so the two flag
about as often; which flags are real errors, and the best threshold, need
the measurement Zeus J's card reports (flags against later corrections).
Until then Zeus J stays the default.

## The family

On the clean test (bars exact of 347). Each row changes one thing from an
earlier one. The practice exam guided the recipe; the clean test only
reports, though with this many readers it has started to choose between
close ones.

| run | what changed | clean test |
|---|---|---:|
| Zeus J | the previous default | 225 |
| light encoder (stage2-602II) | MuSViT-light, 4-layer decoder | 225 |
| full encoder (stage2-full-J) | MuSViT-Base | 241 |
| B1 | larger adapters, Op. 48 No. 5 II added | 251 |
| C0 | two-voice bars kept | 242 |
| C1 | 8-layer decoder | 265 |
| C2–C5 | pretrained encoder, column memory, both | 253–263 |
| C6 | Zeus's own decoder design on MuSViT | 221 |
| D1 | re-paired Philhar staves with two voices (2,444 against 2,246) | 265 |
| **D3** | D1 with the practice exam and Madrid in training | **270** |

## Known limits

- **New hands:** about 24% symbol errors on a hand and a work it hasn't seen.
- **Rhythm in dense passages:** dropped or added groups of 32nds, dots.
- **Public staves:** see above; it is a Boccherini specialist now.
- **Speed:** 0.28 s a staff to read on a Mac, against Zeus J's 0.05.
- **A small clean test:** one movement can't separate readers within about
  4 points.

## Future directions

- **Synthetic quartet staves**, printed then handwritten, aimed at new hands
  (experiments/musvit/NEXT.md).
- **A second clean test in a new hand**, so that progress on new hands can be
  measured without the music flattering it.
- **Measure and retune the edition's flags** with this reader, then make it
  the default.
