# Staff tracing: three ideas from flattening the Harvard pages, none needed here yet

2026-10-28. Flattening the curl out of the Harvard photographs (Houghton fMS
Mus 6) needed a staff finder that follows staves into a steep corner curl
without slipping a line. Three of its ideas were tried in the labeler's
`find_staves`. On the 111 reviewed Op. 48 pages it already finds every staff
the editors kept, so there was little to win: two ideas did nothing, one
was mixed. `detect.py` is unchanged; `tools/score_staves.py` is new, to
measure the next change to staff finding.

## The three ideas

1. **The line above and below count against a staff.** A comb of five lines
   scores a fit one line off 4 of 5; counting the line above and below
   against it makes that 3 of 5. On the Harvard pages it was the main cure
   for staves traced a line off.
2. **Thick ink filtered out before scoring.** Beams and noteheads are
   thicker than a ruled line; an opening removes them so a beam lying along
   the staff doesn't look like its lines.
3. **Pay for changes of slope, not drift.** `_staff_scores` caps drift at
   0.4 staff space per strip. Charging for the change of slope instead
   (second-order dynamic programming, retracing each staff within a space
   of its first path) lets a staff follow a steady steep curl cheaply, while
   a jump of a line costs a lot.

## What was measured

`tools/score_staves.py`, on every reviewed music page: kept staves found
(top and bottom within half a space), a line off, missed; detected staves
no kept staff explains (extra); and how sharp the five lines come out in
the band straightened along the traced path (peaks over the paper between
them, 0-1; needs no truth). Bar-line counts too, from detection alone
(without the learned model the editor uses).

| | Kept staves found | Sharpness |
|---|--:|--:|
| Current | 864 / 864 | 0.220 |
| 1. Line above and below count against | 863 | 0.216 |
| 2. Thick ink filtered out | 863 | 0.222 |
| 3. Pay for changes of slope | 864 | 0.234 |
| All three | 864 | 0.232 |

- No version traces a staff a line off; the current one never did.
- The 42 extra staves are ruled staves the editors deleted (40 of them in
  `rejected_staves`), 34 with no bar lines: empty, or a title or text.
  None of the ideas is about those.
- Idea 3, staff by staff: sharper on 55% (more than 2%), less sharp on 25%;
  median +3%; worse on KHM 602 (median −1%), best on RES-507-16 and -18
  (+12%). Bar lines: 2,801 found, 152 false, 2,668 missed, against 2,768,
  145, 2,701 now.

## Why so little

These scans and photos curl far less than the Harvard pages. The Harvard
staff finder's ideas earned their keep on pages with a steep curl into the
gutter and beams along the lines; here the current tracer already sits on
the lines.

## What followed

- `detect.py` unchanged. Idea 3 is the one to retry, on pages that curl.
- `tools/score_staves.py` and its tests kept, as the baseline for that.
- The Harvard flattening went to the quartet-data repo as
  `manuscripts/_RAW/harvard_flatten.py` (all 253 pages: worst staff per page
  16.2 px → 2.0 px median, 37.8 → 3.2 for the worst 10%), for its own
  pipeline, not the labeler's.

## Cost

Mac mini (M1) CPU, about 15 minutes for the labeler runs (estimated). The
Harvard flattening runs, about an hour, belong to the quartet-data work.
