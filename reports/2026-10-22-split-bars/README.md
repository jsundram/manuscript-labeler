# Bars that cross a line: +1,917 bars

2026-10-22. A bar that a copyist broke across two lines kept both lines
out of the training sets. Cutting the score's bar where the two lines'
readings fit its halves, and giving each line its part, adds 334 staves
and 1,917 bars (+6%); 30 of the staves (169 bars) by a re-cut of the
alignment, below.

| set | staves before | bars before | staves after | bars after |
|---|--:|--:|--:|--:|
| dataM4 → dataM5 | 4,134 | 23,900 | 4,344 | 25,053 |
| dataW3 → dataW4 | 1,066 | 7,415 | 1,190 | 8,179 |
| dataP3 → dataP4 | 21 | 147 | 21 | 147 |
| dataG213-3 → dataG213-4 | 435 | 2,440 | 435 | 2,440 |
| **all** | **5,656** | **33,902** | **5,990** | **35,819** |

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

## The red staves: a re-cut, and why it recovers little

Of the 3,691 unpaired staves, about 700 (4,100 bars) were put out by one
boundary rule alone, most beside a line break where the alignment paired
one staff's end measure with a whole bar and took the other staff's
measure there as extra. The alignment can't split such a bar when a
piece's reading is as long as the bar (the documented case: a half read
in doubled values). autopair.py now re-cuts it (recut): the two become a
split where break_cut fits, the measure paired whole reads more like its
piece than like the bar, and the extra measure's staff pairs something
else (not a heading or a scrap of detection).

- **First try, without the second condition:** 233 staves newly kept,
  but three of four checked by eye were wrong. Op. 32 p139-0 ends with
  all of III 3 and a bar line, labelled with its first quarter; MS-1292
  p108-2 ends with a bar line and blank staff, labelled with an eighth of
  II 14. In every one the measure paired whole read as the whole bar
  (unlike 0.0 to 0.08): the alignment was right, and the extra measure
  was something else (a second ending, a heading).
- **With it:** 38 staves kept, 30 into the sets (169 bars), none lost or
  changed. Checked by eye: KHM 622 p5-4 (ends with the half-note chord
  that opens I 45), Mus.ms. 2861 p34-7 (opens with I 21's last two
  quarters), Op. 22/6 Vmbr153 viola p36-2 (ends with II 14's first
  quarter). Tests: tests/test_split_bars.py.

So most of the red staves are not bars that cross a line. What they are
(second endings, headings read as measures, measures the reader merged)
is the next question; detection's bar lines may tell a staff that ends
with a bar line from one whose bar runs on.

## Re-pairing faster

A full re-pair took about 45 minutes. Profiled on one source (25 s): the
alignment's edit distance (unlike, pure Python) about half, cutting the
staves' images to look up their cached readings 6 s, imports 4 s; the
encoding (LilyPond, once per part, quartet and movement) 11 s of 43 on a
first run.
- **The encoding is cached** (philhar.encoding, ~/.cache/manuscript-
  labeler/zeus/philhar/), keyed by a hash of Philhar's files for the
  quartet, philhar.py, the edition's events.py and facsimile.py, the part
  and movement, and LilyPond. The set builder uses it too. Results are
  the same, file for file.
- **Sources paired six at a time** on the Mac's cores: the whole re-pair
  in 8.3 min with an empty cache, 5.7 min with it.
- A faster pure-Python unlike gained only 23%; numba on it is the next
  step if needed.

## Not done

- The rest of the red staves (above).
- Multi-bar rests (about 40 staves on Op. 32 alone).
- Try pairing (the labeler) now counts a staff with split bars as one
  that would go into a training set.

## Cost

Mac (M1) CPU: the re-pair of all sources about 45 min each, three times,
then about 6 min each, five times; the sets about 7 to 20 min each, five
times; analysis and checking by eye about 2 h. No Modal: the readings
were cached.
