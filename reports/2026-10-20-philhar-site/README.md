# Philhar's site: manuscript and LilyPond pairs beyond the quartets (2026-10-20)

Working note. Philhar ("Editions Le Concert") encoded much 18th-century
music in LilyPond. His site, le-concert.pagesperso-orange.fr, is down. The
Wayback Machine has it. We already pair his Boccherini quartets with
manuscripts. The question here: what else on his site comes from a
manuscript, in another period hand, with LilyPond we can get?

**Verdict.** A small but real seam. Ten work sets name a manuscript source.
Six are new, period string music, with LilyPond archived and a scan online:
18 works, roughly 1,700 staves of parts in at least five hands. The best are
Boccherini's op. 4 trios (Sibley parts), Michael Haydn's quintet MH 411
(Salzburg parts) and Campioni's op. 7 duos (Berlin parts). philhar.py reads
them after renaming files and a `Global.ily` fix. The rest of the chain
assumes a quartet, so trios, duos and a quintet need small changes.

## Counts

- **Composers:** 38 composer pages.
- **Work sets:** 64. **Works:** 251 LilyPond zips (250 works; Fauré's
  Élégie comes in two versions).
- **Scoring:** 15 sets of string quartets, 10 string trios, 4 duos, 1
  quintet, 10 cello and bass, 5 for two bass instruments, 18 orchestral, 1
  piano and cello.
- **Sources named:** 48 sets print only; 6 name none; **10 name a
  manuscript** (32 works). Of the 10, 6 are manuscript only (Giardini,
  J. Haydn, M. Haydn, Hofmann, Hummel, Koessler) and 4 mix manuscript and
  print (Boccherini op. 4 trios, op. 22, op. 24; Campioni).
- **LilyPond archived:** all 251 zips have a Wayback capture with status
  200 and a zip type. I fetched 13; all unpack.
- **Scans:** all 10 manuscript sources have a scan online.
  - Checked live: Berlin's viewer (Campioni, J. Haydn) and Eichstätt's
    (Hofmann) answer.
  - Dresden (M. Haydn) refuses scripted requests (403), but IMSLP has its
    scan.
  - The Sibley trio parts, the Montecassino score, Giardini and Hummel are
    listed on IMSLP. I didn't fetch them.
  - Op. 22 and op. 24 are already on disk.
- **Links:** 25 sets link an IMSLP work page. Gallica and BnF are named in
  the text but never linked. No library is linked.
- **New and in scope:** 18 works in 6 sets (string music, 1750–1810, not
  already ours).

Raw list: [philhar-site.json](philhar-site.json), one entry per work set,
with every zip, its Wayback capture, and the resolved manuscripts.

## Ranked: manuscript-sourced works

Staves are rough: bars per part from Philhar's `Trame.ily`, at about 8 bars
a staff, times the parts. Past pairings kept 22–73% of detected staves.

| # | Work | Manuscript Philhar used | Parts or score, date | Scan | LilyPond | Staves | Why here |
|---|---|---|---|---|---|---:|---|
| 1 | Boccherini, 6 Trios op. 4, G. 83–88 (2 vl, vc) | US-R M351.B664M (Sibley), RISM 130195; and a score, probably I-MC 1-C-7 (Montecassino) | 3 parts, 1766–75, unknown hand | IMSLP (Sibley); Internet Culturale | archived; **already on disk** in `boccherini-quartet-data/lilypond/dl-scripts/boccherini/trios/` | ~600 | Biggest. String parts. A non-Berlin hand of Boccherini's own music. Berlin also holds KHM 620–624 (5 of the 6, Schober's hand, SBB scans): ~500 more staves on the same encodings. |
| 2 | M. Haydn, Quintet in F, MH 411 (2 vl, 2 va, vc) | D-Dl Mus.3403-P-513, RISM 210044350 | 5 parts, 8+8+7+7+7 folios, ca. 1770–1800, Salzburg copy | IMSLP (from SLUB) | archived; sample downloaded | ~600 | A new hand and region. One source, so the encoding should match it. 921 bars, 7 movements. |
| 3 | Campioni, 6 Duos op. 7 (vl, vc) | D-B Mus.ms. 2861, RISM 452007625 | 2 parts, 10+10 folios (41 images), ca. 1780 | SBB, IMSLP | archived; sample downloaded | ~260 | Parts near our copyists' date. Berlin scans download by script. But the encoding mixes the manuscript with Bremner's print. |
| 4 | J. Haydn, Baryton Trios Hob. XI:25–27 (baryton, va, vc) | D-B Mus.ms. 10037 (Johann Elssler and others), RISM 452005366 | 3 parts, ca. 1790 | SBB, IMSLP | archived | ~140 | Elssler, a Viennese professional, is a new hand. Small: 3 of the volume's 72 trios. The baryton part is an odd staff. |
| 5 | L. Hofmann, Divertimento in D (2 vc, b) | D-Eu Esl VIII 405, RISM 450300198 (copyist Steger) | 3 parts, 2+2+2 folios, ca. 1800 | Eichstätt (bot gate, by hand), IMSLP | archived; sample downloaded | ~60 | Same Eichstätt collection as our op. 2 copies. All bass and tenor clef. Small. |
| 6 | Giardini, Duo in F (vl, vc) | a manuscript on IMSLP; library not named | parts, date unknown | IMSLP | archived | ~55 | Small, and the source is unidentified (perhaps I-Gl M. (3) 22.7, RISM 850810319). |
| – | Boccherini, Quartets op. 22 | F-Pn Vmb ms. 153 (Baillot) | parts | on disk | in quartet data | | Already paired (336 staves ready). His cSource names the Chevardière print; the manuscript gave variants. |
| – | Boccherini, Quartets op. 24 | F-Pn MS-1292, autograph | score, 1777 | on disk | in quartet data | | Already tried: 29 of 468 staves kept. |
| – | Hummel, Cello Sonata op. 104 | HAAB Weimar, autograph | score and cello part, 1824 | IMSLP | archived | | Out of period; piano. |
| – | Koessler, Suite for 3 cellos | D-B, autograph | 1925 | IMSLP | archived | | Out of period. |

**Leads, not ranked.** Period manuscript copies of works Philhar encoded
from prints, found in RISM with scans. Each would pair the same way.

- Boccherini cello sonatas G. 1 and G. 4: Eichstätt Esl VIII 407 and 349,
  ca. 1790.
- Boccherini trio G. 98 (op. 14 no. 4): Eichstätt Esl VIII 21, parts,
  ca. 1790.
- Hoffmeister: Eichstätt Esl VIII 395 (a quartet in G) and 430 (a trio in
  G), Leipzig Go. S. 215 (three quartets). Not yet matched to his op. 14 and
  op. 22 by key or incipit.

## What pairing would take

The sample is in `~/Data/manuscript-labeler/philhar-site/` (MH 411,
Campioni op. 7, Hofmann), with a README.

**The layout is the same.** A `Trame.ily` skeleton holds time, key and
repeats under `\tag #'mvtI ...`. Notes are written once per part and
movement, with `\tag #'partie` for part-only marks. That is what
philhar.py reads.

**The names are not.** Files carry the work's number:
`12005-HaydnM-Quintette-MH411-Trame.ily`, `12005-01-Violon1-1.ily`,
`11029-03-Bs-2.ily`, `13021-1-Cello-3.ily`. The quartet data was renamed to
`Trame.ily` and `01-V1-1.ily` by hand.

**Tested.** I copied four works to philhar.py's names and ran it with
LilyPond 2.26 on one part and movement each:

- MH 411 and Hofmann read, using the quartet data's `Global.ily`. Their own
  fails in 2.26, in its `\paper` block.
- Campioni reads with its own `Global.ily` after `convert-ly`. Its notes
  use macros defined there (`\un`, `\rinf`).
- G. 83 (2012, LilyPond 2.16) reads after `convert-ly` on every file, plus
  one fix: its staccato helper passes `"staccato"` where 2.24 wants a
  symbol.
- Bar counts match the skeletons (MH 411 movement I: 170; G. 83 movement
  I: 105).
- Each needs `cc.eps` and `cc2.eps` beside it.

**Changes, smallest first:**

1. An import step per work: copy and rename to `Trame.ily`, `Global.ily`
   and `0N-<part>-M.ily`; run `convert-ly`; fix old Scheme; add the eps
   files. The same as was done for the quartets.
2. philhar.py: a part-to-file map per work instead of the fixed quartet
   one, and movements past IV (MH 411 has seven).
3. The rest of the chain fixes the parts to `vn1, vn2, va, vc` (autopair,
   autodetect, dataset, barcheck, compare). Trios and duos fit inside that.
   The quintet's second viola, Hofmann's three bass parts and the baryton
   need new part names, or a mapping onto the four.
4. Each manuscript needs its page map (which part on which page), as for
   the other sources.
5. Scans: Berlin resolves by script. Eichstätt needs a browser. Sibley and
   the Dresden copy come from IMSLP, which needs a logged-in browser.

## Caveats

- **Which source the notes follow.** Philhar often lists several sources
  and follows one, noting others in comments. Campioni mixes manuscript and
  print (`BR:` and `MS:` comments). The op. 4 trios name two prints and two
  manuscripts and don't say which the notes follow. Expect some bars that
  disagree with the scan; pairing drops them, at a cost in yield.
- **Detection is the bottleneck.** Its staff and bar-line detectors were
  trained on Op. 48. On Schober's Op. 32 hand it kept 22%. New hands may do
  as badly until detection is retrained.
- **"Manuscript" on his site is loose.** Giardini's names no library.
  Op. 4's "score" is identified only by IMSLP's listing.
- **Staff counts are estimates** from bar counts, not from the scans.
- **Snapshot.** Composer pages came from captures of 30 September to
  3 October 2023. The Wayback index has no composer page beyond these 38.
  Captures from 2015 show a smaller, earlier site.
- **The site is not his whole output.** IMSLP holds more Philhar editions
  (Boccherini op. 32 and 33, used already, aren't on the site). His IMSLP
  uploads were not surveyed.
- **Licence:** CC BY-NC-SA.

## Method

- Crawled the home page and 38 composer pages from the Wayback Machine
  (raw `id_` captures, about one request a second). Listed every zip, PDF
  and outside link per work set (`scripts/parse.py`, `scripts/build.py`).
- Checked every zip's archive status with one CDX query.
- Resolved each named manuscript in RISM Online's JSON API and IMSLP's
  public wiki API, without logging in (`scripts/rism.py`,
  `scripts/imslp.py`). Checked the scans' landing pages, not the scans.
- Counted bars from each `Trame.ily` (`scripts/bars.py`).

## Cost

Mac (M1) CPU, about 1 hour of wall time, mostly polite waits on the
network. No GPU.
