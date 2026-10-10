# A language model on the pages

Step 3 of the plan: can Claude say what a page is and whose part it is,
and read the text the editor marks, well enough to propose them on a new
manuscript? A first measured test on the reviewed pages, before building
anything into the labeler.

    uv run experiments/llm/pages.py <edition-repo>                # kind and part, one page at a time
    uv run experiments/llm/marks.py <edition-repo> --mode blind   # each mark's text, transcribed
    uv run experiments/llm/marks.py <edition-repo> --mode known   # ... offered the other sources' texts
    uv run experiments/llm/boxes.py <edition-repo>                # a title page's lines of text: boxes and text

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
copyist's spelling or the modern one ("Menuetto", "Dalcapo" against
"Minuetto", "Da Capo"), ordinals ("Violino 1.mo" typed
"Violino I", "Violino 2°" typed "Violino 2"), the fermata sign written
out. A few are misreadings ("Allegro" for "Allegretto moderato", "con
moto di Molto" for "con poco di Mosso"), and a few look like label slips
(KHM 602 p. 1: the box p1m2 holds "di Luigi Boccherini", its text is
"Compositor di Camera ..."; p. 9 m3's box holds "Violino 2.do", its text
"Quartettino").

**The convention** (the editor's decision, 2026-10-09): follow the
copyist. A mark's text keeps the manuscript's spelling, capitals and
ordinals ("Menuetto", "Dalcapo", "Violino 1.mo"), with
abbreviations expanded ("All.tto" is "Allegretto"). This is what the
prompt (now reader.py's) already asks for; the labels that use the modern
spelling are what is out of step.

After ten labels were set to the copyist's ordinals ("Violino 1.mo",
"Violino 2°") and five "Mese di Giugnio" to what the pages say, "Giugno"
(Claude's reading; the editor's slip), blind reading matches 138 of 167
(exact 56). The "known" answers no longer apply (the texts offered
changed); asking them again would cost about $0.86.

## Title pages: finding the text (boxes.py, 2026-10-09; $0.30)

    uv run experiments/llm/boxes.py <edition-repo> [--overlays DIR]

The 20 reviewed title pages, each sent whole (1568 px), asking for every
line of writing: its box in pixels of that image and its text. Each of
the editor's 65 marks matched to the Claude box overlapping it most:
found 55 at an overlap (IoU) of 0.5 or more, 61 at 0.3. Claude's boxes
sit tight on the ink; the editor's leave a margin, about 0.1 of the
line's height at the sides and 0.2 above and below (medians), which is
most of the edges' difference (median 0.008 of the page's height). The
four missed: the Vma covers' label, where the editor boxed "Boccherini /
6 quatuors inédits" as one and Claude as two lines; RES 507 (14)'s
"Boccherini", where Claude's box takes in the big flourish around it
(twice); and KHM 602 p. 1, whose marks are the slips in TODO.md. Of
Claude's 13 boxes matching none: the other half of the Vma label (5),
"N° 1" on four Vma title pages (not marked, as it's the catalogue's wrong
number, but it is on the page: fine to propose), the flourishes and the
slips. Text of a found box: 49 of 58 as the editor typed it.

So the labeler proposes these boxes on a page Claude calls a title page,
widened by the editor's margin (reader.py; boxes.py now asks its prompt
and scores the widened boxes): found 58 of 65 at 0.5, 62 at 0.3, edges
off by a median 0.004 of the page's height.

The labeler now asks these same prompts (reader.py; these scripts import
them). The texts it offers differ: every checked text in the edition, this
source's included, where "known" here offers other sources' only.

## Reading a bar's notes (bars.py, 2026-10-09)

    uv run experiments/llm/bars.py <edition-repo> [--limit N] [--effort low] [--same-as ANSWERS]

Zeus's task (experiments/zeus/), given to Claude Opus 5.5 and scored the
same way:
- 40 example bars with their encoding in a cached prefix;
- each test bar at 40 px a staff space, with its clef, key and time.

On a pilot of 10 held-out bars (viola II 1–10, about 3¢ a bar):

| | bars exact | rhythm | pitch | errors |
|---|---|---|---|---|
| Claude, low effort | 1 | 5 | 2 | 19 |
| Claude, high effort | 1 | 4 | 3 | 12 |
| Zeus zero-shot | 4 | 6 | 7 | 18 |
| Zeus fine-tuned | 6 | 6 | 7 | 16 |

A single read by a large model is not better than Zeus on this hand. The
edition's `/encode` gets its accuracy from what follows its reading:
- enforced resolution with a pitch grid;
- bar checks, headcheck and crosscheck;
- two blind readers per kind of mark, and adjudication of their
  differences;
- rules learned from corrections.
