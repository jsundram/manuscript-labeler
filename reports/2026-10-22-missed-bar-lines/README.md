# Bar lines the reading missed: +305 bars, and a faster re-pair

2026-10-22. Where the reader read two bars as one measure ("two") and
detection found the bar line between them, the staff now pairs, and so
does the staff beside it. The sets gain 43 staves and 305 bars, fewer than
hoped: on most such staves detection finds fewer bar lines than the
reading, not more. A full re-pair now takes about 4 minutes, not 45.

| set | staves before | bars before | staves after | bars after |
|---|--:|--:|--:|--:|
| dataM5 | 4,344 | 25,053 | 4,371 | 25,215 |
| dataW4 | 1,190 | 8,179 | 1,206 | 8,322 |
| dataP4, dataG213-4 | 456 | 2,587 | 456 | 2,587 |
| **all** | **5,990** | **35,819** | **6,033** | **36,124** |

The sets are rebuilt in place (no new names); "before" is the state after
[Bars that cross a line](../2026-10-22-split-bars/).

## Why

At 465 of the paired manuscripts' 9,914 line breaks a staff's end measure
was paired with two bars (the line-break table in
[Bars that cross a line](../2026-10-22-split-bars/)). The staff itself is
put out ("two at"), and with --neighbours so is the staff beside it, in
case the reading dropped a bar there and the neighbour took it.

## The rule

autopair.py: on a staff where detection found a bar box for every bar the
reading's measures hold (its measures, and one more for each measure
paired with two bars), each such measure is a bar line the reading missed.
- The staff isn't put out for it, nor is the staff beside it.
- It keeps the check every paired measure gets (no further than UNLIKE
  from its two bars).
- It is named ("irregular": "a bar line the reading missed"), and the box
  marked ("two"); dataset.py labels each of its bars (staff_boxes; one
  of LABELLED, which Try pairing uses too).
- Not with --musicxml: G. 213's merge takes a twin copy's pairing for a
  staff put out, one-bar measures only, and its dataset takes only those;
  with the rule 4 of its staves left the set.

## What it found

- 66 staves newly kept (530 bars), 62 labellable; 43 into the sets
  (305 bars). No staff kept before was lost or changed.
- Checked by eye: MS-1292 p32-5 holds II 43 and 44 in one stretch, the
  bar line between them faint (the reader missed it, detection found it),
  labelled as four bars that match; KHM 621 p10-2, put out before beside
  a neighbour's two-bar measure, now in, its 11 bars matching the 11 drawn.
- Why so few: of the staves still out with a two-bar measure whose counts
  are recorded, detection mostly finds 3 to 5 fewer bar boxes than the
  reading's measures (and two-bar measures) need. There, detection
  misses bar lines too, or the two-bar measure is the alignment absorbing
  a slip elsewhere; neither says which staff holds the bar. Better bar-line
  detection on these hands may be the larger lever.

Tests: tests/test_split_bars.py (test_a_bar_line_the_reading_missed).

## Re-pairing faster

- **The parallel pairer** (experiments/zeus/parallel_pair.py): autopair.py
  on every paired source with the options it was first paired with,
  `cores - 2` at once (pairing is CPU work, one process each), then the
  merges (both.py, G. 213's merge.py). It replaces the per-group recipes
  run one at a time.
- **numba** compiles the alignment's edit distance (autopair._unlike),
  each measure's tokens numbered once (ids). The same result on 20,000
  random pairs; 69 times as fast as align calls it (0.015 s against
  1.04 s); about 5 s to compile once, 0.15 s to load after.
- A full re-pair, every result the same file for file: 45 min one at a
  time; 8.3 min six at a time with the encodings uncached; 5.5 min
  cached (philhar.encoding, the commit before); **3.6 min** with numba.
  Try pairing answers in 0.8 s.
- What's left in a run: cutting each staff's image to look up its cached
  reading (6 s of a source's 25 s before numba), and imports.

## Not done

- The staves where detection's bar lines disagree with the reading
  (above).
- Caching the staff crops' hashes, for the next minute of a re-pair.

## Cost

Mac (M1) CPU: re-pairs about 4 to 6 min each, five times; the sets about
8 min, twice; analysis and checking by eye about 1 h. No Modal.
