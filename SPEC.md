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

- **Feed `Structure.ily` from the labels.** Today `Structure.ily`'s bar
  counts (`s2*48`, repeats) are filled in by counting bars in a
  manuscript by eye. The labels already hold those counts per movement,
  with repeat positions and pickups, so the labeler could export them
  (e.g. a `structure.json`, or the `\repeat volta 2 { s2*48 }` lines
  themselves; the time signature would need labelling). That makes
  bar-line accuracy matter twice, so: only from reviewed runs, and with a
  cross-check that sources of the same work agree.

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
  With a `\time`, bars are numbered as LilyPond numbers them, following
  the position within the bar: a `\partial` at the very start is the
  pickup, bar 0, and a section's short last bar plus the next section's
  upbeat are one bar (G227's Minuet, `\partial 4 s4 s2.*7 s2 } { s4
  s2.*19 s2`, is 8 + 20). A `\partial` later gives the current bar's
  remaining length: on a bar line it begins a short bar, which counts
  (G228's Trio ends `s2.*23 \partial 2 s2`, bar 68); within a bar it
  sets how much of it is left (shorter or longer), adding no bar. A bare
  `s` repeats the last duration, and text in markings is ignored. In the labels the matching upbeats have `bar_count`
  0, a short bar 1. Time changes, alternative endings, block comments and
  `\repeat unfold` are handled.
- **Labeler settings:** `sources/labeler.json`. For now one:
  `{"older_crops": ["D-B_KHM-602", ...]}`, sources (PDF names without
  `.pdf`) labelled before the editor's crop standard settled: the crop
  model learns only the crops the editor changed there, not those
  accepted as proposed (crops.py).

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

## Output format (draft, schema 2)

One file per source, in the edition repo next to the PDF, named
`<pdf name>.labels.json`. Coordinates are fractions of
the page width and height (0–1), so they don't depend on render resolution.

```json
{
  "schema": 2,
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
  by fitting a line to each edge of the bright paper (against the scanner
  bed) and intersecting them, so torn or rounded corners don't pull them
  inward; dragged into place by the editor. Re-detect keeps moved corners;
  "Reset to detected" replaces them.
- **Mark `text`** follows the copyist: the manuscript's spelling, capitals
  and ordinals ("Menuetto", "Dalcapo", "Violino 1.mo", "Violino 2°"), with
  abbreviations expanded ("All.tto" is "Allegretto"). `text_auto: true`
  (optional) marks a text Claude read that the editor hasn't edited
  (reader.py); typing in the field drops it.
- **Mark `kind`:** `text`, `tempo`, `title`, `dynamic`, `stray`, `unclear`,
  `other`, `signature`. A `title` is a movement's or section's heading
  ("Menuetto", "Trio"), apart from its tempo, which may be written
  elsewhere or not at all; like a tempo written above the music, it
  belongs to the first bar of the staff below it. Structure.ily gets a
  title alone as its `\tempo` (the edition's way), a title with a tempo as
  a `\sectionLabel` before the `\tempo`. Schema 4 added it (3 → 4 changes
  nothing).
- **Signatures: clef, key, time.** What is written at a line's start
  belongs to its staff: `clef`, `key` (the key signature as written:
  sharps > 0, flats < 0, 0 none; its mode isn't written) and `time`
  (`"2/4"`, `"3/4"`, … or `"C"`, `"C/"`), each only where the line sets or
  changes it; a movement's first line sets key and time (the labeler
  asks, on that page, while one is missing). A change written mid-line is
  a **signature mark** (kind `signature`, with any of the three), a box
  around it. A change holds from where it is written (a box's centre, or
  the bar line it starts at: a change at the start of a bar governs the
  whole bar), through later staves of the page, until the next; on a cue
  staff only the cue, on a score page only its own staff. The page's
  `clef` is the clef at the top of the page (a new page takes the one in
  force at the end of the part's previous page, else the part's usual
  one). Everything recorded is visible on the page, and the boxes and
  staff starts can train a detector. Schema 2 added clef marks; schema 3
  renamed them signature marks (nothing else changes: every box keeps its
  place and id).
- **`rejected`** (on a system) and **`rejected_staves`** (on a page),
  optional: x of bar lines / y of staves the editor deleted, so re-running
  detection doesn't bring them back.
- **`role`** (on a system, optional): `"cue"` for a cue staff (e.g. the
  violin I cue at the start of the cello part). It's drawn but not counted.
  Absent means `"part"`.
- **`bar_count`** sits on the bar line that *ends* the bar. It is 1 by
  default, and N for an N-bar rest. 0 marks a pickup: it isn't counted and
  shares the number before it (bar 0 at the start of a movement), matching
  the opening `\partial` in `Structure.ily` and the upbeat that completes
  a section's short last bar; a short bar a later `\partial` makes is 1.
- **Bar line `kind`:** `single`, `double`, `repeat_start`, `repeat_end`,
  `repeat_both`, `final`.
- **Bar numbers aren't stored.** They're derived (part, page order, systems
  top to bottom, `ends_movement`), so they can't go stale.
- **Formatting:** keys sorted and pretty-printed, so git diffs stay readable.

## Structure.ily and the labels

`Op48-N/Structure.ily` is the work's skeleton: each movement's time, key,
tempo, bar counts and repeats, shared by every source of the work.

1. A work starts either from a written Structure.ily or from a source
   labelled first.
2. When a movement is complete in a source (every part's pages reviewed
   through its end) and Structure.ily has no real block for it (missing,
   or the template's `s2*1`), the Bar counts panel offers to write it
   (structure.py): the parts must agree on bars, upbeats and repeats (a
   multi-bar rest stands for its bars) and not write different keys or
   times; the block is shown first, with what the page doesn't show
   asked (each key's mode, an upbeat's length), and must read back
   (parse_structure) as the labels say before it is written (atomically,
   the old file backed up). A movement already written is never
   overwritten: where a source differs from it, that is a difference
   between sources, shown as warnings, for the editor.
3. Structure.ily then serves every source of the work: their bar counts,
   repeats and tempos are checked against it, and its key and time are
   the defaults for a movement's first line (after what another part of
   the same source states), written into the labels when a page is
   marked reviewed.
4. It also proposes what it knows about bar lines, as bars are numbered:
   on bar lines detection placed and the editor hasn't touched, on pages
   not yet reviewed, the movement's pickup and the upbeat after a section
   that ends mid-bar (`bar_count` 0), the repeat signs where sections end
   (`repeat_both` between two repeated sections, `repeat_end` before a
   heading such as "Trio", whose opening sign stands at a line's start),
   and `ends_movement` at the movement's last bar. Numbered as they go,
   they follow the editor's fixes: adding a missed bar line moves the
   repeat after it along. Detection proposes only single and double bar
   lines, so a repeat on an untouched bar line is the proposal's, taken
   back (to single) where the numbering no longer puts it. Bar line
   positions are never steered by it. Movements still the template's
   propose nothing (the server flags them `template`).

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
      "marks": ["p2m1"],
      "clefs": ["alto"]
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
- **`marks`:** ids of marks whose centre lies in the bar's crop. A tempo
  outside every crop (written above the music) goes to the first bar of
  the nearest staff below it. Any other mark outside every crop goes to
  the last bar of the nearest staff that its text reaches: "Segue il
  Trio" and "Da capo il Minuetto" refer to the end of the music they're
  written under, wherever along it the text begins.
- **`pages`:** `{"2": {"corners": [TL, TR, BR, BL]}}` for pages whose
  paper corners are set, for cropping or straightening whole pages.
- **`complete`:** which part and movement runs are fully labeled and
  reviewed: every bar's page is reviewed, the run ends with a bar line
  marked `ends_movement`, and no earlier page is unlabeled. The build should
  only use complete runs, or clearly mark partial ones.
- **`reviewed`:** a per-bar flag. Unreviewed bars can be shown, greyed or
  flagged.
- **`clefs`:** the clefs in force across the bar, in order: the one at its
  start, then any it changes to (`["bass", "tenor"]`). A line's first bar
  takes the clef written before its music. The export's `schema` stays 1:
  this field was added without changing the others.

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
  - Empty ruled staves (title pages, after a part ends, under "Segue il
    Trio") are dropped when the ink *between their lines* is under 1%.
    Counting the 2.5 spaces around a staff, as at first, kept staves with
    a title or text just above or below them. In KHM 602/603 every staff
    with music has at least 3% between its lines, empty ones at most 0.6%.
  - A page's kind: music if its staves have bar lines; otherwise blank if
    it has no dark ink (text is darker than ruled lines), "other" if over
    2% of it is strongly coloured (the photographer's colour charts), and
    a title page otherwise. Blank and other pages get no part or clef;
    title pages keep inheriting the part, as the editor sets the next part
    there, but get no clef (a music page's clef is carried from the part's
    previous music page). All 15 non-music pages of KHM 602/603 come out as the editor
    marked them.
- **Staff end.** A staff is proposed to end just after its last bar line
  when the ruled lines beyond it are blank (under 1% ink). Ink there, such
  as a custos, a missed bar line or a bar running on to the next line,
  keeps the full length. The editor's "End at last bar line" trims by hand.
  Where a line ends mid-staff (a movement's end, a cue that stops, "da
  capo" text), the ink after the last bar line isn't blank, so a second
  rule: end the staff where the ink *between its lines* stops, if 8 or
  more empty spaces follow to the ruled end. Text above or below doesn't
  count; music running on to the next line leaves no such gap. Against
  the editor's right edges on reviewed pages, the big misses (70-96
  spaces) shrank to 5-16 (trailing flourishes). Limiting it to short tails
  (for fear of cutting music after a missed bar line) lost most of the
  gain, and the lines it flagged did end there.
- **Left edge and crop margins**, measured against what the editor set on
  KHM 602 pp. 2-4 and 6-8:
  - On the treble-clef pages the editor moved nearly every left edge 2-3
    staff spaces left; on alto pages, not at all. This copyist writes the
    treble clef partly left of where the ruled lines begin, and its curl
    reaches well left of its heavy middle. The left edge now follows the
    clef's ink left (up to 4 spaces past the ruled lines) plus half a
    space: within a space of the editor's on 80% of staves (was 56%).
  - The editor set crops of 3-7 spaces above (usually 3.5-4.5) and 2-6
    below, against a fixed default of 2.5. (Since 2026-10-09 a learned
    model chooses the edges once trained; this rule is its fallback and
    one of its features: see "Learned crop edges".) Now each staff's crop reaches
    its own outermost ink (ledger notes, slurs, dynamics, text) plus one
    space, stopping at a clear staff space or where the space shared with
    the next staff is emptiest. Off by about half a space on average
    (the fixed 2.5 was off by 1.2-1.3).
- **Music start on the cello part.** The start landed between the bass
  clef and its key signature, 2.6 spaces early (median) on page 14. The
  editor spotted why: this copyist writes the bass clef's B flat on or
  above the top line, where the clear-paper test, which looked only at
  the staff's own spaces, didn't see it. It now looks from two spaces
  above the staff to one below (staff lines left out). Lines 2+ of
  reviewed pages, within 1.5 spaces of the editor's start: bass 25% ->
  62%, treble and alto unchanged (~70% / ~60%). Tried and dropped:
  reading the clef and key as separate glyphs (this hand breaks into
  irregular pieces: worse everywhere), and a hint from the previous page's
  clef+key width (57% -> 61%, not worth it; key changes defeat it).
- **Clef vs. opening line, brace and label** (cello p. 16). A thin stroke
  followed by clear paper was taken for a system's opening line and
  skipped, but a bass clef starts with exactly that (a thin arc, then a
  gap before its body and dots), so the clef was skipped and the staff
  started after it. Now a stroke is only skipped if it also runs the
  staff's full height; and a treble clef's spine (thin, full height) is
  told from a brace by the brace running on 3 spaces to the next staff or
  an opening line having clear paper after it. A brace is looked for
  first, since a part's name ("Violoncello") is often written over the
  ruled lines before it. Reviewed pages: left within a space 84%, start
  within 1.5 spaces 69% (both up slightly). Still wrong: curly braces
  wider than half a space, and bass-clef arcs reaching more than 4 spaces
  into the margin (reaching further made other pages worse). The left edge
  is cosmetic for the export (each line's first bar is cut from the music
  start); the start matters.
- **Calibration on two reviewed sources** (2026-10-03: KHM 602 and 603
  fully reviewed, 1404 bar lines). Re-fitting the bar-line thresholds on
  both found the two copyists want the same settings (no per-copyist
  values needed); 89% found, 24 false. The "ink past the staff" stem test
  is now off: the note-head test catches stems, and it only cost long bar
  lines. Crops (off by ~0.4 space) and left edges (80% within a space)
  carried over to KHM 603. The music start didn't: detection was 4-5
  spaces early on KHM 603's staggered key signatures (30% within 1.5
  spaces). New pages now take the clef-and-key room from the editor's
  previous page of the same part (not across a title page), snapped to
  clear paper: 58% on KHM 603, 63% on KHM 602 (was 53%). Tests now hold
  detection to frozen corrections from both sources.
- **Learned bar-line filter** (2026-10-05). A bake-off on 1404 labelled
  bar lines (experiments/barlines) found that trained detectors (Detectron2,
  D-FINE, YOLO) and a small learned filter all beat the hand-tuned rules,
  mostly by missing far fewer bar lines; the filter matched the deep models
  within noise while training in seconds. So detection now proposes loose
  candidate strokes (`detect.candidates`) and a gradient-boosted classifier
  (`learn.py`), trained on the editor's reviewed pages through the same
  detection steps, keeps the bar lines. The server trains it in the
  background at start-up (cached by the reviewed labels), retrains when a
  reviewed page changes, and falls back to the hand-tuned rules until a
  model exists. Trained on one quartet, tested on the other: edits (false +
  missed) 85 -> 47 (KHM 603) and 100 -> 62 (KHM 602). A second pass
  (2026-10-05) sees the bar widths the first implies (a missed bar line
  leaves a bar twice the typical width), learned from first passes
  cross-fitted over 5 groups of pages: 12% fewer errors under
  cross-validation; end to end on the bake-off's test lines 28 -> 26.
  The deep detectors and the filter mostly err on different bar lines, so
  a vote of unlike methods would halve errors again, but would put PyTorch
  in the server; not done.
- **Detectors for new hands; a cached vote** (2026-10-07). With a third
  and fourth copy labelled (F-Po RES 507 (14), two hands; F-Pn Vma ms
  1067 (1), photographed), the learned filter proved tied to the hands it
  learned: end to end on Vma ms 1067 (1), which it never saw, 150 errors
  in 376 bar lines, where YOLO26n trained on the other sources made 35.
  The YOLOs carry to new copies; votes with the filter are within noise
  of the best single YOLO (experiments/barlines/results.md). So the
  detectors' predictions are made ahead of time for every page
  (tools/predict_barlines.py, about a second a page, into the cache;
  staves cut across the paper's width so the editor's edits to staff
  ends don't invalidate them). Detection votes them, staff by staff,
  with its own bar lines (the learned filter's, or the rules') before
  each staff's end is decided (detections.py, detect_page's `vote`): a
  bar line stays if two of the three propose it, taking its own bar
  line's position and kind where there is one. Without two detectors'
  predictions for a page, detection is as before.
  Two dead ends, written up there: segmenting whole pages into staff,
  clef-key-time and crop outlines (YOLO26/YOLO11-seg) didn't learn; and
  oemer couldn't run. Staff finding itself is sound (every staff found
  on the test pages); its weak points are each staff's right end and
  music start.
- **Staff ends as detector classes** (2026-10-07). The line detector also
  learns "start" (left end to music start) and "end" (the right end) on
  the paper-wide lines. Within a staff space of the editor's right end
  on 97–99% of test lines, where the labeler's detection (with the
  learned filter and the vote) manages 56–79%; music starts and left
  ends better too (experiments/barlines/results.md). The cached
  predictions carry each staff's surest start and end, and detection
  takes a staff's ends and music start from them where one is sure
  (detections.make_ends, detect_page's `ends`), the rules elsewhere; a
  start with the detector's own sure bar lines before it is mid-line and
  ignored. On the test lines, the labeler's right end within a staff
  space went from 56% to 95% (familiar hands) and 79% to 96% (an unseen
  copy), music starts 44% to 81% and 81% to 86%; the swap of the model
  into the vote cut bar line errors too, 18 to 6 and 29 to 26. Pretraining on MUSCIMA++ didn't help. Zeus (full
  OMR, zero-shot) counts our bars well but can't read our clefs.
- **Bar-line labels from Structure.ily** (2026-10-09). On the unseen
  test pages, most of the editor's bar-line edits were labels, not
  positions: repeat kinds, upbeats, movement ends. Structure.ily knows
  them, so it proposes them (see "Structure.ily and the labels").
  Measured (tools/score_structure.py) on the four reviewed sources whose
  work has one, bar lines where the editor put them but untouched and
  cleared: all 164 of the editor's labels proposed (85 repeat signs, 48
  upbeats, 31 movement ends), and 4 the editor didn't make: three repeat
  signs (labelled a double bar on KHM 602 cello II bar 8, single on Vma
  ms 1067 (1) cello I 118 and II 44) and one movement end (KHM 603
  violin II, II 60, the part's last bar).
- **Learned crop edges** (2026-10-09; crops.py, experiments/crops). What
  a crop should hold (the editor): first, everything needed to read the
  music on its staff and nothing that could confuse (a stray dynamic,
  another staff's markings); then, as little as possible, for the
  synoptic score. On 507 reviewed staves, crop_margins' edge was within
  half a space of the editor's 70% (above) / 68% (below) of the time,
  too wide 21% / 15%. A third of the editor's crops equal it exactly:
  accepted as proposed. And the standard tightened over time: the newest
  pages leave out a movement's title, an empty ruled staff, and a
  floating dynamic above the staff (the copyists write dynamics under
  the staff they belong to, so one above belongs to the staff above),
  where older crops kept them. So a model chooses among candidate edges
  every quarter space, by the ink each keeps and cuts and whose it is
  (blobs reaching into this staff, into the neighbour, or floating,
  given to the nearer), with crop_margins' edge as a feature; it learns
  from the newest crops (weighed 3x) and the older ones the editor
  changed. Leaving each source out: all staves 72% / 77% within half a
  space (too wide 12% / 7%); the newest pages (the 8 test pages) above
  64% -> 66%, below 72% -> 84%. Tried and dropped: a rule (own ink's
  reach plus a margin: 43% on the newest), weighing the newest crops
  like the rest (newest above 57%), learning only from changed crops
  (59%), and flagging
  close calls (the model's least sure picks were no likelier wrong). It
  retrains as pages are reviewed, so the newest standard gains weight;
  what it misses is mostly above the staff (titles, the staff above's
  dynamics). Erasing ruled lines must spare strokes crossing them, or a
  stem's outer half looks like a floating mark.
- **Odd bar widths as a check.** Counting beats would need reading the
  rhythm (full OMR). A cheaper proxy: a missed bar line merges two bars
  into one about twice as wide as its neighbours. On pages not yet
  reviewed, bars over 1.8x or under 0.4x their line's typical width are
  outlined and listed in Warnings (with the ratio), and so is music after
  a line's last bar line longer than half a typical bar (detection trims
  a blank end, so it suggests a missed final bar line). A line's first bar
  is left out: its width depends on the music start. On the reviewed pages
  of KHM 602/603 (all bars correct) 2.2% of bars are flagged anyway
  (notes-dense bars, so it's hidden once a page is reviewed); a removed
  bar line is flagged 57% of the time, an added one 11% (halves of a bar
  often look normal). The
  bar counts against Structure.ily say *whether* a movement is off; the
  widths suggest *where*.
- **Staff extent and music start.** The ruled lines often run into the
  margin before the clef. A column counts as staff when the line rows are
  dark and the spaces aren't. The music start is after the first heavy ink
  (the clef) and the next clear stretch (after the key signature). A thin
  stroke with clear paper after it is the system's opening line, not the
  clef. Where the guess fails, the page's typical clef width is used. It's
  good on KHM 602 and the BnF copy, rougher on Gallica scans.
- **Bar lines.** They lean, so each column is tested along several slants
  (on the straightened staff). Measured with `tools/score_barlines.py`
  against the editor's reviewed pages of KHM 602 (pp. 2, 3, 6; 194 bar
  lines):
  - First version: 168 found, **107 false**, 26 missed. Nearly all the
    false ones were stems of beamed sixteenths crossing the staff (violin I
    page 6 alone: 86).
  - Two rules from the editor fixed that: a bar line has no note head on it
    (a stem has a head at one end and beams across it), and bars are at
    least about 1 cm wide (4 staff spaces). A stroke with wide ink across
    it for more than 0.35 staff spaces of its height is dropped; of strokes
    closer than 4 spaces, only the cleanest is kept. Now: 165 found,
    **2 false**, 29 missed.
  - Tried and dropped: judging "wide" against the stroke's own width, to
    spare thick final bars. It let many stems back in (16-20 false).
  - Of the 29 still missed, 18 were faint or broken (covering 73-88% of
    the staff height against a required 88%), 6 ran past the staff and
    were taken for stems, 3 had a note or dynamic touching them, 2 lost the
    spacing rule. With stems now caught by the head test, the other tests
    could relax: steeper leans tried (0.3), more ink allowed past the staff
    (0.9), a stricter head test (0.25 spaces). Lowering the required cover
    overall brought stems back, so instead a second pass looks only where
    a gap is over 1.6x the line's typical bar, and accepts a weaker stroke
    (70% cover) near its middle. Now: **179 found (92%), 3 false**, 15
    missed (8 faint, 4 touched, 3 long), stable across nearby settings.
  - **Improving with more data:** `tools/tune_barlines.py` re-fits the
    thresholds (one at a time, keeping what helps) to every reviewed page;
    `tests/test_detect.py` holds detection to a frozen snapshot of the
    editor's corrections (`tests/fixtures/khm602_barlines.json`). After
    tuning on more pages, re-freeze both together. If the Paris copies
    want different thresholds than KHM 602, keep per-copyist settings
    rather than a compromise.
  - **Not** a prior from `Structure.ily`: the goal is for bar counts from
    this tool to *feed* `Structure.ily`, so using it to steer detection
    would be circular. Independent checks are the editor's review and
    agreement between sources of the same work. (It does label the bar
    lines detection finds, once a first source has written it: see
    "Structure.ily and the labels".)
- **Snapping hand-placed bar lines.** The editor places bar lines within
  millimetres but upright, while many are slanted. Placing or dragging one
  now fits it to the stroke under it: within about a staff space either
  side, every lean up to 0.4, the column of ink covering most of the
  staff's height, centred on the stroke. Nothing convincing (60% cover)
  that close: left where it was put. Dragging an end handle (setting the
  lean by hand) never snaps. On the 399 bar lines of KHM 602's reviewed
  pages, moved up to 0.8 spaces and stood upright: snapped back to within
  0.03 spaces (median) of where they belong.
- **Bar counting by eye** worked best from whole-line strips, counting bar
  lines and cross-checking against the expected total.

### About Claude's readings (`reader.py`)

Measured on the reviewed pages (experiments/llm/README.md, 2026-10-09):
a page's kind right on 93 of 95 (detection's rule: 86); a part, when
Claude names one, right 56 times in 57, but it declines on violin pages
without a part name (violin I and II look alike on a page alone). So a
new page takes Claude's kind, a title page Claude's part, and a music
page the part carried from the page before (69 of 85 alone; every miss a
title page starting a new part), with Claude's reading shown where it
disagrees. Mark text: 138 of 167 read blind (ignoring case and
punctuation), once the labels followed the copyist.

A page Claude calls a title page is also asked for its lines of writing
(a second call, about 1.5¢): each line's box and text become the page's
text marks, proposals (`text_auto`) on a page nobody has touched. On the
20 reviewed title pages (experiments/llm/boxes.py) Claude's boxes sit on
the ink and the editor's leave a margin, so they're widened by the
editor's median margin (0.1 of the line's height at the sides, 0.2 above
and below); then 58 of the editor's 65 boxes are found at an overlap of
0.5, 62 at 0.3. The misses: a two-line label the editor boxed as one,
and a flourish taken into a box. Text: 49 of 59 as typed.

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
