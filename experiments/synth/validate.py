# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "verovio==6.3.0", "resvg-py==0.5.0", "opencv-python-headless==4.10.0.84", "numpy", "lxml", "pillow",
#   # the LMX reader (Delinearizer); score_to_lmx.py writes LMX with Zeus's pinned encoder
#   "linearized-musicxml==1.0.0",
# ]
# ///
"""Engrave every staff in a dataset folder (dataset.py's) and check verovio drew what its LMX
says (copyist.check: notes, rests, beamed groups); count and list those it didn't.

    uv run experiments/synth/validate.py ~/.cache/manuscript-labeler/zeus/dataL2
"""
import sys, time, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import copyist

D = Path(sys.argv[1])
fails, bad, n, t0 = collections.Counter(), [], 0, time.time()
for lmx in sorted(D.glob("*/*.lmx"))[: int(sys.argv[2]) if len(sys.argv) > 2 else None]:
    text = lmx.read_text()
    try:
        xml = copyist.lmx_to_musicxml(text)
        svg = copyist.engrave(xml, "Leipzig", None)
        copyist.check(svg, text, xml)
        n += 1
    except ValueError as e:
        bad.append((str(lmx.relative_to(D)), str(e)))
    except Exception as e:
        fails[type(e).__name__ + ": " + str(e)[:80]] += 1
print(f"{n} drawn as written, {len(bad)} not, {sum(fails.values())} failed, in {time.time() - t0:.0f} s", dict(fails))
for b in bad[:15]:
    print(*b)
