# Crop edges

Can a model choose each staff's crop (`above` / `below`, in staff spaces)
the way the editor does, better than `detect.crop_margins`' rule? Yes,
modestly; the labeler uses it (`crops.py`, which documents the method).

    uv run experiments/crops/evaluate.py <edition-repo> [--older A,B ...]

trains `crops.py`'s model leaving out one source at a time and scores
each side's edge against the editor's: within half a staff space, too
tight, too wide. `--older` (else the edition's `sources/labeler.json`)
names the sources whose crops predate the editor's current standard.

## Results (2026-10-09)

507 reviewed staves in six sources; older:
D-B_KHM-602, D-B_KHM-603, F-Po_RES-507-14, F-Pn_Vma-ms-1067-1. Within
half a space of the editor's edge (too tight, too wide):

| | today above | learned above | today below | learned below |
|---|---|---|---|---|
| D-B KHM 602 | 72% (10, 18) | 78% (15, 7) | 64% (20, 16) | 82% (13, 5) |
| D-B KHM 603 | 73% (14, 13) | 74% (23, 3) | 75% (8, 17) | 90% (5, 5) |
| F-Pn Vma ms 1067 (1) | 76% (6, 18) | 71% (16, 13) | 70% (18, 12) | 71% (17, 12) |
| F-Pn Vma ms 1067 (2) | 53% (7, 40) | 80% (3, 17) | 73% (13, 13) | 77% (10, 13) |
| F-Po RES 507 (14) | 62% (8, 30) | 70% (13, 17) | 57% (24, 19) | 61% (36, 3) |
| F-Po RES 507 (16) | 74% (0, 26) | 52% (10, 39) | 71% (19, 10) | 90% (0, 10) |
| all | 70% (9, 21) | 72% (16, 12) | 68% (17, 15) | 77% (16, 7) |
| test pages (newest) | 64% (3, 33) | 66% (7, 28) | 72% (16, 11) | 84% (5, 11) |

"Today" is crop_margins on the editor's staves. A third of the editor's
crops equal it exactly (accepted as proposed), which flatters it.

What was learned along the way:

- The editor's standard tightened: the newest pages leave out a
  movement's title, an empty ruled staff and a floating dynamic above
  the staff (it belongs to the staff above: dynamics are written under
  their staff); older crops accepted as proposed kept them. Training on
  the newest crops (3x) and only the older ones the editor changed
  beat every crop alike (newest above 57%) and changed ones only (59%).
- Erasing the ruled lines to tell blobs apart must spare strokes that
  cross them, or a stem's outer half looks like a floating mark.
- No simple rule fits: own ink's farthest reach plus a margin, fitted on
  older changed crops, got 43% of the newest top edges.
- The model's margin between its two best edges doesn't predict its
  mistakes (the least sure fifth was no likelier wrong), so it doesn't
  flag close calls.
- Still missed: mostly above the staff (titles, the staff above's
  dynamics), where only the newest 61 staves show the standard. The
  server retrains as pages are reviewed.
