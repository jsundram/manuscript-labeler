# Pairing recheck (2026-11-03)

New pairing rules, found on Op. 48's answer key, kept 401 more staves on
the sources without labels. Were they right? The editor fixed 51 pages of
those sources in the labeler, and the pairing is scored against them.
**They hold: 92% of kept staves have the right measures, before and after,
with 31 more kept.** Two more rules came out of the pages the editor
flagged: a bar a repeat splits whose first part reads too long, and a bar
that runs on to the next line where the reader dropped its first part.

Page: [index.html](index.html), published as
https://claude.ai/artifact/PzY5JGMRQZ4JE2e5pauxSx (21 staves the rules
gained or lost, one question each). Built by `build.py` from `page.html`.

## What the editor's fixes can score

These sources have no Structure.ily, so the labeler numbers each page's bars
from 1: the fixes say where every bar line is, and its count (1, or 0 for
an upbeat or a bar's second part), and whether a staff runs on, but not
which bars. `score_fixed.py` compares each staff's number of measures with
the pairing's (its boxes, a run-on piece included). Where a bar splits
across a line break, the editor sometimes marks it on the next staff (a
0) and the pairing on this one (runs on), so the counts are not compared.

51 fixed pages, 333 staves the pairing read: G. 213's KHM 587 (41 pages,
every part), KHM-621 p7 and p10, Dresden Mus.3403-P-513 p53 and p71,
MS 202 p18, MS 200 p12, MS 1292 p34, Op. 32 p130, G208 p8, G209 p20.

## Results

| | Op. 48: kept / right / wrong | Fixed pages: kept / right measures / wrong |
|---|---|---|
| Before (1ea3e2f) | 974 / 968 / 6 | 203 / 187 / 16 |
| The rules of 2026-11-02/03 (heading cascade, ends across the break, pieces) | 1,018 / 1,012 / 6 | 232 / 213 / 19 |
| + a repeat's first part read whole, + run-on bars | 1,025 / 1,020 / 5 | 234 / 216 / 18 |

Across every paired source (no labels): the first rules kept 10,639 →
11,040 staves (426 gained, 25 lost, none kept by both with other bars);
the last two, 29 gained and 8 lost, and 19 kept staves gained the run-on
bar they start. Of the 8 lost, 2 are the run-on rule adding a box the
reading already had (the bar-box count then puts the staff out), 6 the
repeat rule letting the alignment take other paths.

**Partial bars.** The editor marked 54 staves running on (all in KHM 587).
Detection doesn't cut them short (53 end within 2% of the editor's end);
the pairing gives 40 their run-on bar. Of the other 14, the reader dropped
the piece or read it into the bar before. The run-on rule recovers it where
detection sees music past the last bar line and the next staff opens with a
short measure (p14-8, p15-2, p25-2); not where the reader reads that
measure whole (p15-3) or detection missed the last bar lines (p15-4, p15-8).
The rest wants the staff read bar box by bar box.

Kept with the wrong number of measures: 18, 15 of them KHM 587's dense
32nd-note movement I, where the reader also reads two bars as one (p14-2,
p14-5, p14-7: three bar lines, one or two measures read).

## Score pages: bar lines line up through a system

A prototype only (not in detect.py): keep a bar line seen at the same x on
at least 2 staves of a system, and give it to every staff. On the 5 fixed
score pages (48 staves): found 139 → 154 of 197, missed 58 → 43, false 14 →
6. Pooling weak strokes too, to rescue faint lines, did worse (notes on the
same beat line up across parts as well).

## Cost

Mac mini (M1, 16 GB), measured: the full re-pair three times (85, 40 and
28 minutes), Op. 48 four times (about 10 minutes each), detection on the
score pages (5 minutes). About 3.5 hours. No cloud.
