# Synthetic quartet staves

Staves drawn as our copyists draw them, with labels that are exact by
construction: the drawing is made from the label. For training the MuSViT
reader (`experiments/musvit`) on music and hands it hasn't seen enough of.

## How a staff is drawn (`copyist.py`)

1. **The music:** an LMX staff, as our labels are written. It's turned into
   MusicXML (`lmx2xml.py`, the lmx package's reader) and laid out by
   **verovio**. Verovio draws every symbol our labels have: key and time
   signatures, slurs, ties, tuplets, grace notes, staccato, trill and fermata.
   The staff is justified to a length in staff spaces: a real staff's length
   when the music comes from one, else a length drawn from the hand's range.
2. **Redrawn by hand rules:**
   - noteheads become tilted ovals that touch their stems;
   - stems vary in length and width;
   - beams thicken and waver;
   - slurs loosen and staff lines wave;
   - every other glyph is jittered;
   - bar lines lean;
   - tuplet numbers are often left out, as the copyists do.
3. **Ink and paper:**
   - the music is sheared about the staff's middle so the stems lean;
   - every stroke is warped smoothly, then rastered once, with staff lines in
     their own lighter ink;
   - the paper is a real staff's background with the ink lifted off;
   - show-through from the back of the page, and noise;
   - a JPEG quality like the scans'.
4. **Distractions in the margins:** dynamics and tempo words, and the ink of
   the staves above and below, cut from real staves. None of these is in LMX,
   so the label is unchanged. The reader has to learn to ignore them, as it
   does on real pages.
5. **The crop:** as `compare.staff_crop` crops a real staff. That's the
   staff, 2.5 spaces above and below, and a space at each end.

**Hands** (`HANDS`) are ranges of habits sampled per staff: staff-space size,
slant, notehead shape and tilt, stem and beam weight, ink, and staff length.
The hands are:
- `berlin`: KHM 602/603.
- `parisA`: RES 507, vn1 and vc.
- `parisB`: RES 507, vn2 and va. Leaves clef and key off 80% of its staves,
  as on its continuation lines, while the label keeps them.
- `vma`: Vma ms 1067.
- `generic`: wide ranges.

**The copyists' own clefs:**
- Glyph shapes come from verovio's SMuFL fonts (Petaluma, Leipzig, Bravura),
  except the opening clef.
- In 80% of staves that clef is one of the copyist's own (`real_clef`), cut
  from the start of their training staves by `harvest_clefs.py`:
  - the staff lines are lifted off;
  - the cut ends at the emptiest column within the clef kind's range of
    widths;
  - only the 60% of cuts most like their group's median are kept.
- That gives 34 Berlin treble, 16 alto and 10 bass clefs; Paris A 19 treble
  and 13 bass; Vma 52 treble, 27 alto and 25 bass.
- Paris B gives none (its continuation lines have no clef).
- The `generic` hand draws from every hand's clefs.
- Stored in `~/.cache/manuscript-labeler/zeus/glyphs/clefs`; rebuild with
  `uv run experiments/synth/harvest_clefs.py`. `sheet.png` there shows them.

**The check (`copyist.check`):** a staff is drawn only if verovio drew every
note, rest and beamed group its label has. Verovio misreads a few beamed
chords:
- Op. 48 (dataL2): 9 of 726 staves left out;
- Philhar (dataM): 2 of 2,444.

`validate.py` runs this check over a dataset folder.

## Music

- **Our own training music** (`gen.py --real-width`). It re-draws D1's
  training staves in other hands, at their own lengths. It can only use
  staves from a training list, never the clean test (KHM 603 I) or the
  practice exam.
- **OpenScore String Quartets** (CC0,
  [github.com/OpenScore/StringQuartets](https://github.com/OpenScore/StringQuartets)).
  That's 102 classical-era scores: Haydn (38), Mozart (23), Beethoven (12),
  Schubert (8), Saint-Georges (6), Arriaga, Dittersdorf, Viotti, Boccherini
  (G.213), Cherubini, Gossec, Hoffmeister, Kalliwoda, Onslow and Spohr.
  `score_to_lmx.py` cuts each part into staves:
  - Each staff copies a real staff's size: it stops at that staff's number
    of notes and rests, or at its number of bars, whichever comes first.
  - A staff never runs across the end of a movement.
  - Labels follow dataset.py's conventions: key and clef on every staff, time
    where it starts or changes, no stems, and only staccato, trill and
    fermata among the marks.
  - It uses Zeus's own LMX encoder at Zeus's pin.

  That gives 44,609 staves. Left out:
  - 683 with hidden objects;
  - 115 the encoder rejected;
  - 95 with tokens the reader doesn't know (keys of six sharps, rare
    tuplets).

  `gen.py` also skips any drawing wider than the reader takes (aspect ratio
  above 21), since the reader would squeeze it.

## Use

```sh
# quartet scores -> staff LMX
uv run experiments/synth/score_to_lmx.py OUT_LMX scores/*.mxl --real ~/.cache/manuscript-labeler/zeus/dataL2
# LMX -> training staves (dataset.py's layout: GROUP/<id>.jpg, .lmx, samples.GROUP.txt)
find OUT_LMX -name '*.lmx' > list.txt
uv run experiments/synth/gen.py ~/.cache/manuscript-labeler/zeus/dataS3 S-osq list.txt --limit 8000 --match-density
uv run experiments/synth/gen.py ~/.cache/manuscript-labeler/zeus/dataS S-own ~/.cache/manuscript-labeler/zeus/dataL2/samples.D-B_KHM-602-I.txt ... --real-width
# the explainer page: stages, habits, real against drawn per hand, galleries
uv run experiments/synth/explainer.py copyist-staves.html --osq-list list.txt
# by eye: real staves above their music drawn in a hand
uv run experiments/synth/sheet.py sheet.png D-B_KHM-602/p2s3:berlin F-Po_RES-507-17/p10s3:parisB
```

One staff takes about 0.35 s on one core. `gen.py` writes `hands.GROUP.json`
(each staff's hand) beside the samples file. With `--match-density`, each
hand is given music as dense as the middle half of its own real staves.

## Why not Smashcima

We tried Smashcima 1.1.2 first, with MUSCIMA++ glyphs. It draws single
staves, but not key or time signatures, slurs, ties, grace notes, tuplet
numbers, articulations, or 32nd rests and flags. All of those are common in
our staves. Verovio lays out all of them, so the handwriting is done here,
on top of its layout.

We tried it again on 2026-10-19 as training data for Segment Anything. It
traced Berlin's symbols worse than no training at all. See
`reports/2026-10-19-smashcima/` (with pictures) before trying it again.

## Results

See `experiments/musvit/BRIEF.md` (2026-10-18, synthetic staves).
