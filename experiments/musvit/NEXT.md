# Next: bank the win, then explore

Written 2026-10-18. BRIEF.md is the log; README.md the results so far.

## Stage gate: crown a reader before exploring further

**Done 2026-10-18** (README.md, round 4): D3 crowned and released as
`musvit-D3` (270/347 on the clean test), `musvit-D1` kept as the held-out
reference; the no-Op. 22 run showed Madrid measures the music more than the
reader, so the rule in step 2 was replaced by the clean test plus the
held-out pair; public benchmarks measured; model card, registry entries,
zeus-score 1.1.0. Still open from the gate: measure and retune the edition's
flags with musvit-D3 before it replaces Zeus J as the default.

The plan as written:

Nothing new is tried until these are done. The aim is a model we can name,
use and compare everything else against.

1. **Read the overnight results** (scratchpad `overnight-summary.md`): Zeus J,
   C1, C4 and the two retrained readers (D1, D2: same recipes, plus the
   re-paired Philhar staves with two voices) on the Madrid test (375 staves)
   and the clean test.
2. **Pick the recipe.** Rule: the best on Madrid by symbol errors, unless it is
   within the noise (paired resampling over staves) of a simpler one, which
   then wins. The clean test breaks a tie; it no longer chooses alone.
3. **A clean Madrid number.** Op. 22's music is in training through its
   Berlin and Paris copies, so Madrid flatters every model that saw it (Zeus J
   too). Retrain the chosen recipe once without any Op. 22 source and score
   Madrid: that is the number to quote for an unseen hand and unseen music.
   (About $1.)
4. **Train the crowned model** on everything except the Madrid copies: all
   Op. 48 movements (KHM 602 II and Op. 48/5 I included), all re-paired
   Philhar staves; stop at the pass the held-out run chose (`--stop-at`).
   Name it (for example `musvit-1`), give it a model card like Zeus's (data,
   recipe, both test numbers, what it gave up on Dolores, licence: CC BY-NC-SA
   from MuSViT and Zeus's data) and a registry entry beside Zeus's.
5. **Record what we learned** in README.md: what helped, what didn't, what
   didn't stack, costs.
6. **Commit and push.** Wiring it into the edition (replacing Zeus J in
   zeus_score) is its own step after this, with the flag threshold retuned.

## Exploration batch: synthetic quartet staves

The hypothesis: our errors sit in the quartet idiom (viola in alto clef, dense
32nds, broken chords, double stops), and the public staves we pretrain on are
not quartet writing. Unlimited exactly-labelled quartet staves, printed and
then handwritten, should teach that idiom. Supporting evidence: Smashcima
synthetic manuscripts took Zeus from 41% to 33% SER on real piano manuscripts
(Mayer et al. 2026, arXiv 2606.09479), with replay best.

Each step is measured on Madrid (and the clean test) against the crowned
model, and kept only if it beats it beyond the noise.

### E1. Replay (cheapest; run first)

Mix a share of the public staves (and later, synthetic ones) into stage 2.
Measure Madrid, the clean test, and Dolores (does it keep what it knew?).
Cost about $1 per run; try 10% and 30%.

### E2. Quartet music to render

Sources, licence first:
- **Our own encodings**: Philhar's Boccherini quartets and the edition's
  Op. 48, written per staff by dataset.py already. Nearly free; exactly our
  composer. Leave out the test pieces' music (KHM 603 I, Op. 22).
- **OpenScore String Quartets** (CC0): built for this kind of use.
- **humdrum-data / kernscores**: Haydn, Mozart, Beethoven quartets in kern;
  convert to MusicXML (verovio or music21). Check its licence file.
- **MuseScore** quartet parts download as MusicXML (about 2,600 quartet
  scores). Its search filters by licence, so take only those marked public
  domain or CC0, and fetch them within the site's terms (no scraping beyond
  what they allow).

Output: single-staff MusicXML per part line, cut into staves the way our
staves are (a system's worth of bars), with LMX labels from the lmx encoder.

### E3. Printed renders

Render each staff with verovio (fast, scriptable), at our staves' size and
proportions, with mild scan augmentation. Use as the public-data stage
(replacing or joined to Dolores/OmniOMR), then stage 2 as usual.
Cost: a day's work; about $5 per stage 1.

### E4. Handwritten renders from hands we've seen

Smashcima renders MusicXML in a handwritten style from a glyph set (MuNG
annotations of symbols). Two routes:
- **Generic glyphs first** (MUSCIMA++): free, and the paper found the glyph
  source stopped mattering after fine-tuning on real staves.
- **Our copyists' glyphs**: needs symbol-level annotation of our hands, which
  the paper put at about ten times the cost of transcribing. Only if generic
  glyphs help and the gap to our hands looks like the limit. A cheaper idea to
  test first: harvest glyphs automatically from our labelled staves (we know
  each staff's notes; cutting noteheads, stems, beams and clefs at the
  positions the reader attends to), then hand-check a sample.

Check first: whether Smashcima renders a single staff (its paper renders
piano systems) and how it joins stems to noteheads (the paper names this as
a gap for historical hands).

### Order and stopping

E1 → E2+E3 → E4 (generic) → E4 (our hands, only if warranted). Stop a line
when it fails to beat the crowned model on Madrid beyond the noise. Budget:
ask before any stage-1 run; the user OK'd about $30–40 per productive night.

## Still open, outside this batch

- Cut staves on Modal, not the Mac: read_auto.py and autopair.py each crop
  every staff locally (slow at background priority). The PDFs are already in
  the musvit-staves volume (/staves/pdfs); a Modal function can cut and read
  in one pass, and autopair can take the keys from it instead of re-cutting.

- Replace Zeus J in the edition (PyTorch path in tools/zeus_score.py, Mac
  re-check, flag-threshold retune, package and licence).
- Measure what fine-tuning gives up on public benchmarks (Dolores; others
  only if a final model warrants it).
- Extend label-free pretraining with the shelf's manuscripts (scores
  included: Op. 8/4, BnF Op. 2/1, Leipzig Op. 32).
- A movement the user encodes next, kept out of training, as a second clean
  test.
