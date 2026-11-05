# Opus checks the pairing's left-out staves (2026-11-05)

The pairing leaves out staves whose readings it can't trust, though for
most it still proposes bars. **Shown each such staff with the score's bars
around it, Opus accepted 1,017 of 1,895 proposals. 520 of them, 2,945 bars,
are now added to the pairing; the rest can't be labelled yet, mostly
because Opus wasn't asked where a line's first and last bars are cut.** The
editor found none of Opus's accepts wrong. In the new labels the editor
checked, 18 of 20 were right, and the 2 faults were in cutting rules the
pairing's own staves share; both are now fixed.

Two changes came out of the checking. The set builder now labels
multi-bar rests (`rest:measure multirest:N`), about 320 staves it used to
leave out. And it leaves out two kinds of bad cut.

## The question

`experiments/llm/pairing/check_leftout.py` shows Opus the staff (padded
4 staff spaces above and below, not the readers' 2.5, so notes far off
the staff stay in) and the score's bars from 3 before the proposal to 3
after, as text. Then it asks: "the line holds bars f to l; is that exactly
right?" A line may begin with the end of a bar the line before started,
or end partway through one; those count as right. Opus answers in three
fields: `working` (bar by bar along the line), `right`, and `insights`
(what made it hard).

Sources: G. 213's three copies, scored against OSSQ's MusicXML, and the 51
Philhar-paired sources, scored against Philhar's LilyPond. Dresden is the
readers' held-out test and is left out. `notes.py` reads both encodings
into one form. It fills the bars a multi-bar rest covers, which Philhar's
encoding leaves out, and merges Philhar's two-note tremolos.

### Earlier, on the API: which task

KHM 587's staves, whose bars the editor fixed, on the API (Opus,
`pair_check.py`):

| task | right |
|---|---|
| read the bars from the staff and a text of the score | 41 of 50 exact |
| the same, the staff twice the size | 38 of 50 |
| the same, with the score engraved | 39 of 50 |
| the same, the staff's bar boxes drawn | 40 of 50 |
| **check a proposal (text), effort medium** | true bars accepted 40/50, moved bars rejected 48/50 |
| **check a proposal (text), effort high** | 45/50 and 49/50 |

Checking beats reading. These runs gave G. 213's movements II–IV the
wrong clef and key (a bug since fixed), so their numbers are low, but
they still pick the task.

### Four ways of showing the score

48 questions each on KHM 587: its 24 left-out staves, each asked once
with its true bars and once with them moved by one.

| the score shown as | true bars accepted | moved bars rejected | wrong |
|---|---|---|---|
| text | 22/24 | 24/24 | 2 |
| LilyPond | 21/24 | 24/24 | 3 |
| text, the proposed bars only | 21/24 | 23/24 | 4 |
| engraved under the staff, asked where each end falls | 22/24 | 21/24 | 5 |

Text won narrowly, and the engraved picture made the worst mistake:
accepting moved bars. The same staves defeated every version: runs of
near-identical tremolo bars (p24-4/5/6). On p23-1 all four said the line
also holds the start of bar 36, which the key doesn't have; the key may be
wrong there.

## The run

1,895 questions through `claude -p` on the editor's subscription, not the
API: the API key unset, three to six at a time, each run stopping at a set
share of the 5-hour window. **Accepted 1,017, rejected 876, 2 unanswered.**
The share rejected rose as the run went on (35% to 48%), because each
source's left-out staves are asked in turn, so the later questions came
from harder sources (full scores, poor crops).

Opus's insights pointed to real faults: a crop that cut the notes
(F-Pn RES-507-2 p6-1), repeat-bar signs copyists use, and early bugs in
the score's text (voices run together, wrong clefs, empty bars under a
multi-bar rest). Each was fixed before the main run.

**The editor's checks** (`spotcheck.py`; verdicts in
`experiments/llm/pairing/results/`). On 20 answers, Opus's 15 accepts had
none judged wrong: 13 right, and 2 the editor couldn't fully decide. Of
its 5 rejections, the editor agreed with 4. One right proposal was lost
(Op22-3-G185 p20-0).

## The question should have asked where each end falls

A label must say whether a line's first and last bars are whole, and
where a split bar is cut. The question counted a part bar as right, so a
"yes" doesn't say which. Asking for the two ends as well would have cost
almost nothing, and every accept would be usable as it stands. Most of
the cost below comes from that.

## Adding the accepts to the pairing

`experiments/zeus/add_opus.py` writes
`results/autopair-<source>-plus-opus.json`, which the labeler now shows
first. Each added staff is marked `opus` and carries Opus's working. A
staff is added only where its neighbours on the part settle both ends:

- **Whole bars:** the line before ends one bar earlier and the line after
  starts one bar later, or the staff opens or closes its movement.
- **A bar shared with a kept line:** cut where the pairing cut it for that
  line (90 cuts).
- **A bar shared with another accepted line:** cut where the bar's halves
  best fit the end of one line's reading and the start of the next
  (`autopair.break_cut`, within its usual limit; 146 cuts, 4 with no cut
  that fits).
- **A bar a repeat splits:** two measures, as the pairing's own staves
  have.

**Added: 520 staves, 2,945 bars.** Left out:

| reason | staves |
|---|---|
| a neighbour rejected or never paired, so an end is unknown | 308 |
| a bar shared with a kept line that holds it whole | 72 |
| a multi-bar rest | 69 |
| neighbours that skip or repeat bars | about 45 |

## Multi-bar rests

The readers' notation, LMX, has a bar rest but no multi-bar rest. So the
set builder left out every staff that had one: 251 the pairing kept, plus
69 of Opus's. The pairing already tells which form the copyist used. One
sign for the run becomes one measure, `rest:measure multirest:N`; a bar
rest in every bar becomes N bar rests. On the six sources built for the
check, none were left out for a multi-bar rest. The readers learn the
token when training widens their vocabulary.

## The label check

`labelcheck.py` shows each staff as the reader sees it, over its label
engraved to the same width (LMX → MusicXML → LilyPond). The sample was 20
labels: 15 of Opus's added staves (6 cut from readings, 4 cut as for a kept
neighbour, 5 whole bars) and 5 multi-bar rests. The editor marked all 20
right. Their notes found two faults:

- **US-R M351 p12-1:** the movement begins on this line, but the kept line
  before it had been paired with the first part of its bar 1, and the cut
  was reused. Both labels were wrong. Now a movement's first bar is never
  cut across a line break (this pair only).
- **RES 507-2 p75-8:** a bar a repeat splits where the music changes to
  2/4. Such a bar is cut where the movement's opening upbeat starts, which
  is wrong once the time changes. Now left out: about 58 staves, 38 of
  them the pairing's own.

The third note, a grace note the copyist leaves out (M351 p11-2), is the
edition's. Labels follow the edition.

## Not done

- **The staff sets aren't rebuilt.** Rebuilding with Opus's staves and the
  multi-bar rests is left to the next training run.
- **The 308 with an unknown end:** a cheap pass over Opus's working could
  recover about 200.
- **A crop check:** flag readings that show a bad crop (notes off the
  staff, a line read short for its width) before they reach Opus or a
  set.

## Cost

- **Claude API** (the earlier tests on KHM 587): $12.20 (measured,
  per-answer cost).
- **The editor's Claude plan, through `claude -p`:** the test and the main
  run used about 1.9 five-hour windows (measured from the rate-limit events
  each answer reports). The week's use went from 24% to 41%, which also
  counts this conversation. Each question took about 0.09–0.11% of a
  window. At API prices the answers would have cost $157 (`claude -p`'s
  reported cost; not billed).
- **Mac (M1):** about 2.5 hours of wall time for the runs (estimated from
  the logs). Engraving and building the check's labels took about 20
  minutes.
