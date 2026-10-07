# Bar-line bake-off: results

Three rounds, newest first. 2026-10-07 teaches the line detector where
staves start and end, and tries MUSCIMA++ pretraining; 2026-10-06
adds a second source in two hands; 2026-10-05 is KHM 602/603 alone. Per-model detail,
training curves and checkpoints: the model cards (static/models/, served
by the labeler at /static/models/; written by cards.py). See README.md
for the design.

## Staff ends and music starts, as detector classes (2026-10-07)

The corpus rebuilt with corpus.py --paper (each staff cut straightened
across the paper's whole width, as the labeler's cached predictions are,
with the editor's left end, right end and music start recorded) and
--test-source F-Pn_Vma-ms-1067-1 (all of it held out, unseen by
training): 250 training lines from KHM 602/603 and RES 507 (14), 1724 bar
lines; 135 test lines, 807 bar lines (63 lines of familiar hands, 431 bar
lines; 72 lines of Vma ms 1067 (1), 376). tiles.py adds two classes beside
"barline": "start", from the staff's left end to the music start (the
clef, key and time), and "end", a staff space wide around the staff's
right end; a box only where the tile holds all of it. YOLO26n, 50
epochs, mirroring off (it would turn an end into a start).

**Bar lines**: YOLO26n made 13 errors on the familiar hands and 21 on
Vma ms 1067 (1), where it made 16 and 27 before the new classes. Not like
for like: the earlier lines were cut from staff end to staff end, which
cut some bar lines at a staff's end in half (about 8 of the 27), and the
paper-wide lines add margins to err in. No sign the new classes cost bar
lines.

**The staff's ends and music start** (landmarks.py): the model's most
confident "start" box gives the left end (its left edge) and music start
(its right edge), its "end" box the right end (its centre); against
detect.py as the labeler runs it (the editor's page corners, the music
start hint from the previous page, the learned filter, and the vote with
the cached YOLO11n and YOLO26n, both of which move where a staff's right
end is trimmed). Errors from the editor's, on the lines where both
answer; share within 1 staff space / over 3:

| | familiar: labeler | familiar: model | Vma: labeler | Vma: model |
|---|---|---|---|---|
| left end | 71% / 21% | 94% / 2% | 81% / 13% | 90% / 0% |
| music start | 44% / 37% | 79% / 10% | 81% / 17% | 84% / 3% |
| right end | 56% / 22% | 97% / 0% | 79% / 3% | 99% / 0% |

The model found no "start" or "end" on 2 of the 72 Vma lines. The
labeler's numbers are flattered three ways: the learned filter learns
from every reviewed page, these test pages included; the cached YOLOs
were trained on an earlier split, which may hold some of these familiar
test lines; and the editor's labels start from the labeler's own
detection, so a start or end accepted as it was is the labeler's answer
(the music start is recorded wherever it lies right of the left end,
whether set or accepted; on Vma the labeler's median error is 0). The
right end, which the editor edits most, is nearly solved by the model,
most of all on the familiar hands.

Mosaics (on in training) can clip a start or end box at a seam, which
tiles.py otherwise avoids; turning them off for these classes is a
next try.

### MUSCIMA++ pretraining: no gain (muscima_corpus.py)

MUSCIMA++ v2.0 (CC BY-NC-SA 4.0): 140 pages of the CVC-MUSCIMA set, 20
pieces each rewritten by 50 musicians on printed staff paper, scanned to
black and white. Converted to the same lines (883 lines, 4746 bar lines
after dropping each system's opening line, which the editor's labels
don't count; 839 clef-key-time regions), drawn as grey ink on grey paper
with a little blur and noise. YOLO26n trained 10 epochs on it (77 min;
mAP50 0.98 on its own validation tiles), then 50 epochs on ours, against
the same 50 from YOLO's COCO weights:

| | familiar hands | Vma ms 1067 (1) |
|---|---|---|
| bar line errors, from COCO | 13 (5 false, 8 missed) | 21 (3, 18) |
| bar line errors, from MUSCIMA++ | 8 (2, 6) | 30 (2, 28) |

The staff's ends and music start came out about the same (within 1
staff space: 92/85/97% familiar, 87/89/97% Vma), with no "end" on 6 Vma
lines. Better on the hands it trained on, worse on the unseen one (which
pretraining was meant to help), from one run each: not worth a
non-commercial dataset in the training data.

## Three hands (2026-10-06)

The corpus rebuilt from every reviewed page: 313 lines, 2155 bar lines.
KHM 602/603 (one copyist, 213 lines) and F-Po RES 507 (14) (Op. 48 No.
3), whose Violin I and Cello are one paper and hand ("Paris A", 46
lines) and Violin II and Viola another ("Paris B", 54 lines). Split by
line as before (seed 1, stratified by source): 63 test lines, 431 bar
lines (287 KHM, 68 Paris A, 76 Paris B). Every model retrained on the
training lines.

### Errors on the test lines (false + missed)

| method | KHM | Paris A | Paris B | all | per line |
|---|---|---|---|---|---|
| Detectron2 Faster R-CNN R50-FPN | 7 | 1 | 3 | 11 | 1021 ms |
| YOLO11n (Ultralytics, 50 epochs) | 10 | 1 | 4 | 15 | 53 ms |
| YOLO26n (Ultralytics, 50 epochs) | 12 | 2 | 2 | 16 | 50 ms |
| learned filter + bar widths, ink relative to the paper | 16 | 4 | 4 | 24 | 48 ms |
| learned filter + bar widths, ink cutoff 120 | 12 | 6 | 16 | 34 | 137 ms |
| YOLO26n on MLX (yolo-mlx, 25 epochs) | 23 | 1 | 11 | 35 | 42 ms |
| D-FINE small (40 epochs, kept epoch 8) | 18 | 10 | 7 | 35 | 206 ms |
| hand-tuned rules | 30 | 22 | 51 | 103 | 17 ms |
| learned filter, end to end (learn.py on whole pages) | 27 | 10 | 4 | 41 | 176 ms |

- **The faint hand.** Paris B writes bar lines in fainter ink: with a
  fixed ink cutoff of 120, a third of them never became candidates, so
  the learned filter couldn't find them whatever it learned (16 of its
  34 errors). Judging ink relative to each staff's paper (66 levels
  darker; detect.PAPER) brings 98% of them in. Under 5-fold
  cross-validation (learned filter + widths): RES 507 (14) 162 -> 45
  errors, KHM 77 -> 89; all 239 -> 134. Now in the labeler.
- **A new hand needs a few pages** (crosshand.py, ink relative to the
  paper, errors per 100 bar lines, KHM plus k pages of the new hand,
  tested on its other pages): Paris A 4.3 with none of its own pages
  (it reads like KHM); Paris B 32.9, 18.2, 15.7, 10.6 with 0, 1, 2, 4.
  Adding the other Paris hand doesn't help (Paris A 4.3 -> 7.5).
- **Trained on KHM alone**, the detectors carry over unevenly: YOLO11n
  9.4 / 19.5 errors per 100 on Paris A / B, Detectron2 41 / 57 at its
  KHM threshold (its confidences fall on unfamiliar ink).
- **YOLO26 is no better than YOLO11** here (16 against 15: noise).
- **yolo-mlx** trained more slowly than Ultralytics on this Mac (about 4
  minutes an epoch against 83 s; its batches are prepared on one CPU
  thread, the GPU 13-43% busy, other work running) and can't resume, so
  ran 25 epochs; twice YOLO26n's errors, mostly false bar lines.
- **D-FINE** trains on the Mac's GPU with dfine_patch.py (transformers'
  D-FINE uses F.linear with a 1-D weight, whose backward fails on MPS:
  pytorch/pytorch#188891); its validation errors were 4-8 from epoch 5
  on, its test errors higher, mostly missed.

### Voting

ensemble.py on the same test lines: proposals within the tolerance
merged, kept if a majority of the methods propose them. All seven agree
on 322 of 431 bar lines; of the 109 any of them misses, 85 are missed by
one method only (and 2 by all seven); 29 of 41 false bar lines come from
one method only. The YOLOs and Detectron2 miss the same few bar lines;
the learned filter's mistakes are its own.

| vote (majority) | errors | per line (sum) |
|---|---|---|
| 2 of 3: YOLO26n, YOLO11n, learned filter | 9 | ~150 ms |
| 2 of 3: Detectron2, YOLO26n, learned filter | 10 | ~1.1 s |
| 2 of 3: Detectron2, YOLO26n, YOLO11n | 10 | ~1.1 s |
| 4 of all 7 | 11 | ~1.5 s |
| 2 of 3: YOLO26n, learned filter, hand-tuned rules | 14 | ~115 ms |
| best single (Detectron2) | 11 | 1021 ms |

One split, several groupings tried (choosing the best is hindsight), and
a couple of errors either way is noise. The learned filter here is the
straightened-lines run; in the labeler it also inherits staff detection's
errors.

### An unseen copy: F-Pn Vma ms 1067 (1)

A later copy (1810-40), photographed rather than scanned, in a new hand:
its reviewed pages (Violin I pp. 3-6, Violin II p. 9, Viola p. 15, Cello
p. 21; 72 lines, 376 bar lines), scored with the models trained on the
three-hand corpus above, none of which saw it. Errors (false + missed):

| method | Violin I | Violin II | Viola | Cello | all | per line |
|---|---|---|---|---|---|---|
| D-FINE small | 15 | 1 | 3 | 5 | 24 | 187 ms |
| YOLO26n | 14 | 1 | 1 | 11 | 27 | 70 ms |
| YOLO11n | 16 | 2 | 4 | 10 | 32 | 139 ms |
| YOLO26n on MLX | 19 | 4 | 7 | 3 | 33 | 46 ms |
| Detectron2 | 64 | 35 | 3 | 19 | 121 | 912 ms |
| learned filter + bar widths | 49 | 47 | 38 | 4 | 138 | 44 ms |
| learned filter, end to end | 52 | 56 | 31 | 11 | 150 | 43 ms |
| hand-tuned rules | 88 | 66 | 53 | 4 | 211 | 10 ms |
| vote, 2 of 3: YOLO26n, YOLO11n, learned filter | | | | | 17 | |

The detectors carry to a new copy (6-9 per 100 bar lines); the learned
filter doesn't (its candidates and measurements are tied to the hands it
learned). Detectron2 goes quiet again (all its errors are misses). Of the
17 bar lines most detectors missed, about 8 sit at the very end of the
test crop (cut in half: a test-set artifact; the labeler searches a space
past the staff's end), about 5 are this copyist's repeat signs (one
slashed stroke with dots, unlike any training hand), one a stray bar
line on a clef.

### The vote end to end (e2e_vote.py)

As the labeler would run it: staves detected on whole pages, the learned
filter (learn.py) on them, and the detectors on those staves cut out
across the paper's width (corpus.paper_band, with the editor's corners
where set: the crops tools/predict_barlines.py caches), their bar lines
kept from each staff's left end to a space past its right end (the
labeler's rule: detections.py). The test lines' labels are
hidden from the learned filter's training (on the three-hand test, the
other staves of their pages are not: that corpus is split by line, so
the filter's numbers there are a little flattering; on Vma ms 1067 (1)
every reviewed line is a test line). The detectors are the three-hand
corpus's. Errors:

| method | three-hand test lines (431) | Vma ms 1067 (1) (376) |
|---|---|---|
| learned filter alone (the labeler today) | 41 | 150 |
| YOLO11n | 22 | 51 |
| YOLO26n | 28 | 35 |
| D-FINE | 49 | 44 |
| vote: learned filter, YOLO26n, YOLO11n | 21 | 37 |
| vote: YOLO26n, YOLO11n, D-FINE | 24 | 39 |
| vote: learned filter, YOLO26n, D-FINE | 32 | 34 |

Anything with a YOLO in it halves the labeler's errors on familiar hands
and cuts them by about three-quarters on a new copy. Which is best
varies by test set and is within noise; YOLO26n is the steadiest single
detector, the vote of the learned filter and both YOLOs the best on
familiar hands. Detected staves cost the detectors several errors
against the editor's staves (YOLO26n 16 -> 28 on the three-hand test).

### Staves by segmentation: didn't learn (staves_seg.py)

Could a segmentation model find the staves, their music start and crop
better than detect.py's staff tracing and rules? Three outlines per
counted staff from the editor's labels (staff, clef-key-time region,
crop), each following the staff's bend, on whole pages (imgsz 1280),
split by page: 33 training, 3 validation, 13 test (all of Vma ms 1067
(1) and 2 pages of each other source).

- YOLO26n-seg: losses went NaN within an epoch or two, with mosaics
  (pages cut in quarters clip long staff outlines to slivers) and with
  mixed precision on the Mac's GPU. Without both it trained, but its
  validation recall stayed near 0.2 (box mAP50 about 0.1); early
  stopping ended it at epoch 71, and at confidence 0.25 it found no
  staves on the test pages.
- YOLO11n-seg (mosaics, one mask per outline): validation recall rose
  to about 0.5 by epoch 6, then collapsed to 0 by epoch 11; stopped.

Likely causes: staves are extreme shapes for these models (about 30
times wider than tall), the staff and crop outlines are nearly the same
box, and 33 pages is little for a page-level model.

Today's detection, on the same 13 test pages against the editor's
staves, sets the bar: it finds every staff (108 of 108, 5 false); what
is weak is two points on each:

| | median (staff spaces) | within 1 space | over 3 spaces |
|---|---|---|---|
| left end | 0.0 | 82% | 13% |
| right end | 1.6 | 37% | 32% |
| music start | 0.5 | 67% | 21% |
| crop above | 0.2 | 89% | 5% |
| crop below | 0.2 | 86% | 2% |

So the next attempt targets those points: "music start" and "staff end"
as classes of the line detector, on the same straightened lines.

### oemer: not usable (oemer_eval.py)

oemer (MIT; an end-to-end OMR system whose U-Nets saw handwritten music)
as a zero-shot staff finder, on the same test pages: about 5 minutes a
page on the CPU; it uses numpy aliases removed in 1.24 and its old
dependency set can't be installed on Python 3.11; with the aliases
restored, its staff extraction crashed on every page ("invalid index to
scalar variable"). Not a building block.

## Round 1: KHM 602/603 (2026-10-05)

43 test lines, 287 bar lines (21 lines from KHM 602, 22 from KHM 603),
same split for every method; thresholds chosen on validation lines.

### On the straightened test lines

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

### End to end, as the labeler runs

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

### Cross-validation

5 folds over all 213 lines (1404 bar lines), every line tested once, for
the cheap methods:

| method | found | false | missed | errors | recall | precision |
|---|---|---|---|---|---|---|
| learned filter + bar widths | 1344 | 26 | 60 | 86 | 95.8% ± 1.3% | 98.1% ± 1.2% |
| learned filter | 1333 | 27 | 71 | 98 | 95.0% ± 0.6% | 98.0% ± 0.8% |
| classical | 1242 | 16 | 162 | 178 | 88.5% ± 2.9% | 98.7% ± 0.6% |

### Do they make the same mistakes? Voting

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

### Reading it

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
