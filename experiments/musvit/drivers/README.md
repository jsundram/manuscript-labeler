# Drivers

The scripts that ran the MuSViT experiments, 16–19 October, with their
summaries. They were written in a session's scratchpad and are kept here as
they ran, so each result in `BRIEF.md` can be traced to the commands behind
it.

**They aren't tidy tools.** Most launch `modal run` on `modal_app.py` or
`pointer_modal.py` and wait. Some name the session's scratchpad (now gone)
or `~/.cache/manuscript-labeler` paths. To rerun one, read it first and
point its paths at `~/Data/manuscript-labeler` (see `docs/storage.md`).

| Script | What it ran | Summary |
|---|---|---|
| `repair.sh` | Re-paired the 34 detected sources with reader C4 | `repair-summary.txt` |
| `madrid.sh` | Paired the Madrid copies of Op. 22 with Zeus J and C4; kept staves both pair alike | |
| `overnight.py` | The overnight chain of 18 October: dataM, dataT, D1 and D2, scored on Madrid and the clean test | `overnight-summary.md` |
| `color_test.py` | Reading in colour against grey | `color-summary.md` |
| `holdout.py` | H1: D1's recipe without Op. 22 and Op. 32, scored on music it hasn't seen | `holdout-summary.md` |
| `control.py` | H1's control: as many Philhar staves, chosen at random | `control-summary.md` |
| `train_d3.py` | Trained musvit-D3 (run D3-tf8-all), the released reader. Named `release.py` in the scratchpad; not the packager `../release.py` | |
| `synth_gap.py` | musvit-D1 on synthetic staves against real ones it hasn't seen | |
| `synth_test.py` | S0 and S1: D1's recipe with and without synthetic staves | `synth-summary.md` |
| `synth_first.py` | SF1 and SF2: synthetic staves first, then real | `synth-first-summary.md` |
| `philhar_first.py` | PF1 and PF2: the hand-or-music test, Philhar's music drawn two ways | `philhar-first-summary.md` |
| `cheap/cheap.py`, `cheap/analyze.py` | Replay (E1) and strip height | `cheap/*-summary.md` |
| `bench*.py` | The public benchmarks: Dolores and OmniOMR test staves read by Zeus and the MuSViT readers, then scored alike (`bench_score.py`) | `~/Data/manuscript-labeler/experiments/benchmarks/public-table.md` |
| `dolores/` | Fetches Dolores's symbol annotations from the MusiCorpus zip by range requests (`listzip.py` lists it, `fetch_all.py` fetches; needs `remotezip`). The pointer's Dolores staves are built from these | |
| `shrink.py` | Shrinks the pointer's staves to 256 px high, their places scaled with them | |
