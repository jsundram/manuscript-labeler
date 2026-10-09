# A language model on the pages

Step 3 of the plan: can Claude say what a page is and whose part it is,
and read the text the editor marks, well enough to propose them on a new
manuscript? A first measured test on the reviewed pages, before building
anything into the labeler.

    uv run experiments/llm/pages.py <edition-repo>                # kind and part, one page at a time
    uv run experiments/llm/marks.py <edition-repo> --mode blind   # each mark's text, transcribed
    uv run experiments/llm/marks.py <edition-repo> --mode known   # ... offered the other sources' texts

Claude Opus 5.5 at low effort, structured output, the API key from the
labeler's `.env` (`ML_API_KEY`). Answers are cached in `answers/`
(committed), keyed by the prompt and, for a mark, its box, and saved as
they come, so a rerun pays only for what's new or changed. The calls must
run outside Claude Code's sandbox (it blocks the macOS certificate check
the Python client uses).

"Known" offers the texts from the reviewed pages of every other source,
all four works, though its prompt calls them "other manuscripts of the
same works". Rewording it would mean asking again ($0.86); a labeler
version would offer the same work's texts first.

## Results (2026-10-09; $2.67 in all)

**Pages** (95 reviewed, the page alone, 1568 px; $1.24, 1.3¢ a page).
Kind: 93 of 95. The two others are pages the editor marked blank that
hold a title ("Mese di Febraro 1794. Quartettino ...") under a colour
chart: Claude called them title pages. Part: when Claude named one, it
was right 56 times in 57 (RES 507 (14)'s viola, in a treble clef, taken
for violin I). It declined on 28 music pages, nearly all violin pages
with no part name on them: violin I and II look alike, so the part has
to come from the part's title page, as the labeler already carries it
forward. So a page alone gives: the kind, a title page's part, and a
check on the carried-forward part where the clef settles it (alto: viola;
bass or tenor: cello).

**Marks** (167 transcribed text, tempo and other marks; the box with a
margin). Ignoring case, accents, spacing and punctuation (symbols such
as "°" kept): blind 124 of 167 ($0.51), offered the texts typed in the
other sources 134 of 167 ($0.86); exactly as typed, 49 and 71. Most of
the differences are conventions, applied unevenly in the labels: the
copyist's spelling or the modern one ("Giugnio", "Menuetto", "Dalcapo"
against "Giugno", "Minuetto", "Da Capo"), ordinals ("Violino 1.mo" typed
"Violino I", "Violino 2°" typed "Violino 2"), the fermata sign written
out. A few are misreadings ("Allegro" for "Allegretto moderato", "con
moto di Molto" for "con poco di Mosso"), and a few look like label slips
(KHM 602 p. 1: the box p1m2 holds "di Luigi Boccherini", its text is
"Compositor di Camera ..."; p. 9 m3's box holds "Violino 2.do", its text
"Quartettino").

**The convention** (the editor's decision, 2026-10-09): follow the
copyist. A mark's text keeps the manuscript's spelling, capitals and
ordinals ("Giugnio", "Menuetto", "Dalcapo", "Violino 1.mo"), with
abbreviations expanded ("All.tto" is "Allegretto"). This is what the
prompt in marks.py already asks for; the labels that use the modern
spelling are what is out of step.
