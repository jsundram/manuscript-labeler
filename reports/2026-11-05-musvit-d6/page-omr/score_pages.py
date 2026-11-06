# /// script
# dependencies = ["linearized-musicxml @ git+https://github.com/OMR-Research/lmx.git@87fca1c38bda83bc032596ab00af28412f92941d", "mcr-metric==1.1.0"]
# ///
"""MCR per page: page-omr's kern and D6's staves (joined in page order; a staff lmx
can't turn into MusicXML is left out) against the page's labels, by mcr-metric.

    uv run score_pages.py OUT
"""
import re, sys, importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location("ms", str(Path(__file__).resolve().parents[3] / "experiments/zeus/mcr_score.py"))
ms = importlib.util.module_from_spec(spec); spec.loader.exec_module(ms)
import mcr

def lmx_xml(text):
    """Joined staves as MusicXML; a staff lmx can't convert is dropped (scored as missing)."""
    staves = re.findall(r"measure key:.*?(?= measure key:|$)", text)
    ok = []
    for s in staves:
        try: ms.musicxml(s); ok.append(s)
        except ValueError: pass
    return ms.musicxml(" ".join(ok)), len(staves) - len(ok)

tot = {}
for d in sorted(Path(sys.argv[1]).iterdir()):
    if not (d / "truth.lmx").exists(): continue
    ref = ms.musicxml((d / "truth.lmx").read_text())
    nref = len(mcr.parse(ref, format="musicxml").events)
    row = [d.name, f"{nref} notes"]
    for name, fmt in [("page-omr-a1-kern.krn", "kern"), ("D6.lmx", "lmx"), ("D6-key.lmx", "lmx")]:
        f = d / name
        if not f.exists(): continue
        if fmt == "kern":
            pred, dropped = f.read_text(), 0
        else:
            pred, dropped = lmx_xml(f.read_text()); fmt = "musicxml"
        try:
            r = mcr.score(pred, ref, pred_format=fmt, ref_format="musicxml")
            npred = len(mcr.parse(pred, format=fmt).events)
        except Exception as e:
            row.append(f"{name}: unscorable ({type(e).__name__})"); continue
        w = npred + 2 * nref
        t = tot.setdefault(name, [0, 0]); t[0] += r.mcr * w; t[1] += w
        row.append(f"{name.split('.')[0]} {r.mcr:.1%} (recall {r.content_recall:.0%}, {npred} notes{f', {dropped} staves dropped' if dropped else ''})")
    print(" | ".join(row))
for k, (c, w) in tot.items(): print(k, f"MCR {c / w:.1%}")
