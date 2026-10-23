# Journal

Newest first. Each entry says what prompted a report, the question it
answers, what it concluded, and what was done about it. The reports
themselves are listed in [index.md](index.md).

## 2026-10-23: musvit-D5

[Write-up](2026-10-23-musvit-d5/)

**Context.** Boccherini 6k tied D4 and miscounted bars on Dresden; the
editor asked for the variants (fewer steps, Op. 48 weighted up), then a
repeat of D4's own recipe ("I'm very curious"), then Op. 48 ×3 on D4's
drawn stage, twice.

**Question.** Did the new data make the reader worse, and which reader is
best?

**Finding.** No: D4's own recipe, run again, miscounts as the new readers
do (20 against 8); single runs can't rank readers this close. Every
Boccherini 6k reader cuts beam errors fivefold. Op. 48 ×3 from Drawn 11k
is as good as D4 on notes and better at the edition's flags.

**Why a report.** A release, and the evidence that runs need repeating.

**What followed.** Released as musvit-D5 (seed 1, the editor's pick),
zeus-score 1.4.0's default.

## 2026-10-23: Bar lines counted on the paired manuscripts

[Write-up](2026-10-23-bar-line-counts/)

**Context.** Detection's bar counts disagreed with 28% of the training
labels; the editor asked whether the pairing was showing wrong labels, and
how much more data would make the bar-line filter 5–10% better.

**Question.** Who is wrong where they disagree, and does more data help?

**Finding.** The labels were right every time looked at (6 of 6). The
filter's count accuracy is flat from 27 to 111 reviewed pages (77%);
training on the paired counts adds 1 point. Stems and the open last box
are the errors to fix.

**Why a report.** It decides where the bar-line effort goes.

**What followed.** Nothing yet: rules for stems and the last box are next.

## 2026-10-22: Boccherini 6k

[Write-up](2026-10-22-boccherini-6k/)

**Context.** The day's redetection and pairing fixes doubled the labelled
staves (3,411 to 6,275); the editor asked to train on them, with a
held-out manuscript in a new hand, the clef-change drawn stage, and more
CPU workers.

**Question.** Does twice the data make a better reader?

**Finding.** No. The clean test ties (277 of 347). On a held-out hand,
symbol errors fell by a third, but the editor's question (why only 48
staves exact?) showed that was beams: in notes and rhythm D4 reads it
better, because the new reader miscounts bars on more staves. Held-out
scores must compare notes and rhythm bar by bar, as the clean test does.

**Why a report.** A training run, and a change in how readers must be
compared.

**What followed.** Not released yet; the editor to decide. The batch
workers doubled the staves trained a second.

## 2026-10-22: Bar lines the reading missed

[Write-up](2026-10-22-missed-bar-lines/)

**Context.** The line-break counts in the split-bar report showed 465
breaks where a staff's end measure was paired with two bars; the editor
asked for detection's bar lines to settle them, and for a faster re-pair
(a parallel pairer, numba).

**Question.** Where detection found the bar line the reader missed, can
the staff and its neighbour be kept?

**Finding.** Yes, but few qualify: +43 staves, +305 bars. On most such
staves detection finds fewer bar lines than the reading, not more. A full
re-pair takes 3.6 min, from 45.

**Why a report.** The sets change again, and the speed-up changes how
cheaply pairing ideas can be tried.

**What followed.** Sets rebuilt in place. Better bar-line detection on
these hands is the likely next lever for the red staves.

## 2026-10-22: Bars that cross a line

[Write-up](2026-10-22-split-bars/)

**Context.** In the new pairing view the editor saw that "bars that cross
lines cause both lines to be unpaired", and asked for the fix.

**Question.** Why does a bar broken across two lines keep both out, and
can each line get its part of it?

**Finding.** Two causes: the set builder took only plain staves, so a
correctly paired half-bar was left out (blue); and where the reading
mangled the half-bar, the boundary rules put out both lines (red). The
first is fixed: the score's bar is cut where the two readings fit its
halves best, and each line labelled with its part; bars a repeat splits
too, where each half is its own measure. +304 staves, +1,748 bars. For
the second, a re-cut where the alignment paired the bar whole on one
staff: +30 staves (169 bars); a looser first try was wrong three times in
four, which showed most red staves aren't bars that cross a line.

**Why a report.** The sets change, and the red half is the next pool to
recover.

**What followed.** dataM5 and dataW4 built; the labeler's pairing view
reads them. Not yet trained on or uploaded. Re-pairing made faster (45 to
6 min): LilyPond's encoding cached, sources paired six at a time.

## 2026-10-22: Re-detecting the paired manuscripts

[Write-up](2026-10-22-redetection/)

**Context.** The pairing kept 7,297 of 11,608 detected staves. The user:
"reprocess and repair all paired manuscripts and harvest more bars", then
"Are there other improvements to make before redetection? The point of the
redetection is to get more bars for training or testing."

**Question.** What in detection loses bars, and how many come back when
it's fixed?

**Finding.** Staves measured short (grey paper, faint ruling, lines off the
trace, detector ends mid-line) and written staves missed in ruled slots.
Fixed in detect.py; re-detected, re-read and re-paired: +520 staves, +3,122
bars (+10%). Right ends on the reviewed staves within a space 47% → 59%.
Most staves still left out are reading mistakes, not detection's.

**Why a report.** The new sets replace the old ones for training, and the
detection changes reach the labeler's own proposals.

**What followed.** dataM4, dataW3, dataP3 and dataG213-3 built; not yet
trained on or uploaded.

## 2026-10-20: Philhar's site, beyond the quartets

[Notes](2026-10-20-philhar-site/)

**Context.** Philhar's Boccherini encodings already label our manuscripts.
His site is down but archived. The user: "it lists his lilypond sources for
many other works. On each composer page he lists the source for the works,
and some of them are also manuscript sources. So we have another potential
manuscript <-> lilypond paired dataset."

**Question.** Which of his works come from a manuscript in a period hand,
with LilyPond and a scan we can still get?

**Finding.** 38 composers, 251 LilyPond zips, all archived. Ten sets name
a manuscript; six are new 1750–1810 string music with scans online: 18
works, about 1,700 staves of parts. Best: Boccherini's op. 4 trios (Sibley
parts, and Berlin's Schober copies), Michael Haydn's quintet MH 411, and
Campioni's op. 7 duos. Same file layout as the quartets, other file names;
philhar.py reads them after renaming.

**Why a report.** It names the next hands to pair, and what pairing them
would need.

**What followed.** A sample of three works' LilyPond is in
`~/Data/manuscript-labeler/philhar-site/`. Nothing paired yet.

## 2026-10-20: Boccherini Manuscript Census

[Page](https://claude.ai/artifact/GEGbPnXax1fNfotaSK1pDy) · [folder](2026-10-20-manuscript-census/)

**Context.** Labelled Boccherini staves are the scarce training data. The
user asked: "How many staves of unlabeled (no lilypond or ossq encodings)
manuscripts other than op 48 do we have (boccherini-sources)? Can you give
me that breakdown?"

**Question.** How many manuscript staves are on disk, and which could get
labels, from where?

**Finding.** About 11,500 staves in 54 manuscripts. 2,916 are labelled and
in training (dataM and Madrid from Philhar's encodings, KHM 587 from
OSSQ's). About 2,880 more are in those same manuscripts but the first
pairing didn't keep them, about 1,870 have a Philhar encoding but were
never paired, and about 3,830 have no encoding. "Paired" had been read as
"labelled"; it isn't.

**Why a report.** It sizes the next sources of training data.

**What followed.** The user: "I can't believe we've been sitting on the
philhar pairings without trying to use them." Re-pairing dataM's sources
with the G. 213 fixes and pairing the seven unpaired ones started the same
day.

## 2026-10-20: What Modal has cost us so far

[Page](https://claude.ai/artifact/M4P24Eiua6etJvUnay9Tjq) · [write-up](2026-10-20-modal-compute/)

**Context.** The user is pricing compute for the modelling work: "I'd like
to understand how we used modal so far, and how much it's cost in
practice", with machines, cost, peak GPU memory, GPU utilization and
training speed, to see whether we could have more speed, lower cost or
both, and whether Modal's elastic billing fits our bursty work.

**Question.** What has Modal cost, on what, and what would change it?

**Finding.** $101.81 metered for 60.2 GPU-hours, all between 17 and 20
October; the public stage is nearly half. Training containers used about
one CPU core, and CPU-only changes slowed passes a lot, so the GPU
probably waits on batch building: more CPU workers, or an L4, may be the
cheaper win. Elastic billing fits this use; an always-on L40S pays only
past 300–400 GPU-hours a month. Peak GPU memory and utilization were never
logged.

**Why a report.** It sets the baseline for choosing compute.

**What followed.** Three timing runs (under $1) and two one-line logging
changes are proposed, not run.

## 2026-10-20: Drawn staves with clef changes

[Report](2026-10-20-clef-change-staves/)

**Context.** The OSSQ report found that every reader so far misses the
same four cello clef changes in the clean test, and that those passages
also draw false flags in the edition. The user asked how to fix the clef
detection problem and agreed to "pinning zeus, clef change data set and
flag". compare.py was changed to score the clef apart, and a set of 3,970
drawn staves with clef changes inside the staff was built (dataS4).

**Question.** With the clef-change staves in the drawn stage (Drawn 15k,
against Drawn 11k) and D4's chain otherwise unchanged, does the reader
write the clef changes, and at what cost elsewhere?

**Finding.** Mostly yes: clef errors 4 → 1, and pitch 316 bars against
311. Bars exact tied at 277 (+0, −11 to +11). In the edition's flag test
it caught the same 94 of 107 errors with 11 false flags against 14; the
clef-passage false flags remain. All inside the noise.

**Why a report.** It is the first targeted use of drawn staves: a set made
for one weakness, measured on it.

**What followed.** Not adopted yet. The second runs of D4 and D3L2-h96
come first, to tell small gains from luck.

## 2026-10-20: OSSQ's period staves in the public stage

[Report](2026-10-20-ossq-stage-1/)

**Context.** OSSQ-OMR pairs scanned string-quartet prints with their
encodings. The user asked for its staves to be prepared on Modal, kept to
music printed 1750–1800, and then: "I think we do 1) OSSQ staves." The
period subset (13,241 staves of Haydn, Mozart and Beethoven Op. 18) was
re-cropped to our convention and checked first.

**Question.** Does a public stage with OSSQ's print staves (Public 22k,
against Public 9k) make a better reader of our manuscripts, with D4's
other stages unchanged?

**Finding.** No. 268 of 347 bars against D4's 277 (−9, −21 to +3), with
pitch down most (302 against 311). Public 22k itself read unseen hands
better: OmniOMR 0.229 to 0.183, Dolores 0.117 to 0.112. Boccherini 3k
washed that out. The debrief guessed OSSQ's labels ignore the
cellos' clef changes; a check of all 13,241 showed they don't. Instead, 8
of the lost bars are four cello clef changes where the OSSQ reader left
out the clef sign but wrote the notes' real pitches, which compare.py,
placing notes by staff position, counts a 13th off. On three of the four,
D4 left the clef out too, with wrong pitches the scorer counts right; only
one (3 bars) is the OSSQ reader's own mistake. Without them, a tie.

**Why a report.** It was the main use planned for OSSQ, at $11.62, and it
closes that path for now.

**What followed.** D4 stays the default. The same day, G. 213's three
copies (the Sibley and Berlin prints, KHM 587) were paired with OSSQ's
encoding, which gives a print test if OSSQ is tried again.

## 2026-10-20: A drawn stage before the Boccherini stage, at 128 and 96 px

[Report](2026-10-20-synthetic-and-strip-height/)

**Context.** A drawn stage first had gained 12 to 14 bars before
Boccherini 2.9k, D1's recipe (Synthetic staves first, then real). The
brief had named 96 px as a candidate strip height for the next crowned
run, since it read as well as 128 and faster. The user asked for both:
Drawn 11k before Boccherini 3k, D3's last stage, and the 96 px change as
a fast follow.

**Question.** Does Drawn 11k help before Boccherini 3k, and does 96 px,
with and without it?

**Finding.** They only help together. At 128 px Drawn 11k did nothing
(270 against 272). At 96 px without it, reading fell to 260
(−12, beyond the noise); with it, 277 (80%), the best so far: +17 over 96
px alone, +7 over the released D3, which is inside the noise. Pitch
improved most (311 bars right). One run of each.

**Why a report.** It decides the next release: a candidate musvit-D4 that
reads as well or better and 30% faster.

**What followed.** Released the same day as musvit-D4, zeus-score 1.3.0's
default, on the grounds that it is as accurate and faster; the release reads
exactly as the run did (40 of 40 staves identical). A second run of each is
left for the next round of training.

## 2026-10-19: Smashcima for Segment Anything: tried, dropped

[Report](2026-10-19-smashcima/)

**Context.** We're teaching Segment Anything to trace each symbol of the
Berlin copyist's hand (KHM 602/603), so each note the reader reads can be
tied to its ink. Real training labels come from the classical pass, which is
only right in places, so we tried synthetic staves with exact masks:
- Verovio renders in the copyist's hand, and in five plain fonts;
- Smashcima, which writes staves out by hand from MUSCIMA++'s 50 writers.

**Question.** Does Smashcima's handwriting teach Segment Anything more about
a handwritten page than rendered fonts do?

**Finding.** No: it traced Berlin worse than no training at all (0.577
against 0.620; real labels 0.717). There are three reasons:
- the hand is a modern pen, not a quill;
- Smashcima 1.1.2 draws no slurs, ties, tuplets, grace notes or key
  signatures;
- our labels have a house style that clean masks don't share. A Berlin head
  label carries its stem stub.

**Why a report.** So that, a month from now, Smashcima doesn't look like an
untried idea, or a promising one with the wrong settings. The report shows
the model's own tracings beside ours.

**What followed.** Smashcima was dropped and its files deleted. Real labels
from our own pages remain the only thing that helps on the real hand. Next is
prompting each symbol on its own small tile, to raise stems: 0.70 with real
labels, 0.45 with Smashcima.
A hand-checked Berlin test set would separate the model's errors from our
labels' quirks.

## 2026-10-19: Segment Anything on the Berlin hand: real labels help, renders don't

[Report](2026-10-19-segment-anything/)

**Context.** The map knows where each symbol of a Berlin staff is and what
it is, but not its exact extent. SAM2 turns a point or a box into a mask, so
we prompted it from the map and fine-tuned its mask decoder: on the
classical pass's confident symbols from KHM 602, and on renders with exact
masks.

**Question.** What teaches SAM2 the Berlin hand: real labels, stricter real
labels, copyist renders, plain renders, or renders first and real after?

**Finding.** Only real labels: 0.717 on held-out KHM 603, against 0.620
untrained. Heads went from 0.55 to 0.85, stems from 0.19 to 0.70. Every
synthetic source scored below untrained on Berlin, and each was best on its
own renders. Renders then real tied real alone (0.706). Strict labels, a
quarter of the data, scored slightly lower (0.702). Stems are limited by the
mask's resolution. Over whole staves the classical pass still leaves less
ink unclaimed (2.8% against 6.9%).

**Why a report.** The runs' scores lived only in result files under ~/Data,
which is allowed to be lost, and in chat. The report keeps the method, all
seven decoders on four test sets, and the model's tracings on Berlin.

**What followed.** The classical pass stays the labeller. Proposed next:
prompt each symbol on its own small tile, to raise stems, dots and hooks; and
a hand-checked Berlin test set, to separate the model's errors from our
labels' house style. Smashcima was dropped (see its report).

## 2026-10-19: The pointer: the reader says where each symbol is

[Report](2026-10-19-pointer/)

**Context.** D3 reads well but never learned to point at what it reads, so
tying a reading to the ink was left to the classical map. The map is built
by hand from staff lines, heights and ink, and is right only in places. Of
the options proposed, the user chose option 1: have the reader point. They
asked for Dolores to be added once it was found to be a reasonable download.

**Question.** Does D3 already know where each note, rest and bar line it
reads sits on the staff? How does that compare with the classical map,
scored against exact places?

**Finding.** Yes. A head of 0.39 M parameters, trained with D3 frozen,
places 93% of notes within half a space on rendered staves of unseen music.
On KHM 603's good bars, 93% land within half a space of the map's. The map
places notes more tightly (0.07 against 0.10 space) but never finds 23–35%
of rests. Most pointer misses go sideways, worst in runs of repeated notes.
One Berlin staff of triple stops had its chord notes pulled toward the
middle one. Dolores raised its own test (70% to 81%) and left ours flat.

**Why a report.** The results existed only as logs in ~/Data and in chat.
This is the first time the classical map has been scored against exact
places.

**What followed.** Nothing yet. Proposed: keep places in left-to-right
order; combine the pointer (every note and rest), the classical map
(refined notes) and Segment Anything (masks from those points). Untested:
pointing from D3's own reading. Stage B wasn't needed.

## 2026-10-19: Synthetic staves first, then real

[Report](2026-10-19-synthetic-first/)

**Context.** Mixing drawn staves into the real training stage,
Boccherini 2.9k (S1), gave nothing on the clean test. The Smashcima paper trains on synthetic
staves first, then real ones, so we tried that order (SF), and then the
same with Philhar's own music drawn two ways, in a copyist's hand and in
plain print (PF), to ask whether the hand or the music matters.

**Question.** Does a drawn stage of its own (Drawn 11k, or Drawn Philhar
11k), before Boccherini 2.9k, help the reader on the clean test? Does the hand it's drawn in, or the music,
matter?

**Finding.** The order matters. SF2 read 278 of 347 bars (+12 on S0's 266,
+1 to +23) and PF2-copyist 280 (+14, +2 to +26). Copyist hand against
plain print (−6 for plain) and Philhar's music against OpenScore's (+2)
were inside the noise. One seed each.

**Why a report.** The runs finished overnight and their results sat in
summary files, unreported, until code review on 2026-10-20 turned them up.
The Copyist Staves page and the brief still said synthetic staves didn't
help; that was the mixed run.

**What followed.** Nothing yet. Proposed: a crowned run with the drawn
stage first (Boccherini 3k from SF1 or PF1-copyist), Madrid and Op. 32
scores for SF2 and PF2, and a second seed.

## 2026-10-19: Copyist Staves (backfilled)

[Page](2026-10-19-copyist-staves/) · [artifact](https://claude.ai/artifact/CNZpaaxfr9DejFz4DkHMCN)

**Context.** The MuSViT reader is weakest on hands it hasn't seen, and
labelled staves are few. So we drew staves in our copyists' hands from
labels alone: the 44,609 staves cut from the OpenScore quartets, laid out by
Verovio and redrawn by hand rules.

**Finding.** musvit-D1 reads the drawings about as well as real staves it
hasn't seen (17.2% symbol errors against 17.7%), so they sit inside what it
knows. Training with them reached a better practice exam sooner, but read
the clean test no better: 262 bars of 347 against 266. A first rebuild of
Berlin staves, from a map of every symbol and the copyist's own glyphs, is
at the top of the page.

**What followed.** The hand rules were judged too far from the manuscripts.
The work turned to rebuilding staves from the copyists' own glyphs, and to
synthetic masks for Segment Anything (see the Smashcima report). Later
that day, synthetic staves as a stage of their own, before the real one, did
gain: 278–280 bars against 266 (see Synthetic staves first, then real).

## 2026-10-19: Synthetic quartet staves (backfilled)

[Write-up](../experiments/synth/README.md)

**Context.** The recipe behind Copyist Staves: how a staff is drawn, which
hands, where the music comes from.

**Finding.** It's a method, not a result. Its results are in the MuSViT brief
and on the Copyist Staves page. It records that Smashcima was first passed
over because it can't draw key or time signatures, slurs, ties, grace notes
or tuplets.

## 2026-10-19: ISMIR 2026 papers (backfilled)

[Notes](../docs/ismir2026-papers.md)

**Context.** ISMIR 2026's 150 papers were read against our goal, handwritten
single parts in and engraved scores out, to find what bears on the labeler,
the readers and the plan in NEXT.md.

**Finding.** A reading list with each paper's bearing on us. The arXiv IDs
are confirmed, and the papers not on arXiv are marked as such. Five papers
were read in full.

## 2026-10-19: Research TODOs (backfilled)

[Notes](../docs/research-todos.md)

**Context.** The standing research plan for reading Boccherini's manuscripts
by machine, with a status on each item.

**Finding.** Item 1, fine-tuning Zeus, is done: the clean test went from 42%
(stock) to 65% (run J). The rest are open or in progress.

## 2026-10-18: Inside musvit-D3 (backfilled)

[Page](2026-10-18-inside-musvit-d3/) · [artifact](https://claude.ai/artifact/DxTgDxM6Uy9poktZJy9DgH)

**Context.** Made when musvit-D3 was released, to show what the reader
actually does. It follows one hard staff, the viola's string-crossing 32nds
in Op. 48/2 I, bars 27–29, which Zeus read none of right.

**Finding.** The page goes step by step: strip, patches, encoder, the
decoder's attention as it writes each symbol, and where it goes wrong. On an
unseen movement, D3 gets 78% of bars exact against Zeus's 65%. It ends with
what comes next: synthetic staves in our hands, a second held-out hand, and
mixing public staves back in.

**What followed.** Commits 71c4879, 8756df9 and e13c525 built and refined
it. Its "what comes next" became the synthetic-staves work.

## 2026-10-18: Zeus rebuilt on MuSViT; the D3 model card; the brief and next steps (backfilled)

[Write-up](../experiments/musvit/README.md) · [model card](../zeus-score/MODEL_CARD_MUSVIT.md) · [brief](../experiments/musvit/BRIEF.md) · [next](../experiments/musvit/NEXT.md)

**Context.** Item 3 of the research TODOs: would an encoder pretrained on
9.7 million IMSLP pages read our copyists better than Zeus's own? The bar
was run J's 65% on the clean test, with a stop if the first run didn't beat
it. The brief is the plan and day-by-day log.

**Finding.** Yes. musvit-D3 gets 270 of 347 bars exact against Zeus J's 225
(+13.0 points, 95% interval +9.2 to +17.0). It fixes most of the viola's
broken-chord 32nds. Two training stages, the larger encoder, larger adapters
and an 8-layer decoder each helped.

**What followed.** D3 was released (commit 7bec03a) and made zeus-score's
default (5ae301a). musvit-D1 was kept as the held-out reference. NEXT.md set
the order: crown a reader first, then explore synthetic staves and new hands.

## 2026-10-17: One Staff, Two Readers (backfilled)

[Page](2026-10-17-one-staff-two-readers/) · [artifact](https://claude.ai/artifact/M5jeeezZqfNww8hKaoLrUL)

**Context.** During the MuSViT work: why does Zeus fail on the viola's
32nds, and does the new reader see them differently? One staff (KHM 603,
Op. 48/2 I, bars 22–26) is shown as each model receives it.

**Finding.** Zeus packs each 16 px column into one step, 93 steps in all.
The reader keeps a grid of 992 patches of 16 × 16 px. A staff space is
about 11 px for Zeus and 14 px for the reader, and a 32nd note gets about 21
px of width against 28. In bar 25, Zeus drops two notes and loses the
pattern. The reader keeps all 16 notes and the rhythm, but reads the low A
a step or two low.

## 2026-10-16: Zeus, run J: model card (backfilled)

[Model card](../zeus-score/MODEL_CARD.md)

**Context.** Zeus packaged as zeus-score, with a model registry (commits
2c87ecb and c9149fd). The card records run J's training and the family's
history on the clean test.

**Finding.** Run J, epoch 8, adopted on 2026-10-16 in place of run G. It
gets 65% of bars exact on the clean test, against the stock model's 42%.

**What followed.** Two days later the MuSViT reader replaced it as the
default.

## 2026-10-15: Boccherini OMR Lab Report (backfilled)

[Page](2026-10-15-omr-lab-report/) · [artifact](https://claude.ai/artifact/9YA4M3Y8x9vtGHCvcQNSKB)

**Context.** A summary of the first two weeks (1–13 October): every model
trained, every data source and every result, for bar-line detection and Zeus
fine-tuning for the Op. 48 edition.

**Finding.**
- Bar-line detection is close to solved: 99% found on 8 unseen pages.
- Reading is not. Fine-tuning Zeus took a trained copyist from 45% to 81%
  of bars exact, and an unseen one from 55% to 65%.
- The gains come from labelled data in the hand being read. Data from other
  hands adds little.

**What followed.** The same day, the clean test (KHM 603 I) was set aside,
held out from every later decision (commit 7ad31b2).

## 2026-10-14: Zeus on other composers' manuscripts (backfilled)

[Write-up](../experiments/zeus/ossq/README.md)

**Context.** Does fine-tuning on Boccherini's copyists narrow Zeus? This
needed hands nobody trained on, with an encoding to score against. Three
quartet manuscripts from OSSQ-OMR, fetched from IMSLP, were used: Andrée,
Maier and Mayer.

**Finding.** Yes, on two of three hands. Bars exact for run G against the
untouched model: Maier 47% against 54%, Andrée 30% against 35%. Mayer,
whose writing is closer to the copyists', gained: 34% against 23%.

## 2026-10-12: Zeus Fine-Tunes (backfilled)

[Page](2026-10-12-zeus-fine-tunes/) · [artifact](https://claude.ai/artifact/3wqTa3curxdsXXHt625zki)

**Context.** Every Zeus fine-tune and detector retrain from 10 to 12
October, with what each trained on and how it scored, to decide when to
train again.

**Finding.** Best was run G, epoch 8: run F's recipe on 2,340 staves (2,246
paired automatically from Philhar's encodings, 94 labelled). It got 81% of
bars exact on KHM 602 II and 65% on the unseen Vma 1067 (1) II, with no
runaways.

## 2026-10-11: Philhar Manuscript Sources (backfilled)

[Page](2026-10-11-philhar-manuscript-sources/) · [artifact](https://claude.ai/artifact/Tkusnh9BaqA2DjkWxYBKMy)

**Context.** Philhar's encodings of other Boccherini sets could become
training data if their manuscripts' staves can be paired bar for bar without
labelling. This page tallies every set and source.

**Finding.** 1,905 of 4,025 detected staves on part copies (47%) were ready,
up from 192 a day earlier under a looser pairing rule. Detection is where
staves are lost, worst on Op. 32's hand (22%). Sources marked "check" got in
almost entirely by the new rule.

**What followed.** These staves went into run G's training (see Zeus
Fine-Tunes). The method went in as commit 1f76c6d.

## 2026-10-09: Zeus against the edition's encoding (backfilled)

[Write-up](../experiments/zeus/README.md)

**Context.** Could Zeus be a second source of transcription for the edition?
It was measured against the Op. 48/1 encoding, which is checked and taken
as right (commit 6bb200f).

**Finding.** Stock Zeus read 40% of KHM 602's bars entirely right. As a
checker it would flag 60% of bars, every one a false alarm. The write-up
grew to cover fine-tuning, training pairs without labelling, the clean test
and Apple's GPU plugin.

**What followed.** It led to the fine-tunes, then the MuSViT reader.

## 2026-10-09: A language model on the pages (backfilled)

[Write-up](../experiments/llm/README.md)

**Context.** Step 3 of the plan: can Claude say what a page is, whose part
it is, and read the editor's text marks, well enough to propose them? This
was a measured test before building anything in (commit cf0fb73).

**Finding.** Page kind was right on 93 of 95 pages, and the part was right
56 times in 57 where Claude named one. Marks: 124 of 167 right blind, 134
when offered the other sources' texts. Most differences were spelling
conventions.

**What followed.** The editor set the convention that mark text follows the
copyist. Claude was then built into the labeler for new pages and title
pages (commits 816bc45, 1c9b90c, 025f553).

## 2026-10-09: Crop edges (backfilled)

[Write-up](../experiments/crops/README.md)

**Context.** Can a model choose each staff's crop the way the editor does,
better than the old rule?

**Finding.** Yes, modestly. Within half a staff space of the editor's edge:
72% against 70% above the staff, 77% against 68% below, across 507 reviewed
staves. The editor's standard had tightened on the newest pages.

**What followed.** The labeler uses the learned crop (commit b738d42).

## 2026-10-07: Zeus on Our Manuscripts (backfilled)

[Page](2026-10-07-zeus-on-our-manuscripts/) · [artifact](https://claude.ai/artifact/TZUoUmrMSAgTjNBWHDHPJn)

**Context.** A first look at Zeus, OmniOMR's handwritten-music reader, on our
hands, before any training on them.

**Finding.** Its newest single-staff model read 11 test staves from four
sources: Berlin KHM 602 and 603, Paris RES 507 and Vma 1067. Each scan is
shown beside its reading. It never reads our alto clefs; it guesses treble
or bass, so readings are shown moved into the part's clef.

**What followed.** It was measured against the edition's encoding two days
later (Zeus against the edition's encoding).

## 2026-10-05: Bar-line bake-off (backfilled)

[Design](../experiments/barlines/README.md) · [results](../experiments/barlines/results.md)

**Context.** Which bar-line finder saves the editor the most rework? Every
method gets the same straightened staff line from the editor's reviewed
pages and is scored against the editor's bar lines (commit f526240).

**Finding.** It ran in four rounds, 5 to 8 October. On 8 pages no model saw,
the editor kept 92% and 90% of detected bar lines unchanged. Detectron2, as
a third voter, didn't earn its place (commit 5140c87).

**What followed.** The labeler's detection uses its own finder with two YOLO
models voting.

## 2026-09-27: Music Encoding Field Guide (backfilled; LMX added 2026-10-19)

[Page](2026-09-27-music-encoding-field-guide/) · [artifact](https://claude.ai/artifact/JM1SnfoDos1xi2wcE5Jiyf)

**Context.** Written before this repo existed, while building a converter
from RISM's Plaine & Easie incipits (658 Boccherini quartets) to MusicXML,
LilyPond and ABC. The project's encoding work leans on it: the edition is
LilyPond, the readers write LMX, and Verovio draws.

**Question.** Which formats hold what, and what survives converting between
them?

**Finding.** Almost nothing converts losslessly. Whether a format states
things outright or infers them from context predicts where converters break
better than how rich it is.

**LMX added (2026-10-19).** LMX, the readers' format, joined the ladder and
the matrix, with a section of its own and a real label from KHM 603. It
writes the accidental that is drawn, not the pitch that sounds, so reading
it means applying the key. The conversions to and from MusicXML are marked
as measured on this project's data: the 44,609 quartet staves, and labels
from the edition read back exactly.
