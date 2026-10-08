# Bar-line bake-off

Which bar-line finder saves the editor the most rework? Every method gets
the same input: one straightened staff line, its staff position known, from
the editor's reviewed pages of D-B KHM 602 and 603 (Op. 48 Nos. 1 and 2).
It returns bar lines along the line, scored against the editor's.

## Running it

Data, renders and model weights go outside the repo (the repo is in
Dropbox); pass any directory as `<corpus>`.

```bash
E=~/Dropbox/Code/boccherini-opus-48
C=/some/scratch/dir
uv run experiments/barlines/corpus.py $E $C        # lines + labels, train/test split
uv run experiments/barlines/tiles.py $C            # detector tiles (YOLO + COCO), val ids
uv run experiments/barlines/harness.py $C classical
uv run experiments/barlines/run_learned.py $C
uv run experiments/barlines/run_learned.py $C --widths   # second pass with bar widths
uv run experiments/barlines/run_labeler.py $C $E         # learn.py end to end on whole pages
uv run experiments/barlines/run_labeler.py $C $E --rules # the hand-tuned rules, end to end
uv run experiments/barlines/run_yolo.py $C
uv run experiments/barlines/run_dfine.py $C        # CPU (see below)
uv run --python 3.12 experiments/barlines/run_measuredetector.py $C $E   # weights: see its docstring
<venv-with-detectron2>/bin/python experiments/barlines/run_detectron2.py $C
uv run experiments/barlines/crossval.py $C         # 5-fold CV, classical vs learned
uv run experiments/barlines/harness.py $C table
uv run experiments/barlines/ensemble.py $C           # shared mistakes, majority vote
uv run experiments/barlines/ensemble.py $C yolo-yolo11n learned-gbm-widths classical   # a chosen few
```

## Design

- **Corpus** (`corpus.py`): every counted staff line with bar lines on the
  reviewed music pages, straightened along the editor's bend, cropped 3
  staff spaces above and below. Split by page, for good (from 2026-10-08):
  a page's side comes from a fixed hash of its source and number (`--test`
  of the pages), so no page is on both sides and a page stays where it is
  as more are reviewed, and models trained on different corpora can be
  compared on the same test pages; `test_pages.json` lists pages always
  held out (annotated to measure detection on unseen pages), and
  `--test-source` holds a whole copy out (a new hand). Validation (tiles.py)
  and cross-validation folds (crossval.py) are whole pages by the same kind
  of hash; what trains on whole pages (learn.py, in run_labeler.py and
  e2e_vote.py) leaves every test page out. A corpus is built into a new
  directory. (Results before 2026-10-08 used a per-line split, seed 1,
  stratified by source: lines of one page could be on both sides.)
- **Scoring** (`harness.py`): a prediction counts if within 0.6% of the page
  width of a bar line (the labeler's tolerance), matched one to one.
- **Detectors** see 640 px tiles of the lines at full resolution (bar lines
  are 2-4 px wide), boxes the staff's height and a staff space wide; 10% of
  the training lines are validation, for early stopping and for choosing
  each method's confidence threshold (never the test lines).
- **Times**: training wall time and processing time per line on this Mac
  (Apple silicon). YOLO and Detectron2 ran on the GPU (MPS); D-FINE on the
  CPU, because its backward pass fails on MPS ("mat2 must be a matrix");
  MeasureDetector (TensorFlow) on the CPU. Several jobs overlapped, so
  times are indicative.

## Results

See `results.md` (written from `harness.py table`).
