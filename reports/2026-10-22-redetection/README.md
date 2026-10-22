# Re-detecting the paired manuscripts: +3,100 bars

2026-10-22. The 57 paired manuscripts were detected again, read again and
paired again, after five fixes to staff detection. The staff sets gained
520 staves and 3,122 bars (+10%).

| set | staves before | bars before | staves after | bars after |
|---|--:|--:|--:|--:|
| dataM3 → dataM4 | 3,686 | 21,294 | 4,134 | 23,900 |
| dataW2 → dataW3 | 999 | 6,930 | 1,066 | 7,415 |
| dataP2 → dataP3 | 21 | 147 | 21 | 147 |
| dataG213-2 → dataG213-3 | 430 | 2,409 | 435 | 2,440 |
| **all** | **5,136** | **30,780** | **5,656** | **33,902** |

The biggest gains: Op. 32 (+203 staves, +1,342 bars), MS-200's Op. 8/4
(+94 staves; score pages that failed the ruling layout before), MS-202's
Op. 2/1 (+51), US-R's Op. 4 (+74 kept), the Op. 24 score (+29). A few
older sources lost a handful each (G161 −7, G162 −5, G186 −4): their crops
changed, so the readings and pairings shifted a little either way.

## Where bars were lost, and what was fixed

Of 11,608 detected staves the pairing kept 7,297. Most of the rest were
put out for reading mistakes (an extra or missing measure, a measure
unlike its bar: about 2,200 staves). Detection's share was the staves
measured short (786, put out by autopair's short-staff rule), staff ends
(about 950), and staves missed outright. The fixes, all in `detect.py`:

1. **Each staff's own ink threshold.** `staff_extent` counted a pixel as
   ink below a fixed 175. On Op. 32's grey paper (lines ~90, spaces ~175)
   the spaces passed for ink; on the Paris copies' faint brown ruling
   (lines ~172, spaces ~230) the lines failed, and only the fallback to
   the whole paper, when no column passed at all, had kept those staves
   whole. Ink is now darker than halfway from the staff's lines to its
   spaces. A first try, halfway from the darkest ink to the paper, cut
   faint ruling short beside heavy notes; it was caught on a contact sheet
   of the staves it shortened.
2. **Lines half a space off the trace.** A column passes if the five lines
   pass at any shift within half a space: on staves dense with ink the
   trace drifts toward an end.
3. **Short staves with music past their ends take the page's span.** A
   staff measured under half the page's span, with music between its lines
   from 8 spaces past its end, takes the span (autopair's short-staff test,
   moved into detection). Where the music then stops, the existing trim
   ends the staff.
4. **A detector's end is ignored where music runs on past it.** yolo26n
   puts confident staff ends mid-line (Paris vc p18 at 0.29 of the page, at
   0.75, where its music runs to 0.91). The same test now turns such an end
   away. This also changes the labeler's own proposals.
5. **Ruled slots followed along the neighbours' ruling.** In a gap of whole
   staff spacings, the missing staff was traced freely from its strongest
   row, and on a dense staff the trace wandered up to three spaces onto the
   beams (Op. 32 pp. 3, 14, 24). The slot staff now follows the staves
   above and below, half a space either way, and is scored on the strips
   where it is seen (a score bar of 0.12, from 0.2). Empty slots are still
   dropped by the music-on-it test.

**On the editor's 1,110 reviewed staves,** through the labeler's own
detection (detectors' vote and ends):

| | before (HEAD) | after |
|---|--:|--:|
| right end within 1 staff space | 47% | 59% |
| median right-end error (spaces) | 1.31 | 0.56 |
| staves cut more than 3 spaces short | 52 | 34 |
| bar lines found / false | 3,951 / 137 | 3,975 / 142 |

No editor staff missed (5 unmatched before); the same 41 extra staves (empty
ruling and headings) on plain detection. 166 tests pass, including new ones
for Op. 32 pp. 3, 14, 24 (slot staves) and p. 138 (grey paper).

**On the paired sources,** detection found 10,788 staves, against 10,527.
Staves under half their page's median width fell from 333 to 235. Checked
by eye on contact sheets: of 143 added staves nearly all are written staves
(a few are empty staves holding a heading such as "Segue Allegro Giusto",
which the pairing passes over); of the 33 newly short ones nearly all end
where the music ends or hold only a heading, two or three are still cut
short (G186 p21). In the W and G pairings, autopair's short-staff rule put
out 69 staves, against 275.

## Not changed

- autopair's short-staff rule stays as it was. It now rarely fires; it was
  kept for the case it was added for (a short staff whose missing bars the
  alignment hands to the staves below it).
- The hand-listed staff ids (the Mus.ms.2861 drop list, G. 213's
  eye-checked staves) all still name the same staves.

## Where it lives

- Detections: `experiments/zeus/auto/<source>.json`; readings:
  `answers/<source>-auto-musvit-{D3S-h96,C4-bocch-tf8-L-best}.json`;
  pairings: `results/`.
- Sets: `~/.cache/manuscript-labeler/zeus/{dataM4,dataW3,dataP3,dataG213-3}`
  (see `docs/storage.md`). Not yet on Modal.

## Cost

- Mac (M1): detection about 30 min (six at a time), three times over;
  pairing about 45 min; set building about 15 min; evaluation about 1 h.
  Measured from logs, rounded.
- Modal L4, reading 12,169 changed staves (7,544 with D3S-h96, 4,625 with
  C4-bocch-tf8-L): $0.72 billed for the first full hour; about $1.2 in all
  (estimate; the last hour wasn't billed yet).
