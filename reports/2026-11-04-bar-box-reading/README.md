# Reading a staff one bar box at a time: worse (2026-11-04)

Most staves the pairing leaves out are misread: a measure that isn't there,
or two bars read as one. The idea: cut each staff at its detected bar lines,
read each piece separately, and the reader can no longer run bars together
or invent one. **On KHM 587 it keeps fewer staves than reading whole staves,
even where detection is exactly right. Dropped.**

## How

`experiments/musvit/read_boxes.py`: each detected staff cut at its detected
bar lines; the staff's opening (clef, key, time: everything before its
music starts) put before each piece, so the reader knows the pitches; each
piece read by musvit-D5; the readings joined back into one staff's (the
repeated clef, key and time dropped). G. 213's KHM 587: 246 staves, 1,317
pieces, then paired as usual.

## Results

Scored as in [the D5 pairing](../2026-11-04-d5-pairing/) (its
`compare_readers.py`), against the editor's 41 fixed pages:

| musvit-D5 reading | kept | right measures | kept, staves D5 never trained on | kept, staves whose detection is exactly right |
|---|--:|--:|--:|--:|
| whole staves | 171 | 154 | 76 of 146 | 149 of 198 |
| one bar box at a time | 123 | 108 | 59 of 146 | 107 of 198 |

"Exactly right": every bar line within 1.2% of the page width of the
editor's, and the staff's start within 1.5%.

## Why

- **The reader reads a bar alone worse**, even where detection is right. It
  was trained on whole staves; a bar after a glued-on opening is not what it
  has seen.
- **Detection's errors go into every piece.** Where a staff's start is placed
  after some of its music (10 of 243 staves), the opening glued before each
  piece carries notes or a bar line, read again in each. A missed bar line
  leaves two bars in one box; a false one, through a stem, cuts a bar in two.
  A whole staff's reading doesn't depend on them.
- 97 of 1,317 pieces were read as two or three measures. Cutting at the bar
  line's own edge (0.1 staff space past it) instead of 0.3 past its centre
  changed nothing: those pieces hold missed bar lines or a wrong start
  (`pieces.jpg`, eight of them).

## What would change it

A reader trained on such pieces, and detection of the staff's start scored
and fixed. Neither is worth it now: a better reader on whole staves (D5)
added 739 staves the same day.

## Cost

Modal L4, two reads of 1,317 pieces: $0.05 (Modal's billing). Mac (M1):
two pairings of KHM 587, about 10 minutes.
