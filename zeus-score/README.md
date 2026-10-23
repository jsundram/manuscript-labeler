# zeus-score

Asks a Zeus OMR model how likely it finds *your* reading of a manuscript, note
by note. Give it the manuscript, where its staves and bars are, and the notes
you believe are there. For every token of every staff (a pitch, a duration, an
accidental, a tie, a bar line), it returns how probable Zeus finds yours and
what Zeus would have written instead. Where Zeus strongly prefers something
else, your reading is worth a second look. The Op. 48 edition flags encoded
notes this way: on a movement Zeus never trained on, 76% of its flags were real
errors, and they covered 90% of the errors in the kinds it checks (pitch,
rhythm, accidentals).

The models are Zeus (OmniOMR's reader for handwritten music) fine-tuned on
Boccherini's copyists, see [MODEL_CARD.md](MODEL_CARD.md), and readers built
on MuSViT (PRAIG's pretrained music encoder) that read the same staves into
the same format, see [MODEL_CARD_MUSVIT.md](MODEL_CARD_MUSVIT.md).
`musvit-D5`, the default since 1.4.0, gets 82% of the clean test's bars exact
(musvit-D4 80%, within the noise; musvit-D3 78%, Zeus J 65%). On a manuscript
in a copyist's hand none of its training had, it is as good as D4 in notes
and rhythm and makes a fifth of D4's beam errors. Its flags for the edition,
at the flag floor of 3, catch 95 of 107 errors with 11 false (D4: 94, 14).
Give `--model musvit-D4`, `--model musvit-D3` or `--model J-lr1e5-e8` for the
earlier readers.

> **Licences.** This code is MIT. **The models are CC BY-NC-SA 4.0:
> non-commercial use only, and adaptations must be shared alike.** They are
> fine-tuned from OmniOMR's Zeus weights (https://github.com/OmniOMR/zeus)
> or from MuSViT's (https://github.com/OMR-PRAIG-UA-ES/MuSViT), which carry
> that licence. Each model's archive holds the licence text and a notice.

## Install

    uv tool install "git+https://github.com/jsundram/manuscript-labeler@zeus-score-v1.5.0#subdirectory=zeus-score"
    zeus-score fetch       # once, with the network

`fetch` downloads the default model, checks its sha256, and builds the
environment the scoring runs in: for a MuSViT reader, PyTorch and transformers,
about 1 GB, built by uv; it scores on the Mac's GPU. Everything after that works offline, including inside a
sandbox with no network. `uv` must be on the path. The first time, `fetch`
also needs GitHub, PyPI and uv's Python downloads.

A Zeus model's environment is Python 3.10, Zeus and tensorflow 2.12 instead,
about 1.4 GB, built the same way by `zeus-score fetch J-lr1e5-e8`.

Zeus needs tensorflow 2.12, which has no build for Apple-silicon Macs under
that name, so the environment pins Apple's `tensorflow-macos` 2.12 instead. That
is why the scoring runs in an environment of its own and not in yours. The
package itself has no dependencies.

To pin it in a project instead of installing it as a tool, depend on the same
URL. In a `pyproject.toml`, use `"zeus-score @ git+https://...@zeus-score-v1.5.0#subdirectory=zeus-score"`,
then run `uv run zeus-score fetch` once and `uv run --offline zeus-score ...`
after that.

## Commands

    zeus-score --pdf M.pdf --structure S.json --events DIR --out scores.json [options]
    zeus-score read ... --out reading.json [--against DIR]   a MuSViT reader's own reading (below)
    zeus-score compare ... --events A --against B --out FILE  two sets of notes counted the same way
    zeus-score fetch [NAME[@VERSION]]    a model (the default if none is named), and the environment
    zeus-score models [--json]           the registry: each model's version, licence, training data, accuracy
    zeus-score --help                    every option
    zeus-score --version

Scoring options:

| option | |
|---|---|
| `--pdf FILE` | the manuscript |
| `--bars FILE` | its bar export from the manuscript-labeler (default: the PDF's name with `.bars.json`, beside it) |
| `--structure FILE` | each movement's key and time: a JSON file (below) or a labeler-style `Structure.ily` |
| `--events DIR` | your reading: `DIR/<part>-<movement>.json`, one file per part and movement |
| `--out FILE` | where the scores are written |
| `--parts P ...`, `--movements M ...` | which to score (default: every one in the bar export). A part or movement with no events file is left out and listed. |
| `--shifts 0 -1 1` | also score every pitch moved by these octaves. Use it to find a passage written in another register, such as a cello in treble clef. Default `0` alone. |
| `--model NAME[@VERSION]` | a registry model; the default if left out. A path to a model folder also works, for experiments. |
| `--cache DIR` | where models are fetched to and found (default `~/.cache/manuscript-labeler/models`) |
| `--renders DIR` | where page renders are written and read (default `~/.cache/manuscript-labeler/zeus/renders`), in a folder per PDF named for it and a hash of its contents |
| `--edition DIR --source NAME` | the Op. 48 edition's layout: finds `sources/G*/NAME.pdf`, its `.bars.json` and `Op48-<n>/Structure.ily` |

Before every use, the model's weights are checked against the registry's
sha256. Renders are written under a temporary name and then renamed, so
processes running side by side are safe.

## Inputs

### The bar export (`--bars`)

What the [manuscript-labeler](https://github.com/jsundram/manuscript-labeler)
exports once a source's bar lines are labelled: where each staff is on its
page, and which bars it holds. The scorer reads:

- `systems`: `{id: {page, left, right, top, bottom, bend}}`. Each staff's page
  (1-based) and its box as fractions of the page. `top` and `bottom` are its
  outer staff lines, and `bend` is a few offsets that straighten a curved
  staff.
- `bars`: `[{part, movement, bar, count, system, clefs}]`, in order.
  - `count` is 1 for a bar that starts on the downbeat. It is 0 for an upbeat
    that shares the bar's number, where one bar is split across a repeat or a
    line break.
  - `clefs` lists the clef or clefs written in the bar (`treble`, `alto`,
    `tenor`, `bass`). More than one means the clef changes inside the bar.

The labeler writes it from its labels (`labels.py`, `bars_export`). The
format is versioned by its `schema` field.

### The structure (`--structure`)

Each movement's key and time, with any changes:

```json
{
  "I":  {"time": "2/4", "key": 3},
  "II": {"time": "3/4", "key": 3,
         "changes": [{"bar": 28, "on_bar_line": false, "key": 2}]}
}
```

- `key` is in fifths: sharps positive, flats negative, 0 for none.
- A change holds from its bar. With `"on_bar_line": false` (a change in the
  middle of a split bar), it holds from that bar's upbeat. `on_bar_line`
  defaults to true.
- A change can set `key`, `time` or both.

A `Structure.ily` in the Op. 48 edition's form (a `\tag #'mvtI { \time 2/4
\key a \major ... }` block per movement) works too.

### The reading (`--events`)

One JSON file per part and movement, `DIR/vn1-I.json` and so on. Each holds
an object keyed by bar number (a string; `"0"` is a pickup). Each bar is a
list of its events in order:

```json
{"1": [
  {"label": "n1", "kind": "note", "pos": "0", "grace": "-1/8", "voice": 1, "dur": "8th",
   "notes": [{"pitch": "D5", "acc": null}], "tie": false, "tie_to": null,
   "slur": ["("], "beam": [], "tup": [], "art": [], "clef": "clefs.G"},
  {"label": "n2", "kind": "note", "pos": "0", "grace": "0", "voice": 1, "dur": "quarter",
   "notes": [{"pitch": "C#5", "acc": "sharp"}], "tie": false, "tie_to": null,
   "slur": [")"], "beam": [], "tup": [], "art": ["staccato"], "clef": "clefs.G"}
]}
```

| field | |
|---|---|
| `kind` | `note` (a note or a chord on one stem), `rest`, `mmrest` (a whole-bar rest). Other kinds (`spacer`, `mark`) are ignored. |
| `label` | `n1`, `n2` ... for notes and `r1` ... for rests: their order in the bar, as they sound |
| `pos` | onset from the start of the bar, in whole notes, as a fraction (`"0"`, `"3/8"`) |
| `grace` | `"0"` for an ordinary note. For a grace note, a negative fraction: how far before the note at `pos` it is drawn. |
| `voice` | an integer. A bar with events in more than one voice is scored as one voice (the upper, with notes that start and last together as one chord), and listed in that staff's `approximate`. |
| `dur` | `breve`, `whole`, `half`, `quarter`, `8th`, `16th`, `32nd`, `64th`, plus a `.` per dot. Inside a tuplet, the written value. |
| `notes` | the heads: `pitch` in scientific notation as it sounds (`C4` is middle C, `Bb3`, `F#5`, `Cx4`), and `acc`, the accidental printed (`sharp`, `flat`, `natural`, `double-sharp`, `double-flat`, or null) |
| `tie`, `tie_to` | a tie starts here, and the note it ends on as `[bar, note number]` |
| `slur` | `"("` for each slur starting here, `")"` for each ending |
| `beam` | `"start"` and/or `"stop"`: where a beam begins and ends |
| `tup` | `[["start", 2, 3]]` opens a tuplet (3 in the time of 2) on this event; `[["stop"]]` closes the open one before it |
| `art` | any of `staccato`, `fermata`, `trill` |
| `clef` | the clef in force, as a LilyPond glyph (`clefs.G`, `clefs.C`, `clefs.F`). Used only where a bar changes clef. |

The Op. 48 edition writes these files from its LilyPond encoding with
`scripts/events.py <quartet> <part> <movement> --json`, which also adds
fields this ignores. Another project can write them from its own encoding.

## Output

```json
{
  "format": 1,
  "model": {"name": "J-lr1e5-e8", "version": "2026-10-16", "sha256": "39eada41...", "engine": "zeus"},
  "labeler_commit": "c035c20", "zeus_commit": "c8569eb",
  "source": "D-B_KHM-603", "movements": ["II"],
  "staves": [
    {"sid": "p10s2", "part": "vn1", "mvt": "II", "bars": [[5, 1], [6, 1]],
     "tokens": ["measure", "key:fifths:3", "time", "beats:3", "...", "C#5", "quarter", "..."],
     "approximate": [], "unknown": [], "trained": true,
     "shifts": {"0": {"lp": [-0.01, "..."], "best": ["measure", "..."], "best_lp": [-0.01, "..."]}}}
  ],
  "left_out": [{"sid": "p3s1", "part": "va", "mvt": "I", "bars": [1, 6], "reason": "..."}]
}
```

- **`format`** goes up with any change a reader must handle.
- **`model`** names the weights that scored the file; `sha256` is the
  weights file's; `engine` is `zeus` or `musvit` (added in 1.1.0; older files
  lack it and are Zeus's). `zeus_commit` is null for a MuSViT model.
- **`tokens`** is your reading of the staff in Zeus's text format, LMX
  (linearized MusicXML). Each `measure` token begins the next of the staff's
  `bars`, as `[bar, count]` pairs in order.
- **`shifts["0"]`** holds four parallel lists, each one entry longer than
  `tokens` (the extra entry is the end of the staff):
  - `lp`: the log-probability Zeus gives your token;
  - `best`: the token Zeus would have written there;
  - `best_lp`: that token's log-probability.
- **`trained`** says whether the model was trained on this source and
  movement. Where it's true, Zeus has learned the reading it was trained on
  and objects less; those movements are also named on stderr.
  - true: the registry lists this source and movement, or lists the source
    among its other training sources;
  - false: the source was named with `--source` (or `--edition`), and the
    registry doesn't list it;
  - null: unknown. Either the model was given by path, or the source is named
    only by its PDF's file name and the registry doesn't list that name. Name
    sources as the registry does (`zeus-score models`) to get true or false.
- **`approximate`** lists the bars written as one voice (see `voice` above);
  their scores don't say what the manuscript has. `unknown` lists the tokens
  Zeus has no word for.
- **`left_out`** lists the staves that couldn't be scored, and why. Examples:
  a bar whose notes don't fill it, a bar split where its notes can't be cut,
  or a part with no events file.

### Reading it: where Zeus objects

The gap `best_lp - lp` is how much likelier Zeus finds its own token than
yours (0 where it agrees). The Op. 48 edition flags a bar when a gap is above
3. There, floors from 2.5 to 4 caught the same errors, within a bar or two.

```python
import json
s = json.load(open("scores.json"))
for st in s["staves"]:
    bars, sh = iter(st["bars"]), st["shifts"]["0"]
    bar = None
    for tok, lp, best, best_lp in zip(st["tokens"], sh["lp"], sh["best"], sh["best_lp"]):
        if tok == "measure":
            bar = next(bars)
            continue
        if best_lp - lp > 3 and not best.startswith("beam:"):
            print(st["part"], st["mvt"], bar, f"ours {tok}, Zeus {best}, gap {best_lp - lp:.1f}")
```

Two refinements the edition makes (`scripts/differences.py`, `objections`):

- **Beams.** Zeus's beam tokens differ from encodings too often to mean
  anything, so objections that prefer a beam are skipped. The exception is
  where your token is an accidental: there, a beam means Zeus wants no
  accidental.
- **Mark tokens.** A mark Zeus wants where your next note starts belongs to
  the note before.

It also keeps only each bar's strongest objection of each kind.

## A reader's own reading (`read`, `compare`)

Since 1.5.0. Scoring asks how likely the model finds *your* notes; `read`
asks what the model itself reads there. It needs a MuSViT reader.

    zeus-score read --edition DIR --source SRC --movements I --out reading.json \
        [--parts ...] [--against DIR] [--model NAME[@VERSION]] [--batch 1] [--renders DIR]
    zeus-score compare --edition DIR --source SRC --movements I \
        --events A --against B --out comparison.json

`read` takes scoring's options, less `--events`, `--shifts` and
`--structure` (`--pdf` and `--bars` work as there). Each staff is cut as for
scoring and read greedily. `--batch` is how many staves are read together,
in order of width. It defaults to 1, each staff alone, so a staff's reading
doesn't depend on which others were read with it. The model card's numbers
were read 8 at a time on the Mac's GPU; one at a time, on the CPU as in a
sandbox, gives the same 283 of 347 on the clean test, with 6 of 66 staves
read differently.

Its output: `format` (1), `command` ("read"), `model`, `labeler_commit`,
`source`, `movements`, and `decoding` (`method` "greedy", `beam`, `batch`,
`batch_order`, `device`, `precision`, `max_tokens`). Readings differ a
little by device and precision, so compare readings made the same way.
Then per staff, in `staves`:

- `sid`, `part`, `mvt`, `bars` and `trained`, as in the scores file;
- `tokens`: the reading, LMX, and `measures`: the same split at each
  `measure`;
- `paired`, and `pairing`: per bar box, `bar`, `count`, `how` and the
  `measures` it was made from. A reading can miss or add a bar line, read a
  repeat-split bar whole, or run past the staff's end, so measures and
  boxes don't always match one to one. `how` is "one" (one measure),
  "merge" (two measures, an added bar line), "split" (one measure for two
  boxes, a missed one), "whole" (a split bar read whole, all of it in its
  first box), or "rests" (bar rests for an N-bar rest). The pairing is
  compare.py's, made from the labels' time signatures only. `paired` is
  false, and `pairing` null, where no pairing fits; that staff's bars
  count as wrong;
- `ended`: false if the reading ran out of length before it ended (a
  runaway);
- `lp`, `runner_up`, `runner_up_lp`: per token, and one more for the end,
  its log-probability, the likeliest other token and that one's;
- `mean_lp` and `below_half`: the mean of `lp`, and the share of `lp`
  below a probability of 0.5. A staff the model fits poorly shows a lower
  mean and a larger share.

With `--against DIR` (your notes, as scoring's `--events`), `against` adds
each bar counted as the model card counts it (`experiments/zeus/compare.py`):
notes, rests, durations, dots and grace notes, pitches named in the labels'
clef, accidentals apart, beams and slurs not compared. Per bar in `bars`:
`part`, `movement`, `bar`, `exact`, `rhythm`, `pitch`, `exact as written`
(in the reading's own clefs), `errors`, and both sides as text (`ours`,
`read`). `tally` sums them for "all", each part and each movement. A bar
with a clef change inside it isn't compared ("bars not compared").

`compare` counts one set of your notes (`--events`) against another
(`--against`, taken as right) by the same rules, over the same bars, with
the same `tally` and `bars`. Use it to put another reading, such as a
person's, on the same scale as the model's.

## The registry

`zeus_score/models.json` (or `zeus-score models --json`) has one entry per
published model, with these fields:

- `name`, `version`, and `default` on one of them;
- `engine`: `zeus` (when left out) or `musvit`: which scoring script runs it
  and what its archive holds (Zeus: `weights.h5` and its options; MuSViT:
  `reader.safetensors`, `reader.json`, `vocab.json`);
- `sha256` of the weights (`weights.h5`, or `reader.safetensors`), and `url`
  and `archive_sha256` of the release archive;
- `licence`;
- `trained_on`: the sources and movements, by the Op. 48 edition's names, such
  as `{"D-B_KHM-602": ["I", "II"]}`;
- `trained_on_other`: other sources;
- `trained_at`: the labeler commit;
- `accuracy`: scores on held-out sources;
- `card`: a link to the model card.

A new model is a new entry, never a changed one: the same name and version
always mean the same weights.

## Development

The scoring code is the labeler's own: `tools/zeus_score.py` plus
`experiments/zeus/compare.py`, `dataset.py`, `labels.py` and `structure.py`;
for MuSViT models, `tools/musvit_score.py` (the same, with the reader in
Zeus's place) and `experiments/musvit/proto.py` (the reader).
They are copied into the package when it is built (`hatch_build.py`), so
there is one copy of them; an sdist carries the copies. `tools/zeus_score.py`
runs on its own too, from a labeler checkout. Tests:
`tests/test_zeus_score_package.py` and `tests/test_zeus_score_inputs.py`.
