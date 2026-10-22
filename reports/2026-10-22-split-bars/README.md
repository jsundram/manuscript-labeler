# Bars that cross a line: +1,748 bars

2026-10-22. A bar that a copyist broke across two lines kept both lines
out of the training sets. Cutting the score's bar where the two lines'
readings fit its halves, and giving each line its part, adds 304 staves
and 1,748 bars (+5%).

| set | staves before | bars before | staves after | bars after |
|---|--:|--:|--:|--:|
| dataM4 → dataM5 | 4,134 | 23,900 | 4,331 | 24,985 |
| dataW3 → dataW4 | 1,066 | 7,415 | 1,173 | 8,078 |
| dataP3 → dataP4 | 21 | 147 | 21 | 147 |
| dataG213-3 → dataG213-4 | 435 | 2,440 | 435 | 2,440 |
| **all** | **5,656** | **33,902** | **5,960** | **35,650** |

## What kept them out

The editor saw it in the labeler's pairing view: both lines either side
of a bar that crosses the break were red or blue.

- **Blue (paired, left out of the sets):** the alignment had paired the
  two half-measures with the one bar ("split"), but the set builder took
  only plain staves, every measure one bar: a label can't hold half a bar
  unless someone says where the bar is cut. 441 staves (2,308 bars) were
  out for that alone; 381 more for a bar a repeat splits or a multi-bar
  rest.
- **Red (unpaired):** where the reading made the half-bar into an extra
  measure, or merged it with the next bar, the boundary rules
  (--neighbours, --short-ends, --long-ends) put out both lines, since the
  bar numbers might be off by one. That is about 820 staves (4,700 bars),
  and is not addressed here.

## The fix

- **autopair.py (break_cut):** a bar split across a line break is cut at
  the onset in the score's bar whose two halves are least unlike the two
  measures the reader read either side of the break (the alignment's own
  measure; at most BREAK_FIT = 0.5 on average). A grace note goes with
  the note it leads into. A kept staff lists such halves ("halves"), and
  names any other measure that isn't one bar ("irregular": a multi-bar
  rest, a bar a repeat splits, one read as one measure, a split no cut
  fits).
- **dataset.py (staff_boxes):** such a staff is labelled with its part of
  each split bar, through the cut the labels already use for a bar a
  repeat splits (box_events). A bar a repeat splits is now taken too,
  where the reader read its halves as two measures, cut where the
  movement's pickup starts, as the labels' are. A staff is still left out
  for a multi-bar rest, a bar a repeat splits read as one measure, or a
  split no cut fits (dataset.labellable; Try pairing uses the same rule).
- The print's reading (dataP) has no onsets to cut at; G. 213's staves are
  cut from the MusicXML score another way (musicxml_pairs). Neither
  changes.

## Checked

By eye, on new staves against their labels:
- Mus.ms. 2861 p37-3 opens with the second half of bar I 9 (cut at 1/2):
  a grace, a dotted quarter with a sharp, an eighth, as written.
- MS-1292 p112-6 opens with the second half of II 54: eighth, rest,
  rest, eighth (a slur on), as written.
- Paris vn1 p16-3 ends with the first half of I 14: eighth, rest, a grace
  and eighth, rest.
- Op. 32 p37-6: bar IV 56, split by a repeat, is three eighths and a
  one-eighth upbeat, two measures either side of the repeat sign.

Review before committing found two faults in the first build (6,011
staves, 35,981 bars), both fixed and the sets rebuilt:
- A staff holding both a line-break half and a bar a repeat splits lost
  its cut, so the half was labelled as the whole bar. Paris RES-507-2
  p7-2 opened with all of II 4 where the staff has only its second half
  (four sixteenths, as written now). Op. 22 Paris vn1 p16-6, left out
  before for this, is now in (checked by eye).
- A bar a repeat splits that the reader read as one measure was labelled
  as the whole bar inside a staff, and as a half at a staff's end. About
  400 such staves are now left out: their label would lack the repeat
  bar line.
52 staves went, 1 came, 1 changed; dataset.py's labelling has tests now
(tests/test_split_bars.py).

Every label is also checked by dataset.py as before: read back as a
reading is, it must be the score's events bar for bar.

## Not done

- The red half: staves the boundary rules put out. Detection's bar lines
  could say which line holds the bar (a neighbour's end measure paired
  with two bars, where detection found a bar line between them, is a bar
  line the reader missed, not this staff's bar).
- Multi-bar rests (about 40 staves on Op. 32 alone).
- Try pairing (the labeler) now counts a staff with split bars as one
  that would go into a training set.

## Cost

Mac (M1) CPU: the re-pair of all sources about 45 min, the sets about
20 min, analysis about 30 min. No Modal: the readings were cached.
