# /// script
# requires-python = ">=3.11"
# ///
"""agent_read.py's reading scored as the edition scores its readers: by
`zeus-score compare` against the person's final notes, bar by bar, beside
the Opus readers' first reading and musvit-D5's own reading of the same bars
(the run's d5/ folder, from the edition's scripts/d5_measure.py).

    uv run experiments/llm/score_agent_read.py <edition-copy> <edition> --part vn1 [--bars 0-13] [--reader gemma]

Writes <edition-copy>/build/<reader>/score-<part>.json.
"""

import argparse
import json
import shutil
import subprocess
from pathlib import Path


def bar_range(text: str) -> set[int]:
    a, _, b = text.partition("-")
    return set(range(int(a), int(b or a) + 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("copy", type=Path)
    ap.add_argument("edition", type=Path)
    ap.add_argument("--part", required=True)
    ap.add_argument("--bars", help="first-last; default every bar of the part")
    ap.add_argument("--reader", default="qwen", help="the open model's name in the tally")
    a = ap.parse_args()
    state = json.loads(next((a.copy / "build/encode").glob("*/state.json")).read_text())
    run, q, mvt = state["run"], state["quartet"], state["mvt"]
    source = Path(state["source"]["file"]).name.replace(".bars.json", "")
    d5 = a.edition / "build/encode" / run / "d5"
    out = a.copy / "build" / a.reader
    (out / "events").mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["uv", "run", "--offline", str(a.copy / "scripts/events.py"), q, a.part, mvt, "--json"],
                       capture_output=True, text=True, check=True)
    (out / "events" / f"{a.part}-{mvt}.json").write_text(r.stdout)
    zeus = shutil.which("zeus-score") or str(Path.home() / ".local/bin/zeus-score")
    res = out / f"compare-{a.part}.json"
    subprocess.run([zeus, "compare", "--edition", str(a.edition), "--source", source, "--movements", mvt,
                    "--parts", a.part, "--events", str(out / "events"), "--against", str(d5 / "final"),
                    "--out", str(res)], check=True, capture_output=True, text=True)
    readers = {a.reader: json.loads(res.read_text())["bars"],
               "opus": json.loads((d5 / "read-vs-final.json").read_text())["bars"],
               "d5": json.loads((d5 / "reading-vs-final.json").read_text())["against"]["bars"]}
    wanted = bar_range(a.bars) if a.bars else None
    rows = {}
    for who, bars in readers.items():
        for b in bars:
            if b["part"] == a.part and (wanted is None or b["bar"] in wanted):
                rows.setdefault(b["bar"], {"final": b.get("ours")})[who] = {
                    "exact": b["exact"], "rhythm": b["rhythm"], "pitch": b["pitch"], "read": b.get("read")}
    tally = {who: {k: sum(r.get(who, {}).get(k, False) for r in rows.values()) for k in ("exact", "rhythm", "pitch")}
             for who in readers}
    (out / f"score-{a.part}.json").write_text(json.dumps({"bars": len(rows), "tally": tally, "rows": rows}, indent=1))
    print(f"{a.part} bars {a.bars or 'all'} ({len(rows)}): " + "; ".join(
        f"{who} exact {t['exact']}, rhythm {t['rhythm']}, pitch {t['pitch']}" for who, t in tally.items()))


if __name__ == "__main__":
    main()
