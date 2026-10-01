# manuscript-labeler: initial spec

A local web tool for marking up scanned music manuscripts, one page at a
time: staves, bar lines, bar numbers, and anything confusing on the page. It
writes a JSON description of each manuscript that other tools read. The first
consumer is a synoptic edition, which shows the same bar from every source
side by side.

Status (2026-10-01): working first version. `server.py` serves the editor
(`static/`), proposes staves and bar lines, numbers bars live, checks counts
against `Structure.ily`, and autosaves `.labels.json` and `.bars.json`.
Not built yet: per-bar crop export, cross-source alignment, multi-staff
systems, note-head overlay (see Requirements).

## Why it exists

It was born out of the
[Boccherini Op. 48 edition](https://github.com/jsundram/boccherini-opus-48):
six string quartets (G 226–231) engraved in LilyPond from manuscripts that
have never been published. Two needs drive it:

1. **A synoptic edition.** Show each bar of the engraving next to the same
   bar in every manuscript source (Berlin copies, Paris autographs, Paris
   copies). That needs every source cut into bars, with bar numbers that
   line up across sources.
2. **Proofreading.** Putting the manuscript bar right beside the engraved
   bar makes transcription mistakes obvious. In one session an encoder
   misread whole rhythms and skipped a bar; side by side, both would have
   been caught at once.

The tool is general (any scanned part or score). This edition is just the
first user.

## Users and workflow

One editor at a time, on their own machine.

1. Run `uv run server.py <edition-repo>`. The edition repo holds the source
   PDFs (e.g. `sources/G226/D-B_KHM-602.pdf`).
2. Open the page in a browser and pick a source.
3. Go through the source page by page:
   - The page opens with **automatic proposals**: staves found, bar lines
     found, bars numbered.
   - The editor fixes them: drag, add or delete bar lines, adjust staves,
     set the page's part and movement.
   - Optionally, mark anything confusing: text, dynamics, stray marks, ink
     blots, unclear signs, with a note.
   - Mark the page **reviewed** and move on.
4. Running bar counts are checked against what's expected for each movement
   (see "Known metadata").
5. Output: one JSON file per source. The synoptic build reads it.

## Requirements

### Must

- **Page by page.** List all pages with their status (no labels, auto,
  edited, reviewed), part, and bar range. Opening a page shows the scan with
  the labels drawn on top. Zoom and pan.
- **Automatic labels on first open.** Staves and bar lines are detected
  (see `detect.py`). Bars are numbered automatically. Auto items are marked
  as auto until the editor touches them.
- **Easy correction.**
  - Click to add a bar line; drag to move it; delete it.
  - Bar lines are slanted in handwriting, so each has a top x and a
    bottom x. Each end can be adjusted.
  - Add, resize and delete staves.
  - Set a bar line's kind: single, double, repeat start, repeat end, final.
  - Mark a bar as covering several bars, e.g. a whole-bar rest with "2"
    over it counts as two bars.
  - Mark "movement ends here".
- **Bar numbers.** Bars run continuously through a part, across pages, and
  restart at each movement. The number of every bar is shown on the page.
  Changing one bar line renumbers everything after it, live.
- **Page metadata.**
  - What the page is: music, title page, blank, other.
  - Which part it belongs to (violin I, violin II, viola, cello, or score).
  - The clef. Default: the same as the previous page of that part.
- **Annotations ("marks").** A box on the page with a kind (text, dynamic,
  stray mark, unclear, other), optional transcribed text (e.g. "dolcis."),
  and a free note.
- **Known metadata shown in the UI.**
  - The source's library, shelfmark, RISM ID, Gérard number and online link.
  - The expected bar counts per movement, compared live with the counted
    ones (see below).
- **Never lose work.**
  - Autosave every change to the JSON file (debounced). Write atomically
    (temp file and rename).
  - Keep rolling backups outside the edition repo.
  - The UI code and the labels are separate files, so changing the UI can't
    touch saved labels. The JSON has a `schema` version, and the server
    migrates old versions forward.
- **Keyboard driven.** E.g. `b` add bar line, `s` add staff, `m` add mark,
  `Del` delete, arrows nudge, `Enter` mark reviewed and go to the next page.
- **Python via uv** (`uv run`, inline PEP 723 dependencies). Plain
  HTML/JS/SVG front end; no build step.

### Should

- **Re-run detection** on one page without disturbing anything the editor
  has already edited.
- **Bar detail view.** Show the selected bar enlarged, with each staff line
  and space labelled with its pitch for the page's clef. `prototypes/zoom.py`
  does this; it made reading the hand far easier.
- **Note-head pitch overlay** for the bar detail view (`prototypes/heads.py`).
  It's a reading aid, not data.
- **Mismatch warnings.** E.g. "movement I: 118 bars counted, 130 expected",
  or "repeat sign at bar 47, expected after bar 48".

### Later

- Export per-bar crop images, keyed by source, part, movement and bar
  number, for the synoptic page.
- Align bar numbers across sources when one source has an extra or missing
  bar.
- Several staves per system (full scores), not just one staff per line.

## Known metadata (edition repo)

The server reads these, if present:

- **The source list:** for now, the table in
  `boccherini-opus-48/sources/README.md` (siglum, shelfmark, RISM ID, online
  link). A machine-readable `sources/manifest.json` there would be better.
- **Expected bar counts:** `boccherini-opus-48/Op48-N/Structure.ily`. Each
  `\tag #'mvtI { ... }` block counts its bars as spacer rests: `s2*48`
  = 48 bars, inside `\repeat volta 2 { }`. Parse each movement's total and
  where its repeats fall. Example (Op48-1): movement I is 48 + 82 bars;
  movement II is Minuet 8 + 28, Trio 16 + 20.

Example source: `sources/G226/D-B_KHM-602.pdf`, Berlin, Staatsbibliothek,
KHM 602, RISM 1001015844. It is a set of parts, 17 pages:

| Pages | Content |
|---|---|
| 1 | viola title page |
| 2–4 | viola part |
| 5 | violin I title page |
| 6–8 | violin I part |
| 9 | violin II title page |
| 10–12 | violin II part |
| 13 | cello title page |
| 14–17 | cello part |

The cello part opens with a braced violin I cue staff for bars 1–4. That's a
second staff on one system: a case to handle.

## Output format (draft, schema 1)

One file per source, in the edition repo next to the PDF, named
`<pdf name>.labels.json`. Coordinates are fractions of
the page width and height (0–1), so they don't depend on render resolution.

```json
{
  "schema": 1,
  "source": { "pdf": "sources/G226/D-B_KHM-602.pdf", "siglum": "D-B",
              "shelfmark": "KHM 602", "rism": "1001015844", "gerard": 226 },
  "pages": {
    "2": {
      "status": "reviewed",
      "kind": "music",
      "part": "va",
      "clef": "alto",
      "notes": "",
      "systems": [
        {
          "id": "p2s1",
          "top": 0.112, "bottom": 0.142, "left": 0.146, "right": 0.962,
          "start": 0.171,
          "auto": false,
          "barlines": [
            { "id": "p2s1b1", "x0": 0.154, "x1": 0.151, "kind": "single",
              "auto": true, "bar_count": 1, "ends_movement": false }
          ]
        }
      ],
      "marks": [
        { "id": "p2m1", "x": 0.31, "y": 0.29, "w": 0.04, "h": 0.02,
          "kind": "text", "text": "dolcis.", "note": "long s = dolcissimo" }
      ]
    }
  }
}
```

The rules:

- **A bar** is the space between consecutive bar lines in a system. The
  first bar of a system runs from the end of the clef and key signature to
  the first bar line.
- **`start`** (on a system) is where the music starts, after the clef and
  key signature. The first bar of the system runs from there.
- **`bend`** (on a system, optional): the staff's vertical offset at 5
  evenly spaced points from `left` to `right`, linearly interpolated, so a
  staff can follow a slanted or curled page (page 2 of KHM 602 rises about
  a staff space at the right). `top` / `bottom` are the staff without it.
- **`above` / `below`** (on a system, optional, default 2.5): how many staff
  spaces the bar crops reach beyond the staff, to keep ledger-line notes,
  dynamics and text. Shown as a dashed band in the editor.
- **`above` / `below` on a bar line** (optional) override the staff's crop
  for the bar it ends, for tight spacing where one band doesn't fit every
  bar. Crops of neighbouring staves may overlap; each bar is cut out on
  its own.
- **`corners`** (on a page, optional): `{"points": [TL, TR, BR, BL],
  "auto": bool}`, the paper's corners as `[x, y]` page fractions. Proposed
  from the bright paper against the scanner bed; dragged into place by the
  editor.
- **Mark `kind`:** `text`, `tempo`, `dynamic`, `stray`, `unclear`, `other`.
  Tempo marks (e.g. "Andante Moderato") are shown per movement next to the
  `\tempo` texts in `Structure.ily`, as a check that movements line up.
- **`rejected`** (on a system) and **`rejected_staves`** (on a page),
  optional: x of bar lines / y of staves the editor deleted, so re-running
  detection doesn't bring them back.
- **`role`** (on a system, optional): `"cue"` for a cue staff (e.g. the
  violin I cue at the start of the cello part). It's drawn but not counted.
  Absent means `"part"`.
- **`bar_count`** sits on the bar line that *ends* the bar. It is 1 by
  default, and N for an N-bar rest. 0 marks a pickup: it isn't counted and
  shares the number before it (bar 0 at the start of a movement), matching
  `\partial` in `Structure.ily`.
- **Bar line `kind`:** `single`, `double`, `repeat_start`, `repeat_end`,
  `repeat_both`, `final`.
- **Bar numbers aren't stored.** They're derived (part, page order, systems
  top to bottom, `ends_movement`), so they can't go stale.
- **Formatting:** keys sorted and pretty-printed, so git diffs stay readable.

## Interface to the synoptic build (the contract)

The labels file above is the labeler's own working format. The synoptic
build, which lives in the edition repo on the LilyPond side, should not have
to know how bar numbers are derived. So the labeler also writes a flat
**bar export**, regenerated on every save:
`<pdf name>.bars.json`.

```json
{
  "schema": 1,
  "source": { "pdf": "sources/G226/D-B_KHM-602.pdf", "siglum": "D-B",
              "shelfmark": "KHM 602", "rism": "1001015844", "gerard": 226 },
  "complete": { "va": ["I"], "vn1": [] },
  "bars": [
    {
      "part": "va", "movement": "I", "bar": 5, "count": 1,
      "page": 2, "system": "p2s1", "barline": "p2s1b5",
      "quad": [[0.312, 0.098], [0.398, 0.098], [0.396, 0.156], [0.310, 0.156]],
      "staff": { "top": 0.112, "bottom": 0.142 },
      "reviewed": true,
      "marks": ["p2m1"]
    }
  ]
}
```

The fields:

- **`quad`:** the bar's four corners, in this order: top-left, top-right,
  bottom-right, bottom-left. Coordinates are page fractions. It includes a
  vertical margin above and below the staff, so notes and dynamics that
  stick out are kept (default: 2.5 staff spaces each side; set per staff). It is a
  quadrilateral, not a rectangle, because bar lines lean and staves bend.
  Each side's top and bottom follow the staff at that bar line, plus the
  system's `above` / `below`.
- **`count` > 1:** one image stands for several bars, e.g. a two-bar rest.
  The build shows it once, spread across those bars. `count` 0 is a pickup.
- **`barline`:** the id of the bar line that ends the bar, for tracing a
  bar back to the labels file.
- **`marks`:** ids of marks whose centre lies in the bar's crop. A mark
  outside every crop (a tempo or title above the music) goes to the first
  bar of the nearest staff below it.
- **`pages`:** `{"2": {"corners": [TL, TR, BR, BL]}}` for pages whose
  paper corners are set, for cropping or straightening whole pages.
- **`complete`:** which part and movement runs are fully labeled and
  reviewed: every bar's page is reviewed, the run ends with a bar line
  marked `ends_movement`, and no earlier page is unlabeled. The build should
  only use complete runs, or clearly mark partial ones.
- **`reviewed`:** a per-bar flag. Unreviewed bars can be shown, greyed or
  flagged.

### What the edition repo does with it (planned)

This is a sketch for agreement, not built yet.

1. **Crop.** For each bar: render the PDF page (`pdftoppm`, fixed dpi), cut
   out the `quad`, straighten it into a rectangle, and save
   `build/facsimile/<siglum>/<part>-<mvt>-<bar>.png`.
2. **Generate LilyPond.** Write one `.ily` per source, part and movement,
   built from spacer rests just like `Structure.ily`, with each bar's image
   attached above it:
   ```lilypond
   \tag #'mvtI {
     s2^\facsimileBar "build/facsimile/D-B/va-I-005.png"
     ...
   }
   ```
   Laid over the part's notes (`<< ... >>`), each manuscript bar then prints
   above its engraved bar, and the bar checks keep the two in step. A
   synoptic score stacks one such image line per source.
3. **Style.** `\facsimileBar` goes in `common/style.ily`: image width fitted
   to the engraved bar, plus a small siglum label.

### First milestone

**One reviewed, fully labeled page:** D-B KHM 602, page 2, the first page of
the viola part: 10 lines, movement I bars 1 to about 74, including the
first-half repeat sign. Its
`.bars.json` is the test fixture for:

- the crop and LilyPond step above;
- styling the facsimile line over `Op48-1/03-Va-1.ily`.

It's also the first real proofreading test: the viola sketch there is
known to have errors.

## What we learned so far

These are from hand-transcribing the viola part of D-B KHM 602.

### About detection (`detect.py`)

Pages are rendered with `pdftoppm -scale-to 2800` (long side 2800 px, about
200 dpi for KHM 602).

- **Staves.** All 10 staves on page 2 of KHM 602 are found now, and every
  staff on the Paris pages tried (BnF photo, Gallica scan).
  - Hand-ruled lines on a curled page are *wavy*, not just tilted: a line
    drifts up and down by several pixels across the page. A full-width row
    profile smears them, which is why the last two staves were missed.
  - Fix: cut the page into 24 narrow vertical strips, score each row of each
    strip for "staff here" (five dark rows a staff space apart, lighter rows
    between), and trace each staff across the strips with a little drift
    allowed per strip (dynamic programming). Each staff is then straightened
    along its traced path before bar lines are searched.
  - The staff space is the most common distance between neighbouring dark
    *runs* of rows. Lines are 4–5 px thick, so counting peaks instead of
    runs gave 5 px. Autocorrelation was fooled by thick note ink.
  - "Near-solid row" filtering (for scanner borders) must look at the whole
    page width: in a narrow strip a thick staff line is near-solid too.
  - Empty ruled staves (title pages, after a part ends) have under 1% ink
    between the lines and are dropped. A page with staves but no bar lines
    is proposed as a title page.
- **Staff end.** A staff is proposed to end just after its last bar line
  when the ruled lines beyond it are blank (under 1% ink). Ink there, such
  as a custos, a missed bar line or a bar running on to the next line,
  keeps the full length. The editor's "End at last bar line" trims by hand.
- **Staff extent and music start.** The ruled lines often run into the
  margin before the clef. A column counts as staff when the line rows are
  dark and the spaces aren't. The music start is after the first heavy ink
  (the clef) and the next clear stretch (after the key signature). A thin
  stroke with clear paper after it is the system's opening line, not the
  clef. Where the guess fails, the page's typical clef width is used. It's
  good on KHM 602 and the BnF copy, rougher on Gallica scans.
- **Bar lines.** They lean, so each column is tested along several slants
  (on the straightened staff).
  Results are noisy: line 1 truly has 10 bar lines; the detector finds 9.
  Page 2 gets 78 proposals for about 74 bars. On the Paris copies, thin
  grey bar lines are often missed (41 found on a BnF page of 12 lines). The cause is note stems that span the staff, and
  faint or broken bar lines.
  - The automatic proposal is a starting point only. The UI has to make
    fixing it fast.
  - Ideas to try:
    - require ink above *and* below the staff to be absent;
    - use the median bar width per line as a prior;
    - learn from the editor's corrections.
- **Bar counting by eye** worked best from whole-line strips, counting bar
  lines and cross-checking against the expected total.

### About reading this copyist's hand

These matter for the bar-detail view and any future OMR:

- The tall hook-shaped rest is a 16th rest, not a quarter rest.
- A stem with no flag is a quarter note.
- Small flagged notes before a note are grace notes.
- The recurring rhythm is 16th–8th–16th.
- "dolcis" with a long s (ſ) means dolcissimo.
- A "2" over a whole-bar rest is a two-bar rest.
- Round blobs that look like ink spots can be real note heads.
- When a bar doesn't add up, the mistake is usually a misread rest, not a
  wrong note value.

## Prototype code (`prototypes/`)

These are scratch scripts used during the viola transcription. They work on
page renders made with `pdftoppm -r 300 -png`, and assume a `hi/` folder of
renders next to them.

| Script | What it does |
|---|---|
| `staves.py` | Staff positions on a page (earlier, cruder version of `detect.find_staves`). |
| `zoom.py PAGE CENTER_Y X0 X1 OUT [scale]` | Crops one staff and labels every line and space with its alto-clef pitch, plus an x ruler. The most useful reading aid. Needs to become clef-aware. |
| `heads.py PAGE CENTER_Y X0 X1 [OUT]` | Finds note-head blobs (morphological opening) and reports their pitch, optionally drawn on the crop. It corrected two misreadings; it also finds false heads in letters and beams. |
| `barlines.py PAGE Y...` | First bar-line attempt; unreliable. Superseded by `detect.find_barlines`. |
| `bar.sh`, `ov.sh` | Wrappers that combine the zoom and the head overlay. |

## Open questions

1. ~~Where should the labels JSON live?~~ **Decided (2026-10-01):** in the
   edition repo, next to the source PDFs
   (`sources/G226/D-B_KHM-602.labels.json` and `.bars.json`). The edition is
   their only consumer. Each edition commits them once a run is reviewed.
   This tool therefore writes into the edition repo it's pointed at, and
   keeps nothing edition-specific itself (backups go to a local cache).
2. **Systems with more than one staff:** full scores, and cue staves like
   the cello part's opening.
3. **Several editors:** one at a time is assumed. Would file locking or
   per-page merge be needed?
4. **Should detection improve from corrections,** e.g. per-source tuning?
