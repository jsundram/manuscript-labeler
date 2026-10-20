# Reports

The findings: what we tried, what it showed, and why. Code and labels say
what the labeler does; reports say what we learned getting there.

- **[index.md](index.md):** every report, newest first, with what it found.
- **[journal.md](journal.md):** the story. One entry per report, giving the
  context, why it was made, and what it led to.

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
