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
elsewhere. Two cautions in comparing with published numbers:
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

## What's next
- **The loop.** Each finished movement taught D6 something about its hand;
  the next reader should take the movements finished after it, as this
  one did.
- **More of the new music:** the Vma copies of Op48-4 and Op48-6
  (F-Pn Vma-ms-1067-2 and -4, about 1,400 bars, once their bar boxes are
  reviewed: 141 of 716 and 0 of 1,013 are). Vma-ms-1067-2 I is Op48-4 I's
  music and stays out while that movement is the test.
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
uv run experiments/musvit/release.py D6-A reader.pt musvit-D6 2026-11-05 --out <dir> --licence <LICENSE> --notice <NOTICE.md>
uv run reports/2026-10-20-clef-change-staves/flag_test_local.py <dir>/musvit-D6@2026-11-05 musvit-D6@2026-11-05 \
  388863c1968a7ce94e1c3dad2c3de5660c5e4ce6a23d686981cc986051c335b0 -- musvit-D6@2026-11-05 musvit-D5@2026-10-23
```

`<zeus>` is `~/.cache/manuscript-labeler/zeus`. The runs are on the Modal
volume `musvit` (`runs/D6-A`, `runs/D6-B`); their training logs are here.
The readings are in `experiments/zeus/results/` (`*-musvit-D6-*-mps.json`).

## Cost

- **Modal** (`modal billing report`, hourly, the two apps): D6-A $0.86,
  D6-B $1.86 (L40S, 24 passes of 57 s and 123 s). $2.72 in all.
- **Mac (M1):** building the sets, about 2 minutes; reading and scoring
  three readers on the held-out movement, two on the clean test and
  three on Dresden, about 45 minutes; the release's checks (Dresden in
  notes and rhythm, the flag test) and packaging, about 30 minutes.
