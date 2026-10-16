# Zeus, run J (J-lr1e5-e8, 2026-10-16)

OmniOMR's reader for handwritten music, fine-tuned on Boccherini's copyists.
It reads one staff at a time and writes out its notes. The Op. 48 edition
uses it as a second reader: where Zeus strongly disagrees with an encoded
note, the encoding checks raise a flag. It is the default model of
[zeus-score](README.md), and the labeler's.

> **Licence: CC BY-NC-SA 4.0. Non-commercial use only; adaptations shared
> alike.** These weights adapt OmniOMR's Zeus weights
> (https://github.com/OmniOMR/zeus, snapshot ayce-2026-08-03), which carry
> that licence. Attribution: OmniOMR (Zeus and its weights); Jason Sundram
> (fine-tuning and training data).

The same card as a web page: `static/models/zeus.html` (in the labeler,
under "model cards").

## The model

| | |
|---|---|
| Architecture | Zeus "solo26". A small convolutional network (3 stages of 2 residual blocks, 32 channels) reads a staff image 96 px high. Each 16 px-wide slice goes to a 2-layer recurrent encoder (192 units), and a 1-layer decoder writes the staff as tokens. |
| Output | Linearized MusicXML (LMX), 168 tokens in all: measures, clefs, keys, times, pitches, accidentals, durations, dots, beams, slurs, ties, chords, rests, grace notes and fermatas. Zeus's clef tokens are unreliable on these hands, but its note placement isn't, so scoring names pitches in the labelled clef. |
| Starting weights | ayce-2026-08-03: OmniOMR's solo-staff snapshot, trained on MusiCorpus (Dolores train and validation, OmniOMR train) |
| This model | Run J's eighth and last epoch, 28 MB. Release [`zeus-J-lr1e5-e8-2026-10-16`](https://github.com/jsundram/manuscript-labeler/releases/tag/zeus-J-lr1e5-e8-2026-10-16); sha256 of weights.h5 `39eada410ca5ded4265aec3775d1b345fcbbf23ab550906a703912dcd8832d6d`. |
| Input | One staff from the labeler's bar export: from its left end to its right, a staff space beyond each and 2.5 spaces above and below, straightened along its bend, the paper brightened to white. A staff space is about 11 px. |
| Environment | Python 3.10, tensorflow 2.12 (`tensorflow-macos` on Apple silicon), Zeus at commit c8569eb |
| Training | 2.5 hours on an Apple-silicon Mac: 8 epochs of 321 steps |
| Adopted | 2026-10-16, replacing run G |

## Training data

2,568 staves. Every staff's truth is checked: read back through the scoring
code, it must match its encoding exactly. Staves with two voices are left out.

| source | work | hand | staves | its truth |
|---|---|---|---:|---|
| D-B KHM 602 | Op. 48 No. 1, I and II | the Berlin copyist | 65 + 32 | the edition's checked encoding |
| D-B KHM 603 | Op. 48 No. 2, II | the Berlin copyist | 32 | the same |
| F-Po RES 507 (14) | Op. 48 No. 3, I and II | Paris A (vn1, vc), Paris B (vn2, va) | 47 + 29 | the same |
| F-Pn Vma ms 1067 (1) | Op. 48 No. 3, I and II | the Vma copyist | 70 + 47 | the same |
| **Op. 48, from the edition** | | | **322** | |
| Op. 2, G. 159–164 | six quartets, parts | copyists | 519 | Philhar's encodings, from Boccherini's autographs, paired automatically |
| Op. 22, G. 183–188 | six quartets, Berlin parts | copyists | 568 | the same |
| Op. 22, Paris part-books | Nos. 2, 3, 4, 6 | a copyist | 318 | the same |
| Op. 32, G. 201–206 | six quartets, parts | a copyist | 444 | the same |
| F-Pn RES 507 (2) | Op. 33, parts | copyists | 397 | the same |
| **Philhar** | | | **2,246** | 62.7% of those sources' 4,025 staves |

"Paired automatically" means each staff was detected, read by Zeus and
aligned bar by bar with the encoding. It was kept only if every measure paired
cleanly.

- **Held out:** KHM 603 movement I (Op. 48 No. 2 I), the clean test. It has
  been kept out of every training run and every choice of recipe since it was
  encoded.
- **No development set:** the former ones went into training, so that all
  labelled data is used.
- **Not used:** the Op. 24 autograph full score, engraved prints, and the
  OSSQ manuscripts (run H tried one; it didn't help).

## How it was trained

- **Recipe.** Zeus's own trainer continues from the stock weights. Learning
  rate 1e-5 with cosine decay to 0, batch 8, 8 epochs, seed 42. The only
  augmentation is a sideways shift of up to 8 px. The last epoch is kept; no
  epoch is chosen by its test score.
- **Why so gentle.** At 1e-4 the first fine-tunes learned the Berlin copyist
  and forgot the Paris hands (RES 507 (14) II went from 83% to 39% of bars
  exact). At 1e-5, trained hands gain and unseen hands don't lose. Neither
  the full augmentation set nor more epochs helped.
- **Code.** In the labeler's `experiments/zeus/`: `dataset.py`,
  `autodetect.py` and `autopair.py` build the data, `finetune.py` trains, and
  `compare.py` scores.

By epoch, on the clean test: 51, 60, 61, 62, 62, 63, 65, 65% of bars exact.
Training loss went from 0.71 to 0.19.

## Results on the clean test

KHM 603 movement I, 347 bars. A bar is exact when every event matches the
encoding in pitch and duration, including rests, chords and grace notes. Bars
whose measures won't pair with Zeus's count as wrong.

| model | bars exact | rhythm right | pitch right | events right | vn1 | vn2 | va | vc |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| stock (ayce-2026-08-03) | 42% | 50% | 53% | | 40% | 30% | 43% | 56% |
| run G | 62% | 71% | 69% | | 49% | 50% | 64% | 86% |
| run I | 64% | 74% | 71% | 79% | 56% | 46% | 66% | 87% |
| **run J** | **65%** | **74%** | **74%** | **80%** | 53% | 55% | 60% | 91% |

- **J against I:** 225 bars exact against 222, which is within the test's
  noise of about 4 points. What clearly changed is that J invents far fewer
  notes: 36 extra events against 128.
- **Its 412 wrong events:** 201 in duration, 164 in pitch, 36 extra, 36
  missed, 35 in chord size, 11 an octave out, 10 grace notes, and 7 a rest
  for a note or the reverse. Where it reads the note right, it shows the
  accidental as encoded 99% of the time.
- **Where it fails:** dense 32nd notes. About 90 of the viola's 104 wrong
  pitches are in one broken-chord figure, which crosses strings (bars 26–31
  and 61–67). Zeus pulls the low note up toward its neighbours. The clefs
  were read right.
- **Where it's good:** the cello (91% exact) and sparse writing.

## As the edition's second reader

The edition flags a bar where Zeus finds its own reading more likely than ours
by more than 3 in log-probability, on a pitch, a rhythm or an accidental.
This was measured on Op. 48 No. 2 I as it stood right after the read, before
any correction; J never saw that movement. 107 of its 337 bar-parts were later
corrected in those kinds.

| model, floor 3 | bar-parts flagged | of them wrong | wrong ones flagged | pitch | rhythm | accidental |
|---|---:|---:|---:|---:|---:|---:|
| run G | 122 | 95 (78%) | 89% | 12 / 19 | 9 / 27 | 78 / 80 |
| **run J** | **126** | **96 (76%)** | **90%** | 12 / 19 | 10 / 27 | 78 / 80 |

- Floors from 2.5 to 4 catch the same errors, within one or two.
- Rhythm is the weak spot. LilyPond's bar check catches most of the rhythm
  errors Zeus misses.
- On movements J trained on (every encoded Op. 48 movement but No. 2 I), it
  objects less. The scores mark those staves `trained`.

## The family, stock to J

The clean-test column is the fair comparison. The development movements
guided the recipe and flatter the models: KHM 602 II overstates by about
20 points.

| run | date | trained on | staves | recipe | development movements | clean test | what it taught us |
|---|---|---|---:|---|---|---:|---|
| stock | 08-03 | MusiCorpus (OmniOMR) | — | — | KHM 602 II 45%, Vma II 55%, RES 507 (14) II 79% | 42% | Reads the Paris hands well and the Berlin copyist poorly. Its clefs are often wrong. |
| first fine-tune | 10-09 | KHM 602 I, RES 507 (14) II | 94 | lr 1e-4, 30 epochs | KHM 602 II 51 → 68%* | 47% | A trained hand gains a lot. Trained on KHM 602 alone, RES 507 (14) II fell from 83% to 39%*: it overfits. |
| C | 10-10 | KHM 602 I and II, Op. 33 Paris parts, 600 Dolores staves | 889 | lr 1e-4, 20 epochs | RES 507 (14) II 76%, Vma II 44% | 48% | Mixing in other data didn't stop unseen hands from falling. |
| sweep | 10-11 | run C's data | 889 | lr 3e-5, 1e-5, 3e-5 with augmentation; 8 epochs | lr 1e-5: RES 507 (14) II 77%, Vma II 55–56% | 48% | At 1e-5, unseen hands don't lose. Augmentation didn't help. |
| D | 10-11 | KHM 602 I, RES 507 (14) II, Op. 33, 600 Dolores | 886 | lr 1e-5, cosine, 8 epochs (the recipe) | KHM 602 II 62–64%, Vma II 55–56% | 47% | Trained hands gain without new hands losing. |
| E | 10-11 | KHM 602 I, RES 507 (14) II, every Philhar part source (1,711), 2,000 Dolores | 3,807 | the recipe | KHM 602 II 78–80%, Vma II 60–62% | 60% | The first gain on an unseen hand: other Boccherini copyists help. |
| F | 10-11 | E without Dolores | 1,807 | the recipe | KHM 602 II 76%, Vma II 64–65% | 59% | Dolores adds nothing. |
| G | 10-12 | more Philhar staves (three detections combined) | 2,340 | the recipe | KHM 602 II 81%, Vma II 64–65% | 62% | More of the same hands no longer helps an unseen one. |
| H | 10-13 | G plus 190 Philhar staves and 145 of OSSQ's Mayer A | 2,675 | the recipe | Vma II 66–67%; Maier 39–42% (G 47%) | 59% | Another composer's hand didn't help. Not adopted. |
| I | 10-14 | G plus Op. 48 No. 3 I (Vma 70, RES 507 (14) 47) | 2,457 | the recipe | KHM 602 II 83–84%, Vma II 69–70% | 64% | A hand's own bars moved it when other hands' data didn't. |
| **J** | 10-16 | I plus KHM 602 II, Vma 1067 (1) II, KHM 603 II | 2,568 | the recipe | none (they're in training) | **65%** | Far fewer invented notes. Adopted. |

\* Scored before 2026-10-11, when only bars Zeus paired were counted.

**What the clean test shows:** the recipe work, from the first fine-tune to D,
didn't move it (47–48%); it kept unseen hands from getting worse. The big step
came with E, from Boccherini's other copyists: 13 points. After that, gains are
a few points a run, near the test's noise.

## Known limits

- **Dense passagework.** 32nd notes and broken chords across strings:
  durations are misread, and low notes are pulled toward their neighbours.
- **Double stops** come out as two voices. Two-voice staves are kept out of
  training.
- **Clefs.** Its clef tokens are unreliable; its note placement isn't.
  Forcing the labelled clef made the viola worse.
- **Hands it hasn't seen** gain least. Op. 48 Nos. 4–6 (Vma ms 1067 (2),
  RES 507 (16) and (17)) are new hands until some of their staves are encoded.
- **Resolution.** About 11 px per staff space: a head misplaced by a step is
  hard for it to see.
- **A small clean test.** 347 bars from one copyist can't tell runs apart
  within about 4 points.

## Future directions

- **Encode a few staves of each new hand.** This has been the one reliable
  lever. The first movement of each of Op. 48 Nos. 4–6 would teach Zeus those
  copyists, and the movement after it can serve as that hand's test.
- **A bigger clean test, one per hand.** That would tell runs apart within a
  point or two, and make seeds or ensembles worth measuring.
- **Two-voice staves and double stops** in the training data, written as
  chords or voices instead of left out.
- **Rhythm decoded under the bar check.** A search over Zeus's readings that
  only accepts measures adding up to the time signature would fix most of what
  the bar check now only flags.
- **Pitch measured, not re-read:** measure the head's place on the staff
  where Zeus's step is doubtful.
- **Passagework.** Oversample dense 32nd-note bars, or train on taller staff
  images.
- **More Philhar staves.** 37% are still unpaired, and the Op. 24 autograph
  score needs whole systems paired.
