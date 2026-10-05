# Bar-line bake-off: results (2026-10-05)

43 test lines, 287 bar lines (21 lines from KHM 602, 22 from KHM 603),
same split for every method; thresholds chosen on validation lines. See
README.md for the design.

| method | found | false | missed | recall | precision | F1 | edits per 100 bar lines | train | per line |
|---|---|---|---|---|---|---|---|---|---|
| Detectron2 Faster R-CNN R50-FPN | 280 | 5 | 7 | 97.6% | 98.2% | 0.979 | 4.2 | 45 min (GPU) | 1066 ms (GPU) |
| D-FINE small | 283 | 12 | 4 | 98.6% | 95.9% | 0.973 | 5.6 | 83 min (CPU*) | 593 ms (CPU*) |
| learned filter (gradient boosting on detect.py's candidates) | 277 | 8 | 10 | 96.5% | 97.2% | 0.969 | 6.3 | 15 s | 117 ms |
| YOLO11n | 285 | 18 | 2 | 99.3% | 94.1% | 0.966 | 7.0 | 119 min (GPU)** | 87 ms (GPU) |
| classical (detect.py today) | 260 | 3 | 27 | 90.6% | 98.9% | 0.945 | 10.5 | none | 12 ms |
| MeasureDetector, pretrained, off the shelf | 128 | 408 | 159 | 44.6% | 23.9% | 0.311 | 198 | none (can't retrain) | 5834 ms (CPU) |

"Edits per 100 bar lines" = (false + missed) / 287 × 100: each false one
is a delete, each missed one a hold-b-click (which snaps).

\* D-FINE's backward pass fails on the Mac GPU (MPS), so it trained and ran
on the CPU; on a working GPU it would be several times faster.
\*\* YOLO hit the 2-hour job limit at epoch 85 (best at epoch 71, still
creeping up); its time is the limit, not convergence.

Cross-validation (5 folds over all 213 lines, every line tested once) for
the two cheap methods:

| method | found | false | missed | recall | precision |
|---|---|---|---|---|---|
| learned filter | 1333 | 27 | 71 | 95.0% ± 0.6% | 98.0% ± 0.8% |
| classical | 1242 | 16 | 162 | 88.5% ± 2.9% | 98.7% ± 0.6% |

## Reading it

- Every trained method beats today's detector, mainly by missing far fewer
  bar lines (27 missed → 2-10), at the cost of a few more false ones.
- The top four are within a handful of errors of each other on 287 bar
  lines: the order among them isn't reliable from one split. Separating
  them would need cross-validation of the deep models (hours each) or more
  labelled data.
- They differ much more in cost. The learned filter trains in 15 seconds
  on the editor's own labels, runs in a tenth of a second per line, needs
  only scikit-learn, and its candidates reach 284 of 287 bar lines (the
  ceiling for any filter on them). Detectron2 needs a source build on
  macOS, 330 MB of weights and about a second per line; D-FINE needs the
  CPU here; YOLO is AGPL-3.0, awkward for an MIT tool.
- MeasureDetector's 2019 models don't transfer to this hand: boxes merge
  bars, split them into slivers, or overlap; and it can't be retrained on
  Apple silicon (TensorFlow 1.13).
- What none of this measures: a new copyist. Both quartets are in one
  hand; the Paris copies' thin grey bar lines are the real unknown, and
  need a few reviewed pages before any of these numbers carry over.
