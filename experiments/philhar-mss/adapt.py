# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow"]
# ///
"""Make Philhar's zips readable by experiments/zeus/philhar.py, and check them.

    uv run experiments/philhar-mss/adapt.py [<edition-repo>] [<philhar-site root>] [work ...]

For each work folder <root>/<work>/unpacked (from fetch_lily.py) it builds
<root>/lily/<work>/ in philhar.py's layout (so autopair's --philhar <root>/lily
--quartets <work>,... can find it):

    Trame.ily  Global.ily  01-V1-M.ily  02-V2-M.ily  03-A-M.ily  04-Vc-M.ily  05-A2-M.ily

- Part files are renamed from Philhar's per-work names (11018-1-V1-1.ily,
  13021-1-Cello-1.ily, 12005-04-Alto2-3.ily ...). PARTS maps his part names
  to ours. A duo's violin is vn1. The quintet's second viola is va2 (05-A2).
- Line endings are made LF (the op. 4 skeletons are old-Mac CR only).
- convert-ly brings each file up from its \\version (2.16-2.24) to 2.26.
- Two fixes to old Scheme, in Global.ily: \\paper and \\header blocks are
  dropped (MH 411's fails in 2.26 and nothing here engraves pages), and the
  op. 4 staccato helper's "staccato" string becomes a symbol.
- cc.eps and cc2.eps are kept beside it.

philhar.py itself is not edited. This script imports it and widens its
part map (adds va2) and movement list (to VIII) before calling read().
Then it reads every part and movement and checks each has bar events, and
that its bar count matches the skeleton's. Writes <root>/lily/<work>/check.json
and prints a table.
"""

import json
import re
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "experiments/zeus"))
import philhar  # noqa: E402

PARTS = {   # Philhar's file part name -> our part
    "V1": "vn1", "Violon1": "vn1", "Violon": "vn1",
    "V2": "vn2", "Violon2": "vn2",
    "Alto": "va", "Alto1": "va", "A": "va",
    "Alto2": "va2",
    "Vc": "vc", "Cello": "vc", "Violoncelle": "vc",
}
FILES = {**philhar.FILES, "va2": "05-A2"}
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"]
PART_FILE = re.compile(r"(?P<num>\d+[a-z]?)-(?:(?P<i>\d+)-)?(?P<name>[A-Za-z]+\d?)-(?P<mvt>\d)\.ily")


def lf(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")


def drop_block(text: str, name: str) -> str:
    """Remove top-level `\\name { ... }` blocks (brace-matched)."""
    out, i = [], 0
    for m in re.finditer(rf"\\{name}\s*\{{", text):
        if m.start() < i:
            continue
        depth, j = 0, m.end() - 1
        while j < len(text):
            depth += {"{": 1, "}": -1}.get(text[j], 0)
            j += 1
            if depth == 0:
                break
        out.append(text[i:m.start()])
        i = j
    out.append(text[i:])
    return "".join(out)


def build(work: Path) -> tuple[Path, dict]:
    src, dst = work / "unpacked", work.parent / "lily" / work.name
    if dst.exists():
        shutil.rmtree(dst)   # built output, rebuilt from unpacked/ each run
    dst.mkdir(parents=True)
    parts = {}
    for f in sorted(src.iterdir()):
        name = f.name
        if name.endswith("-Trame.ily"):
            out = "Trame.ily"
        elif name.endswith("-Global.ily"):
            out = "Global.ily"
        elif name in ("cc.eps", "cc2.eps"):
            shutil.copy2(f, dst / name)
            continue
        elif (m := PART_FILE.fullmatch(name)) and m["name"] in PARTS:
            part = PARTS[m["name"]]
            parts.setdefault(part, []).append(int(m["mvt"]))
            out = f"{FILES[part]}-{m['mvt']}.ily"
        else:
            continue
        (dst / out).write_text(lf(f.read_text(encoding="utf-8", errors="replace")))
    ilys = sorted(str(p) for p in dst.glob("*.ily"))
    r = subprocess.run(["convert-ly", "-e", "-b", "-d", *ilys], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[-2000:])
    for bak in dst.glob("*.ily~"):
        bak.unlink()
    g = dst / "Global.ily"
    text = g.read_text()
    text = drop_block(drop_block(text, "paper"), "header")
    text = re.sub(r"\(add-script m \"(\w+)\"\)", r"(add-script m '\1)", text)
    g.write_text(text)
    return dst, {p: sorted(v) for p, v in parts.items()}


def skeleton_bars(trame: Path) -> dict[str, list[int]]:
    """Bar numbers per movement from Trame.ily's spacers: 0 for a pickup,
    then 1..n (a bar split around a repeat sign counts once)."""
    text = re.sub(r"%.*", "", trame.read_text())
    out = {}
    for blk in re.split(r"\\tag\s*#'mvt", text)[1:]:
        mvt = re.match(r"[IVX]+", blk).group(0)
        ts = re.search(r"\\time\s+(\d+)/(\d+)", blk)
        meas = Fraction(int(ts[1]), int(ts[2]))
        total, last = Fraction(0), Fraction(0)
        # a spacer with no duration (`s_\markup`) repeats the last one's
        for d, dots, n, k in re.findall(r"\bs(?:(\d+)(\.*)(?:\*(\d+)(?:/(\d+))?)?)?(?=[\s_^\\}]|$)", blk):
            if not d:
                total += last
                continue
            v = t = Fraction(1, int(d))
            for _ in dots:
                v /= 2
                t += v
            last = t
            total += t * int(n or 1) / int(k or 1)
        pk = re.search(r"\\partial\s+(\d+)(\.*)", blk)
        p = Fraction(1, int(pk[1])) * (Fraction(3, 2) if pk[2] else 1) if pk else Fraction(0)
        n = -(-(total - p) // meas)          # ceiling
        out[mvt] = ([0] if p else []) + list(range(1, int(n) + 1))
    return out


def covered(bars: dict, measure: Fraction) -> set[int]:
    """Bars the part fills: notes and rests, multi-bar rests over their span."""
    out = set()
    for num, bar in bars.items():
        for c in bar.cols:
            if c.kind in ("note", "rest"):
                out.add(num)
            elif c.kind == "mmrest":
                d = Fraction(1, 2 ** c.log) * (2 - Fraction(1, 2 ** c.dots)) * c.scale
                out.update(range(num, num + max(1, round(d / measure))))
    return out


def check(edition: Path, lily: Path, parts: dict) -> dict:
    philhar.FILES, philhar.ROMAN = FILES, ROMAN
    expect = skeleton_bars(lily / "Trame.ily")
    res = {}
    for part, mvts in parts.items():
        for n in mvts:
            mvt = ROMAN[n - 1]
            key = f"{part} {mvt}"
            try:
                bars, split, changes = philhar.read(edition, lily, part, mvt)
            except Exception as e:  # noqa: BLE001
                res[key] = {"ok": False, "error": str(e)[-600:]}
                continue
            have = covered(bars, philhar.measure(lily, mvt))
            want = set(expect.get(mvt, []))
            res[key] = {"ok": bool(have), "bars_with_events": len(have), "skeleton_bars": len(want),
                        "missing": sorted(want - have), "extra": sorted(have - want), "split": sorted(split),
                        "matches_skeleton": have == want}
    return {"parts": parts, "skeleton": {m: len(v) for m, v in expect.items()}, "reads": res}


def main():
    args = sys.argv[1:]
    edition = Path(args.pop(0) if args else "~/Dropbox/Code/boccherini-opus-48").expanduser()
    root = Path(args.pop(0) if args else "~/Data/manuscript-labeler/philhar-site").expanduser()
    works = args or sorted(p.name for p in root.iterdir() if (p / "unpacked").is_dir() and p.name != "lily")
    summary = {}
    for w in works:
        lily, parts = build(root / w)
        c = check(edition, lily, parts)
        (lily / "check.json").write_text(json.dumps(c, indent=1) + "\n")
        bad = [k for k, v in c["reads"].items() if not v["ok"] or not v.get("matches_skeleton")]
        summary[w] = {"parts": list(parts), "movements": len(c["skeleton"]),
                      "bars": sum(c["skeleton"].values()), "reads": len(c["reads"]), "problems": bad}
        print(f"{w:20s} parts={','.join(parts):18s} mvts={len(c['skeleton'])} "
              f"bars={sum(c['skeleton'].values()):4d} reads={len(c['reads'])} problems={bad}", flush=True)
        for k in bad:
            print("   ", k, json.dumps(c["reads"][k])[:400])
    (HERE / "lily-check.json").write_text(json.dumps(summary, indent=1) + "\n")


if __name__ == "__main__":
    main()
