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
