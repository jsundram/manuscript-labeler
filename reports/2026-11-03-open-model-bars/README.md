# An open model reading bars: Qwen3.6-27B and Gemma 4, one look a bar and as the edition's reader

**Question.** The edition's readers (Claude Opus 5.5 inside `/encode`)
beat musvit-D5 on Op48-4 I: 269 of 290 bars exact against 231. Could an
open model run the same way, and later be fine-tuned? First: does it read
a bar shown once? Then, as the fairer test (the user's point, 2026-11-04):
does it read as the edition's reader does, with the same instructions,
tools and bars?

**Finding.** No, either way. Shown each bar once, Qwen3.6-27B gets 2-3%
of KHM 602 movement II's bars exact (Zeus untrained 45%). Asked for the
rhythm alone it does no better (21% and 25% of bars right in rhythm,
against Zeus's 55%). Given the edition's reader prompt and tools for
violin I bars 0-13 of Op48-4 I, it looked at every bar, then thought in
circles for 75 minutes and 317,000 output tokens and never wrote one
(Opus: 12 of the 14 exact, in about 117,000). Fine-tuning it isn't worth
it on this evidence. Gemma 4 31B, shown each bar once, does better than
Qwen but no better than Zeus untrained (7% and 6% exact, 36% and 35%
right in rhythm), so it wasn't given the reader test. Legato 2, when its weights arrive, would compete
with D5 as a reader, not take Opus's place: it reads, it doesn't think
or use tools.

## 1. One look a bar (2026-11-03)

`experiments/llm/bars.py`, the 9 October pilot, with `--backend openai`:
the same prompt, the same 40 example bars with their answers, the same
crops (40 px a staff space, clef, key and time given) and the same scoring
by compare.py's rules against the edition's notes. All 284 whole bars of
KHM 602 II, two sampling seeds, thinking off. The model is served by
vLLM on Modal (`experiments/llm/vllm_modal.py`, FP8 weights on one L40S),
its answers held to the schema by vLLM's structured output.

| reader | bars | exact | rhythm right | pitch right |
|---|---|---|---|---|
| Qwen3.6-27B, seed 1 | 284 | 8 (3%) | 74 (26%) | 12 (4%) |
| Qwen3.6-27B, seed 2 | 284 | 7 (2%) | 68 (24%) | 13 (5%) |
| Qwen, asked for the rhythm alone (`--ask rhythm`), seeds 1, 2 | 284 | | 61 (21%), 72 (25%) | |
| Gemma 4 31B, seed 1 | 284 | 19 (7%) | 103 (36%) | 20 (7%) |
| Gemma 4 31B, seed 2 | 284 | 16 (6%) | 100 (35%) | 17 (6%) |
| Qwen, the pilot's 10 bars (va 1-10), each seed | 10 | 0 | 2, 3 | 0 |
| Opus 5.5 one look, low / high effort (the pilot, rescored against today's notes) | 10 | 1, 1 | 5, 4 | 2, 3 |
| Zeus untrained (ayce, 2026-10-11) | 284 | 127 (45%) | 155 (55%) | 176 (62%) |

Of 1,012 events, 80 and 86 are right. The errors are of every kind: 591
pitch and 460 duration errors in seed 1, 175 extra events, 58 notes for
rests. In the viola's first bars it reads the top of each double stop a
third high (C4 for A3) and calls a bar rest a half note. Twelve of the 15
exact bars, across both seeds, are the viola's.

**Gemma 4 31B (2026-11-04).** The same run, with `google/gemma-4-31B-it`
in bf16 on one H100, its model card's sampling (temperature 1.0, top_p
0.95, top_k 64) and its default picture budget (280 tokens, more than a
bar crop at 40 px a staff space needs). Of 1,012 events, 155 and 148 are
right, nearly twice Qwen's, but it adds 253 events that aren't there and
gets 634 pitches wrong. The gate set before the run was 20% exact for the
reader test; at 6-7% it wasn't run.

**Rhythm alone.** The same bars, examples and crops, the question cut to
each event's kind, written value, dots and grace. It didn't help: a
narrower question doesn't make the model see beams and flags better, so
splitting the reading into rhythm, pitch, slurs and marks for this model
isn't worth building.

D5 is not in the table: it probably trained on this manuscript, so it
isn't a fair comparison here.

## 2. As the edition's reader (2026-11-04)

`experiments/llm/agent_read.py`: the reader's prompt word for word as
`.claude/workflows/encode.js` builds it (the encoder agent's
instructions, the setup, `docs/encode/reader.md`, the assignment from the
run's `plan-read.json`), and the encoder agent's tools (a shell, reading a
file or a picture, writing a file), with pictures shrunk as Claude Code
shrinks them for Opus. The edition is a clone at the commit Op48-4 I's
readers started from (3205935), its run folder holding only the files
written before reading began (the copyist notes, 02:58, a minute before
reading; the form map; the plan) and its note files seeded by
`encode.py seed`. Qwen thinks before every reply, with its model card's
settings for thinking with pictures (temperature 1.0, 32,768 tokens a
reply). Served on one H100 with a 128k context and tool calls
(`VLLM_AGENT=1`). Scored by `score_agent_read.py`: `zeus-score compare`
against the person's final notes, as the edition's `d5_measure.py` scores
its readers.

**Violin I, bars 0-13 (the first reader's chunk):**

| reader | bars exact | output tokens | turns | longest reply |
|---|---|---|---|---|
| Opus readers' first reading | 12 of 14 | about 117,000 | 135 | 3,900 tokens |
| musvit-D5 | 12 of 14 | | | |
| Qwen3.6-27B, in the same place | 0 (none written) | 317,000 in 75 minutes | 12 | 32,768 (cut off 8 times) |

What it did: read the rules and the copyist notes, zoomed every bar at 50
px a staff space and looked at each, in order. Then its thinking went in
circles ("looking at the image more carefully..."): how long the bar is,
which way the stems go, where a bar line falls. It took the movement for
3/4 for some 50,000 tokens before reading `Structure.ily` (2/4); the seed
lines say 2/4 too. Turn 10 thought for 30,909 tokens; from turn 11 every reply ran to the 32,768-token cap
without acting. After three cut-off replies the loop tells the model its
thinking reached the limit and asks it to act; it was told twice and
still didn't write.

What Opus did differently, from its transcript (its thinking isn't kept,
its calls and token counts are): it read `Structure.ily` sixth; it thought
briefly and often (135 turns, never more than 3,900 tokens); it settled a
doubt by looking again with a tool (some 20 extra zooms: half bars at
100-150 px a staff space, taller views, a dynamics view, slur and
dynamics sheets, the other parts' bar 0), not by looking again in its
head; and it wrote the 14 bars, then checked them with the overlay and
the head check, and fixed bar 11.

Every turn, with its thinking, is in `qwen-reader-vn1-0-13.jsonl.gz`.

The first attempt (`qwen-reader-vn1-0-13-attempt1.jsonl.gz`) stopped
after 8 turns: the loop took a reply cut off at 16,384 tokens of thinking
for the final answer. The loop now asks again, and the reply length and
sampling follow the model card.

## What wasn't tried

- **More chunks or parts.** With no bar written in the first chunk, the
  part (step 2 of the plan) and the four parts (step 3) weren't run.
- **Gemma 4 31B as the reader.** Not run: it failed the one-look gate.
- **Faster decoding** (Qwen's built-in draft head, vLLM's MTP option),
  for any longer run: the model writes 73-76 tokens a second here, about
  60% of what an H100's memory speed allows.
- **Legato 2,** a reader built for sheet music (research TODO 15(c)). It
  is a rival to D5 (it reads system by system, with no thinking or
  tools), not to the Opus reader; its weights are awaiting approval.

## Cost

From `modal billing report` (hourly, full hours, so the last minutes may
be missing):
- one look: $0.81 on an L40S, about 0.4 GPU-hours;
- a failed start: $2.94. vLLM's default of 256 requests at once needs more
  memory than this model leaves on one 48 GB card, so the server crashed
  at startup and restarted for an hour, while the check waited only for it
  to answer. Fixed with `--max-num-seqs`;
- the reader and the rhythm-alone runs, sharing one H100: $7.13, about 2
  GPU-hours.

- Gemma 4 one look a bar, both seeds: $1.13 on an H100, about 18 minutes.

Total about $12.05 (measured).
