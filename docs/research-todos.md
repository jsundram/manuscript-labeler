# Zeus / Boccherini OMR — Research TODOs

## 1. Fine-tune Zeus on Boccherini ground truth

> **Status, 16 Oct: done, and the default model is now run J.**
> - Every run started from the solo-staff checkpoint `ayce-2026-08-03`. The first fine-tune (9 Oct) used 126 corrected staves.
> - Eight runs since then, C to J, with a learning-rate sweep along the way. The recipe settled on learning rate 1e-5, cosine decay, 8 epochs.
> - Held out by whole movements, never neighbouring strips. The clean test is KHM 603 movement I, 347 bars.
> - Bars exact on the clean test: stock 42%, J 65%.
> - Errors are measured by category in `experiments/zeus/compare.py`: duration, pitch, octave, chord size, extra and missed, grace, rest for note, and accidentals as printed. Clefs are compared with the labels.
> - Not yet broken out on their own: tuplets, beaming, ledger lines.
> - What moved it: a hand's own bars, and Philhar's other copyists (+13 points). Other composers' hands didn't help, and neither did more epochs.
> - Details: `zeus-score/MODEL_CARD.md`.

- Start from the current solo-staff, manuscript-aware Zeus checkpoint.
- Use roughly 100–150 corrected Boccherini staff strips for an initial experiment.
- Hold out complete pages or sections for validation and test rather than randomly splitting neighboring strips.
- Measure error by category, especially:
  - alto/tenor/ambiguous clefs
  - octave errors
  - pitch errors
  - tuplets
  - beaming
  - accidentals
  - ledger lines

## 2. Build the ground-truth conversion pipeline

> **Status, 16 Oct: done.**
> - `experiments/zeus/dataset.py` goes from the edition's LilyPond, via `events.py`, to MusicXML in the labels' clefs. Zeus's own `lmx` encoder then turns that into LMX.
> - Every staff is read back through the scoring code and must match its encoding exactly.
> - Every encoded movement becomes training data with no extra work; run J used them all except the clean test.
> - Philhar's encodings are paired with their manuscripts automatically (`autodetect.py`, `autopair.py`): 2,246 staves from Op. 2, 22, 32 and 33.
> - The same conversion scores a reading token by token (`tools/zeus_score.py`, now the `zeus-score` package).

- Determine the cleanest route from corrected **LilyPond** source to the **MusicXML / LMX** representation Zeus expects.
- Automate this so that every newly corrected manuscript strip can become training data with minimal additional work.

## 3. Rebuild Zeus on the MuSViT vision encoder

*Added 16 Oct, ranked above the Smashcima work (item 4).*

MuSViT (https://grfia.dlsi.ua.es/musvit/) is an image encoder pretrained on
9.7 million IMSLP pages. Only the encoder is released (CC BY-NC-SA, like
Zeus; the Hugging Face download asks for contact details). It can't read
music by itself: it needs a reading head trained on labelled staves.

- **Why:** Zeus's own image reader is small, and our weak spots are hands it
  hasn't trained on and dense 32nd-note passagework. An encoder that has seen
  far more hands may cope better with both.
- **How it fits:**
  - MuSViT's light encoder (25M parameters, staff images 128 px tall, near
    Zeus's height) replaces Zeus's image reader.
  - Their released code's staff reader (a sequence head with a CTC output,
    trained with LoRA adapters) learns to write Zeus's output format, LMX,
    so `experiments/zeus/compare.py` scores it like any Zeus run.
- **The catch:** Zeus's output stage only works with its own encoder, so the
  new head starts from nothing. It trains first on the public sets Zeus used
  (OLiMPiC and Dolores, which we have, plus OmniOMR), then on our ~2,500
  staves.
- **Compute:** the light encoder runs at roughly Zeus's speed on this Mac
  (the full 85M one several times slower). The public-data stage could take
  a day or more.
- **First test, about 2–3 days:** the light encoder, with run J's recipe
  and data plus the public pretraining. Score it on the clean test (KHM 603
  movement I). **Stop if it doesn't beat J's 65% of bars exact.** Also look
  at the viola's broken-chord bars (26–31, 61–67), where J fails.
- **Afterwards, if it holds:** test it on a hand neither model has trained
  on: the first encoded movement of Op. 48 No. 4, 5 or 6.
- **No-training side use:** rank staves, or IMSLP manuscripts, by how close
  their handwriting is to a given copyist's, to choose training data
  (about an afternoon; untested).
- **Discussed 14 Oct** (lab report, "Next directions" item 6) and parked
  until the Vma I encoding, which is now done.

## 4. Investigate Boccherini-specific synthetic handwriting with Smashcima

> **Status, 16 Oct: not started.**

- Determine exactly what is required to add a new writer/style to Smashcima.
- Find out whether a useful Boccherini style could be built from tens or hundreds of isolated glyph examples rather than fully annotating pages.
- Prioritize distinctive examples of:
  - G clefs
  - F clefs
  - C/alto and tenor clefs
  - noteheads
  - rests
  - accidentals
  - stems and beams
  - flags
  - other recurring symbols
- Test whether symbolic Classical-period music can then be rendered into large quantities of plausibly Boccherini-like synthetic training data.

## 5. Test a two-stage adaptation strategy

> **Status, 16 Oct: not started; it needs item 4 (Smashcima) first.**
> - Related: run H added real handwriting from another composer (145 staves of OSSQ's Mayer A). It didn't help: 59% against G's 62% on the clean test.
> - So far, a scribe's own genuine bars have been the reliable lever.

Compare:

1. Generic manuscript-aware Zeus
2. → adaptation using a large synthetic Boccherini-like Smashcima corpus
3. → final fine-tuning on a relatively small set of genuine Boccherini image/transcription pairs

Against:

- direct fine-tuning of Zeus using only real Boccherini examples.

The key question is whether synthetic scribe-specific adaptation substantially reduces the quantity of genuine ground truth required.

## 6. Reproduce a published Zeus training result

> **Status, 16 Oct: not done.**
> - No GPU has been rented. Every fine-tune ran on this Mac: about 10 to 15 minutes an epoch at full speed, roughly 2.5 hours a run.

- Rent a single 24–48 GB NVIDIA GPU rather than buying hardware.
- Budget roughly **$150–$200 for one 3–4 day baseline reproduction**.
- First establish an end-to-end reproducible training pipeline without changing the authors' setup.
- Then experiment with:
  - manuscript-heavy sampling
  - removing less representative printed/synthetic sources
  - oversampling C-clef material
  - different mixtures of Dolores / OmniOMR / OLiMPiC
  - varying amounts of synthetic handwriting

## 7. Understand the current Zeus training corpus better

> **Status, 16 Oct: partly done.**
> - Found: the stock checkpoint was already trained on most of MusiCorpus (Dolores train and validation, OmniOMR train). Only the test splits are unseen.
> - Found: Zeus's clef *tokens* are often wrong on these hands, but its note *placement* is right. Scoring therefore names pitches in the labelled clef.
> - Forcing the labelled clef made no difference overall (`clefread.py`). It helped violin 2 and hurt the viola.
> - The current weak spot is dense 32nd-note passagework, such as broken chords across strings, rather than clefs.
> - Not yet done: counting the alto- and tenor-clef material in the training corpora.

- Quantify how much alto- and tenor-clef material occurs in:
  - Dolores
  - OmniOMR
  - the current solo-staff Zeus training mixture
- Look for systematic mismatches between the training corpus and eighteenth-century handwritten string parts.
- Investigate whether observed clef failures correlate with underrepresented symbol classes.
- Identify other potentially underrepresented Boccherini-specific notation patterns.

## 8. Create a fixed benchmark now

> **Status, 16 Oct: partly done.**
> - The clean test is fixed: KHM 603 movement I (Op. 48 No. 2 I), 347 bars, held out since 15 Oct. Every model so far has been scored on it (`experiments/zeus/README.md`).
> - It's too small: one movement by one copyist can't separate models within about 4 points. One held-out movement per hand is the next step.
> - Recognition metrics are tracked as listed in item 1.
> - Workflow metrics:
>   - The edition's `/encode` evidence records the person's active minutes and corrections per 100 bar-parts.
>   - Zeus is now the edition's second reader. On Op. 48 No. 2 I, 76% of its flags were real errors, and it caught 90% of the errors in the kinds it checks.
>   - Since 16 Oct the labeler logs every interaction and its time, shown in its Time panel.

- Preserve a set of manuscript strips that are **never used for training**.
- Include:
  - easy examples
  - dense passagework
  - C clefs
  - ambiguous clefs
  - tuplets
  - unusual beaming
  - accidentals
  - ledger-line passages
  - repeated/parallel material
- Keep this benchmark fixed so that later model experiments remain directly comparable.

Track both:

### Recognition metrics

- pitch errors
- octave errors
- duration errors
- clef errors
- accidental errors
- tuplet errors
- beaming errors
- other symbol/structure errors

### Workflow metrics

- number of human interventions
- number of LilyPond edits
- human correction time per strip
- human correction time per page/movement

**Human correction time is probably the most important ultimate metric.**

## 9. Explore data selection and active learning

> **Status, 16 Oct: not started as such.**
> - Related: Zeus's objections already pick which encoded bars a person checks.
> - The edition's `encode.py signals` writes per-bar records as the seed for calibrated confidence.

Investigate whether the system can choose which manuscript passages are most valuable to correct next.

Prefer examples that:

- represent currently weak symbol classes
- expose new handwriting variants
- have high model uncertainty
- produce disagreement among recognition passes
- are unlike material already in the training set

Avoid spending annotation effort on large numbers of nearly identical easy examples.

Eventually connect this to the larger **calibrated confidence / value-of-information** framework:

> Which next human annotation or model action is expected to reduce future transcription error the most?

## 10. Mine the Prague group's talks and papers

> **Status, 16 Oct: not done.**
> - Jiří Mayer's 12 Oct talk hasn't been reviewed here.
> - OSSQ's manuscripts (Mayer A, Andrée, Maier) were tried as test and training data on 13 Oct.

In particular, follow:

**Jiří Mayer — “Why computers still can’t read music reliably?”**  
October 12, 2026

Listen specifically for discussion of:

- manuscript adaptation
- synthetic training data
- domain shift
- underrepresented notation
- clefs
- fine-tuning
- data requirements
- error analysis
- active learning
- future Zeus / OmniOMR research directions

Also review the earlier Prague / OmniOMR / WoRMS presentations for details that may not appear in the papers.

## 11. Keep the central research hypothesis explicit

> **Status, 16 Oct: the evidence so far supports it, partly.**
> - With 322 genuine Op. 48 staves, plus 2,246 staves paired automatically from Boccherini's other copyists, the clean test went from 42% to 65% of bars exact.
> - As a checker of encoded notes, Zeus is already useful.
> - Correction time, the target here, is now being logged in both the labeler and the edition, so it can be measured.

Test the hypothesis:

> **Can scribe-specific adaptation turn a general handwritten OMR model into a useful Boccherini transcription system using only a modest amount of genuine annotated manuscript material?**

The success criterion is **not necessarily perfect OMR**.

The practical target is:

> **Substantially reduce the human correction effort required to produce a reliable LilyPond transcription of each movement.**
## 12. Close the loop: D3 checks each finished manuscript, then a quick retrain

*Added 19 Oct, from ISMIR 2026 P7-4 ("When AI Annotates First"; notes in `docs/ismir2026-papers.md`).*

The flow:

1. Label the manuscript in the labeler and mark it final.
2. Encode it in LilyPond.
3. Run musvit-D3 over its staves. It flags the bars where it is doubtful, or where it disagrees with the encoding.
4. The editor checks each flag:
   - an encoding error is fixed in the LilyPond;
   - a D3 error is left alone, and becomes training signal.
5. Run a quick retrain with the movement's bars. The conversion pipeline already turns every encoded movement into training staves.

- **Keep the order: a person encodes, then D3 checks.**
  - P7-4 scored every annotator's final labels against independent ground truth. Starting from a strong model's proposals, annotators fixed only about 21% of its remaining errors (81% from a weak one).
  - A D3-first draft would invite the same misses.
- **For a new copyist, retrain early, not at the end.**
  - P7-4's largest gains came from the first one to five corrected samples. Time per patch went from 7:09 to 3:41.
  - A hand's own bars are already our strongest lever (item 1).
  - So: encode and check the first page or so, fine-tune, then let the improved D3 check the rest.
- **Where it runs:**
  - The labeler shows D3's flags as boxes on the page, to confirm or fix. Each decision is logged like every other correction.
  - "Retrain" starts a Modal job; training doesn't run in the labeler.
  - The fixes land in the edition's LilyPond, beside Zeus's flags.
- **Guard against forgetting:**
  - Re-score KHM 603 movement I after every retrain. Replay hurt unseen hands (BRIEF), so the mix needs care.
  - Keep the previous model as the default unless the new one holds.
- **Open:**
  - How quick is "quick"? A short continued fine-tune on one movement hasn't been timed.
  - Whether the bars D3 got wrong should be weighted up in the retrain.

## 13. Calibrate D3's confidence

*Added 19 Oct.* Item 12 is only as good as D3's flags. Zeus's flags are 76% real errors and catch 90% of the errors in the kinds it checks (item 8). D3's have never been measured.

- **Signals to combine into one score per bar:**
  - **The reader's own token probabilities:** the lowest one, the mean log-probability, and the margin between the top two choices.
  - **Whether the bar adds up:** durations against the time signature. A cheap rule, and often decisive.
  - **Two readers disagreeing:** D3 against Zeus J.
  - **Readings that change under small perturbations:** re-read the staff with a slightly different crop, height or contrast, and see whether the bar changes.
    - This is the Monte Carlo idea from the IJDAR 2025 staff-region paper (`docs/ismir2026-papers.md`).
  - **Copies that disagree:** the same bar in another manuscript of the movement, where one exists.
- **Calibrate:**
  - Apply temperature scaling to the token probabilities.
  - Then fit a small logistic (or isotonic) model from the signals to the chance the bar is wrong.
  - Fit on bars D3 didn't train on: the clean test, and the movements held out from each run.
  - The seed data exists: the edition's `encode.py signals` writes per-bar records for exactly this (item 9).
- **Measure it the way the editor will use it:**
  - At a fixed budget (say, the 10% of bars most in doubt), what share of the flags are real errors, and what share of all errors do they catch?
  - Also a reliability diagram: does a bar scored 30% wrong turn out wrong about 30% of the time?
- **Check before trusting it on a new hand:**
  - P7-4's prediction-confidence ratio predicted how badly a model would transfer, before any labelling.
  - The same check on D3's per-bar scores over a new manuscript would say whether to fine-tune first (item 12).

## 14. Retrain the labeler's YOLO detectors online

*Added 19 Oct, from P7-4 and PixelSmart.*

- **Already online:** the learned bar-line filter (`learn.py`) and the crop edges (`crops.py`). Each retrains in the background whenever a reviewed page changes.
- **Not online:** the YOLO detectors.
  - Their predictions are made ahead of time (`tools/predict_barlines.py`), from weights trained offline (`experiments/barlines`).
  - These are the detectors that carry to new hands: 35 errors in 376 bar lines on Vma ms 1067 (1), where the learned filter made 150.
- **The change:** when a new manuscript's first pages are reviewed, start a short background fine-tune of YOLO26n from the existing weights. Then re-predict that manuscript's remaining pages and refresh the vote.
  - P7-4 suggests a handful of corrected pages gets most of the gain.
- **To measure:** bar-line errors on the rest of the manuscript after one, two and five reviewed pages, against the stock weights. Also how long the fine-tune and re-prediction take on this Mac.

## 15. Ideas from Legato 2

*Added 22 Oct, from Yang, Zheng, Ebert and Smith, "LEGATO 2: Toward Multimodal Sheet Music Recognition and Understanding" ([arXiv 2607.05769](https://arxiv.org/abs/2607.05769), 7 Jul 2026).*

> **Status, 22 Oct: not started.** The weights were requested on Hugging Face on 22 Oct and are waiting for approval.

**What it is.**
- A YOLOv8 finds each system on the page.
- A vision-language model then reads the systems one at a time, in ABC:
  - the image encoder is Llama-3.2-11B-Vision's, kept frozen;
  - the decoder is smaller, trained from scratch (114M trainable parameters with the projection).
- Each system's reading is conditioned on the ABC already written for the systems above it, cut to the last 1,024 tokens. Earlier images aren't used.
- It was trained on synthetic printed pages only (PDMX-Synth). It has no handwriting in training or testing.
- Results are page-level OMR-NED, against Audiveris:
  - camera photos of OpenScore string quartets: 31.6 against 75.4;
  - IMSLP piano scans: 34.2 against 71.5.
- Reading system by system made its largest gain: on the camera quartets, Legato 1's 58.2 fell to 35.2.

**Cautions from papers we've already read** (`docs/ismir2026-papers.md`):
- **P12-5 ("Measure for Measure"):**
  - A frozen Llama-Vision encoder did far worse than DINOv2 (38% MCR against about 6%).
  - Their page-omr scored 6.38% MCR on the Sheet Music Benchmark, against LEGATO's 35.92%.
  - Legato 2 doesn't compare itself with page-omr.
- **P13-3 (OSSQ-OMR):** part-level input beat system-level, with no sign that the models used the other parts. That concerns parts read side by side, not the line before, so it doesn't rule out (a). It's still a reason to keep the hint small.

### (a) The previous staff as a hint

- **The idea:** put the previous staff's reading in front of the decoder, so it can carry the clef, key and time signature.
- **Not the clef test again:** `experiments/zeus/clefread.py` forced Zeus to write only the labelled clef, and a wrong forced clef derailed the reading (item 7). Here the reader still reads the current clef freely. The hint is something it can learn to trust or ignore.
- **What it can carry:** copyists rewrite the clef and key at every line, but not the time signature. So expect the gain mostly in time signatures and unclear clef shapes.
- **Two variants:**
  - the previous staff's whole reading, cut short as Legato 2 does;
  - only the clef, key and time in force at its end.
- **Training data:** staves are named by page and staff (`p3s4`), so the one before is easy to find. Some aren't kept, so there are gaps.
- **Train on the reader's own readings of the previous staff**, not the encoding's, so training sees what reading will see.
- **Test:** D1's recipe with and without the hint, scored on the clean test. It can't separate runs within about 4 points.

### (b) Legato 2 on the printed test bed

- **Where:** `experiments/print-omr`, Bärenreiter BA 2676 (4,140 encoded part-bars).
- **How:** read its pages on Modal. Convert the ABC to MusicXML per page, which `readings.py` already reads for Audiveris.
- **Measure:**
  - bars exact alone (OSSQ reader 82.5%, Audiveris 61.0%);
  - with the OSSQ reader: bars agreed, and the share right. Audiveris gives 60% of bars at 99.2%.
  - whether it reads the cello's tenor clef, which the MuSViT readers miss and Audiveris gets.
- **The open question:** Audiveris earns its place because its mistakes differ from MuSViT's. Legato 2 is also a neural reader trained on synthetic data, so its mistakes may not be independent.
- **Run page-omr (P12-5) beside it.** It's the stronger printed-page reader on paper.

### (c) Legato 2 as a manuscript reader

- **First:** read the clean test as it is, after converting its ABC to compare.py's events.
- **Then:** fine-tune it on our staves, with ABC targets converted from our encodings.
- **The bar:** musvit-D3's 270 of 347.
- **Check first:** its image tiling was built for whole systems. A staff is about 13 times wider than it is tall.

### (d) A repetition penalty when reading

- Legato 2 picks a repetition penalty (1.0, 1.1 or 1.2) and a beam size on its validation set.
- Beam search didn't help us (`experiments/musvit/README.md`). A penalty might cut runaways.
- It's a reading-time setting, so it can be tried on any saved model with no retraining. Score it on the practice exam.

### (e) Train on jittered staff boxes

- Legato 2 tested itself on deliberately damaged system boxes and stayed ahead of Audiveris (47.4).
- **For us:** on new hands, detection is the limit (on Op. 32, staves landed wrong and thin bar lines were missed). Jittering each staff's crop edges in training may make the reader more forgiving.
- It changes training, so run it alone against a run without it.

### (f) Standard metrics for public tests

- **OMR-NED** comes from the Sheet Music Benchmark paper (Martinez-Sevilla et al., ISMIR 2025, [arXiv 2506.10488](https://arxiv.org/abs/2506.10488)). Legato 2 and OSSQ-OMR report it.
  - Report it on public tests (MusiCorpus test, OSSQ-OMR), so our numbers line up with the papers'.
  - Use the paper's reworked musicdiff, not the stock one.
- **MCR is the better second number** (P12-5, `mcr-metric`):
  - It matched musicians' correction effort at ρ 0.64, against OMR-NED's 0.36.
  - In OMR-NED, one wrong duration in mid-bar cost 15 operations.
- **Keep bars exact for our decisions:**
  - Pairing and the edition's flags work by the bar.
  - Both metrics would count our encodings' conventions as errors: no stems, and tremolos written either way.

## 16. Notation the training data leaves out, and drawn staves for what no set has

Found on 2026-10-23 looking for a bias in the staves that didn't pair
(reports/2026-10-23-abbreviations, reports/2026-10-23-musvit-d5). Each is a
kind of notation the reader has never been taught, so it can't learn it from
more of the same data. Bundle them, with the Op. 48 manuscripts below, into
the next training run, two seeds (about $2).

- **Multi-bar rests** (251 paired staves left out of the sets; dataset.py's
  staff_boxes can't label one). The LMX vocabulary has a bar rest
  (`rest:measure`) but no multi-bar rest with its number: decide how a label
  writes one (N bar rests, or a new token with the reader's vocabulary
  widened) before building.
- **Clef changes within a staff** (182 left out: "Philhar's clef changes on
  the staff"). LMX writes mid-staff clefs (the drawn clef-change staves,
  dataS4, do); dataset.py would write the encoding's clef where it changes,
  checked against the reading's clefs.
- **A bar a repeat splits, read as one measure** (166 left out). The label
  could be the whole bar with the repeat sign inside it, if LMX can write a
  repeat bar line mid-measure; else leave out.
- **Two-note tremolos** (`\repeat tremolo`, 15 passages in Philhar's files):
  not recorded by philhar.py yet, unlike stem-stroke abbreviations.
- **Drawn staves of figures no set has**, with experiments/synth's
  copyist.py: first triplet 32nds after a 16th rest (no set's labels have a
  triplet 32nd; musvit-D5 lost six clean-test bars on it, violin II
  26–67). Find the others by comparing the clean test's and Dresden's
  errors with the figures the training labels contain.
- **Op. 48 No. 4 and No. 6 as training staves**: RES-507-16, Vma-1067-2 and
  RES-507-18 are labelled, but their movements aren't encoded yet
  (Op48-4/, Op48-6/ are the template). Once they are, build dataL3: the
  edition's own hands, the most valuable staves.
- **Bar-line detection on new hands** (reports/2026-10-23-bar-line-counts):
  not more reviewed pages (flat from 27 to 111), but rules for stems that
  cross the staff, and for the box count's open last box (a key change or
  custos after the line's last bar line counted as a bar).
