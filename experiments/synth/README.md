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

## Clef changes inside the staff (dataS4)

Every reader we have misses the clean test's four cello clef changes (KHM 603
I, p20s8, p20s9, p21s4, p21s5), and our training staves have few changes
(`experiments/ossq/clef-check.md`). `gen_clefs.py` draws staves that have
them.

**The music** is OSQ staves (`osq-all.txt`, re-rooted at
`~/Data/manuscript-labeler/experiments/synth/osq-lmx`). OSQ's one Boccherini
is G. 213, so nothing of Op. 48 is drawn. A stretch of a real staff moves to
the clef a copyist would write it in, where it sits high:
- the stretch's lowest and highest notes must fit the new clef;
- it must reach above the part's usual staff;
- no note may be left past four ledger lines in either clef.

The pitches are kept. Only the clef, and so where the notes sit, changes.

**The clef tokens** go where dataL2's labels put them:
- at a bar line, right after `measure` (and any key and time);
- inside a bar, right before the next note's pitch, and only between beamed
  groups and tuplets.

About three in four changes are at a bar line. A key written again after a
change is drawn but never labelled, as in dataL2.

**Kinds** (`kinds.S4-clef.json` gives each staff's kind, source and clefs):

| kind | staves | what |
|---|---:|---|
| vc-treble | 1,106 | cello, bass to treble (mostly back) |
| vc-tenor | 875 | cello, bass to tenor (mostly back) |
| vc-open | 477 | cello opening in tenor or treble, mostly back to bass |
| va-treble | 678 | viola, alto to treble (mostly back) |
| va-open | 199 | viola opening in treble |
| osq-real | 237 | OSQ staves that already change clef or open unusually, as they are |
| vn-plain | 398 | violins unchanged, for balance |

**Sources:**
- Treble-high cello staves are scarce (about 7% of OSQ's cello staves), so
  a cello staff may be drawn twice, in another hand with another stretch.
- Paris B never draws an unusual opening clef: it leaves the opening clef
  off, so the clef couldn't be seen.

**The drawing:** `copyist.draw(..., changes=True)`. It's off for dataS3's
sets, and with it off the output is the same as before.
- A change at a bar line is drawn after the bar line, mostly. Verovio puts
  it before.
- The key is written again after the new clef, in that clef's positions:
  Berlin 85%, Vma 80%, Paris 10%.
- Changes are drawn about full size.
- Each clef, not just the opening one, may be the copyist's own
  (`harvest_clefs.py`):
  - tenor is the hand's alto clef moved a space up;
  - the cut is cleaned of residue and thickened if hairline.
- `lmx2xml.add_stems` now applies a clef inside a bar from where it stands.
  This also redraws, with corrected stems, 16 of the 191 OpenScore staves
  that already change clef inside a bar, with or without `changes`. Their
  labels don't change, and staves with one clef draw as before.

**Checked by eye:** contact sheets of every kind, with each staff's label
written under it (clef, bar, first note after it).
- The clef stands where the label puts it, and the notes after it sit on the
  right lines.
- A restated key sits in the new clef's positions.
- Doubtful: some of Vma's own treble cuts are faint or cut in half, and a few
  carry a sharp from their source's key.

Rebuild (about 5 minutes, six processes, sandbox off to write the cache):

```sh
uv run experiments/synth/gen_clefs.py ~/.cache/manuscript-labeler/zeus/dataS4 S4-clef --n 4000 --jobs 6 --seed 48
modal volume put musvit-staves ~/.cache/manuscript-labeler/zeus/dataS4 /dataS4
```

`--plan-only` prints the plan and stops; `--limit N` draws only the first N
staves. Training names the list `/staves/dataS4/samples.S4-clef.txt`.

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
