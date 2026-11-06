# musvit-D6: the edition's new movements in training, and the rare marks weighted up (2026-11-05)

D5 misses grace notes and double stops in copies it never trained on
([2026-11-03-open-model-bars](../2026-11-03-open-model-bars/)). No change
to its design or to how it was asked fixed that, so this tries data:
the movements the edition has finished since D5 trained, in the copies D5
never saw.

**Verdict: both runs read the held-out movement better than D5, with no
loss elsewhere.** On Op48-4 I (F-Po RES 507 (16), a copy no reader
trained on), run A gets 244 of 290 bars exact and run B 247, against D5's
233. Both gains are outside the noise (95% intervals +4 to +19 and +5 to
+23 bars). On the clean test they match D5 (283 and 284 of 347, D5 283);
on Dresden they are within half a point. Two of the grace notes no reader
or question head saw before (violin I 17 and 18) are now read.
**Released: run A as musvit-D6, zeus-score 1.6.0's default** (below).
The user chose A, the simpler recipe, as B's 3 more bars are within noise.

**2026-11-06: the labels' key was wrong for Op. 48 No. 4, and D6 is
released again.** Scoring in MCR (below) showed `labels.py` read the
edition's English note names as Dutch: `\key ef \major` became four
sharps, in Op48-4's labels and so in D6. Fixed, the set rebuilt, D6
retrained (D6-K): the same on Op. 48, better on Dresden (81.1%), without
the wrong key; **released as musvit-D6@2026-11-06, zeus-score 1.7.0's
default.** Readers guess the key on staves that show none, so it can now
be given them from Structure.ily (`zeus-score read --key`). The paper's
own page model, run on our pages, doesn't read them (MCR 94%).

## The runs

D5's recipe exactly (`train_b6k.py --init SF1-h96 --op48 3 --seed 1`: from
Drawn 11k, 24 passes of a 30-pass schedule, LoRA rank 64 on attention and
MLP), with the new staves added and weighted as Op. 48's are (three
times). Driver: `experiments/musvit/drivers/train_d6.py`.

| | new staves | weighting | count head | staves a pass |
|---|---|---|---|---|
| **D6-A** | Op48-4 II (RES 507 (16), 32 staves), Op48-6 I and II (RES 507 (18), 89), as `dataL3` | as D5 | no | 7,828 |
| **D6-B** | the same | every staff with a grace note or chord listed once more (2,574) | yes, loss weight 0.5 | 10,402 |

- **Held out:** Op48-4 I (RES 507 (16), 36 staves), the seeing test's
  bars; the clean test (KHM 603 I); Dresden (Mus.3403).
- **The count head** (`proto.py --count-loss`): a small head on the
  memory the decoder reads, trained beside the reader to give each
  staff's number of grace notes and chord notes, read from its LMX. The
  question heads showed D5's encoder dropped grace-note detail that
  MuSViT's pretraining had kept; this asks the encoder to keep it. Its
  weights go to `counts.pt`, apart from the reader's, so the reader reads
  as any other.
- **The sets:** `dataset.py` as of 18:27 (it now labels multi-bar rests;
  these movements have none, and 15 whole-bar rests D5's vocabulary
  already has). 3 staves of Op48-4 I and 1 of Op48-6 left out by its
  checks.

## Results

Every reader read here the same way (`read.py --device mps`, scored by
compare.py bar by bar).

| reader | Op48-4 I, bars exact (held out) | grace-note bars found (of 29) | double-stop bars found (of 36) | clean test (of 347) | Dresden, symbol errors |
|---|---|---|---|---|---|
| musvit-D5 | 233 | 18 | 30 | 283 | 9.6% |
| **D6-A** | **244** (+11; won 13, lost 2) | 20 | 28 | 283 | 10.2% |
| **D6-B** | **247** (+14; won 18, lost 4) | 21 | 28 | 284 | 9.5% |

None marks a grace note or double stop in a bar of the seeing test
without one (d′: D5 2.78 and 3.38, A 2.96 and 3.18, B 3.05 and 3.18).
Dresden's symbol errors count every token (beams, slurs and
articulations too), so half a point there is style, not notes.

- **Data was the lever.** A, the new movements alone, gives most of the
  gain: 11 bars on the movement held out. D5's misses there were the
  copyist's hand, and 32 staves of it (one other movement) taught a good
  part of it.
- **Grace notes in this hand are now partly read.** Of the 11 bars whose
  grace note D5 missed, A finds 2 (violin I 17 and 18) and B 3 (also
  violin II 4, the bar in `../2026-11-03-open-model-bars/grace-note-vn2-4.jpg`).
  Violin I 17 and 18 were among the 8 no encoder's question head and no
  one-look Opus found: the information was in the picture, and examples
  of this hand were what was missing.
- **Double stops didn't move.** A and B each find 28 of 36, D5 30; the
  bars traded (B gains viola 47, loses viola 32, 51 and cello 62) are
  within noise. Weighting them up and counting them didn't help here.
- **B against A: +3 bars, within noise**, for twice the training time
  (123 s a pass against 57). Its extra grace note (violin II 4) is the
  one the pretrained encoder's question head also found.

## In the field's standard measure: symbol error rate

OMR papers report symbol error rate (SER): the edits (insertions,
deletions, substitutions) needed to turn a staff's output into its truth,
over the truth's length, summed over the staves. The MuSViT paper reports
it on its staff-level benchmarks. Here it is `proto.py --epochs 0` on each
held-out set's staves, over every LMX token (notes, rests, durations, and
beams, slurs, ties and articulations too):

| held-out set | staves | musvit-D5 | musvit-D6 | staves exact, D5 → D6 |
|---|---|---|---|---|
| Op48-4 I, F-Po RES 507 (16) | 36 | 14.7% | **12.4%** | 0 → 1 |
| Op48-2 I, D-B KHM 603 (the clean test) | 65 | 9.2% | 9.2% | 11 → 14 |
| Dresden Mus.3403 | 354 | 9.6% | 10.2% | 44 → 39 |

The same story as bars exact: better on the copyist it gained, the same
elsewhere. (Op48-4 I's labels had the wrong key, below; D6, trained on
Op48-4 II's, writes it on 13 staves and D5 on none, but that is 13 tokens
of 5,761, at most 0.2 points of the 2.3. These are against the old
labels.) Two cautions in comparing with published numbers:
- **Different tokens and data.** These are LMX tokens on our copyists;
  the MuSViT paper's are another encoding on other corpora (its nearest,
  FMT, handwritten modern notation: about 30% with a probe head on a
  frozen encoder). The numbers rank our readers; they don't place them
  against the paper's.
- **Markings count as much as notes,** and in the pairing's labels (Dresden)
  they follow the encoding, not the copyist, so SER there rewards the
  labels' style (reports/2026-10-22-boccherini-6k). Bars exact in notes
  and rhythm, the measure-level rate this report leads with, is the one
  that tracks the edition's work.

Not computed: OMR-NED (the Sheet Music Benchmark's measure, which counts
edits per kind of symbol on MusicXML); the LMX converts to MusicXML, so it
could be.

## In correction effort: Musical Correction Rate (MCR)

MCR is new at ISMIR 2026 (Hornbogen and Valentin, "Measure for Measure"),
proposed because it tracks the work of correcting a reading better than
SER or OMR-NED (their study of 46 pages). Each note is an event (pitch as
MIDI, duration, onset, staff, grace, and its slurs, articulations and
ornaments); measures are aligned, then the notes within them; a wrongly
described note costs one per attribute that differs, an extra note 1 to
delete, a missing one 2 to enter, over the cost of retyping from blank.
0 is perfect. Scored here with the authors' package (`mcr-metric` 1.1.0,
MIT) by `experiments/zeus/mcr_score.py`: each held-out staff's reading and
its label, both turned from LMX into MusicXML by the lmx library. A
reading lmx can't turn into MusicXML (a voice running past its bar; 2 or
3 staves a reader) is scored as empty, the cost of retyping the staff.

| reader | clean test (KHM 603 I, 65 staves) | without unconvertible readings and markings |
|---|---|---|
| musvit-D5 | 11.5% | 5.6% |
| **musvit-D6** | **9.9%** | 5.5% |

The paper's own model scores 9.91% zero-shot on OpenScore Quartets
camera pages (printed music, whole pages, finding its own structure);
D6 reads a staff at a time from the editor's crops and bar boxes, so the
two numbers are not a ranking, only the same scale.

**Op48-4 I: the labels had the wrong key, now fixed.** MCR compares
pitch as MIDI, so a key signature or clef counts on every note it
inflects. Looking at why Op48-4 I scored about 21% showed its labels'
key was wrong: four sharps, where Structure.ily has `\key ef \major`
(three flats). `labels.key_fifths` read LilyPond's Dutch note names only;
the edition writes English ones (`ef`, `bf`, `fs`; `\language "english"`
in its common/style.ily), and `ef` read as E. It now reads both (only
`es` and `as` mean different notes in the two, and a Structure.ily that
states `\language "english"` settles them). Of Op. 48 only No. 4 changes
(I and II, four sharps to three flats). Of the built sets only `dataL3`
had it: its rebuild, `dataL4`, differs in that one token on its 68
Op48-4 staves and nothing else. So the 32 Op48-4 II staves D6 trained on
said four sharps, and D6 writes four sharps on 13 of Op48-4 I's 36. The
notes in those labels were right (LMX writes a pitch's letter and octave,
and accidentals as printed), and compare.py, which scores pitch with the
key apart, isn't affected: bars exact and the seeing test stand.
zeus-score carries the same parser, so it writes the wrong key token for
Op48-4 (a token, not the notes; key objections aren't among the
edition's flag kinds).

Scored against the corrected labels, Op48-4 I is mostly a test of
guessing: this copy writes the clef and key on each part's first staff
only (4 of the 36), and both readers get the key wrong on nearly every staff, and the clef on
a quarter of them. `--label-signature` gives each reading the label's
first key and clef (moving its notes to where they sit on the staff under
that clef), to score the notes alone. Over the 34 staves both readers'
readings turn into MusicXML:

| reader | Op48-4 I, own key and clef | wrong key, wrong clef (of 36) | given the label's key and clef | clean test, either way |
|---|---|---|---|---|
| musvit-D5 | 27.2% | 32, 9 | 6.6% | 7.7% |
| **musvit-D6** | 29.2% | 34, 8 | **5.6%** | **7.4%** |

On the clean test the label's key and clef change nothing (that copy
writes them on every staff). Over all 36 Op48-4 I staves, the
unconvertible ones counted as empty, D6 scores 9.8% given the key and
clef, D5 8.3%: D6 has two readings lmx can't convert, D5 one. A reader
that guessed the key from the music before (the previous staff, or
Structure.ily, which zeus-score already reads) would score close to the
"given" column.

## The key given: Structure.ily's, for staves that show none

The reader writes each staff's key from what it sees. On a staff without
one it guesses, and it guesses a definite key, not none: its commonest,
two sharps or one. Each staff is read alone, so it can't carry the key
over from the part's first staff. On Op48-4 I (three flats throughout;
each part's first staff written, which every reader reads right):

| part | D5 | D6 (2026-11-05) | D6-K (2026-11-06) |
|---|---|---|---|
| violin I | −3 2 2 2 2 2 1 1 2 2 1 | −3 4 2 4 2 4 1 4 4 4 4 | −3 2 2 2 2 2 1 1 2 −3 1 |
| violin II | −3 2 2 2 2 2 2 2 1 | 4 1 1 1 4 1 4 1 1 | −3 2 1 0 2 0 1 2 1 |
| viola | −3 2 2 2 2 2 2 1 | −3 1 2 1 2 2 1 1 | −3 1 2 2 2 2 1 1 |
| cello | −3 2 2 2 2 2 2 1 | 4 1 4 1 4 2 2 1 | −3 2 2 1 2 2 −3 1 |

(Fifths: sharps positive. D6's four sharps are the wrong labels it
learned; D6-K, trained on corrected ones, doesn't write them.) The notes
give no clue: in E-flat the Bs, Es and As carry no written flats.

So the key now comes from Structure.ily: `read_cached` takes each
reading's first symbols, and `read.py --key` and `zeus-score read --key`
(1.7.0) begin each staff `measure key:fifths:<key in force at its first
bar>`, the reader going on from there. On Op48-4 I:

| reader | bars exact | MCR, own key | MCR, key given | MCR, key and clef given (`--label-signature`) |
|---|---|---|---|---|
| D5 | 233 → 236 | 27.2% | 11.7% | 6.6% |
| D6 (2026-11-05) | 244 → 242 | 29.2% | 11.3% | 5.6% |
| D6-K (2026-11-06) | 242 → 243 | 26.8% | 13.3% | 6.1% |

(MCR over the 34 staves all readings turn into MusicXML; bars exact,
which scores pitch apart from the key, read without → with it.) The notes
read the same with the key given; MCR more than halves. What's left is
the clef: 8 to 13 staves a reader read in a wrong clef, which moves every
note. The clef in force is the labels' (the editor marks it per staff),
so the same start could carry it; not tried yet.

## The key fixed: D6-K (released as musvit-D6@2026-11-06)

D6-A's recipe again (`train_d6.py --name D6-K --new dataL4`), the new
movements' set rebuilt with the corrected key (`dataL4`: 68 Op48-4 staves
differ from `dataL3` in that token only).

| reader | Op48-4 I, bars exact | clean test, bars exact | clean test, MCR | Dresden, bars exact (notes and rhythm) | Dresden, symbol errors |
|---|---|---|---|---|---|
| musvit-D5 | 233 | 283 | 11.5% | 79.9% | 9.6% |
| D6-A (2026-11-05) | 244 | 283 | 9.9% | 78.5% | 10.2% |
| **D6-K (2026-11-06)** | 242 (won 4, lost 6 against D6-A) | 283 (won 5, lost 5) | 9.9% | **81.1%** (15 staves miscounted, D6-A 22) | 9.8% |

The same reader on Op. 48, a little better on Dresden (within the
noise of two runs of one recipe, which have differed by 12 miscounted
staves), and without the wrong key. Released in D6-A's place as
musvit-D6's new version.

## The paper's model on our pages

page-omr (Hornbogen and Valentin's reader, `tobiashornbogen/page-omr-a1-kern`,
the zero-shot pretrain: DINOv2-base and a 12-layer decoder, whole pages
at 518×728 to **kern; code at e369a44) read every page of the two
held-out sets whose staves are all held out: 7 of KHM 603 I and 2 of
Op48-4 I, about 2 minutes a page on the Mac's GPU (`page-omr/`: pages.py, run.py, score_pages.py,
and its readings in `kern/`). Each page scored with mcr-metric against
its staves' labels joined; D6's readings of the same staves joined the
same way.

| page | notes | page-omr | D6 | D6, key given |
|---|---|---|---|---|
| KHM 603 p. 2 | 285 | 99.2% | 1.7% | |
| KHM 603 p. 3 | 215 | 91.1% | 2.8% | |
| KHM 603 p. 8 | 322 | 100% | 17.6% | |
| KHM 603 p. 9 | 236 | 92.0% | 8.8% | |
| KHM 603 p. 14 | 260 | 100% | 14.0% | |
| KHM 603 p. 15 | 210 | 100% | 18.5% | |
| KHM 603 p. 21 | 142 | 89.3% | 9.3% | |
| RES 507 (16) p. 7 | 192 | 89.5% | 42.5% | 20.1% |
| RES 507 (16) p. 10 | 330 | 100% | 25.0% | 5.1% |
| **all** | 2,192 | **94.2%** | **15.4%** | |

It doesn't read these pages. On every one it falls into a loop until its
3,072-token limit: a whole-bar rest a bar (763 bars of them on four
pages), or the same C-major bar of eighths and a quarter; every page
opens in 4/4 with a flat key or none (KHM 603 I is in three sharps,
Op48-4 I in three flats; both in 2/4). Where its MCR is below 100%, its
hundreds of repeated Cs pair partly with real notes. Its training was
printed music rendered from PDMX; these are landscape manuscript part
pages squeezed into its portrait input. The paper reports 9.91% zero-shot
on camera photos of printed quartets; handwriting is outside what it
learned. (D6's page MCR is higher than its staff MCR: a staff it reads
with a bar too many or too few shifts the page's measure alignment.)

## The release: musvit-D6 (run A)

Checked as D5 was before its release:

- **Dresden in notes and rhythm** (`held_out.py`, markings apart; 354
  staves, 3,172 bars): D6 78.5% of bars exact, D5 79.9%. The gap is all
  miscounted staves (22 against 18); on the 325 staves both count right,
  85.8% and 85.4%. Within the run-to-run noise (two runs of D4's recipe
  miscounted 8 and 20). D5's cached readings were from before Dresden's
  set gained a staff (353 then), so it was read again.
- **Flags for the edition** (`flag_test_local.py`, Op48-2 I, after the
  read, 107 later corrections):

| floor | reader | flagged | wrong | false | caught |
|---:|---|--:|--:|--:|---|
| 2 | musvit-D6 | 108 | 95 | 13 | 95 |
| 2 | musvit-D5 | 108 | 95 | 13 | 95 |
| **3** | **musvit-D6** | **106** | **94** | **12** | **94** |
| **3** | **musvit-D5** | **106** | **95** | **11** | **95** |
| 4 | musvit-D6 | 105 | 93 | 12 | 93 |
| 4 | musvit-D5 | 103 | 95 | 8 | 95 |
| 6 | musvit-D6 | 100 | 92 | 8 | 92 |
| 6 | musvit-D5 | 100 | 93 | 7 | 93 |
| 8 | musvit-D6 | 99 | 91 | 8 | 91 |
| 8 | musvit-D5 | 98 | 92 | 6 | 92 |

  At the edition's floor of 3, one error apart (D5 catches violin I 59,
  D6 doesn't) and one false flag. Op48-2 I is KHM 603's copyist, which D6
  gained nothing on; the floor stays 3.

**Release:** musvit-D6-2026-11-05 (`release.py D6-A reader.pt`),
reader.safetensors sha256
388863c1968a7ce94e1c3dad2c3de5660c5e4ce6a23d686981cc986051c335b0, archive
d0d0bb01c2db4d0d3fda4a1cacafe589d4bbe56e60c83e98043d60e00f5e1804.
zeus-score 1.6.0 makes it the default (D5 and the earlier readers stay
listed); the edition's `scripts/encode.py` pins `musvit-D6@2026-11-05`.
The pairing and Try pairing still read with D4 and D5 as before (their
readings are cached under those names).

**Release, 2026-11-06:** musvit-D6-2026-11-06 (`release.py D6-K
reader.pt`), reader.safetensors sha256
ff40e756d4d127ab882148ac518b1c5c5fae14673bbb0ca97ac4db31e4a8cc0d, archive
bf175218ba2ed905e4e03141e570ba8c94563b0632a2fbf8620fd916a91fd4e4, trained
at d940f33. zeus-score 1.7.0 makes it the default (`musvit-D6` names it;
the 2026-11-05 version stays listed) and adds `read --key`. Flags for the
edition against the 2026-11-05 version (Op48-2 I, 107 later corrections):

| floor | version | flagged | wrong | false |
|---:|---|--:|--:|--:|
| 2 | 2026-11-06 | 106 | 95 | 11 |
| 2 | 2026-11-05 | 108 | 95 | 13 |
| **3** | **2026-11-06** | **105** | **94** | **11** |
| **3** | **2026-11-05** | **106** | **94** | **12** |
| 4 | 2026-11-06 | 103 | 93 | 10 |
| 4 | 2026-11-05 | 105 | 93 | 12 |
| 6 | 2026-11-06 | 98 | 92 | 6 |
| 6 | 2026-11-05 | 100 | 92 | 8 |

At floor 3 the same errors caught, one false flag fewer. The edition's
`scripts/encode.py` pins `musvit-D6@2026-11-06`.

## What's next
- **The loop.** Each finished movement taught D6 something about its hand;
  the next reader should take the movements finished after it, as this
  one did.
- **More of the new music:** the Vma copies of Op48-4 and Op48-6
  (F-Pn Vma-ms-1067-2 and -4, about 1,400 bars, once their bar boxes are
  reviewed: 141 of 716 and 0 of 1,013 are). Vma-ms-1067-2 I is Op48-4 I's
  music and stays out while that movement is the test.
- **The clef, given as the key is.** With the key given, what's left of
  Op48-4 I's MCR is staves read in a wrong clef; the labels' clef could
  start the reading the same way.
- **Op. 48's older sets** were built on 18 October; corrections to those
  encodings since aren't in training. A rebuild is a few minutes.

## Reproduce

```
uv run experiments/zeus/dataset.py ~/Dropbox/Code/boccherini-opus-48 --source F-Po_RES-507-16 --movements II --out <zeus>/dataL3
uv run experiments/zeus/dataset.py ~/Dropbox/Code/boccherini-opus-48 --source F-Po_RES-507-16 --movements I --out <zeus>/dataL3   # held out
uv run experiments/zeus/dataset.py ~/Dropbox/Code/boccherini-opus-48 --source F-Po_RES-507-18 --movements I II --out <zeus>/dataL3
modal volume put musvit-staves <zeus>/dataL3 /dataL3       # and each set's rare.txt: its staves with a grace note or chord
uv run experiments/musvit/drivers/train_d6.py --name D6-A
uv run experiments/musvit/drivers/train_d6.py --name D6-B --rare 1 --count-loss 0.5
modal volume get musvit runs/D6-A ~/.cache/manuscript-labeler/musvit/runs/
uv run experiments/musvit/read.py ~/Dropbox/Code/boccherini-opus-48 --run D6-A --source F-Po_RES-507-16 --movements I --device mps
uv run experiments/musvit/read.py ~/Dropbox/Code/boccherini-opus-48 --run D6-A --device mps          # clean test
uv run experiments/musvit/proto.py held-D6-A --init D6-A --epochs 0 --train <zeus>/dataW4/samples.D-Dl_Mus.3403-P-513.txt \
  --dev <the same> --device mps
uv run experiments/musvit/held_out.py <zeus>/dataW4/samples.D-Dl_Mus.3403-P-513.txt --runs D5-B6k-d11-op48x3-s1 D6-A
uv run experiments/zeus/mcr_score.py <zeus>/test-clean/samples.D-B_KHM-603-I.txt --readings experiments/zeus/answers/D-B_KHM-603-musvit-{D5-B6k-d11-op48x3-s1,D6-A}-mps.json
uv run experiments/zeus/dataset.py ... --out <zeus>/dataL4    # the three dataset.py lines again, keys fixed
uv run experiments/zeus/mcr_score.py --label-signature <zeus>/dataL4/samples.F-Po_RES-507-16-I.txt --readings experiments/zeus/answers/F-Po_RES-507-16-musvit-{D5-B6k-d11-op48x3-s1,D6-A}-mps.json
uv run experiments/musvit/read.py ~/Dropbox/Code/boccherini-opus-48 --run D6-A --source F-Po_RES-507-16 --movements I --device mps --key
modal volume put musvit-staves <zeus>/dataL4 /dataL4
uv run experiments/musvit/drivers/train_d6.py --name D6-K --new dataL4
uv run --with numpy --with pillow python reports/2026-11-05-musvit-d6/page-omr/pages.py <pages>
uv run reports/2026-11-05-musvit-d6/page-omr/run.py tobiashornbogen/page-omr-a1-kern <pages>/*/
uv run reports/2026-11-05-musvit-d6/page-omr/score_pages.py <pages>
uv run experiments/musvit/release.py D6-A reader.pt musvit-D6 2026-11-05 --out <dir> --licence <LICENSE> --notice <NOTICE.md>
uv run reports/2026-10-20-clef-change-staves/flag_test_local.py <dir>/musvit-D6@2026-11-05 musvit-D6@2026-11-05 \
  388863c1968a7ce94e1c3dad2c3de5660c5e4ce6a23d686981cc986051c335b0 -- musvit-D6@2026-11-05 musvit-D5@2026-10-23
```

`<zeus>` is `~/.cache/manuscript-labeler/zeus`. The runs are on the Modal
volume `musvit` (`runs/D6-A`, `runs/D6-B`); their training logs are here.
The readings are in `experiments/zeus/results/` (`*-musvit-D6-*-mps.json`).

## Cost

- **Modal** (`modal billing report`, hourly, the two apps): D6-A $0.86,
  D6-B $1.86 (L40S, 24 passes of 57 s and 123 s); D6-K, 2026-11-06,
  $1.37 (24 passes of 89 s). $4.09 in all.
- **Mac (M1):** building the sets, about 2 minutes; reading and scoring
  three readers on the held-out movement, two on the clean test and
  three on Dresden, about 45 minutes; the release's checks (Dresden in
  notes and rhythm, the flag test) and packaging, about 30 minutes;
  2026-11-06, D6-K's and the key-given readings and checks, about an
  hour, and page-omr on 9 pages, about 20 minutes.
