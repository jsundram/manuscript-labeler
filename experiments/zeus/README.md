# Zeus against the edition's encoding

Could Zeus (OmniOMR's handwritten-music reader) be a second source of
transcription for the edition? Measured against the encoding of Op. 48/1,
made from KHM 602 and checked several times, so taken as right: every
disagreement is counted as Zeus's error.

    UV_PYTHON_INSTALL_DIR=~/.cache/manuscript-labeler/zeus/py \
      uv run --python-preference only-managed experiments/zeus/compare.py <edition-repo> [--source D-B_KHM-602]

Zeus needs Python 3.10 and tensorflow 2.12 (macOS: tensorflow-macos). The
Python is kept in `~/.cache/manuscript-labeler/zeus/py` and the model
snapshot (ayce-2026-08-03, solo staff, weights CC BY-NC-SA) in
`~/.cache/manuscript-labeler/models/zeus/`. Run outside Claude Code's
sandbox. Zeus's readings are cached in `answers/` by staff and crop, so a
rerun of the comparison takes seconds.

How it's read and compared:
- Each staff of the bar export is read whole, straightened.
- Zeus's clefs are wrong on these hands, so its notes are placed on the
  staff by its own clef, then named in the clef the labels give the bar.
- Its measures pair with the staff's bar boxes in order, where it found as
  many.
- Each bar's events are aligned with `scripts/events.py`'s by edit
  distance. Notes that start together with the same duration count as one
  chord on both sides.

## Results (2026-10-09, KHM 602 against Op48-1, movements I and II)

105 staves, 800 bars. On 16 staves Zeus found a different number of
measures than there are bar boxes, so 116 bars weren't compared, 88 of
them cello.

Of the 684 bars compared:

| | all | vn1 | vn2 | va | vc | I | II |
|---|---|---|---|---|---|---|---|
| bars entirely right | 40% | 33% | 41% | 33% | 66% | 36% | 48% |
| bars right in rhythm | 52% | 45% | 49% | 45% | 78% | 47% | 59% |
| bars right in pitch | 58% | 47% | 58% | 57% | 76% | 52% | 67% |
| events right | 74% | 67% | 79% | 74% | 88% | 71% | 83% |

There are 3,476 encoded events (notes, rests, chords, graces):
- **Right:** 2,574.
- **Wrong duration:** 459, the largest category, worst in violin I's dense
  32nds.
- **Wrong pitch:** 259, nearly all one or two steps off, in both
  directions: the head's place misjudged, not a systematic offset.
- **Octave out:** 24.
- **Extra events Zeus added:** 253.
- **Missed:** 107.
- **Double stops:** Zeus reads them as two voices, often with different
  rhythms (95 chord-size errors, plus some of the extra events).
- **A rest for a note, or the reverse:** 78.
- **Grace notes:** 25.

(Rerun after two fixes to the comparison found while building the
training data: grace notes kept before their note, and Zeus's bar rest,
`rest ... rest:measure`, read as one event.)

On notes it read right, the accidental shown agrees with the encoding's
97% of the time.

## What it means

As a second reader checking an encoding, it would flag 60% of bars on
this source, and here every flag is a false alarm. A disagreement with
Zeus says little about a bar. It is closer on sparse writing (the cello,
movement II) than on dense passagework, and its accidentals and
measure counts are more reliable than its rhythms.

The encoding gives the ground truth for fine-tuning it. This script, on a
held-out source, is the benchmark for that.

## Fine-tuning (2026-10-09)

Can Zeus learn this edition's hands from the encoding? The training data
comes from `dataset.py`:
- each staff as compare.py cuts it;
- its notes from `events.py`, written as MusicXML in the manuscript's
  clefs (the labels'), and turned into Zeus's text format by its own
  `lmx` encoder;
- every staff checked by reading it back through compare.py, which must
  match the encoding exactly.

A bar split across two boxes (a short bar and the next upbeat) is cut
where the upbeat starts. Staves with two voices are left out. That leaves
65 staves from KHM 602 movement I, 32 from its movement II, and 29 from
RES 507 (14) movement II. Op. 48/3 movement I is left out because its
encoding is still being worked on.

`finetune.py` runs Zeus's own `train` from the zero-shot snapshot:
- 30 epochs, learning rate 1e-4, batch 8;
- about a minute an epoch on the CPU;
- the final epoch is scored, not the best one.

Scored by compare.py on bars both models could compare:

| test (held out of training) | trained on | model | bars exact | rhythm | pitch | errors |
|---|---|---|---|---|---|---|
| KHM 602 II (238 bars) | KHM 602 I, RES 507 (14) II | zero-shot | 51% | 60% | 71% | 191 |
| | | fine-tuned | **68%** | **85%** | 74% | 160 |
| RES 507 (14) II (233 bars) | KHM 602 I, II | zero-shot | 83% | 91% | 87% | 56 |
| | | fine-tuned | 39% | 68% | 41% | 292 |

- **A hand it was trained on**, in a movement it wasn't: much better.
  Most of the rhythm errors go; pitch hardly moves.
- **Hands it wasn't trained on**: much worse. The error on the held-out
  movement was lowest at epoch 4 and rose from there. The model fitted
  the Berlin copyist and lost what it had for the Paris hands, which it
  read well zero-shot. Its clefs went too: nearly a third of its wrong pitches
  there are 6 steps out, treble read as alto or the reverse.

So fine-tune per hand, or with every hand's data mixed in (as the first
run did), and stop early when testing on a new hand. Op. 48/2 (KHM 603,
the KHM 602 copyist) should gain as the first run did. Op. 48/4–6 (Vma ms
1067 (2), RES 507 (16)) would need some of their own staves encoded
first.

Models are kept in `~/.cache/manuscript-labeler/models/zeus/`
(heldout-602-II.model, heldout-507-14-II.model). They are derived from
CC BY-NC-SA weights.

## What a bar check would catch (barcheck.py, 2026-10-09)

LilyPond refuses a bar whose durations don't fill it. Applied to Zeus's
readings of whole bars (not pickups, split bars, multi-bar rests or a movement's
last bar, which may be short):

| model, test movement | bars wrong | the bar check flags | of those wrong in rhythm | right bars flagged |
|---|---|---|---|---|
| zero-shot, KHM 602 II | 111 of 233 | 73 | 71 of 90 | 6 of 122 |
| fine-tuned, KHM 602 II | 74 of 233 | 21 | 18 of 32 | 2 of 159 |
| zero-shot, RES 507 (14) II | 32 of 218 | 8 | 8 of 13 | 2 of 186 |
| fine-tuned on KHM 602, RES 507 (14) II | 128 of 218 | 46 | 46 of 63 | 0 of 90 |

The bar check flags most rhythm errors (55–80%) and almost no right bars.
It can't see a wrong pitch, which is what remains: zero-shot Zeus plus a
bar check leaves 38 wrong bars unflagged on KHM 602 II, and the
fine-tuned model 53, mostly pitch. Those are for a measurement of heads
(headcheck.py, the aligner), not another reading.

## Training pairs without labelling (autodetect.py, autopair.py, 2026-10-10)

Could encodings made elsewhere (Philhar's Op. 24/3–6 and Op. 33, from
Boccherini's autographs) become training data without labelling their
manuscripts? A staff needs only its part and which bars it holds.

- `autodetect.py`: the labeler's automatic detection on every music page,
  as if unopened (the server's detection, cached detectors' vote and
  staff ends; the learned bar-line filter trained without the source).
- `autopair.py`: Zeus (zero-shot) reads every detected staff. Part by
  part, its measures are aligned with the encoding's bars by dynamic
  programming (rhythm and steps between notes, no clef needed; split bars
  at staff breaks and at Structure.ily's mid-bar repeats; multi-bar
  rests either way). A staff is kept if its measures all pair cleanly,
  none is nothing like its bar, and detection's bar boxes on it are as
  many as Zeus's measures. Its clef is the one under which Zeus's notes
  name the encoding's pitches most often.

Assumed known: which pages are music, and whose part (from the labels).
The cached YOLO detectors were trained on these sources (in-sample); the
learned filter wasn't. The rules were fixed on KHM 602's and RES 507
(14)'s mistakes (multi-bar rests, splits); Vma ms 1067 (1) was the check
(115 kept, none wrong, before the last fix too).

| source | labelled staves | kept | kept, wrong | bars on kept staves | clef chosen right |
|---|---|---|---|---|---|
| KHM 602 | 105 | 73 | 0 | 564 | 72 / 72 |
| RES 507 (14) | 100 | 91 | 0 | 665 | 89 / 89 |
| Vma ms 1067 (1) | 143 | 114 | 0 | 590 | 112 / 112 |

(Clefs scored on staves with one clef in the labels.) The kept staves
aren't the easy ones: Zeus reads 40% of kept bars exactly on KHM 602 and
41% of the rest (RES 507 (14) II: 82% and 79%).

## The clean test: KHM 603 movement I (2026-10-15)

Op. 48/2 movement I, from KHM 603 (the KHM 602 copyist), was encoded after
every training run and choice of recipe. It is held out of training, and of
every decision, from now on. Each new model is scored on it:

    uv run experiments/zeus/compare.py <edition-repo> --source D-B_KHM-603 --movements I --model M

347 bars compared. Bar 46 of the cello isn't compared, because its clef
changes inside the bar.

| model | bars exact | rhythm | pitch | vn1 | vn2 | va | vc |
|---|---|---|---|---|---|---|---|
| zero-shot (ayce-2026-08-03) | 42% | 50% | 53% | 40% | 30% | 43% | 56% |
| run G (2,340 staves; learning rate 1e-5, cosine decay, 8 epochs) | 62% | 71% | 69% | 49% | 50% | 64% | 86% |
| run I (G plus Op. 48/3 I's 117 staves), epoch 7 | 64% | 74% | 71% | 56% | 46% | 66% | 87% |
| run J (I plus KHM 602 II, Vma 1067 (1) II, KHM 603 II; 2,568 staves), epoch 8 | 65% | 74% | 74% | 53% | 55% | 60% | 91% |

Every earlier run, scored on it on 2026-10-16 (last epoch):

| model | bars exact | rhythm | pitch | vn1 | vn2 | va | vc |
|---|---|---|---|---|---|---|---|
| first fine-tune (heldout-602-II: KHM 602 I, RES 507 (14) II; lr 1e-4, 30 epochs) | 47% | 61% | 54% | 49% | 29% | 33% | 77% |
| run C (mixC-e20) | 48% | 61% | 53% | 43% | 52% | 33% | 63% |
| sweep, lr 1e-5 | 48% | 65% | 55% | 42% | 29% | 52% | 69% |
| run D | 47% | 63% | 50% | 36% | 35% | 48% | 68% |
| run E | 60% | 69% | 66% | 50% | 48% | 60% | 80% |
| run F | 59% | 70% | 65% | 50% | 42% | 56% | 86% |
| run H | 59% | 70% | 64% | 44% | 48% | 58% | 84% |

The recipe work (the first fine-tune to D) didn't move it; it kept unseen
hands from getting worse. Boccherini's other copyists (run E) added 13
points. The model card, `static/models/zeus.html`, has the whole family.

- **Fine-tuning holds on a movement nobody watched:** about 20 points over
  zero-shot. But the movement that guided the recipe (KHM 602 II, 81–84%)
  overstated it by about 20 points.
- **One movement can't tell runs apart within about 4 points.** I minus G
  is +1.7 points, with a 95% interval of −1.8 to +5.5 (paired, resampled
  in 4-bar blocks per part). Only 34 bars differ between the two models.
- **Pitch errors here are seldom one step.** Only 2–6 bars are wrong by
  one-step pitches alone, so measuring heads would gain little on this
  movement. Larger shifts in particular passages cost more: viola bars
  25–29 and 62–67, and violin 2's bars 7–13.

Readings are in `answers/D-B_KHM-603-*.model.json`; scores are in
`results/D-B_KHM-603-I-*.model.json`.

## Zeus limited to the labelled clef (clefread.py, 2026-10-15)

On the clean test, some passages come out 4–6 steps off in clefs the
labels have right. On some staves Zeus also opens with the wrong clef:
treble read as alto or tenor, alto as treble or tenor. Would it read
better if it could only write the labels' clef? `clefread.py` reads
each staff one at a time, freely and with every other clef token ruled
out. compare.py scores both readings.

| model | free | labelled clef only | vn2 | va |
|---|---|---|---|---|
| run I | 64% | 65% | +7 bars | −4 bars |
| run G | 62% | 61% | +5 bars | −7 bars |

No better.
- **Violin 2 gains:** two treble staves that Zeus read as alto or tenor
  now come out right.
- **The viola loses:** where Zeus wrote tenor or treble on a viola staff,
  it had still placed the notes right. compare.py names them in the
  labels' clef, so the wrong clef token did no harm. Forcing alto sends
  the rest of the reading down a worse path.

Limiting only the violins would be a rule fitted to this movement. It
would have to be chosen on the dev movements first. Reading one staff at a
time instead of in batches of 8 barely matters (run I: 222 bars
against 222; run G: 215 against 216).
