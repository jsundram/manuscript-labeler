# Brief: a Zeus rebuilt on MuSViT, trained on Modal

Written 2026-10-16. It is item 3 in the research TODOs ("Rebuild Zeus on the
MuSViT vision encoder"); `experiments/zeus/README.md` and
`zeus-score/MODEL_CARD.md` have the background.

## The question, and when to stop

Does an image encoder pretrained on 9.7 million IMSLP pages (MuSViT) read
our copyists better than Zeus's small encoder? The bar to clear is **run J:
65% of bars exact on the clean test** (KHM 603 movement I, 347 bars,
`experiments/zeus/compare.py`). **If the first run doesn't beat it, stop.**
Look too at where J fails: the viola's broken-chord 32nds (bars 26–31 and
61–67) and the violins' passagework.

Run the standard recipe first, and change the training-data mix only after
(see "Later" below).

## What is being built

- **Encoder:** MuSViT-light (about 25M parameters; the full one has 85M).
  Weights: https://huggingface.co/PRAIG/musvit, encoder only, CC BY-NC-SA,
  gated: accept the terms and make a Hugging Face token. Code:
  https://github.com/OMR-PRAIG-UA-ES/MuSViT (PyTorch). Train it with LoRA
  adapters first; unfreeze it later if that helps.
- **Head:** writes Zeus's output format, LMX, so `compare.py` and
  `zeus-score` work unchanged. Zeus's own decoder can't be reused: it is
  matched to Zeus's encoder.
- **Settle first: which head.** MuSViT's code ships a CTC head, and CTC
  can't write more tokens than the encoder has columns. Our staves (run J's
  data, measured 2026-10-16) are about 1,300 px wide at Zeus's 96 px height,
  up to 2,000; at MuSViT's 128 px that's about 1,700. In 16 px columns that's
  about 110 steps. Their LMX runs about 100 tokens on average and up to 407
  on an Op. 48 staff. So either:
  - **an autoregressive decoder** (likely): a small transformer decoder, or
    one like Zeus's (an LSTM with attention), reading the encoder's patches;
  - or **CTC with finer columns:** narrower patches, or upsampling the
    encoder's output sideways.
  Check how MuSViT's own staff-level setup handles this before deciding.

  **Settled 2026-10-16: autoregressive.** Measured on the 322 Op. 48 staves
  in run J's data, at 128 px high: median 108 columns (max 167); LMX median
  105 tokens (p95 229, max 407); **165 of 322 staves have more tokens than
  columns**, so CTC at native width is out. MuSViT's staff-level code is
  worse for us: it squeezes every staff to 128 columns and drops longer
  targets. Its full-page code already pairs MuSViT with a transformer
  decoder (SMT: `experiments/full_page_omr/smt_foundation/modeling_smt.py`,
  8 layers, d_model 256, cross-attending to the patches); reuse that decoder
  on staves.

  **Encoder timing on this Mac (M1), full MuSViT (89M), one staff at a
  time, 128 px high at native width (about 1,040 patches):** forward 355 ms
  on the CPU, 205 ms on the GPU (PyTorch's Metal backend); forward and
  backward 945 ms CPU, 610 ms GPU. So reading on the Mac is practical.
  **Training is not** (2026-10-17): the prototype's first epoch (32 staves)
  took 29 s at normal priority but made the Mac unresponsive, and at
  background priority (`taskpolicy -b`) it finished no epoch in 30 minutes.
  All training goes to Modal; the Mac reads and scores. The weights load with `ViTModel.from_pretrained` (only
  the MAE pretraining decoder's weights are left unused). MuSViT-light is a
  separate gated repo, `PRAIG/musvit-light`.
- **Framework:** PyTorch with standard layers only (no NVIDIA-only
  kernels), so the trained model runs on the Mac's GPU through PyTorch's
  Metal support, or ported to MLX. A port must score the same as the
  original on the clean test before we switch. (Today's Zeus can't train on
  the M1's GPU: tensorflow-metal is 37 times slower; see the Zeus README.)

## The standard recipe

1. **Train the head on public data**, as Zeus's stock model was: MusiCorpus
   (Dolores train and validation, OmniOMR train), with OLiMPiC if Zeus's
   published recipe used it. Check Zeus's paper and repo for the exact mix.
   This stage is needed because the head starts from nothing.
2. **Fine-tune on run J's data:** 2,568 staves. That's 322 from the Op. 48
   encodings (`~/.cache/manuscript-labeler/zeus/dataJ`) and 2,246 Philhar
   staves (`dataG`'s `*-union` sets). Keep J's recipe where it carries over:
   learning rate 1e-5 with cosine decay, a sideways shift of up to 8 px, the
   last epoch kept.
3. **Score locally on the clean test**, the one runtime for comparing models
   (PyTorch on the CPU, or always on the GPU: pick one and keep it).
   `compare.py` needs an adapter: it asks Zeus for a staff's LMX, and the new
   model must answer the same question. Its readings are cached under the
   model's name.
4. **Hold out KHM 602 II for choices along the way** (agreed 2026-10-16,
   for this first test only; J trained on it, so it comes out of this run's
   data), so that the clean test only answers the final yes or no.

## Modal

- **One-time setup:** `! modal token new` (sign-in), and the Hugging Face
  token stored as a Modal secret.
- **Volumes:**
  - `staves`: our training data, about 650 MB, uploaded with
    `modal volume put`. After that, only new movements go up.
  - `public`: Dolores, OmniOMR and OLiMPiC, downloaded inside Modal from
    their publishers rather than uploaded from here.
  - `runs`: checkpoints and logs; models come back with `modal volume get`.
- **The app** (`experiments/musvit/modal_app.py`, to write): an image with
  PyTorch, MuSViT's code and the `lmx` encoder; functions for each stage; a
  GPU type per stage (an A10 or L40S should do for the light encoder).
- **Cost** (Modal's prices on 2026-10-16: L4 $0.80/h, A10 $1.10, L40S $1.95,
  A100 $2.10–2.50; plus about $0.20–0.40/h for CPU and memory; $30 a month
  free): a timing run under $1; this first test likely $5–40; a fuller
  programme $50–300. These are estimates until the timing run. **Ceiling for
  this first test: $40** (agreed 2026-10-16); stop and ask before going over.

**Set up 2026-10-17.** Modal client installed with `uv tool install modal`;
signed in; billing added. No Hugging Face secret was needed: the weights were
uploaded instead. Two volumes: `musvit-staves` (dataJ/ and dataG/, no
pickles, 323 MB) and `musvit` (weights/musvit-light, runs/). The app is
`experiments/musvit/modal_app.py`, running `proto.py` on an L4.

**Prototype passes its overfit test** (2026-10-17, run `overfit32b`): 32
staves of KHM 602 I, trained and read back on themselves. 1 s per pass on
the L4 (29 s on the Mac). Loss sat near 0.9 for the first ~60 passes, then
the decoder learned to look at the image: 6/32 staves exact at pass 100,
28/32 at 150, 32/32 from 250. So the encoder, decoder, padding masks and
LMX round trip all work; this says nothing yet about reading unseen staves.

**Without stage 1, it falls short** (2026-10-17, run `noPublic-602II`):
trained from scratch (head) on run J's 2,536 staves less KHM 602 II, 30
passes, lr 3e-4, L4, about 45 minutes, under $1. Symbol error rate on KHM
602 II's 32 staves, by pass: 5: 57%, 10: 44%, 15: 34%, 20: 32%, 25: 30%,
30: 32%; no staff exact. Training loss kept falling (0.09) while the dev
rate stalled: memorising, not learning to read. For comparison, on the same
32 staves and the same measure: Zeus's first fine-tune (heldout-602-II:
KHM 602 I and RES 507 (14) II only, from the stock model) 22% with 1 staff
exact; stock Zeus 77%. Its readings get the rhythm and layout mostly right
and miss pitches by a step (A3 read as G3) and the time signature. So the
head needs stage 1's public staves: the local copies are Dolores train
6,294 and OmniOMR train 695 + validation 218, about 7,200 staves.

**Scoring fix (2026-10-17).** Dev staves were first read in file order, so
a short staff could share a batch with a long one: the encoder attends to
the white padding and stretches its position embeddings over the padded
width, so the short one read worse. proto.py now reads in width-sorted
batches, as training does. `noPublic-602II` rescored: 32% → 28%.

**Stage 1** (run `stage1-public`): Dolores train + validation and OmniOMR
train + validation, 8,765 staves at 256 px high (shrunk on the Mac; the
model reads them at 128), vocabulary 137 (public and our tokens), 30
passes, lr 3e-4, L4, 4.7 min a pass, about 2.6 hours. On 200 Dolores
test400 staves, width-sorted: pass 15: 31% SER, 24 exact; pass 30: **17%
SER, 41 exact**, 3 runaways (14% with readings cut at twice the answer's
length). Stock Zeus's Dolores test SER was about 12% by Zeus's own
evaluation (zeus-findings), so only a rough guide. Before the run, reading
each file's first time off the volume took about 0.15 s, which idled the
GPU for close to an hour; `modal_app.local_copy` now copies the staves to
the container's disk 64 at a time (28,000 files in about 3 minutes).

**Stage 2** (run `stage2-602II`): from stage 1's best, run J's staves less
KHM 602 II (2,536), lr 1e-4, 15 passes, about 20 minutes. SER on KHM 602
II by pass: 3: 20%, 6: 18.5%, 9: **17.3%** (best), 12: 17.9%, 15: 18.1%;
1 staff exact; no runaways. Zeus on the same 32 staves and measure (their
saved readings, last epoch): runs E 18.7%, F 19.8%, **G 19.0%** (2,340
staves, no KHM 602 II: the closest match to this run's data), H 19.8%;
the first fine-tune 22.3%. (Stock and run D come out near 76%, probably
because their saved readings are of older staff crops; ignore them.) So
the first attempt reads about as well as Zeus G, perhaps 1–2 points
better: within what 32 staves can tell apart. Not yet a win; the clean
test decides.

**The clean test (2026-10-17): a tie with J.** `read.py` crops KHM 603 I's
66 staves as compare.py does, has the reader read them on Modal, writes the
readings into compare.py's cache and runs compare.py (Zeus isn't loaded).
Results in `experiments/zeus/results/D-B_KHM-603-I-musvit-*.json`.

| KHM 603 I, 347 bars | bars exact | rhythm | pitch | extra events |
|---|---|---|---|---|
| Zeus J (e8) | 225 (65%) | 257 | 256 | 36 |
| `stage2-602II` (J's staves less KHM 602 II) | 225 (65%) | 266 | 252 | 17 |
| `stage2-J` (all of J's staves, last pass) | 223 (64%) | 260 | 251 | 46 |

Both readers tie J on bars exact (one movement can't separate runs within
about 4 points). They tend to be better in rhythm and a little worse in
pitch. The viola is as weak as J's (47–52 of 88 bars exact). By the stop
rule above, the first run doesn't beat J.

Spend to here: about $7 of Modal time (estimate).

**Tuning round 1: the full encoder (2026-10-17).** MuSViT (89M), LoRA as
before, `--amp` (bfloat16), L40S, `--patience 3`. Stage 1 `stage1-full`:
60 passes (the cap), 97 s each, best 9.4% SER on the 200 Dolores staves
(pass 55). Stage 2 `stage2-full-602II`: stopped at pass 21, best 12.8% on
KHM 602 II (pass 12). Clean test with its best.pt: **233 bars exact (67%)**,
pitch 272, rhythm 259, extra 47; against J, paired resampling: bars exact
+2.3 points (−1.4 to +6.1), pitch +4.6 (+0.6 to +8.9), 167 fewer wrong
events (92 to 245). README.md has the details. About $12 spent in all.

## Order of work

1. **Feasibility, about an afternoon:**
   - get MuSViT from Hugging Face;
   - read its staff-level setup;
   - decide the head;
   - run the encoder on a few of our staves on this Mac and time it.
2. **The Modal app and data:** set up the volumes, upload the staves, and do
   a timing run of a few hundred steps. Replace the cost estimates above
   with measurements.
3. **Stage 1** on public data. Check the head learns there (its error rate
   on Dolores' test split beside Zeus's) before going on.
4. **Stage 2** on our staves, then score the clean test. Write the result up
   in the Zeus README's clean-test table, and in a model card if it wins.

## Later: the training-data mix

Only once the standard recipe has a score. Ideas from our runs:
- **More of a hand's own bars** helped every time (Op. 48 No. 3 I moved
  Vma II by 5 points); **other composers' hands didn't** (run H, Mayer A).
  Weight the Boccherini copyists.
- **Dolores added nothing** once Philhar's staves were in (runs E against F).
- **Oversample what J gets wrong:** dense 32nds, broken chords, C clefs.
- **Two-voice staves and double stops**, now left out, written as chords or
  voices.
- **Drop or down-weight printed and synthetic sets** in stage 1 if they
  don't help the handwritten test.

## Licences

MuSViT's weights and Zeus's are CC BY-NC-SA, and so is anything trained from
them: non-commercial, shared alike. Zeus's code is MIT. The datasets'
licences allow private research training.

## Where things stand (2026-10-18, before the overnight run)

**Best readers, clean test (KHM 603 I, 347 bars):** `C1-tf8-L` 265 (76%; 8-layer
decoder, original MuSViT, larger adapters, two-voice data) and `C4-bocch-tf8-L`
263 (pretrained encoder; best pitch 298, 11 missed). Zeus J 225 (65%). Both are
held-out models: KHM 602 II and Op. 48/5 I (both sources) never trained. Full
table in README.md. The clean test is now choosing between models, so the gain
needs confirming elsewhere: that is the Madrid test set below.

**Spend:** $47.62 metered this month by 2026-10-18 01:00 ($30 free credit, $17.62
billed). The user allowed about $30–40 more overnight: stop launching past $85
metered (`modal billing summary`).

**Running / queued overnight:**
1. Re-pairing the 34 autodetected sources (Philhar, plus the 3 labelled Op. 48
   ones as a check) with `C4-bocch-tf8-L`: `drivers/repair.sh` (read_auto.py,
   then autopair.py `--model /nonexistent/musvit-C4-bocch-tf8-L-best`). Results:
   `experiments/zeus/results/autopair-<src>-any-count-musvit-C4-bocch-tf8-L-best.json`;
   compare with `...-F-lr1e5-e8.json` (Zeus F's pairing). Op02-1-G159 done: 135 kept
   against F's 132.
2. Madrid test set: the five E-Mc copies of Op. 22 (boccherini-sources
   digitizations G183–G188, `e-mc_1-7040-*`), autodetected as `Op22-<n>-EMc`
   with these page maps (the ripieno bass left out): 188bis Op22-1
   2-5:vc,10-13:vn1,18-21:vn2,26-29:va; 188 Op22-2 10-13:vn1,18-21:vn2,26-29:vc,
   34-37:va; 187 Op22-3 2-7:va,10-15:vn1,18-23:vn2,26-31:vc; 185 Op22-4 10-13:vc;
   186bis Op22-6 2-5:vc,10-13:vn2,18-21:va. 631 staves detected. Paired with
   both Zeus J and C4; the staves both keep with the same bars go to
   `results/autopair-<src>-any-count-both.json` (`drivers/madrid.sh`). A hand
   no model has trained on: test only, never train on it.
3. Then (overnight chain): rebuild Philhar pairs with two voices (dataset.py
   `--pairs ... --results <new results>`), build the Madrid test staves, retrain
   the second stage of C1 and C4 on the expanded labels, score everything on the
   clean test and Madrid (SER and exact staves; Zeus J too).

**New sources checked:** Op. 8/4 (G168, BnF), Op. 2/1 (G159, BnF btv1b10863131t)
and Op. 32 (G202/204, D-LEm) are full scores: pair poorly, pretraining only. The
Stockholm Op. 2 set (S-Skma) is Hummel's print: leave out.

**Not started:** confirm on another encoded movement; replace Zeus J in the
edition (a PyTorch path in tools/zeus_score.py, Mac re-check, flag-threshold
retune, packaging, licence); extend pretraining with the shelf's manuscripts;
measure what fine-tuning gives up on public benchmarks (C1: Dolores 12.5% →
35.7% SER).

**Overnight chain launched 2026-10-18 ~02:45** (`drivers/overnight.py`,
under `caffeinate -i`): waits for repair.sh and madrid.sh, builds dataM (Philhar
pairs, two voices) and dataT (Madrid test), retrains D1-tf8-M (from E2-tf8) and
D2-bocch-tf8-M (from G1-bocch-tf8) on Op. 48 + dataM, scores C1, C4, D1, D2 and
Zeus J on Madrid and D1, D2 on the clean test. Summary:
`drivers/overnight-summary.md`. Test on Op02-1-G159: 116 plain
staves from the new pairing against 114 in dataG.

## 2026-10-18: the stage gate

- **Overnight:** re-pairing kept 3,219 staves (Zeus F 3,158), none wrong on
  Op. 48; dataM 2,444 two-voice Philhar staves; dataT (Madrid) 372. D1-tf8-M
  (C1's recipe on Op. 48 + dataM): clean test 263, Madrid 5.8%; D2 (C4's)
  257, 10.7%; C1 7.4%, C4 7.3%, Zeus J 17.3% on Madrid.
- **Madrid is flattered by the music:** H1 (D1's recipe, 1,508 staves, no
  Op. 22 or Op. 32) 24.1% on Madrid, 31.7% on Op. 32, clean test 247; R1 (a
  random 1,508, both works in) 11.6%, 9.3%, 254. Madrid can't rank readers.
  (A spend-limit stop at about $50 metered disabled the workspace mid-run;
  the user raised it and both were rerun.)
- **Crowned: D3-tf8-all**, D1's recipe and pass 24 on everything but the
  clean test (3,411 staves): clean test 270 (78%), +13.0 points on Zeus J
  (+9.2 to +17.0). Released as `musvit-D3`, with `musvit-D1` as the held-out
  reference (`release.py`; zeus-score 1.1.0 runs them through
  `tools/musvit_score.py`).
- **Mac:** cached decoding (`Reader.read_cached`) and `for_reading` (adapters
  folded, half precision on mps): 1.9 → 0.28 s a staff, same accuracy (D1
  265 on the Mac). Zeus J: 0.05 s. Scoring: 66 staves in 42 s, as Zeus J.
- **Public benchmarks:** README.md, round 4. No published number exists for
  Zeus's solo snapshot; scored here with one metric for every model.
- **Colour test (2026-10-18, user asked):** compare.page_image/staff_crop take
  colour (grey crops byte-identical), color_staves.py cut 3,542 staves again in
  colour (19 min on 8 cores), proto.py --color reads three channels, read.py
  --color. D1c-tf8-M-color (D1's recipe from grey E2-tf8): practice exam best
  0.191 at pass 12 (D1 0.189), clean test 260/347 (D1 263): −0.9 points
  (−3.7 to +1.7), differing on 23 bars. No gain; grey stays.
- **Beams in the Op. 48 labels:** the edition's events.py recorded only beams
  written [ ] (edition 518fdc0 adds LilyPond's automatic ones). Rebuilt as
  dataL2 (same staves, same images; only beam tokens changed): KHM 602's
  unbeamed short notes 728 -> 384 of 2,983 (the rest are flagged notes the
  copyist didn't beam); other sources unchanged within 2. Uploaded to
  musvit-staves /dataL2. Train on dataL2 from now on (dataL kept for the D runs).

## 2026-10-18: the cheap runs (replay, strip height)

proto.py gains `--replay F --replay-from <samples>` (a fresh draw of
F/(1−F) × the training staves from stage 1's staves each pass, mixed in by
width; passes get longer, Boccherini exposure per pass unchanged) and
`--height` (the strip's height; config.json records it when not 128, and
load()/load_release and stage 2 from such a run follow it). Default runs are
unchanged. Drivers and summaries: `drivers/cheap/` (cheap.py,
analyze.py; paired bootstrap, 95%).

- **Replay (E1), on the unseen-music setup:** H1's recipe (no Op. 22 or 32) on
  dataL2, 0/10/30% Dolores+OmniOMR train staves.

  | | H1-L2 (none) | r10 | r30 |
  |---|---:|---:|---:|
  | Madrid SER | 21.2% | 24.6% (+2.3 to +4.5) | 25.2% (+2.7 to +5.2) |
  | Op. 32 SER | 31.9% | 33.4% (+0.6 to +2.5) | 34.3% (+1.4 to +3.6) |
  | Dolores SER | 36.4% | 16.5% | 13.7% |
  | OmniOMR SER | 42.1% | 22.6% | 20.9% |
  | clean test | 253 | 244 (−5.2 to 0.0 pts) | 253 (±2.6) |

  SER as written, readings cut at 2× the reference. Replay keeps the general
  skill (Dolores back near stage 1's 16.7%) but reads the unseen hands
  *worse*. Not kept: general reading is not what fails on a new copyist.
- **Beams fix (dataL2 against dataL, same recipe):** Madrid 24.1% → 21.2%
  (−4.0 to −1.8), Op. 32 31.6% → 31.9% (−0.7 to +1.2), clean test 247 → 253
  (−0.9 to +4.3 pts). One seed each; the bootstrap doesn't cover run-to-run
  noise.
- **Strip height 96 px (both stages retrained):** E2-h96 (E2-tf8's recipe):
  practice exam best 0.100 at pass 55 (E2-tf8 0.124, but E2-tf8 stopped early
  at pass 40 by patience; E2-h96 ran all 60), Dolores 11.5% against 16.7%.
  D1-h96 (D1's recipe on dataL): practice exam 0.190 (D1 0.189), clean test
  259 against 263 (−4.6 to +2.0 pts), Dolores 38.9% against 40.0%. On the Mac
  (mps, half precision, 64 staves, warm): 0.215 s a staff against 0.307 for
  D1, 30% faster. As good within the noise, and faster: a candidate height
  for the next crowned run, not a reason to retrain D3 alone.
- **Cost:** about $7 on Modal (stage 1 at 96 px about $3).
