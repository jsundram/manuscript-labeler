# manuscript-labeler

Label scanned music manuscripts page by page: staves, bar lines, bar numbers,
and confusing marks. Output is a JSON description of each source, for a
synoptic edition and for proofreading an engraving against its sources.

See [SPEC.md](SPEC.md) for the design, the file formats, what's been
learned, and the open questions.

## Run it

Needs [uv](https://docs.astral.sh/uv/) and poppler (`brew install poppler`).

```bash
uv run server.py ~/path/to/edition-repo
```

The edition repo holds the PDFs under `sources/`. The browser opens at
http://127.0.0.1:8048/. Pick a source and work through it page by page:

- Each page opens with proposed staves and bar lines (dashed orange = not
  yet touched). Fix them by dragging, or with the keys below.
- Set the page's kind, part and clef on the right. Part and clef carry over
  from the previous page.
- Bar numbers update as you go, and the left panel compares counted bars
  with `Op48-N/Structure.ily` when it exists.
- **Enter** marks the page reviewed and opens the next.

Labels save automatically next to the PDF: `<pdf>.labels.json` (the working
file) and `<pdf>.bars.json` (the flat export for the synoptic build). Every
save is atomic. A save is refused if the file changed since it was loaded
(e.g. in another tab). Backups go to `~/.cache/manuscript-labeler/backups`.

Main keys (press **?** in the app for all of them): hold **b** and click to
add a bar line (or double-click a staff; it snaps to the ink, and **a**
snaps a selected one), hold **s** / **m** and click to add
a staff / mark, **d** or **Del** delete, **arrows** nudge, **Tab** next bar
line (or staff, or mark, whichever is selected), **1–6** bar line kind,
**e** movement ends here, hold **t** / **g** + **↑ ↓** move the top /
bottom crop edge, **z** detail view with pitch names, **⌘Z**
undo, **, .** previous/next page. Re-detect is a toolbar button: it
re-runs detection on the page and keeps your edits.

## Files

- `server.py`: local web server (rendering, detection, saving).
- `labels.py`: the labels schema, validation, bar numbering and bar export.
- `detect.py`: automatic staff and bar-line proposals (numpy + Pillow).
- `learn.py`: a bar-line filter learned from your reviewed pages (scikit-learn);
  the server trains it in the background and uses it once ready.
- `experiments/barlines/`: the bake-off that chose it (YOLO, D-FINE,
  Detectron2, MeasureDetector, rules, learned filter).
- `crops.py`: crop edges (how far each staff's bar images reach above and
  below it) learned from your reviewed crops, trained the same way;
  `experiments/crops/evaluate.py` scores it against the rules.
- `static/`: the editor (plain HTML/JS/SVG, no build step).
- `tools/score_barlines.py`: scores bar-line detection against your
  reviewed pages; run it before and after changing `detect.py`.
- `tools/tune_barlines.py`: re-fits the bar-line thresholds to every
  reviewed page in an edition (`uv run tools/tune_barlines.py <edition>`).
- `prototypes/`: scratch reading aids from the first hand transcription.

Tests: `uv run --with pytest --with numpy --with pillow --with scikit-learn pytest tests`

## License

MIT. See [LICENSE](LICENSE).
