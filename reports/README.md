# Reports

The findings: what we tried, what it showed, and why. Code and labels say
what the labeler does; reports say what we learned getting there.

- **[index.md](index.md):** every report, newest first, with what it found.
- **[journal.md](journal.md):** the story. One entry per report, giving the
  context, why it was made, and what it led to.

## The reader's training stages

The MuSViT reader is trained in stages. Reports name each stage for what
it trains on and its size in staves, with the run name in parentheses
where it's needed to reproduce something:

| stage | what it trains on | staves |
|---|---|---:|
| **Public 9k** | the public datasets, MusiCorpus's Dolores and OmniOMR (E2-tf8 at 128 px, E2-h96 at 96 px) | 8,765 |
| **Public 22k** | the same, plus OSSQ-OMR's scanned 1750–1800 quartet staves (E3-h96-ossq) | 22,006 |
| **Drawn 11k** | OpenScore's quartets and our own training music, drawn in our copyists' hands (dataS3) | 10,790 |
| **Drawn 15k** | the same, plus staves that change clef inside the staff (dataS3, dataS4) | 14,760 |
| **Drawn Philhar 11k** | Philhar's own music, drawn in our copyists' hands (dataPc) | 10,787 |
| **Engraved Philhar 11k** | the same staves engraved in a printed font (dataPp) | 10,787 |
| **Boccherini 2.9k** | D1's recipe: Op. 48's training movements and the re-paired Philhar staves (dataL2, dataM) | 2,892 |
| **Boccherini 3k** | everything of Boccherini's but the clean test: Op. 48's training and practice-exam movements, the re-paired Philhar staves, the Madrid copies (dataL2, dataM, dataT) | 3,411 |

A reader is its chain: musvit-D3 is Public 9k → Boccherini 3k at 128 px;
musvit-D4 is Public 9k → Drawn 11k → Boccherini 3k at 96 px.

## Adding a report

1. **Make a folder:** `reports/YYYY-MM-DD-slug/`. Put the report in it
   (`README.md`, or `index.html` for a page), with its figures and any script
   that drew them.
2. **Add a row to the index,** at the top.
3. **Add a journal entry,** at the top. Say what prompted the report, the
   question it answers, what it concluded, and what was done about it.
4. **Record its cost,** in a Cost section and in the index's Cost column:
   the machine, and the time it took (wall hours on the Mac). For cloud work
   also the dollars: on Modal, the GPU type, GPU-hours and $ (from
   `modal billing report --show-resources --json`, which can be split by
   app); for the Claude API, the $. Say whether each number is measured
   (logs, billing) or estimated. Analysis alone costs "none".
5. **Cite the report in commits** that act on it, by its folder: "See
   reports/2026-10-19-smashcima."

**A page published as an artifact is a report too.** Save its HTML here, in
its folder, and put its link in the index. When the artifact is republished,
update the saved copy.

**Reports are original work.** They live here, in the repo, never in
`~/Data` (see `docs/storage.md`). Their figures go in the report's folder;
keep each one small, as a JPEG unless it needs sharp edges.

**Earlier write-ups** stay where they were written, so commits and links to
them still work. That covers `experiments/*/README.md`, the model cards and
`docs/`. The index points to each in place.
