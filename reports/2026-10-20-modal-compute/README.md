# What Modal has cost us so far (2026-10-20)

How we've used Modal since the account opened, what it cost, and whether
we could get more speed, a lower cost, or both. Billing figures are
measured (`modal billing report`, pulled 2026-10-20 at 4 pm EDT). Times
are EDT unless marked UTC.

## Summary

**Total to date: $101.81 metered, for 60.2 GPU-hours.** That is about
$72 out of pocket after Modal's $30 monthly credit (the brief recorded
the credit being applied on 2026-10-18). Every dollar fell in 87 hours,
from 1 am on 2026-10-17 to 3 pm on 2026-10-20. Billing shows nothing
before then.

**Spend by kind of work:**

| kind of work | GPU | GPU-hours | $ | share |
|---|---|---:|---:|---:|
| Reader training, public stage (Public 9k and Public 22k) | L40S, L4 | 25.1 | 47.50 | 47% |
| Reader training, Boccherini stage | L40S, L4 | 13.1 | 24.40 | 24% |
| Reader training, drawn stage (Drawn 11k, Drawn 15k, Drawn and Engraved Philhar 11k) | L40S | 2.8 | 5.60 | 6% |
| MuSViT pretraining on our unlabelled staves | L40S | 0.6 | 1.11 | 1% |
| Readings and benchmarks (clean test, Madrid, public tests) | L4 | 5.7 | 4.78 | 5% |
| Segment Anything (`copyist-sam`) | L4 | 11.5 | 15.29 | 15% |
| The pointer (`musvit-pointer`) | L4 | 1.3 | 1.11 | 1% |
| Data prep: cutting staves, OSSQ staves and checks | CPU | 0.1 | 2.02 | 2% |
| **Total** | | **60.2** | **101.81** | |

By resource: L40S $72.71 (37.3 h), L4 $18.30 (22.9 h), memory $6.54,
CPU $4.24. Memory is mostly Segment Anything's ($5.52; see below).

**GPUs used:** two kinds. The L40S (48 GB) for nearly all reader training
since the afternoon of 2026-10-17. The L4 (24 GB) for the first four
training runs, every reading, Segment Anything and the pointer. No A10,
A100 or H100 has been used. No Zeus fine-tune has run on Modal; those ran
on the Mac's CPU before the account opened.

**Typical run, on an L40S, one GPU each:**

| stage | wall time | $ |
|---|---|---:|
| Boccherini stage (1.5k–3.4k staves) | 10–30 min | 0.50–0.95 (median about 0.70) |
| Drawn stage (11k–15k staves) | 20–40 min | 0.63–1.24 |
| Public 9k | 1.4–2.7 h | 2.80–5.52 |
| Public 22k | 5.1 h | 10.30 |

A whole reader like musvit-D4 (Public 9k → Drawn 11k → Boccherini 3k, at
96 px) cost $4.24 and 2.1 GPU-hours. Redoing only its last two stages
costs about $1.40.

**The burst pattern:** four busy days, nothing before them.
- GPUs were running in 55 of the 87 hours. The longest idle gap was 5
  hours.
- Daily spend: $45.65 on the 17th, $17.62 on the 18th, $19.83 on the
  19th, $18.71 on the 20th (to 3 pm).
- At peak, about four GPUs ran at once (sweeps of 4–6 runs on the
  evening of the 17th). On average, 0.7 GPUs ran across the 87 hours.
- Over October so far, that is 4 busy days in 20.

**Speed against cost:**
- **The training loop probably waits on the CPU.** It isn't measured
  directly, but three things point to it:
  - Billing shows our training containers used about 1.0 CPU core on
    average. Each batch is decoded and resized on the main thread,
    eight staves at a time.
  - Two changes that only add CPU work slowed a pass a lot. Zeus's
    augmentation took B0's 25 s pass to 49 s (B3, same model). Reading
    in colour took D1's 39 s to 55 s (D1c), with the same GPU work.
- **If so, a faster GPU buys nothing yet.** Feeding the GPU from several
  CPU workers is the cheapest speed-up on offer. Eight cores cost $0.38 an
  hour on Modal, against the L40S's $1.95. That pays for itself if a pass
  gets more than about 16% faster. The gain is unknown until it's measured.
- **96 px strips are faster, measured.** A pass took 11–45% less time
  than at 128 px (Drawn 11k: 182 s to 100–110 s). Boccherini 3k at 96 px
  took 35 s a pass from one starting point and 47–48 s from another; we
  don't know why. The clean test read as
  well (reports/2026-10-20-synthetic-and-strip-height).
- **L40S against L4:** the L40S ran the full encoder (89M) with bf16 at
  $0.053 a Public 9k pass. The L4 ran the light encoder (28M, float32) at
  $0.063 a pass. So the L40S was faster and cheaper, on a bigger model.
  The same recipe hasn't been timed on both. If the loop is CPU-bound,
  the L4 might be nearly as fast for 41% of the price.
- **Memory on Segment Anything:** memory was 36% of that app's bill. It
  averaged about 60 GiB, probably because every training window was sent
  in the function call and held in memory.

**Does per-second, elastic billing fit?** Yes, at our current use.
- An always-on rented L40S costs $577–796 a month (RunPod, community or
  secure cloud). This month we've paid Modal about $100 metered.
- An always-on GPU only beats Modal past about 300–400 L40S-hours a
  month. That would mean working like the 17th to 20th (about 15
  GPU-hours a day) every day for a month.
- One always-on GPU would also have run each sweep one run at a time. The
  overnight sweeps on the 17th would have taken up to four times as long.
- A local GPU: assume a workstation with one 32 GB card at about
  $3,000–4,000 (an assumption, not a quote). At $70–100 a busy month, it
  would take three to five years to pay back. It also runs one job at a
  time. The Mac mini can't train the reader at all (no pass finished in
  30 minutes).
- What elastic costs us: Modal's L40S is $1.95 an hour against RunPod's
  $0.79–1.09. At this month's use that premium is about $40–50. If a month of
  daily sweeps comes, renting a GPU for that month would be cheaper.

**Not measured:** peak GPU memory and GPU utilization. Neither was ever
logged. An estimate and two one-line ways to measure them are below.

## Runs

Every reader-training app, one GPU each. **GPU-h** is billed GPU time; for
a one-GPU app it is the container's wall time. **s/pass** is the median
training time of one pass over the stage's staves, from the run's log. It
leaves out dev scoring, start-up and copying the staves. **In passes** is
the share of billed GPU time spent in training passes. It is not GPU
utilization. **Started** is the first billed hour, in UTC. The four L4
runs used MuSViT-light (28M) in float32. Every L40S reader run used the
full encoder (89M) with bf16.

| started (UTC) | run | stage | px | GPU | staves | passes | s/pass | staves/s | GPU-h | $ | in passes |
|---|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 10-17 06h | noPublic-602II | Boccherini stage | 128 | L4 | 2,536 | 30 | 80 | 32 | 0.95 | 0.80 | 70% |
| 10-17 08h | stage1-public | Public 9k | 128 | L4 | 8,765 | 30 | 284 | 31 | 2.61 | 2.23 | 91% |
| 10-17 11h | stage2-602II | Boccherini stage | 128 | L4 | 2,536 | 15 | 75 | 34 | 0.36 | 0.31 | 86% |
| 10-17 16h | stage2-J | Boccherini stage | 128 | L4 | 2,568 | 15 | 76 | 34 | 0.36 | 0.31 | 89% |
| 10-17 18h | stage1-full | Public 9k | 128 | L40S | 8,765 | 60 | 97 | 90 | 1.73 | 3.47 | 93% |
| 10-17 20h | stage2-full-602II | Boccherini stage | 128 | L40S | 2,536 | 21 | 27 | 94 | 0.20 | 0.40 | 79% |
| 10-17 20h | stage2-full-J | Boccherini stage | 128 | L40S | 2,568 | 12 | 27 | 95 | 0.13 | 0.26 | 69% |
| 10-17 21h | B0-base | Boccherini stage | 128 | L40S | 2,629 | 24 | 25 | 105 | 0.20 | 0.41 | 83% |
| 10-17 21h | B1-lora64mlp | Boccherini stage | 128 | L40S | 2,629 | 30 | 37 | 71 | 0.36 | 0.73 | 86% |
| 10-17 21h | B2-unfreeze4 | Boccherini stage | 128 | L40S | 2,629 | 30 | 25 | 105 | 0.27 | 0.55 | 77% |
| 10-17 21h | B3-augzeus | Boccherini stage | 128 | L40S | 2,629 | 30 | 49 | 54 | 0.44 | 0.88 | 93% |
| 10-17 21h | pretrain | MuSViT pretraining | 128 | L40S | | 20 | 90 | | 0.55 | 1.11 | 91% |
| 10-17 22h | E1-lstm | Public 9k | 128 | L40S | 8,765 | 60 | 79 | 111 | 1.41 | 2.85 | 97% |
| 10-17 22h | E2-tf8 | Public 9k | 128 | L40S | 8,765 | 40 | 121 | 72 | 1.54 | 3.08 | 88% |
| 10-17 22h | stage1-bocch | Public 9k | 128 | L40S | 8,765 | 60 | 112 | 78 | 1.98 | 3.98 | 93% |
| 10-17 23h | C0-full4-L | Boccherini stage | 128 | L40S | 2,694 | 24 | 33 | 82 | 0.25 | 0.51 | 88% |
| 10-17 23h | F1-columns | Public 9k | 128 | L40S | 8,765 | 60 | 107 | 82 | 1.91 | 3.84 | 93% |
| 10-17 23h | not identified (no log) | | | L40S | | | | | 0.27 | 0.55 | |
| 10-18 00h | C1-tf8-L | Boccherini stage | 128 | L40S | 2,694 | 30 | 38 | 71 | 0.41 | 0.83 | 77% |
| 10-18 00h | C2-bocch4-L | Boccherini stage | 128 | L40S | 2,694 | 30 | 35 | 77 | 0.33 | 0.67 | 88% |
| 10-18 00h | F2-zeus | Public 9k | 128 | L40S | 8,765 | 60 | 160 | 55 | 2.74 | 5.52 | 99% |
| 10-18 00h | G1-bocch-tf8 | Public 9k | 128 | L40S | 8,765 | 60 | 127 | 69 | 2.33 | 4.68 | 90% |
| 10-18 01h | C3-columns4-L | Boccherini stage | 128 | L40S | 2,694 | 24 | 35 | 77 | 0.30 | 0.60 | 78% |
| 10-18 02h | C6-zeus-L | Boccherini stage | 128 | L40S | 2,694 | 24 | 57 | 47 | 0.43 | 0.86 | 89% |
| 10-18 02h | G2-bocch-tf8-cols | Public 9k | 128 | L40S | 8,765 | 60 | 123 | 71 | 2.36 | 4.75 | 89% |
| 10-18 03h | C4-bocch-tf8-L | Boccherini stage | 128 | L40S | 2,694 | 30 | 38 | 71 | 0.38 | 0.76 | 84% |
| 10-18 04h | C5-bocch-tf8-cols-L | Boccherini stage | 128 | L40S | 2,694 | 18 | 42 | 64 | 0.27 | 0.54 | 78% |
| 10-18 09h | D1-tf8-M | Boccherini 2.9k | 128 | L40S | 2,892 | 30 | 39 | 74 | 0.38 | 0.77 | 85% |
| 10-18 09h | D2-bocch-tf8-M | Boccherini 2.9k | 128 | L40S | 2,892 | 18 | 42 | 69 | 0.25 | 0.50 | 84% |
| 10-18 10h | H1 or R1, stopped by the spend limit (no log) | Boccherini stage | 128 | L40S | | | | | 0.12 | 0.25 | |
| 10-18 10h | H1 or R1, stopped by the spend limit (no log) | Boccherini stage | 128 | L40S | | | | | 0.17 | 0.34 | |
| 10-18 16h | H1-tf8-noOp22-32 | Boccherini stage | 128 | L40S | 1,508 | 21 | 21 | 72 | 0.16 | 0.32 | 76% |
| 10-18 16h | R1-tf8-matched | Boccherini stage | 128 | L40S | 1,508 | 30 | 21 | 72 | 0.24 | 0.48 | 74% |
| 10-18 17h | D3-tf8-all (musvit-D3) | Boccherini 3k | 128 | L40S | 3,411 | 24 | 54 | 63 | 0.38 | 0.77 | 95% |
| 10-18 20h | D1c-tf8-M-color | Boccherini 2.9k | 128 | L40S | 2,892 | 21 | 55 | 53 | 0.39 | 0.78 | 84% |
| 10-18 23h | E2-h96 (no log here) | Public 9k | 96 | L40S | 8,765 | 60 | | | 1.39 | 2.80 | |
| 10-18 23h | H1-L2, -r10 or -r30 (no log here) | Boccherini stage | 128 | L40S | | | | | 0.29 | 0.59 | |
| 10-18 23h | H1-L2, -r10 or -r30 (no log here) | Boccherini stage | 128 | L40S | | | | | 0.21 | 0.43 | |
| 10-18 23h | H1-L2, -r10 or -r30 (no log here) | Boccherini stage | 128 | L40S | | | | | 0.37 | 0.74 | |
| 10-18 23h | S0-tf8-L2 | Boccherini 2.9k | 128 | L40S | 2,892 | 30 | 38 | 76 | 0.37 | 0.75 | 86% |
| 10-18 23h | S1-tf8-L2-synth50 (as many drawn staves again each pass) | Boccherini 2.9k | 128 | L40S | 2,892 | 15 | 81 | 36 | 0.39 | 0.77 | 88% |
| 10-19 00h | D1-h96 (no log here) | Boccherini stage | 96 | L40S | | | | | 0.26 | 0.52 | |
| 10-19 02h | SF1-synth | Drawn 11k | 128 | L40S | 10,790 | 10 | 182 | 59 | 0.58 | 1.17 | 87% |
| 10-19 02h | SF2-tf8-L2-after-synth | Boccherini 2.9k | 128 | L40S | 2,892 | 30 | 37 | 78 | 0.36 | 0.72 | 88% |
| 10-19 09h | PF1-copyist | Drawn Philhar 11k | 128 | L40S | 10,787 | 10 | 178 | 61 | 0.57 | 1.15 | 86% |
| 10-19 09h | PF1-plain | Engraved Philhar 11k | 128 | L40S | 10,787 | 6 | 160 | 67 | 0.35 | 0.71 | 76% |
| 10-19 09h | PF2-copyist | Boccherini 2.9k | 128 | L40S | 2,892 | 30 | 46 | 63 | 0.47 | 0.95 | 82% |
| 10-19 09h | PF2-plain | Boccherini 2.9k | 128 | L40S | 2,892 | 18 | 46 | 62 | 0.29 | 0.59 | 80% |
| 10-20 06h | SF1-h96 | Drawn 11k | 96 | L40S | 10,790 | 10 | 110 | 98 | 0.35 | 0.70 | 88% |
| 10-20 06h | D3L2-tf8-all | Boccherini 3k | 128 | L40S | 3,411 | 24 | 47 | 73 | 0.35 | 0.71 | 89% |
| 10-20 06h | D3S-synth-all | Boccherini 3k | 128 | L40S | 3,411 | 24 | 54 | 63 | 0.41 | 0.83 | 90% |
| 10-20 06h | D3L2-h96 | Boccherini 3k | 96 | L40S | 3,411 | 24 | 35 | 98 | 0.26 | 0.52 | 90% |
| 10-20 06h | D3S-h96 (musvit-D4) | Boccherini 3k | 96 | L40S | 3,411 | 24 | 48 | 71 | 0.37 | 0.74 | 88% |
| 10-20 09h | E3-h96-ossq | Public 22k | 96 | L40S | 22,006 | 60 | 292 | 75 | 5.13 | 10.30 | 95% |
| 10-20 14h | SF1-h96-ossq | Drawn 11k | 96 | L40S | 10,790 | 10 | 100 | 108 | 0.31 | 0.63 | 90% |
| 10-20 15h | D3S-h96-ossq | Boccherini 3k | 96 | L40S | 3,411 | 24 | 48 | 71 | 0.34 | 0.69 | 94% |
| 10-20 18h | SF1-h96-clef | Drawn 15k | 96 | L40S | 14,760 | 10 | 201 | 73 | 0.62 | 1.24 | 90% |
| 10-20 19h | D3S-h96-clef | Boccherini 3k | 96 | L40S | 3,411 | 24 | 47 | 73 | 0.34 | 0.68 | 93% |

Sizes before the stage names were settled: 2,536–2,694 staves were run J's
staves and their first rebuilds; 1,508 is H1 and R1's held-out set.
Rows marked "no log" have a billed app but no saved log. They are matched
to runs by the times their run folders appear in the `musvit` volume.

**Other apps, in total:**

| app | what | GPU | apps | GPU-h | $ |
|---|---|---|---:|---:|---:|
| `musvit-zeus` | readings and benchmarks (`read`, `read_samples`, `read_nbest`), and the first overfit tests | L4 | 74 | 5.7 | 4.78 |
| `copyist-sam` | Segment Anything's eight runs, test runs and scoring (reports/2026-10-19-segment-anything) | L4 | 12 | 11.5 | 15.29 |
| `musvit-pointer` | the pointer's two runs and its test (reports/2026-10-19-pointer) | L4 | 3 | 1.3 | 1.11 |
| `musvit-zeus` | cutting staves from the PDFs (`cut_all`) | CPU | 2 | | 0.78 |
| `ossq-staves`, `ossq-period`, `ossq-clef-check` | OSSQ's staves re-cropped, period check, clef check | CPU (one L4) | 23 | 0.1 | 1.24 |
| `tar-tests` | a test | CPU | 1 | | 0.00 |

**Where the billed time went.** 85–95% of a run's billed GPU time was
in training passes. The rest is container start-up, copying the staves
to the container's disk (10 s to 5 min), and scoring the dev staves after
each pass. Short runs lose the most: the shortest spent 69–76%.

**Incidents:**
- A spend limit at about $50 metered disabled the workspace mid-run on
  2026-10-18. Two runs were lost and rerun ($0.59).
- Modal preempted the pointer's `ptrA2-dolores` after 5 passes (24
  minutes). It reran from the start. `proto.py` has no way to resume a
  run, so a preempted run starts over.

## Prices

| GPU | memory | Modal $/s | Modal $/h | RunPod community $/h | RunPod secure $/h |
|---|---|---:|---:|---:|---:|
| T4 | 16 GB | 0.000164 | 0.59 | | |
| L4 | 24 GB | 0.000222 | 0.80 | 0.44 | 0.59 |
| A10 | 24 GB | 0.000306 | 1.10 | | |
| L40S | 48 GB | 0.000542 | 1.95 | 0.79 | 1.09 |
| A100 40 GB | 40 GB | 0.000583 | 2.10 | | |
| A100 80 GB | 80 GB | 0.000694 | 2.50 | 1.19–1.39 | 1.79 |
| RTX PRO 6000 | 96 GB | 0.000842 | 3.03 | | |
| H100 | 80 GB | 0.001097 | 3.95 | 1.99–2.69 | 2.89–3.99 |
| H200 | 141 GB | 0.001261 | 4.54 | | |
| B200 | 180 GB | 0.001736 | 6.25 | | |
| RTX 4090 | 24 GB | | | 0.34 | 0.89 |
| RTX 5090 | 32 GB | | | 0.69 | 1.19 |

- **Modal:** modal.com/pricing, read 2026-10-20. CPU $0.0000131 a core a
  second ($0.047 an hour), memory $0.00000222 a GiB a second ($0.008 an
  hour). Starter plan: $30 a month of credit. Region selection costs
  1.15–1.75×; non-preemptible containers 3×. The brief recorded the same
  L4, A10 and L40S prices on 2026-10-16. Billing agrees: no app-hour was
  billed more than $1.950 an L40S-hour or $0.800 an L4-hour.
- **RunPod:** runpod.io/pricing, read 2026-10-20, on-demand rates. Where
  two numbers are given, the first is PCIe and the second SXM.

**Always-on, at our use.** This month: 37.3 L40S-hours and 22.9
L4-hours.

| option | assumptions | cost for this month |
|---|---|---:|
| Modal, as used | measured | $101.81 metered, about $72 after credit |
| RunPod pods, the same GPU-hours | started and stopped as tightly as Modal (we wouldn't manage that) | $40–54 |
| one RunPod L40S, always on | 730 hours | $577–796 |
| one local 32 GB GPU | about $3,000–4,000 up front (assumption); electricity extra | $83–111 a month over 3 years |

A rented always-on L40S matches Modal's L40S at 296 hours a month
(community) to 408 hours (secure).

## What we don't know, and how to measure it

**Peak GPU memory: never logged.** An estimate for the full encoder at 128
px, batch 8, the widest batch (2,688 px wide, so 1,345 tokens a staff):
- weights 108M in float32: 0.4 GB, plus a bf16 copy;
- gradients and AdamW state for the 19.3M trainable: 0.2 GB;
- activations kept for the backward pass, through all 12 encoder layers,
  because LoRA sits in every layer's attention: about 34 bytes a token
  per hidden unit per layer, so 8 × 1,345 × 768 × 34 × 12 ≈ 3.4 GB. If
  attention runs without a fused kernel, it also stores the score
  matrices: about 14 GB in all;
- the decoder (256 wide, 8 layers, up to 512 tokens): well under 1 GB.

So **an estimate of 4–15 GB** at the widest batch, less for most batches,
and about three quarters of that at 96 px. Either way it fits the L4's 24
GB and uses at most a third of the L40S's 48 GB. This is an estimate. It
assumes the activation sizes in Korthikanti et al. (2022) and hasn't been
checked.

**GPU utilization: never logged.** The CPU signs above suggest it's well
below full. Nothing measures it.

**How to measure both**, each a one-line change (not made):
- In `proto.py`, add `{torch.cuda.max_memory_allocated() / 2**30:.1f}
  GiB` to the per-pass print. It gives each pass's peak memory.
- In `modal_app.train`, before running `proto.py`, start
  `subprocess.Popen(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used",
  "--format=csv,noheader", "-l", "30"])`. It writes the GPU's use every 30
  s into the run's log.
- Modal's web dashboard may chart GPU use per container. It hasn't been
  checked.

**Then, three timing runs** of a few passes each, at under $1 in all:
1. D4's Boccherini stage (D3S-h96's recipe) on an L4, against its L40S
   time.
2. The same on an L40S, with `cpu=8` and the batches built by several
   worker processes.
3. The same with a larger batch, if memory allows. Batch size changes
   training, so it needs its own clean-test check.

## Cost

Analysis only, no GPUs: none. The billing queries and volume listing are
free. On the Mac, under an hour.

## Files

- `billing-daily.json`: `modal billing report --start 2026-09-20 --end
  2026-10-21 --json --show-resources`, by app, day (UTC) and resource. A
  query from 2026-08-20 to 2026-09-20 returned nothing.
- `billing-hourly.json`: the same from 2026-10-14, with `-r h`, by hour
  (UTC).
- `runs.csv`: the runs table above, with app IDs, start and end hours
  (UTC) and training hours.

Sources: the run logs (each prints its app ID, staves and seconds a pass),
`experiments/musvit/BRIEF.md`, `experiments/musvit/modal_app.py`,
`proto.py`, `experiments/synth/sam_modal.py`, and the Cost sections of the
reports from 2026-10-19 and 2026-10-20.
