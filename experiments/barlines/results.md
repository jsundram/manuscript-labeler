# Bar-line bake-off: results (2026-10-05)

43 test lines, 287 bar lines (21 lines from KHM 602, 22 from KHM 603),
same split for every method; thresholds chosen on validation lines. See
README.md for the design.

## On the straightened test lines

Every method gets the same input: the line, its staff known (the editor's).

| method | found | false | missed | errors | flagged by width hints | silent errors | train | per line |
|---|---|---|---|---|---|---|---|---|
| Detectron2 Faster R-CNN R50-FPN | 280 | 5 | 7 | 12 | 3 | 9 | 45 min (GPU) | 1066 ms (GPU) |
| YOLO11n | 285 | 18 | 2 | 20 | 8 | 12 | 119 min (GPU)\*\* | 87 ms (GPU) |
| D-FINE small | 283 | 12 | 4 | 16 | 2 | 14 | 83 min (CPU\*) | 593 ms (CPU\*) |
| learned filter + bar widths (two passes) | 280 | 13 | 7 | 20 | 5 | 15 | 22 s | 70 ms |
| learned filter | 277 | 8 | 10 | 18 | 3 | 15 | 4 s | 29 ms |
| classical (hand-tuned rules) | 260 | 3 | 27 | 30 | 7 | 23 | none | 12 ms |
| MeasureDetector, pretrained, off the shelf | 128 | 408 | 159 | 567 | 435 | 132 | can't retrain | 5834 ms (CPU) |

- **errors** = false + missed: each false one is a delete, each missed one
  a hold-b-click (which snaps).
- **flagged by width hints**: of those errors, how many the labeler's
  bar-width hints point at (a missed bar line inside a bar over 1.8x the
  line's typical width or in unbarred music at the line's end; a false
  one at the edge of a bar under 0.4x). **silent errors** are the rest:
  nothing points at them, so they cost careful checking.

\* D-FINE's backward pass fails on the Mac GPU (MPS), so it trained and ran
on the CPU. \*\* YOLO hit the 2-hour job limit at epoch 85 (best at epoch
71); its time is the limit, not convergence.

## End to end, as the labeler runs

Whole pages through detect.py: the staves, edges and music start are
detected, not the editor's; only the test lines are scored (their labels
hidden from training).

| method | found | false | missed | errors | flagged by width hints | silent errors | train | per line |
|---|---|---|---|---|---|---|---|---|
| learned filter + bar widths (learn.py, as shipped) | 271 | 10 | 16 | 26 | 9 | 17 | 48 s | 221 ms |
| learned filter, one pass (learn.py before bar widths) | 270 | 11 | 17 | 28 | 12 | 16 | 53 s | 189 ms |
| hand-tuned rules | 254 | 8 | 33 | 41 | 6 | 35 | none | 445 ms |

Per-line times here include finding the staves on the whole page.
Detection's own errors (staff edges, music start) cost both methods about
10 errors over the straightened lines; the learned filter still removes a
third of the errors, and with the width hints leaves about half as many
silent ones (17 vs 35). Its second pass (bar widths) saves 2 errors end
to end; the misses here are mostly detection's.

## Cross-validation

5 folds over all 213 lines (1404 bar lines), every line tested once, for
the cheap methods:

| method | found | false | missed | errors | recall | precision |
|---|---|---|---|---|---|---|
| learned filter + bar widths | 1344 | 26 | 60 | 86 | 95.8% ± 1.3% | 98.1% ± 1.2% |
| learned filter | 1333 | 27 | 71 | 98 | 95.0% ± 0.6% | 98.0% ± 0.8% |
| classical | 1242 | 16 | 162 | 178 | 88.5% ± 2.9% | 98.7% ± 0.6% |

## Do they make the same mistakes? Voting

Mostly not (`ensemble.py`, the saved test-line results; MeasureDetector
left out). Of the 287 bar lines, all six methods below find 256; of the 31
any method misses, 18 are missed by only one method and 2 by all six. Of
35 false bar lines (merged across methods within the tolerance), 23 come
from one method only. The two learned filters share the most (7 of their 10
misses; they share a first pass, so their votes aren't independent); the
deep detectors share 2.

A vote pools the methods' bar lines, merges those within the tolerance and
keeps those most methods propose (a majority, fixed in advance):

| vote | found | false | missed | errors | per line (sum) |
|---|---|---|---|---|---|
| 2 of 3: YOLO11n, learned + widths, classical | 282 | 3 | 5 | 8 | ~170 ms |
| 2 of 3: D-FINE, YOLO11n, learned + widths | 285 | 6 | 2 | 8 | ~750 ms |
| 2 of 3: Detectron2, D-FINE, YOLO11n | 285 | 6 | 2 | 8 | ~1750 ms |
| 2 of 3: Detectron2, YOLO11n, learned + widths | 282 | 5 | 5 | 10 | ~1220 ms |
| 2 of 3: YOLO11n, both learned filters | 280 | 5 | 7 | 12 | ~185 ms |
| 3 of 5: all but Detectron2 | 283 | 2 | 4 | 6 | ~790 ms |
| 4 of 6: all six | 279 | 1 | 8 | 9 | ~1860 ms |
| best single (Detectron2) | 280 | 5 | 7 | 12 | 1066 ms |

Votes of unlike methods (a deep detector and the candidate filter) cut
errors by a third to a half against the best single method. Caveats: one
split, several groupings tried (choosing the best is hindsight), and a few
errors either way is noise; the deep detectors are too slow to train to
cross-validate here. Not in the labeler: it would mean running YOLO
(PyTorch, AGPL-3.0) in the server.

## Reading it

- Every trained method beats the hand-tuned rules, mainly by missing far
  fewer bar lines.
- The top methods on the lines are within a handful of errors of each
  other; the order among them isn't reliable from one split. Under
  cross-validation, giving the learned filter bar widths (a second pass
  that sees the bars each candidate would make) cuts its errors by 12% (on the one test split it's
  within noise: 20 vs 18).
- The width hints catch few of the best methods' remaining errors (2-4 of
  12-18): what's left is mostly bars of ordinary width. They matter more
  end to end (9-12 of 26-28), where detection's misses leave wider bars;
  the second pass already uses widths, so it leaves the hints less to
  catch.
- Cost differs far more than accuracy: the learned filter trains in
  seconds on the editor's labels and needs only scikit-learn; Detectron2
  needs a source build on macOS and 330 MB of weights; D-FINE is stuck on
  the CPU here; YOLO is AGPL-3.0.
- MeasureDetector's 2019 models don't transfer to this hand, and can't be
  retrained on Apple silicon.
- Not measured: a new copyist. Both quartets are in one hand; the Paris
  copies need a few reviewed pages before these numbers carry over.
