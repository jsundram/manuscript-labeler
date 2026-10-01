# CLAUDE.md

Start with `SPEC.md`: it is the spec and the record of what's been learned.

- Python goes through `uv` (`uv run`, inline PEP 723 dependencies). Never
  `pip install`.
- Front end: plain HTML/JS/SVG, no build step.
- Never let a UI change endanger saved labels: labels are data files, written
  atomically, with a `schema` version and forward migrations.
- First test data: `~/Dropbox/Code/boccherini-opus-48/sources/G226/D-B_KHM-602.pdf`
  (17 pages, parts; page map in SPEC.md).
