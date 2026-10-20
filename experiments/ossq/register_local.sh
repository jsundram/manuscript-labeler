#!/bin/sh
# Register OSSQ-OMR in ~/Data (the sandbox can't write there; run this yourself).
#   sh experiments/ossq/register_local.sh [--pdfs]
# Makes ~/Data/OMR/datasets/ossq-omr with a SOURCE.md and the small metadata
# this rebuild used; with --pdfs it also copies the IMSLP scans down from the
# ossq-raw Modal volume (about 1 GB; they can be fetched again, so optional).
# Then appends a [[dataset]] entry, with manuscript-labeler as its consumer,
# to ~/Data/registry.toml (once).
set -e
D=~/Data/OMR/datasets/ossq-omr
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$D/metadata"
SHA=7a17e45cddc0b7064fc3a179b62caeb57595e993
for f in data/scores_w_url.yaml data/scanned_score_types.tsv data/scores.yaml data/score_types.md; do
  curl -sfL "https://raw.githubusercontent.com/MALerLab/ossq-omr/$SHA/$f" -o "$D/metadata/$(basename $f)"
done
cp "$HERE/splits.json" "$HERE/scanned_ids.txt" "$HERE/synthetic_ids.txt" "$D/metadata/"
if [ "$1" = "--pdfs" ]; then
  modal volume get ossq-raw pdfs "$D/"
fi
cat > "$D/SOURCE.md" <<'EOF'
# OSSQ-OMR (OpenScore String Quartets for OMR)

Kim, Liu, Valero-Mas, Jeong, "A Dataset and Benchmark for Optical Music
Recognition of String Quartet Scores", ISMIR 2026. Data CC0, code MIT.

- Encodings (corrected to match the scans): https://github.com/MALerLab/ossq-omr
  branch omr-dev, commit 7a17e45cddc0b7064fc3a179b62caeb57595e993.
- Pipeline: https://github.com/MALerLab/omr-data-preprocessor (bdea0d1),
  https://github.com/MALerLab/lmxe; splits from https://github.com/MALerLab/sqomr
  (4926e69) metadata/.
- Scans: IMSLP, at the direct URLs in metadata/scores_w_url.yaml (no login).
- Bulk images: not yet published (Zenodo / Hugging Face TBD).

Here: metadata/ (score list with scan URLs, types, our splits.json and id
lists) and, if copied, pdfs/ (the IMSLP scans, sq<id>.pdf).

The staff images and LMX labels built from it live on Modal, in volume
musvit-staves under ossq/ (scanned, synthetic, manuscript TEST ONLY); the
PDFs and MuseScore renders in volume ossq-raw. Rebuild with
manuscript-labeler's experiments/ossq/ossq_modal.py (see PLAN.md there).
EOF
if ! grep -q 'path = "OMR/datasets/ossq-omr"' ~/Data/registry.toml; then
  cat >> ~/Data/registry.toml <<EOF

[[dataset]]
path = "OMR/datasets/ossq-omr"
name = "OSSQ-OMR (ossq-omr omr-dev 7a17e45): metadata and IMSLP scans"
kind = "dataset"
source = "https://github.com/MALerLab/ossq-omr (scans from IMSLP, URLs in data/scores_w_url.yaml)"
license = "CC0 (encodings); scans under IMSLP's terms (check each score's copyright status there)"
size = "$(du -sh "$D" | cut -f1)"
fetch = "modal run experiments/ossq/ossq_modal.py::fetch (manuscript-labeler), then modal volume get ossq-raw pdfs; or sh experiments/ossq/register_local.sh --pdfs"
added = "$(date +%Y-%m-%d)"
notes = "Staff images and labels built from it are on Modal (musvit-staves/ossq, ossq-raw), not here."

  [[dataset.consumer]]
  project = "manuscript-labeler"
  repo = "~/Dropbox/Code/manuscript-labeler"
  uses = "Scanned quartet staves for MuSViT training (experiments/ossq/ossq_modal.py); manuscripts as a test set only"
  declared = "docs/storage.md"
  registered = "$(date +%Y-%m-%d)"
EOF
fi
echo "done: $D"
