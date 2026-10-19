# ISMIR 2026: papers that bear on this project

Read 2026-10-19 from the [detailed schedule](https://confcats-siteplex.s3.us-east-1.amazonaws.com/ismir26/ISMIR_2026_Detailed_Schedule_10_14_12209fec64.pdf)
(150 papers, 14 sessions, Abu Dhabi, 9–12 November 2026). The goal it's read
against: handwritten single-part manuscripts in, engraved scores out, by way of
the labeler (staves, bar lines), staff readers (Zeus J, musvit-D3, LMX) and the
plan in `experiments/musvit/NEXT.md` (replay, synthetic quartet staves,
Smashcima, new hands).

**About the links.** The session's network blocks arxiv.org, openreview.net,
huggingface.co, zenodo.org and the ISMIR program site, so **no PDF could be
downloaded**. For the same reason, arXiv IDs come from search results, not
from opening the pages. Every GitHub README cited was read directly. The
proceedings aren't out yet, and four papers have no abstract anywhere public;
their sections say so, and are judged from title, authors and context.

## Summary

Verdict: how likely it is to help in the next few weeks.

| ID | Paper | When | Paper link | Code / data | Verdict |
|---|---|---|---|---|---|
| P13-3 | [A Dataset and Benchmark for OMR of String Quartet Scores](#p13-3) (Kim, Liu, Valero-Mas, Jeong) | Thu 12, 10:00 | [arXiv 2608.10978](https://arxiv.org/abs/2608.10978) · [pdf](https://arxiv.org/pdf/2608.10978) | [umbrella](https://github.com/MALerLab/string-quartet-omr-benchmark) · [sqomr](https://github.com/MALerLab/sqomr) · [lmxe](https://github.com/MALerLab/lmxe) · [ossq-omr](https://github.com/MALerLab/ossq-omr) | **High** |
| P12-5 | [Measure for Measure: Reliable Evaluation and a New SOTA for Full-Page OMR](#p12-5) (Hornbogen, Valentin) | Wed 11, 15:30 | not found | [page-omr](https://github.com/tobiashornbogen/page-omr) · [mcr-metric](https://github.com/tobiashornbogen/mcr-metric) | **High** (the metric) |
| P3-7 | [The Debussy Dataset: OMR on Modern Staff Notation Manuscripts](#p3-7) (Scheithauer, Clérice, Romero-García) | Mon 9, 14:00 | not found | [code](https://github.com/HugoSchtr/debussy-omr-ismir2026) · [data](https://github.com/HugoSchtr/debussy-omr-dataset) | **Medium** |
| P7-4 | [When AI Annotates First: Its Impact on Music Score Labeling](#p7-4) (Galan-Cuenca et al., Alicante) | Tue 10, 14:00 | not found | not found | **Medium** |
| P1-3 | [TUTTI: Audio-to-Score Transcription via Fully Synthesized Data](#p1-3) (Hu et al.) | Mon 9, 10:00 | [arXiv 2609.00640](https://arxiv.org/abs/2609.00640) · [pdf](https://arxiv.org/pdf/2609.00640) | [code](https://github.com/a-musiclover/TUTTI) · [TuttiCorpus](https://huggingface.co/datasets/pzzzzz/TuttiCorpus) | Low–medium |
| P14-1 | [Estimating the Reliability of DTW Alignments Using Circumstantial Evidence](#p14-1) (Pratapneni, Yuan, Tsai) | Thu 12, 11:30 | [arXiv 2607.15443](https://arxiv.org/abs/2607.15443) · [pdf](https://arxiv.org/pdf/2607.15443) | not found | Low now, medium later |
| P6-1 | [Pre-trained Audio Encoders for Audio-to-Score Transcription](#p6-1) (Hidalgo-Centeno, Penarrubia, Valero-Mas) | Tue 10, 11:30 | [ISMIR poster 164](https://ismir2026program.ismir.net/poster_164.html#paper) | [a2s-pretrained](https://github.com/ahidalgocenteno/a2s-pretrained) | Low |
| P6-9 | [Full-page Recognition of Handwritten Jeongganbo Scores](#p6-9) (Penarrubia, Han, Jeong, Valero-Mas) | Tue 10, 11:30 | not found | [repo](https://github.com/carlospm12/handwritten-jeongganbo) (empty) | Low |
| P5-1 | [Does Notation Matter? MusicXML Tokenisation](#p5-1) (Poltronieri et al., MTG) | Tue 10, 10:00 | not found | not found | Low |
| P4-3 | [CODA: Discontinuity-Aware Image-Based Score Following](#p4-3) (Yang, Chen, Han) | Mon 9, 16:30 | [arXiv 2607.21899](https://arxiv.org/abs/2607.21899) · [pdf](https://arxiv.org/pdf/2607.21899) | [code](https://github.com/ValleyC/CODA) · [JumpBench](https://huggingface.co/datasets/ValleyC/CODA-JumpBench) | Low |
| P8-7 | [From Prediction to Collaboration: Interactive Symbolic Music Analysis](#p8-7) (Karystinaios, Hentschel, Neuwirth, Widmer) | Tue 10, 15:30 | [arXiv 2607.13587](https://arxiv.org/abs/2607.13587) · [pdf](https://arxiv.org/pdf/2607.13587) | not found | Low |
| P12-4 | [Inferring Implied Harmonies through Voice Leading in Monophonic Instrumental Music](#p12-4) (Borsodi-Benson, Rohrmeier) | Wed 11, 15:30 | not found | not found | Low |
| P4-10 | [Local Multimodal Music Alignment from Global Supervision](#p4-10) (Bukey, Novack, Jung, Jeong, Donahue) | Mon 9, 16:30 | [arXiv 2607.10023](https://arxiv.org/abs/2607.10023) · [pdf](https://arxiv.org/pdf/2607.10023) | not found | Low |
| P10-3 | [STRAdi: Real-Time Violin Transcription for Score Following](#p10-3) (Lee, Park, Nam) | Wed 11, 11:30 | not found | [code](https://github.com/seingreen/STRAdi) | Very low |
| P7-7 | [Robust Instrument-Agnostic Transcription for Western Classical Music](#p7-7) (Venohr, Weiß) | Tue 10, 14:00 | not found | not found | Very low |
| P8-8 | [A Benchmark and Metric for Polyphony via Voice Independence](#p8-8) (Row, Fazekas) | Tue 10, 15:30 | not found | not found | Very low |
| P12-7 | [A Cross-Cultural Dataset of Instrumental Difficulty for Woodwinds and Strings](#p12-7) (Yang, Giraud, Levé) | Wed 11, 15:30 | not found | not found | Very low |

Not on the program, but turned up while searching and worth reading:
[Full-Page OMR of Handwritten Monophonic Scores](https://arxiv.org/abs/2609.05662)
(arXiv 2609.05662, Sept 2026). It is end-to-end full-page OMR on handwritten
single-line scores and cites Smashcima. Its authors and venue weren't
retrievable.

---

## The three to act on

<a id="p13-3"></a>
### P13-3 · A Dataset and Benchmark for Optical Music Recognition of String Quartet Scores

DongMin Kim, Brian Liu (Sogang); Jose J. Valero-Mas (Alicante); Dasaem Jeong
(Sogang). Session 13, Thu 12 Nov 10:00.
[arXiv 2608.10978](https://arxiv.org/abs/2608.10978) ·
[PDF](https://arxiv.org/pdf/2608.10978) (not downloaded: arXiv blocked).

**What it is.**
- **The dataset.** OSSQ-OMR pairs the OpenScore String Quartet encodings with
  IMSLP scans and with synthetic renders: 116 works by 47 composers
  (1773–1994).
  - 24,544 system images: 13,240 synthetic, 11,304 scanned.
  - 98,172 staff/part images: 52,960 synthetic, 45,212 scanned.
  - The scans come from 93 full scores, 17 part-books and 6 manuscripts.
- **The targets** are LMXE, \*\*kern and ABC.
  [LMXE](https://github.com/MALerLab/lmxe) is Mayer's LMX extended to
  several parts and staves, with a YAML header. It ships OMR-NED, TEDn and
  SER.
- **The models:** SMT, Zeus, the hybrids smt-zeus and zeus-smt, and LEGATO.
  - From the abstract: OMR-NED goes as low as 3.6% on synthetic images and
    5.9% on scans.
  - The LSTM decoder (Zeus-style) loses about 2.6× less than the
    Transformer when moving from synthetic to scanned images.
- **Licences:** data CC0, code MIT.
- **Not yet released:** the bulk Zenodo and Hugging Face images. The README's
  badges are still TODO, so for now there are only the MuseScore sources and
  the pipeline that rebuilds everything from them.

**Relevance.** We already use this corpus: `experiments/zeus/ossq/` scores
Zeus on the Maier, Andrée and Mayer manuscripts from its `omr-dev` branch.
What the paper adds:

1. **[sqomr](https://github.com/MALerLab/sqomr): Zeus ported to PyTorch, plus
   Mayer et al.'s augmentations in PyTorch, managed with uv.** Zeus J is the
   one model in zeus-score that still needs a TensorFlow 2.12
   (`tensorflow-macos`) environment of its own, about 1.4 GB. If our Zeus J
   weights load into the port, that environment can go. Whether the weights
   convert cleanly is the first thing to check.
2. **Scanned quartet staves at the staff level, about 45k of them.** NEXT.md's
   hypothesis is that our errors sit in the quartet idiom, which the public
   pretraining staves don't contain. Printed quartet *parts* from real scans
   are a cheaper test of that hypothesis than E3's Verovio renders. They could
   go into stage 1 or into E1 replay. Printed, not handwritten, so the test is
   of the music, not the hand.
3. **LMXE for the multi-staff open question.** The labeler's scores and cue
   staves (SPEC open question 2) need a multi-part target. LMXE is that
   target, and it is derived from the same LMX our readers emit.
4. **The paper's finding about LSTMs:** they lose less than Transformers on
   real scans. Our own result went the other way (the LSTM decoder on MuSViT
   was our weakest, 221). The difference is probably that our training data
   is real scans throughout. It's worth reading their ablation before
   assuming the result transfers.
5. **Boccherini is in OSSQ:** G.213 (Op. 39), score
   [8454356](https://musescore.com/openscore-string-quartets/scores/8454356).
   That makes a Boccherini encoding unrelated to Op. 48 available for a test
   or for E2. Check that it isn't from a source we train on.

**Verdict: high.** Zeus J going PyTorch is a few hours to try. The printed
quartet staves fit E1 and E2 directly, once the bulk images are released or
rebuilt with `omr-data-preprocessor`.

<a id="p12-5"></a>
### P12-5 · Measure for Measure: Reliable Evaluation and a New State of the Art for Full-Page OMR

Tobias Hornbogen, Josef Valentin (Hasso-Plattner-Institut). Session 12,
Wed 11 Nov 15:30. No arXiv or PDF found; the authors' CITATION.cff confirms
the paper.

**What it is.** Two contributions:

- **MCR (Musical Correction Rate),** a metric in its own package,
  [`mcr-metric`](https://github.com/tobiashornbogen/mcr-metric). MIT, no
  dependencies, `pip install mcr-metric`.
  - It parses \*\*kern, ABC and MusicXML natively into note events and
    merges tied notes.
  - It aligns measures by dynamic programming, so one extra bar line costs
    at most one unmatched bar instead of cascading through the rest.
  - Inside each pair of measures it aligns notes with Needleman–Wunsch.
    Costs are calibrated to an editor's effort: removing a wrong note costs
    1, entering a missing one costs 2.
  - It reports the result as the fraction of the work of retyping the page,
    with per-measure diagnostics.
- **[page-omr](https://github.com/tobiashornbogen/page-omr),** a full-page
  model.
  - 184M parameters: a DINOv2-base encoder and a 12-layer decoder, outputting
    \*\*kern or ABC.
  - Trained on PDMX scores rendered with Verovio and Augraphy and heavily
    randomised.
  - 6.38% MCR zero-shot on the Sheet Music Benchmark, against LEGATO's
    35.92%.
  - The paper also corrects errors in that benchmark's references (44 Haydn
    quartet pages, 54 spine errors).

**Relevance.**

- **The metric is the piece for us.** Our numbers today are "bars exact"
  plus symbol errors. `experiments/zeus/compare.py` pairs Zeus's measures
  with the bar boxes in order, and when the counts differ it drops the
  staff: 116 of 800 bars were not compared, 88 of them cello. MCR's measure
  alignment is what would recover those bars.
- **It measures what the edition pays for:** how much the editor has to fix,
  not edit distance.
- **It fits our toolchain.** It reads MusicXML, and our LMX goes back to
  MusicXML with the `lmx` package. A no-dependency package is a one-line
  PEP 723 import. It could be scored next to "bars exact" in
  `tools/musvit_score.py` and the OSSQ `score.py`.
- **The page-omr model** reads printed full pages of piano or quartet score.
  Zero-shot on 18th-century handwriting it will do poorly, and it emits kern,
  not LMX.
- **What's reusable is its data recipe:** the Verovio + Augraphy render
  randomisation is a working version of NEXT.md's step E3.
- **One more angle:** DINOv2-base against MuSViT-Base as the encoder would be
  a clean comparison, but not a short-term one.

**Verdict: high for MCR** (an afternoon: add it as a column and see whether
it ranks D3 against Zeus J the way bars-exact does). **Low for the model.**

<a id="p3-7"></a>
### P3-7 · The Debussy Dataset: Evaluating OMR on Modern Staff Notation Manuscripts

Hugo Scheithauer, Thibault Clérice (Inria); Gonzalo Romero-García (EPITA).
Session 3, Mon 9 Nov 14:00. The paper isn't on arXiv; the code repo says
"proceedings link to be added". The group's earlier argument for this way of
transcribing is in the
[Anthology of Computers and the Humanities, vol. 4](https://doi.org/10.63744/K2fvu4Nzsv6t).

**What it is.**

- **The material:** Debussy autographs (piano, voice and piano, two pianos,
  1887–1915) from Gallica via IIIF. 37 documents.
  - Full-page track: 101 pages, 492 systems, 2,604 measures.
  - System-level track: 561 systems.
- **The transcription:** MusicXML in MuseScore 4, one annotator. It is
  "graphematic": it transcribes what's written. Manuscript phenomena are
  colour-coded (erasures, beat-repeat signs, non-standard repeats, altered
  trills), and hidden elements are kept with `print-object="no"`. 85% of
  pages have at least one such phenomenon.
- **The evaluation:**
  - Table 5 runs SMT, full-page SMT, the three public Zeus checkpoints and
    FCN, CRNN and CNNT zero-shot on Debussy.
  - Table 6 fine-tunes SMT with 5-fold document-level cross-validation, on
    two tracks: LMX from scratch, and PRAIG's kern checkpoint.
- **Licences:** data [CC BY 4.0](https://github.com/HugoSchtr/debussy-omr-dataset),
  also on Hugging Face (`HugoSchtr/debussy-omr-fullpage-lvl`,
  `-system-lvl`). Code MIT.

**Relevance.**

- **A second public handwritten benchmark with LMX ground truth, for a hand
  nobody trained on.** NEXT.md lists "measure what fine-tuning gives up on
  public benchmarks (Dolores; others only if a final model warrants it)".
  musvit-D3 has been crowned, so it now warrants it.
- **The catch:** it's piano grand staff and our readers read one staff.
  Systems would have to be split into staves (MusicXML by part or staff),
  which is doable.
- **Their transcription policy is ours.** SPEC's "label what's written; the
  slip flags itself" is their graphematic policy, and their tags for
  phenomena (abbreviation signs, erasures) are a vocabulary to borrow for
  the labeler's marks.
- **A practical gotcha** in
  [their Zeus README](https://github.com/HugoSchtr/debussy-omr-ismir2026/blob/main/zero_shot_eval/zeus/README.md):
  each public Zeus checkpoint expects different input binarization (adaptive
  for grandstaff-lmx, none for camera-grandstaff and OLiMPiC). Getting it
  wrong changed their published numbers. Check that Zeus J's preprocessing
  matches what its base checkpoint was trained on.
- **Their TF 2.18 fix to `zeus.py`** (subclassing `AbstractRNNCell`) is
  another way out of the TensorFlow 2.12 pin, if sqomr's port doesn't work
  out.

**Verdict: medium.** Use it as a held-out test once staves are cut. Read the
binarization note today.

---

## Worth reading, not acting on yet

<a id="p7-4"></a>
### P7-4 · When AI Annotates First: Measuring Its Impact on Music Score Labeling

Alejandro Galan-Cuenca, Juan P. Martinez-Esteso, Carlos Pérez-Sancho,
Francisco J. Castellanos, Antonio Javier Gallego (Alicante, IUII). Session 7,
Tue 10 Nov 14:00. **No abstract, PDF or code anywhere public yet.**

**What it probably is.** From the title and the group (Gallego and
Castellanos work on OMR layout and human-in-the-loop correction), it measures
how machine pre-annotation changes human labelling of scores: speed,
accuracy, and anchoring (accepting a wrong proposal).

**Relevance.** This is the labeler's design question exactly. Every page
opens with proposals, shown dashed orange until touched, and Claude's readings
are shown in orange too. If editors anchor on proposals, the right response
might be:
- a stronger visual cue for low-confidence proposals,
- spot-check pages that open with no proposals,
- or counting accept-without-edit rates from `activity.py`'s log, which
  already records what the editor touches.

The edition's claim that its encodings were "checked several times" makes
the anchoring question worth asking of Zeus-flag review as well.

**Verdict: medium**, pending the text. Read it when the proceedings appear.
Nothing to build until then.

<a id="p1-3"></a>
### P1-3 · TUTTI: Toward Generalizable Audio-to-Score Transcription via Fully Synthesized Data

Jianhuai Hu, Yashan Wang, Shangda Wu, et al. (Central Conservatory of Music,
Tsinghua). Session 1, Mon 9 Nov 10:00.
[arXiv 2609.00640](https://arxiv.org/abs/2609.00640) ·
[PDF](https://arxiv.org/pdf/2609.00640) · [code](https://github.com/a-musiclover/TUTTI)
(MIT) · TuttiCorpus on [Hugging Face](https://huggingface.co/datasets/pzzzzz/TuttiCorpus)
and [ModelScope](https://modelscope.cn/datasets/Animatopzzhu/TuttiCorpus)
(CC BY-NC 4.0).

**What it is.**
- **The model:** a spectrogram-to-ABC Transformer. Its pretraining data is
  entirely synthetic.
- **The synthetic data:** NotaGen generated about 363k ABC scores,
  conditioned on period and instrumentation, rendered to about 13k hours of
  audio. The model is then fine-tuned on real recordings.
- **On string quartets** (MV2H): 95.6 with full pretraining, 93.0 with
  single-instrumentation pretraining, 72.5 with none.

**Relevance.** The input is audio, so not the model. Two things carry over:
- **The evidence.** Synthetic pretraining on generated music in the target
  idiom is what made quartets work (72.5 → 95.6). That supports NEXT.md's E2
  and E3 hypothesis in a neighbouring task.
- **The data.** TuttiCorpus is 363k ABC scores of period-conditioned
  classical music, an unlimited source of quartet-like parts to render for
  E3 and E4. Two caveats:
  - Generated music may not share Boccherini's idiom. Measure it against
    OSSQ and kern quartets, not instead of them.
  - CC BY-NC is compatible with our models' CC BY-NC-SA, but say so in the
    model card.

**Verdict: low–medium.** A data source for E2 if real quartet encodings run
short. They won't soon.

<a id="p14-1"></a>
### P14-1 · Estimating the Reliability of DTW Alignments Using Circumstantial Evidence

Aanya Pratapneni, Alice Yuan, TJ Tsai (Harvey Mudd). Session 14,
Thu 12 Nov 11:30. [arXiv 2607.15443](https://arxiv.org/abs/2607.15443) ·
[PDF](https://arxiv.org/pdf/2607.15443). No code found.

**What it is.**
- **The method:** an unsupervised confidence score for each region of a DTW
  path. Each region is re-aligned with FlexDTW, whose path can start and end
  anywhere on the matrix edges, and the score is how well the two paths
  agree.
- **The interpretation:** disagreement marks regions that probably don't
  match, such as inserted or missing material.
- **Results:** 19 benchmarks, AUROC 0.970.

**Relevance.** SPEC's "Later" list wants bar numbers aligned across sources
when one source has an extra or missing bar. That is DTW over per-bar
features (event sequences from the readers, or bar widths), with exactly
this failure mode. The method would turn "the alignment says bar 47 ↔ 48"
into "and this stretch isn't trustworthy: look here", which is the
labeler's way of handling uncertainty everywhere else.

**Verdict: low now, medium when cross-source alignment is built.**

<a id="p6-1"></a>
### P6-1 · On the use of Pre-trained Audio Encoders for Audio-to-Score Music Transcription

Antonio Hidalgo-Centeno, Carlos Penarrubia, Jose J. Valero-Mas (PRAIG,
Alicante, the MuSViT group). Session 6, Tue 10 Nov 11:30.
[Program page](https://ismir2026program.ismir.net/poster_164.html#paper)
(unreachable from here) · [code](https://github.com/ahidalgocenteno/a2s-pretrained)
(MIT).

**What it is.**
- **The setup:** pretrained audio encoders, each paired with a fresh
  Transformer decoder and trained frozen, with LoRA, or fully fine-tuned.
  - Encoders: CNN, music2vec, MERT, wav2vec2, Whisper, Qwen2-Audio, Audio
    Flamingo 3.
  - The task is string-quartet audio to kern.
- **The data:** PRAIG's `{haydn,mozart,beethoven}-quartets` kern sets on
  Hugging Face.
- **Results:** none found; the README's citation is still "TBD".

**Relevance.** It's the audio twin of our MuSViT work (pretrained encoder,
adapters, new decoder). If their LoRA-against-full-fine-tuning result
contradicts ours ("unlocking the encoder's top layers: no better than
adapters"), that's worth knowing. Their quartet kern sets are another E2
source.

**Verdict: low.**

<a id="p6-9"></a>
### P6-9 · Full-page Recognition of Handwritten Jeongganbo Music Scores: Dataset and Approach

Carlos Penarrubia, Danbinaerin Han, Dasaem Jeong, Jose J. Valero-Mas.
Session 6, Tue 10 Nov 11:30. The [repo](https://github.com/carlospm12/handwritten-jeongganbo)
holds only a README and licence. The prior printed-Jeongganbo work is
[JOCCH 2025](https://dl.acm.org/doi/10.1145/3715159) with
[code](https://github.com/MALerLab/jeongganbo-omr).

**Relevance.** The notation is different (Korean grid notation), so the only
transferable part is the method: full-page end-to-end reading of handwriting,
which would skip our staff detection. Our bar-line and staff pipeline already
works, and staff-level reading is where our gains are. Nothing is released.

**Verdict: low.**

<a id="p5-1"></a>
### P5-1 · Does Notation Matter? MusicXML Tokenisation for Symbolic Music Generation and Understanding

Andrea Poltronieri, Matteo Spanio, Simone Chieppa, Xavier Serra, Martín
Rocamora (MTG-UPF, Padua). Session 5, Tue 10 Nov 10:00. The abstract is in
[Spanio's bibliography](https://raw.githubusercontent.com/matteospanio/matteospanio.github.io/master/src/data/papers.bib)
(entry `poltronieri2026notation`). No code or PDF found.

**What it is.** A general MusicXML tokenisation framework, tested with 26
language models against MIDI and ABC tokenisations on composer
classification, difficulty, accompaniment and generation. MusicXML wins.

**Relevance.** It vindicates notation-level targets like LMX over MIDI, but
it is about generation and understanding, not OMR, and doesn't compare with
LMX. Our readers are bound to LMX, so there is no reason to switch.

**Verdict: low.**

<a id="p4-3"></a>
### P4-3 · CODA: Cascaded Online Discontinuity-Aware Alignment for Real-Time Image-Based Score Following

Yining Yang, Ruogu Chen, Jie Han. Session 4, Mon 9 Nov 16:30.
[arXiv 2607.21899](https://arxiv.org/abs/2607.21899) ·
[PDF](https://arxiv.org/pdf/2607.21899) · [code](https://github.com/ValleyC/CODA) ·
[CODA-JumpBench](https://huggingface.co/datasets/ValleyC/CODA-JumpBench).

**What it is.** Live audio is followed on page images, top-down: first the
system, then the bar, then the position within the bar. Audio is encoded
with Mamba, the page with a CNN and FPN. A silence-triggered break mode
recovers from repeats and jumps. It is trained on synthetic piano (MSMD) and
untested on scans.

**Relevance.** Its input is system and bar boxes, which our bar export
already provides, and its `repeat_annotations.json` is a format for repeat
order. Audio score-following isn't on our path.

**Verdict: low.**

<a id="p8-7"></a>
### P8-7 · From Prediction to Collaboration: Interactive Symbolic Music Analysis

Emmanouil Karystinaios, Johannes Hentschel, Markus Neuwirth, Gerhard Widmer.
Session 8, Tue 10 Nov 15:30. [arXiv 2607.13587](https://arxiv.org/abs/2607.13587) ·
[PDF](https://arxiv.org/pdf/2607.13587).

**Relevance.** Roman-numeral analysis recast as partial completion, local
revision and filling masked labels from context, with an editing UI. It's a
design reference for interactive correction: the readers could re-read a
staff given the editor's fixed bars as context. Not near-term.

**Verdict: low.**

<a id="p12-4"></a>
### P12-4 · Inferring Implied Harmonies through Voice Leading in Monophonic Instrumental Music Using Graph-Based Methods

Marina Borsodi-Benson, Martin Rohrmeier (EPFL DCML). Session 12,
Wed 11 Nov 15:30. **No abstract or code found.**

**Relevance.** We have single parts. Implied harmony from one line could, in
principle, flag a misread pitch by its harmonic implausibility. But we have
all four parts of every quartet, so actual harmony is available and stronger
evidence.

**Verdict: low.**

<a id="p4-10"></a>
### P4-10 · Local Multimodal Music Alignment from Global Supervision

Irmak Bukey, Zachary Novack, Jongmin Jung, Dasaem Jeong, Chris Donahue.
Session 4, Mon 9 Nov 16:30. [arXiv 2607.10023](https://arxiv.org/abs/2607.10023) ·
[PDF](https://arxiv.org/pdf/2607.10023). No code found.

**Relevance.** It learns local alignment between sheet-image patches and
audio frames (Sinkhorn OT over CLIP and CLAP features) from page-level pairs
only. It aligns image to audio, not image to image or image to symbols.

**Verdict: low.**

<a id="p10-3"></a>
### P10-3 · STRAdi: Real-Time Violin Transcription for Score Following

Sein Lee, Jiyun Park, Juhan Nam (KAIST). Session 10, Wed 11 Nov 11:30.
[Code](https://github.com/seingreen/STRAdi) (Apache-2.0) and
[checkpoints](https://github.com/seingreen/real-time-violin-transcription).
It is a causal CRNN that turns violin audio into notes. Audio only.

**Verdict: very low.**

<a id="p7-7"></a>
### P7-7 · Robust Instrument-Agnostic Music Transcription for Western Classical Music

Yannik Venohr, Christof Weiß (Würzburg). Session 7, Tue 10 Nov 14:00. No
abstract found. It likely extends their ISMIR 2025 work on judging
transcription by consistency across recordings
([Zenodo](https://zenodo.org/records/17811552)). The idea of judging by
consistency across versions has a manuscript analogue: agreement between the
readings of two copies of one bar. Audio only.

**Verdict: very low.**

<a id="p8-8"></a>
### P8-8 · A First Benchmark and Metric for Evaluating Polyphony in Symbolic Music using Voice Independence

Eleanor Row, György Fazekas (QMUL). Session 8, Tue 10 Nov 15:30. No abstract
found. It is a metric for generated polyphony.

**Verdict: very low.**

<a id="p12-7"></a>
### P12-7 · A Cross-Cultural Dataset of Instrumental Difficulty for Woodwinds and Strings

Rui Yang, Mathieu Giraud, Florence Levé (Lille, Algomus). Session 12,
Wed 11 Nov 15:30. No abstract found. It is a dataset of difficulty ratings,
not of notation.

**Verdict: very low.**

---

## Considered and dropped

- **P7-6, The Internet Archive Music Dataset**
  ([arXiv 2609.20870](https://arxiv.org/abs/2609.20870)): audio and captions
  only, no scores.
- **P3-9, synthetic-to-real gap in drum transcription:** the method question
  is shared, but it is audio.
- **P6-6, flute performance analysis; P2-4, high-polyphony symbolic
  routing:** symbolic, but off-task.
- **Everything else:** audio generation, separation, beat tracking,
  captioning, recommendation or ethnomusicology.

## Off the program: other papers and tools

Links collected separately, judged the same way. Pages that couldn't be
opened from here are marked.

| Item | What it is | Verdict |
|---|---|---|
| [Full-Page OMR of Handwritten Monophonic Scores](https://arxiv.org/abs/2609.05662) (Rosello, Ríos-Vila, Rizo, Calvo-Zaragoza; PRAIG, Sept 2026) | See below. Code "on acceptance": not out yet. | **High: read now** |
| [Monte Carlo dropout for staff-region detection](https://link.springer.com/article/10.1007/s10032-025-00541-x) (Oliva-Bulpitt, Martinez-Esteso, Galan-Cuenca, Castellanos, Gallego; IJDAR 2025, open access) | See below. | Low–medium (the idea, not the model) |
| [Matchmaker / pymatchmaker](https://pymatchmaker.readthedocs.io) (Park, Cancino-Chacón, Chiruthapudi, Nam; ISMIR 2025) | An open library for real-time score following, from audio or MIDI to a symbolic score. Online time warping; its best variant is OLTW-Arzt with the onset-sensitive LSE feature. Tested on piano. | Medium, for aligning recordings |
| [NotaGen](https://arxiv.org/abs/2502.18008) (Wang, Wu, … Sun; 2025) | See below. | Low–medium |
| [VioPTT](https://arxiv.org/abs/2509.23759) (Wang, Peng, Su, Cheung; 2025) | Violin transcription that also labels playing technique, trained on synthetic data (MOSA-VPT). STRAdi (P10-3) builds on it. Audio only. | Low |
| [beat_this_live](https://github.com/CPJKU/beat_this_live) (P6-3) | Online beat and downbeat tracking. Its README is still the offline Beat This one. | Low |
| [Pixel Labeler](https://zenodo.org/records/17488553) and [Human vs. Machine: active learning for OMR](https://zenodo.org/records/17706567) (Alicante, ISMIR 2025) | The P7-4 group's prior work. The second paper finds entropy-based selection beats five experts' choice of what to label: 81.1% F1 from 8 patches, where humans needed 16. | Medium, with P7-4 |
| CapCyCin (P8-9) | Music captioning. | None |
| annotifyapp.github.io | A general course on data annotation and Git; nothing about music. | None |

**Full-page handwritten monophonic OMR (arXiv 2609.05662).**
- **Method:** a page generator renders the same RISM incipits two ways:
  - typeset, with Verovio and Augraphy;
  - handwritten, with Smashcima.
  An SMT page transcriber is pretrained on each and fine-tuned on three real
  handwritten collections.
- **Why it matters here:**
  - Single-line parts are our material.
  - Typeset-against-handwritten synthetic pretraining is exactly NEXT.md's
    E3-against-E4 question, already measured, by the group behind MuSViT.
  - Full-page reading would also skip staff and bar detection. But the
    synoptic edition needs bar boxes anyway, so the value for us is the
    pretraining result and, once released, the generator.

**Monte Carlo dropout for staff regions (IJDAR 2025).**
- **Method:** dropout is left on at inference, several predictions are made
  per page, and they are merged per pixel.
- **Results:** 63.6% less relative error than the baseline, with most of the
  gain at staff edges.
- **For us:** our staff finder is classical and already finds every staff,
  so the model isn't needed. The transferable idea is disagreement between
  stochastic predictions as a confidence signal. `experiments/barlines/ensemble.py`
  already votes across detectors. The share of votes could set how strongly
  a proposed bar line is drawn, so the editor's eye goes to the doubtful
  ones.

**NotaGen (arXiv 2502.18008).**
- **What it is:** an LLM-style symbolic generator (ABC). Pretrained on 1.6M
  pieces, fine-tuned on about 9k classical works with
  period–composer–instrumentation prompts, then CLaMP-DPO.
- **Its role elsewhere:** it is the generator behind TUTTI's synthetic data.
- **For us:** it could write unlimited "Classical / Boccherini / string
  quartet" parts for E2. But OSSQ, kern quartets and Philhar's Boccherini
  are real and not yet used up.

**Aligning recordings.** We have the symbolic score (the edition's LilyPond),
so audio alignment is an audio-to-symbolic problem. The bar labels then carry
each bar's time to its boxes in every manuscript.
- **Offline:** DTW over chroma and onset features (synctoolbox) is the
  standard tool.
- **Online:** Matchmaker.
- **Confidence:** P14-1 says where an alignment can't be trusted.
- **Not needed:** image-based following (CODA, P4-3) and audio-only
  transcription (P1-3, P6-1, P7-7, P10-3, VioPTT). They exist for when no
  score exists, and we have one.

## Suggested order

1. **Today:** add `mcr-metric` beside bars-exact in `tools/musvit_score.py`
   (P12-5). Read the Debussy repo's Zeus binarization note against Zeus J's
   preprocessing (P3-7).
2. **This week:** try loading Zeus J into sqomr's PyTorch Zeus (P13-3). If
   it loads, retire the TensorFlow 2.12 environment.
3. **With NEXT.md E1 and E2:** OSSQ-OMR's scanned quartet staves as a replay
   or stage-1 set (P13-3). Debussy's system track, split into staves, as a
   new-hand test (P3-7).
4. **When the proceedings appear:** P7-4's findings against the labeler's
   proposal UI.
5. **When cross-source alignment is built:** P14-1.
