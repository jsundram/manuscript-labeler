# Pairing with musvit-D5's readings (2026-11-04)

The pairing read every source with musvit-D4 (readings `D3S-h96`), and
with C4 too on the older sources. musvit-D5, released 2026-10-23, never
read them. **Read with D5 as well, the paired sources keep 7,237 → 7,976
staves (+739, 10%), and the added staves are about as often right as the
ones already kept.** That is 35 times what the last two pairing rules
gained (21).

## D5 alone, against D4

D5 was trained on the staves the pairing kept, so on those its reading can
repeat its label. Two tests that avoid that:

| | D4 kept | D5 kept | kept by either |
|---|--:|--:|--:|
| KHM 587 (G. 213), 246 staves | 161 | 171 | 183 |
| KHM 587, the 146 staves D5 never trained on: kept / right measures | 62 / 53 | 76 / 68 | |
| Dresden Mus.3403 (held out of every training set), 587 staves | 421 | 458 | 487 |

Right measures are scored against the editor's fixed pages
(`compare_readers.py`, as in [the pairing recheck](../2026-11-03-pairing-recheck/)).

## D5's staves added to every source

`experiments/zeus/add_reader.py` keeps every staff a source's pairing
already keeps and adds the ones D5's own pairing keeps, except:

- a staff D5 trained on (4): its reading can repeat its label, right or
  wrong, the reason the older sources keep only what D4 and C4 both keep;
- a staff whose bars another kept staff of the part already holds (57);
- Dresden, the readers' held-out test, labelled by D4's pairing alone.

It writes `results/autopair-<source>-plus-D5.json`, which the labeler
(pairing.py) now prefers. 739 staves added across 56 sources; most to
Op. 32 (111), M351 (75), MS 1292's score (65), RES 507-2 (45).

**Right?** On the editor's fixed pages, 21 of the 24 added staves have the
right measures (88%), against 216 of 234 (92%) for the staves already
kept: by source, KHM 587 17 of 19, KHM-621 1 of 2, MS 200 2 of 2, MS 1292
1 of 1.

## For training

The added staves' labels are the encoding's bars, not D5's reading, so
they are new labelled staves for the next reader. They are the staves a
reader already reads well enough to pair; the hardest ones stay out.
Dresden stays out of training as the held-out test.

## Cost

Modal L4, reading 10,796 staves: $0.72 from Modal's billing (`modal
billing report --for today -r h`, six apps): KHM 587 and Dresden first,
$0.04; the other 55 sources, four at a time in about an hour, $0.68. Mac (M1): pairing the 57 sources with D5,
39 minutes (measured); the two test pairings, about 15 minutes.
