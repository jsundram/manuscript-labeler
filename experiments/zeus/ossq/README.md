# Zeus on other composers' manuscripts (OSSQ, 2026-10-13)

Fine-tuning Zeus on Boccherini's copyists may narrow it: better on the
hands it trains on, worse on others. To measure that, we need hands
nobody trained on, with an encoding to score against.

[OSSQ-OMR](https://github.com/MALerLab/ossq-omr) (MALerLab, ISMIR 2026,
CC0) has encoded 116 string quartets by 47 composers as MusicXML. Six
of them have manuscripts on IMSLP. Its line breaks follow the manuscript
(its page breaks don't). OSSQ ships no images, so the PDFs come from IMSLP.

Usable:

| manuscript | OSSQ score | pages |
|---|---|---|
| Elfrida Andrée, quartet in A (autograph score) | sq7313978 | 57 |
| Amanda Maier, quartet in A (autograph score) | sq7551068 | 69 |
| Emilie Mayer, quartet in A (score) | sq8818128 | 43 |

Not usable:
- Fanny Hensel: the only scan is 1,000 px.
- Mayer, E minor: a pencil draft whose layout isn't the encoding's.
- Mayer, D: the only manuscript is a piano four-hands arrangement.

## Steps

1. **The PDFs.** IMSLP's browser check blocks plain scripts, so
   `ossq_fetch.py` downloads them with your browser's IMSLP session. It
   reads the cookies when it runs and stores none. Run it yourself, after
   opening imslp.org once in that browser:

       uv run experiments/zeus/ossq/ossq_fetch.py [--browser safari] [--out ~/Downloads/ossq]

2. **The encodings,** from OSSQ's `omr-dev` branch:

       mkdir -p ~/.cache/manuscript-labeler/ossq
       cd ~/.cache/manuscript-labeler/ossq
       B=https://raw.githubusercontent.com/MALerLab/ossq-omr/omr-dev/scores
       curl -sLo sq7313978.musicxml "$B/Andr%C3%A9e,_Elfrida/String_Quartet_in_A_major/sq7313978.musicxml"
       curl -sLo sq7551068.musicxml "$B/Maier,_Amanda/String_Quartet_in_A_major/sq7551068.musicxml"
       curl -sLo sq8818128.musicxml "$B/Mayer,_Emilie/String_Quartet_in_A_Major/sq8818128.musicxml"

3. **Detection,** as the labeler's automatic detection would see each
   page. First run the cached bar-line detectors on the PDFs, then
   autodetect.py. With `--pages 1-N:vn1`, every page is music and every
   staff is kept; score.py groups them into systems.

       uv run tools/predict_barlines.py <edition-repo> --pdf OSSQ-Maier.pdf ...
       uv run experiments/zeus/autodetect.py <edition-repo> --pdf OSSQ-Maier.pdf --name OSSQ-Maier --pages 1-69:vn1
       mv experiments/zeus/auto/OSSQ-Maier.json ~/.cache/manuscript-labeler/ossq/auto-OSSQ-Maier.json

   The learned bar-line filter is trained once per `--name`, on every
   labelled source. To skip retraining, copy one OSSQ name's
   `auto/cache/` folder to the next.

4. **Score,** with Zeus's Python (run outside the sandbox):

       UV_PYTHON_INSTALL_DIR=~/.cache/manuscript-labeler/zeus/py \
         uv run --python-preference only-managed experiments/zeus/ossq/score.py \
         Maier ~/.cache/manuscript-labeler/ossq/sq7551068.musicxml --model <model> ...

   The default models are the untouched snapshot and run G. Readings are
   cached in `~/.cache/manuscript-labeler/ossq/answers/`, and the result
   goes to `result-<name>.json` there.

## What score.py measures

The share of encoded bars Zeus reads exactly right (every note's pitch
and duration, and the rests), by part. `mxl.py` reads OSSQ's MusicXML
system by system, as compare.py reads the edition's encoding.

No one has labelled these manuscripts, so nothing says which staff
holds which bars. Detection's staves are grouped into systems of four.
Those are lined up with the encoding's systems by dynamic programming,
on how many bars every model reads right in rhythm, with one line-up
for all the models. On a lined-up staff, Zeus's measures are paired
with the encoded bars in order, skips free.

So it's stricter than compare.py, which pairs measures with the
editor's labelled bar boxes:
- a bar on a system that nothing lined up with counts as wrong;
- OSSQ's line breaks are sometimes a bar off.

Compare models with each other here, not with the Op. 48 numbers.

## Results

Exact bars, of all encoded bars:

| model | Maier (925 bars) | Andrée (3,295) | Mayer A (3,636) |
|---|---|---|---|
| untouched | 54% | 35% | 23% |
| run G | 47% | 30% | 34% |
| run H, epochs 6–8 | 39–42% | 22–24% | (trained on) |
| run I, epochs 6–7 | 46% | 26–27% | — |

Run H trained on 145 of Mayer A's staves. Each fine-tune on Boccherini's
copyists narrows Zeus on Maier and Andrée. Mayer A, whose writing is
closer to the copyists', gained.
