# Where the data lives

**The rule:** original work (labels, code, findings) lives in Dropbox, and
for this project that means the repo. Everything outside Dropbox can be
downloaded again, rebuilt, or lost without regret. There are two roots for
it, both visible:

- **`~/Data/OMR/datasets/`**: public datasets any project may use. Each
  folder has a `SOURCE.md` saying where it came from.
- **`~/Data/manuscript-labeler/`**: this project's staff sets, renders,
  runs and experiment outputs, built from the repo and the datasets.

Nothing big should live anywhere else. If `du` finds some, it belongs in one
of these or should be deleted.

**The registry:** `~/Data/registry.toml` lists every folder in `~/Data`,
with the projects that rely on it; `~/Data/README.md` says how to add one.
A dataset with no consumers can be deleted. This project is registered as a
consumer of `musicorpus` and `openscore-quartets`, of `ossq-omr` and BA 2676, of `philhar-site` and `philhar-mss`, and of its own folder.
This file is the lasting record of those dependencies: when the labeler
starts or stops relying on a dataset, change both this file and the
registry.

| Folder | What | Size | Where it came from | Also kept |
|---|---|---:|---|---|
| `OMR/datasets/musicorpus` | MusiCorpus v1.0: Dolores and OmniOMR staves with their MusicXML (below) | 4.0 GB | LINDAT, link below | Test staves on Modal (`musvit-staves/public`) |
| `OMR/datasets/openscore-quartets` | 102 classical quartets as MusicXML; CC0 | 15 MB | [OpenScore String Quartets](https://github.com/OpenScore/StringQuartets) | |
| `OMR/datasets/ossq-omr` | OSSQ-OMR's metadata (scan URLs, splits) and, optionally, its IMSLP scans; made by `experiments/ossq/register_local.sh` | small (1 GB with scans) | [ossq-omr](https://github.com/MALerLab/ossq-omr) omr-dev 7a17e45; IMSLP | Staves on Modal (`musvit-staves/ossq`), scans and renders in `ossq-raw` |
| `manuscript-labeler/imslp/barenreiter-ba2676` | Bärenreiter BA 2676, Boccherini's *Ausgewählte Streichquartette* (1952): four engraved parts and the covers; public domain per IMSLP. Its page map is `experiments/print-omr/pagemap.json` | 7 MB | IMSLP #370564–370568, a subscriber's browser download (captcha) | |
| `manuscript-labeler/philhar-site` | Philhar's LilyPond for 14 manuscript-sourced string works (Boccherini op. 4 trios, Campioni op. 7, Giardini, M. Haydn MH 411), one folder each, and `lily/<work>/` in the layout `experiments/zeus/philhar.py` reads; plus the survey's first sample; CC BY-NC-SA | 16 MB | Wayback Machine captures of le-concert.pagesperso-orange.fr; `experiments/philhar-mss/fetch_lily.py` and `adapt.py`; see `reports/2026-10-20-philhar-site/` | |
| `manuscript-labeler/philhar-mss` | Scans of the manuscripts behind those encodings, one PDF per source (SBB KHM 620-624 and Mus.ms. 2861, SLUB Mus.3403-P-513, Sibley M351.B664M, Montecassino 1-C-7, Giardini). Page maps: `experiments/philhar-mss/pagemaps/`. Also `US-R_M351.B664M/US-R_M351.B664M-levels.pdf`, the Sibley scan levelled for detection (rebuilt by `experiments/zeus/wayback-print-pairs/README.md`) | 0.4 GB | Library IIIF and PDF downloads and one IMSLP file: `experiments/philhar-mss/fetch_scans.py` | |
| `manuscript-labeler/experiments/print-omr` | BA 2676's pages at 300 dpi (`pages/`), the same cleaned for Audiveris (`clean/`), and Audiveris's MusicXML and logs (`audiveris/`) | 0.1 GB | `experiments/print-omr` (README, "Rerun") | |
| `manuscript-labeler/tools/audiveris-5.11.0` | Audiveris 5.11.0 (AGPL-3.0), the macOS arm64 app taken out of its release .dmg, with its own Java | 0.2 GB | [GitHub release](https://github.com/Audiveris/audiveris/releases/tag/5.11.0) | |
| `manuscript-labeler/zeus` | Staff sets, page renders, Zeus runs (below) | 16 GB | `experiments/zeus` and `experiments/synth` | Most staff sets on Modal (`musvit-staves`) |
| `manuscript-labeler/musvit` | MuSViT's code (an unmodified clone of its GitHub repo), weights and runs | 2 GB | `experiments/musvit` | Readers as GitHub releases; runs on Modal (`musvit`) |
| `manuscript-labeler/experiments/sam` | Segment Anything: training and test windows, trained decoders, scores | 0.6 GB | `experiments/synth/sam_*.py` | Later runs on Modal (`copyist-sam-runs`) |
| `manuscript-labeler/experiments/synth` | The quartet music cut into 44,609 staves (`osq-lmx`, `osq-all.txt`), sheets and logs | 1.3 GB | `score_to_lmx.py` on `openscore-quartets` | |
| `manuscript-labeler/experiments/maps` | Classical maps and curated glyphs, KHM 602 and 603 | 0.2 GB | `align.py`, `segment.py`, `curate.py` | |
| `manuscript-labeler/experiments/pos` | The pointer's results | 0.1 GB | `pos_data.py`, `pointer.py` | Training staves on Modal (`musvit-staves/pos`) |
| `manuscript-labeler/experiments/benchmarks` | Every reader's readings of the Dolores and OmniOMR test staves, and the tables | 10 MB | `experiments/musvit` | |
| `manuscript-labeler/experiments/scratch-2026-10-19` | The rest of that session's scratchpad: one-off scripts and pictures, fine to lose | | | |

**The OSSQ scans** (IMSLP, for `experiments/zeus/ossq`) aren't kept.
`ossq_fetch.py` downloads them again; it needs you logged in to IMSLP in a
browser.

## Paths the code uses

The code still names `~/.cache/manuscript-labeler/zeus` and
`~/.cache/manuscript-labeler/musvit`. Those are now links to the folders
above, so nothing had to change. `zeus/musicorpus` is likewise a link to
`OMR/datasets/musicorpus`.

The rest of `~/.cache/manuscript-labeler` is the labeler's own cache, managed
by `server.py`, and stays put:
- `renders`: page images for the editor;
- `models`: readers and detectors downloaded from releases;
- `backups`;
- `detections`, `datasets`, `claude`.

The labels themselves are in the repo (`data/`).

## The datasets

**MusiCorpus v1.0** bundles two handwritten-music sets, each staff with its
MusicXML:
- **CVC.Dolores:** 1,209 pages from Catalan archives, 78 scribes, about
  1750–1900. CC BY-NC-SA.
- **UFAL.OmniOMR.**

It matters to us in three ways:
- Zeus's starting model was trained on its train and validation splits.
- Its test splits are our public benchmark: 2,357 Dolores staves and 257
  OmniOMR staves.
- The pointer's Dolores staves come from it.

The full zip is at
`https://lindat.mff.cuni.cz/repository/server/api/core/bitstreams/fdf9ba56-1854-45fc-a8d2-311dfb3ad8c3/content`.
Its stylus polygons are fetched from the zip by range requests, without
downloading the whole of it (`experiments/musvit/drivers/dolores/`). The paper is arXiv 2605.18436, and the handle is
http://hdl.handle.net/20.500.12800/1-6147.

`zeus/data/dolores` is Zeus's copy of the Dolores staves: the same images,
plus LMX. The images are APFS clones of MusiCorpus's, so they take no extra
space. `du` still counts them twice.

## In `zeus/`

- **`dataG` … `dataT`, `dataL2`, `dataS3`, `dataM`:** staff sets, one per
  build. `dataL2` is Op. 48's training staves with every beam. `dataS3` is
  the synthetic staves. `dataG213` is G. 213's three copies paired with
  OSSQ's encoding (`experiments/zeus/g213/README.md`). See
  `experiments/musvit/BRIEF.md`.
- **`dataM2`:** Philhar's LilyPond pairings made again with the G. 213
  pipeline and musvit-D4 (`experiments/zeus/philhar-repair/README.md`):
  dataM's and dataT's sources re-paired, plus the full scores and copies
  never paired before. One list per source, `samples.<source>.txt`; the
  Madrid copies (dataT's role) are `samples.Op22-*-EMc.txt`. On Modal at
  `/dataM2` in `musvit-staves`. Rebuild with `philhar-repair/build.sh`.
- **`dataW`:** Philhar's other string works (Boccherini's op. 4 trios,
  Campioni's op. 7 duos, the Giardini duet, M. Haydn's MH 411) paired
  with their manuscripts, `experiments/zeus/wayback-print-pairs/README.md`.
  One list per source, `samples.<source>.txt`. On Modal at `/dataW` in
  `musvit-staves`. Rebuild with `wayback-print-pairs/build.sh`.
- **`dataP`:** G. 223's two manuscripts (KHM 600, F-Po RES-507 (10))
  labelled with the bars of the Bärenreiter print that two OMR readers
  agree on (same README). One list per source; some staves are cut after
  their first bars. On Modal at `/dataP` in `musvit-staves`.
- **`dataM4`, `dataW3`, `dataP3`, `dataG213-3` (2026-10-22):** the same
  sets, lists and options, from a full re-detection of all 57 paired
  sources (`detect.py`: each staff's ink threshold from its own lines and
  spaces, short staves with music past their ends given the page's span, a
  detector's end ignored where music runs on past it, ruled slots followed
  along the neighbours' ruling). Every changed crop was read again
  (7,544 staves with D3S-h96, 4,625 with C4-bocch-tf8-L) and every source
  paired again; the short-staff rule now fires on 69 staves of the W and
  G sources, against 275. Counts: dataM4 4,134 staves (23,900 bars),
  against dataM3's 3,686 (21,294); dataW3 1,066 (7,415), against 999
  (6,930); dataP3 21 (147), the same; dataG213-3 435 (2,440), against 430
  (2,409). Crops changed, so a staff's image may differ from the earlier
  sets'. Not yet on Modal.
- **`dataS4`:** 3,970 synthetic staves that change clef inside the staff
  (cello bass to tenor or treble and back, viola alto to treble), drawn by
  `experiments/synth/gen_clefs.py` (README there). List
  `samples.S4-clef.txt`; on Modal at `/dataS4` in `musvit-staves`.
- **`g213/`:** the Sibley scan of G. 213 (IMSLP 78818) and OSSQ's encoding
  of it, both downloadable again.
- **`ms200/`:** F-Pn MS-200 (Op. 8 no. 4, a microfilm of two-page
  openings) cut into single pages, and those pages with the film's grey
  paper levelled to white, which detection needs; rebuilt from the archive
  by the commands in `experiments/zeus/philhar-repair/README.md`.
- **`data/`:** Zeus-format datasets: Dolores, OmniOMR, and each manuscript's
  staves.
- **`renders/`:** pages rendered at 2,800 px, one folder per PDF (named for
  it plus a hash of its contents). This is a cache: delete it freely.
- **`runs/logs/`:** Zeus fine-tuning runs, Oct 9–16. Run J's last epoch is
  the GitHub release `zeus-J-lr1e5-e8-2026-10-16`.
- **`py/`:** Python installs for Zeus.
- **`glyphs/`, `maps/`, `philhar-lines/`.**

## Rebuilding what isn't obvious

**The held-out quartet staves**
(`experiments/sam/heldout.txt`, 42,560 of `osq-all.txt`'s 44,609) are the
staves no training set drew from. `sam_synth.py` shuffles `osq-all.txt`
with `random.Random(seed)` and draws from the front. The held-out list is
`osq-all.txt` minus the first 260 staves of that shuffle, for each seed in
0, 100000, 200000, 300000 and each of those plus 7.

## Elsewhere

- **Modal volumes:**
  - `musvit-staves`: staff sets, the public test staves, the pointer's
    staves;
  - `musvit`: weights and runs;
  - `copyist-sam-runs`;
  - `hf-cache`.
- **GitHub releases** (`gh release list`): `zeus-J-lr1e5-e8-2026-10-16`,
  `musvit-D1-2026-10-18`, `musvit-D3-2026-10-18`.
- **Source PDFs:** the edition's `sources/`, and
  `boccherini-quartet-data/manuscripts`.
