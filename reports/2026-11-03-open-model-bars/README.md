# An open model reading bars: Qwen3.6-27B, Gemma 4 and Muse Glimmer, one look a bar and as the edition's reader

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
it on this evidence. Gemma 4 31B and Meta's Muse Glimmer 30B, shown each
bar once, do better than Qwen but no better than Zeus untrained (4-7%
exact, 33-38% right in rhythm), and bigger pictures don't help either.
That alone wouldn't rule them out: on the pilot's 10 bars Opus, shown
each bar once, did no better. But as the reader both wrote all 14 bars
and got none exact. Neither did what the reader's instructions ask:
Gemma looked at 2 of the 14 bars and wrote a made-up sequence; Glimmer
looked at every bar, then wrote one pitch repeated in eighths, and never
compared its engraving with the page. They fall short of Opus in seeing
and, more, in following the procedure that makes Opus's reading right
(section 3). Legato 2, when its weights arrive, would compete
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
| Gemma, 1,120 tokens a picture, seeds 1, 2 | 284 | 16, 16 (6%) | 77, 80 (27%, 28%) | 21, 19 |
| Muse Glimmer 30B, seed 1 | 284 | 19 (7%) | 108 (38%) | 22 (8%) |
| Muse Glimmer 30B, seed 2 | 284 | 12 (4%) | 95 (33%) | 14 (5%) |
| Glimmer, crops at 80 px a staff space, seed 1 | 283 | 11 (4%) | 83 (29%) | 14 (5%) |
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
0.95, top_k 64) and its default picture budget (280 tokens a picture;
Gemma scales each picture to fill it, so a token covers about 30 px of a
bar crop, three quarters of a staff space, where a pitch needs half a
space). Of 1,012
events, 155 and 148 are right, nearly twice Qwen's, but it adds 253
events that aren't there and gets 634 pitches wrong.

**Muse Glimmer 30B (2026-11-04).** Meta's open model
(`meta-models/Muse-Glimmer-30B`, bf16 on one H100, vLLM's
`muse_glimmer` parsers), with the same sampling as Gemma. It has no
switch to turn thinking off, so it ran at its lowest reasoning strength,
and took about an hour a seed. Of 1,012 events, 154 and 125 are right,
level with Gemma; it adds far fewer events (57 against 253) but misses
more (72 against 21), and still gets 574 pitches wrong.

**Bigger pictures.** Two tests of whether the picture was too small.
Gemma given its largest picture budget (1,120 tokens instead of 280)
got no more bars exact and fewer right in rhythm (27-28% against
35-36%), and added more events that aren't there (326 and 333). Glimmer
given crops at 80 px a staff space instead of 40 did no better (seed 2
was stopped: one seed was enough). Neither test adds detail: the crops
are cut from page renders at about 16 px a staff space (the scan itself
has about 24), so both sizes are enlarged copies of the same picture.
But the bar is plain at 40 px (`bar-40-vs-80-px.jpg`: violin I bar 5,
both sizes), so it isn't the picture that limits these models.

**A gate that was wrong.** Before the run, 20% of bars exact was set as
the gate for the reader test, and Gemma at 6-7% was first written up as
failing it. But Opus would fail it too. On the pilot's 10 bars (viola
1-10), shown each bar once:

| reader | exact | rhythm right | pitch right |
|---|---|---|---|
| Opus 5.5, low / high effort | 1, 1 | 5, 4 | 2, 3 |
| Gemma 4 31B, seeds 1, 2 | 1, 0 | 4, 4 | 1, 0 |
| Qwen3.6-27B, seeds 1, 2 | 0, 0 | 2, 3 | 0, 0 |

Ten bars can't rank them, but no general model reads a bar in one look;
the edition's reader gets there with its tools (zooms to 100-150 px a
staff space, a head check that measures noteheads, an engraving compared
with the page). So one look says how well a model sees, not whether it
can read as the edition's reader.

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
| Gemma 4 31B | 0 of 14 (none right in rhythm) | 31,600 in 26 minutes | 23 | |
| Muse Glimmer 30B | 0 of 14 (1 right in rhythm) | 18,500 in 19 minutes | 92 | 1,832 |

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

**Gemma 4 31B and Muse Glimmer 30B (2026-11-04).** The same run, with
each model card's sampling. So that neither would think in circles as
Qwen did, Gemma's thinking was capped at 4,096 tokens a reply (vLLM's
`thinking_token_budget`) and Glimmer ran at medium reasoning strength (the
cap isn't enforced for Glimmer). Gemma had its largest picture budget
(1,120 tokens) and needed an H200 for the 128k context; Glimmer an H100.
Both finished and wrote all 14 bars; neither got one exact.

- **Gemma** zoomed five times but looked at only three pictures (bars 0
  and 1, and one comparison for bar 0). It then wrote bars 1-13 as a
  falling sequence (`c8 b c4 c4`, `b8 a b4 b4`, `a8 g a4 a4`...), some of
  them too long for a 2/4 bar, while the music has no such sequence. Each
  bar's record lists two pictures as looked at and no doubts. It ran
  `compare.py` five times and never looked at what it made.
- **Glimmer** read the rules, the plan, the copyist notes and
  `Structure.ily`, zoomed every bar and looked at each of the 18
  pictures. Then it wrote each bar as one pitch in eighth notes (`e8 e8
  e8`, `g8 g8 g8`...), against dotted rhythms and quarters on the page.
  It ran the head check once and never compared its engraving with the
  page.

Every turn is in `gemma-reader-vn1-0-13.jsonl.gz` and
`glimmer-reader-vn1-0-13.jsonl.gz`; scored by `score_agent_read.py
--reader gemma` and `--reader glimmer`.

## 3. Why: seeing, and keeping to the procedure

The three models fail in different ways. Qwen thought at length but never
settled a doubt by looking again. Gemma skipped looking and wrote what it
expected. Glimmer looked, then wrote filler and checked nothing. Opus's
edge as the reader is less what it sees in one look (the pilot: no better
than Gemma) than what it does next: it looks again, closer, compares its
engraving with the page and fixes what disagrees.

So the next tests would give an open model help of the usual kinds,
rather than a bigger model or a bigger picture:
- **the loop keeps the procedure**, not the model: for each bar, zoom,
  read, compare, head check, revise, and a bar isn't taken until its
  comparison has been looked at;
- **D5's reading as the draft**: its notes engraved over the page, the
  model asked only where they're wrong; checking is easier than reading,
  and the aim is to beat D5;
- **pitch names on the picture**: each staff line and space labelled, so
  a pitch is read off rather than counted (about 60% of these models'
  notes are the wrong pitch). Numbering each notehead as well would rely
  on the head check's detector, which is a filter, not a verdict: on the
  correct Op48-1 II it disagrees with the notes in 209 places;
- **one of Opus's reader runs** (its calls, not its thinking) as an
  example to follow;
- **several readings and a vote.**

Fine-tuning on Opus's reader runs would come after these: it teaches the
procedure, not the seeing.

## What wasn't tried

- **More chunks or parts.** With no bar written in the first chunk, the
  part (step 2 of the plan) and the four parts (step 3) weren't run.
- **The help in section 3,** for any of the models.
- **Muse Spark Open** (Meta's 816B model): too large to serve on a GPU or
  two.
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

- Gemma 4 one look a bar, both seeds: $1.17 on an H100, about 18 minutes;
- two Gemma starts that failed: $0.81 (on an H100 the 128k context
  didn't fit; then the server refused a picture budget sent with each
  request until started with `--trust-request-mm-kwargs`);
- Gemma as the reader and at 1,120 tokens a picture, sharing one H200:
  $2.57;
- a first Glimmer server, replaced to change its reasoning settings:
  $0.79;
- Glimmer as the reader and one look a bar (40 px both seeds, 80 px
  seed 1), sharing one H100 for about 6.7 hours: $27.27. Of that, about
  $5.70 went on the 80 px second seed, stopped unfinished.

Total about $43.50 (measured).
