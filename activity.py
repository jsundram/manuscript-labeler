# /// script
# requires-python = ">=3.11"
# ///
"""The person's time in the labeler, from its activity log (SPEC.md,
Activity): data/<edition>/activity/<YYYY-MM>.jsonl, written by the page
(every edit, page opened, button, key, focus, and a heartbeat while they
work) and the server (how long detection and Claude's reads took).

    uv run activity.py [--edition boccherini-opus-48] [--since 2026-10-16T00:00]
        [--until ...] [--source RES-507-17] [--pages] [--json]

Active time, by the Op. 48 edition's rule (its scripts/activity.py): the
person's events in stretches, a gap of more than ten minutes ending one.
Time from an event to the next is the page's the first was on; time after
the page lost focus isn't counted. A stretch with a single event counts a
minute.
"""

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
GAP = 10 * 60
AWAY = {"blur"}  # the time after this isn't labelling: the tab left


def read(edition_dirs: list[Path], since=None, until=None, source=None) -> list[dict]:
    """The log's events, sorted by time; each has t and t_end (seconds)."""
    lo = datetime.fromisoformat(since).timestamp() if since else 0
    hi = datetime.fromisoformat(until).timestamp() if until else float("inf")
    out = []
    for d in edition_dirs:
        for f in sorted((d / "activity").glob("*.jsonl")):
            for line in f.read_text(encoding="utf-8").splitlines():
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(e.get("t"), (int, float)) or not lo <= e["t"] <= hi:
                    continue
                if source and source not in e.get("file", ""):
                    continue
                e.setdefault("t_end", e["t"] + e.get("seconds", 0))
                e["edition"] = d.name
                out.append(e)
    return sorted(out, key=lambda e: e["t"])


def stretches(events: list[dict], gap: float = GAP) -> list[list[dict]]:
    """The person's events (the page's, not the server's) in runs with no gap over `gap`."""
    runs, end = [], None
    for e in (e for e in events if e.get("src") == "labeler"):
        if end is None or e["t"] - end > gap:
            runs.append([])
            end = e["t_end"]
        runs[-1].append(e)
        end = max(end, e["t_end"])
    return runs


def segments(events: list[dict], gap: float = GAP) -> list[tuple]:
    """[(start, end, (edition, file, where))]: the person's time, piece by
    piece, each on the page it was spent on. Within a stretch, an event's
    own span and the time to the next event are its page's (not after a
    blur); a moment already counted (a heartbeat running on
    over the keys and edits inside it) isn't counted again; a stretch
    shorter than a minute is made up to one at its end."""
    out = []
    for run in stretches(events, gap):
        spent, first, counted = 0.0, len(out), run[0]["t"]
        for e, nxt in zip(run, run[1:] + [None]):
            key = (e["edition"], e.get("file", ""), e.get("where", ""))
            end = e["t_end"]
            if nxt is not None and e.get("kind") not in AWAY:
                end = max(end, nxt["t"])
            start = max(e["t"], counted)
            if end > start:
                out.append((start, end, key))
                spent += end - start
                counted = end
        if spent < 60:
            last = run[-1]
            start = out[-1][1] if len(out) > first else last["t"]
            out.append((start, start + 60 - spent, (last["edition"], last.get("file", ""), last.get("where", ""))))
    return out


def attribute(events: list[dict], gap: float = GAP) -> dict:
    """{(edition, file, where): seconds}."""
    out: dict = defaultdict(float)
    for a, b, key in segments(events, gap):
        out[key] += b - a
    return dict(out)


def bars_per_page(doc: dict) -> dict[str, int]:
    """{"p5": bars}: the bars each music page's bar lines count."""
    return {f"p{n}": sum(b.get("bar_count", 1) for s in p.get("systems", []) for b in s.get("barlines", []))
            for n, p in doc.get("pages", {}).items() if p.get("kind") == "music"}


def labels_doc(edition: str, pdf: str) -> dict:
    f = DATA / edition / re.sub(r"\.pdf$", ".labels.json", pdf)
    return json.loads(f.read_text()) if f.exists() else {}


def whats(e: dict) -> list[str]:
    return [w.strip() for w in e.get("what", "").split(",") if w.strip()]


def tallies(events: list[dict]) -> dict:
    """Edits and corrections of detection by kind; what undo and redo
    changed; the machine's changes (Re-detect, Claude's readings); commands;
    keys; the waits on the server and its work in the background
    ({kind: [times, seconds]})."""
    edits, corrections, commands, keys = Counter(), Counter(), Counter(), Counter()
    undone, machine = Counter(), Counter()
    waits: dict = defaultdict(lambda: [0, 0.0])
    background: dict = defaultdict(lambda: [0, 0.0])
    for e in events:
        n = e.get("n", 1)
        if e.get("kind") == "edit":
            for w in whats(e):
                (corrections if w.endswith("(detected)") else edits)[w] += n
        elif e.get("kind") in ("undo", "redo"):
            for w in whats(e):
                undone[f"{e['kind']}: {w}"] += n
        elif e.get("kind") == "auto":
            for w in whats(e):
                machine[f"{e.get('by', '?')}: {w}"] += n
        elif e.get("kind") == "command":
            commands[e.get("what", "")] += n
        elif e.get("kind") == "key":
            keys[e.get("what", "")] += n
        elif e.get("src") == "labeler-server":
            w = background if e["kind"].endswith("-ahead") else waits
            w[e["kind"]][0] += 1
            w[e["kind"]][1] = round(w[e["kind"]][1] + e.get("seconds", 0), 2)
    return {"edits": dict(edits), "corrections": dict(corrections), "undone": dict(undone),
            "machine": dict(machine), "commands": dict(commands), "keys": dict(keys), "waits": dict(waits),
            "background": dict(background)}


def minutes(s: float) -> str:
    return f"{s / 60:.0f} min" if s < 5400 else f"{s / 3600:.1f} h"


def report(events: list[dict], gap: float, pages: bool) -> dict:
    """Every source's time in the log, for the command line."""
    per = attribute(events, gap)
    days: dict = defaultdict(float)
    for a, b, _ in segments(events, gap):
        days[datetime.fromtimestamp(a).date().isoformat()] += b - a
    sources: dict = defaultdict(lambda: {"seconds": 0.0, "pages": {}, "edits": defaultdict(int)})
    for (ed, f, where), sec in per.items():
        sources[(ed, f)]["seconds"] += sec
        sources[(ed, f)]["pages"][where] = sources[(ed, f)]["pages"].get(where, 0) + sec
    for e in events:
        if e.get("kind") == "edit":
            sources[(e["edition"], e.get("file", ""))]["edits"][e.get("where", "")] += e.get("n", 1)
    for (ed, f), v in sources.items():
        b = bars_per_page(labels_doc(ed, f))
        v["bars"] = sum(b.get(w, 0) for w in v["pages"])
        v["bars_by_page"] = b
        v["edits"] = dict(v["edits"])
    return {"active_seconds": sum(per.values()), "stretches": len(stretches(events, gap)), "days": dict(days),
            "sources": {f"{ed}/{f}": v for (ed, f), v in sources.items()}, **tallies(events), "show_pages": pages}


def show(r: dict) -> None:
    print(f"active {minutes(r['active_seconds'])} in {r['stretches']} stretches")
    for day, sec in sorted(r["days"].items()):
        print(f"  {day}  {minutes(sec)}")
    print("\nby source")
    for name, v in sorted(r["sources"].items(), key=lambda kv: -kv[1]["seconds"]):
        per100 = f", {v['seconds'] / 60 / v['bars'] * 100:.0f} min per 100 bars" if v["bars"] else ""
        print(f"  {name.split('/', 1)[1]:40} {minutes(v['seconds']):>8}  {len(v['pages'])} pages, "
              f"{v['bars']} bars{per100}")
        if r["show_pages"]:
            for where, sec in sorted(v["pages"].items(), key=lambda kv: int(kv[0][1:]) if kv[0][1:].isdigit() else 0):
                bars = v["bars_by_page"].get(where)
                print(f"      {where:>5} {minutes(sec):>8}  {v['edits'].get(where, 0):3} edits"
                      + (f", {bars} bars" if bars else ""))
    for title, c in (("edits", r["edits"]), ("corrections of detection", r["corrections"]),
                     ("undone and redone", r["undone"]), ("changed by detection or Claude", r["machine"]),
                     ("commands", r["commands"]), ("keys", r["keys"])):
        if c:
            print(f"\n{title}")
            for what, n in Counter(c).most_common(12):
                print(f"  {n:5}  {what}")
    for title, w in (("waiting on the server", r["waits"]), ("the server in the background", r["background"])):
        if w:
            print(f"\n{title}")
            for kind, (n, sec) in sorted(w.items()):
                print(f"  {kind:10} {n:4} times, {sec:.0f} s in all")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--edition", help="a folder under data/ (default every one with a log)")
    ap.add_argument("--since"), ap.add_argument("--until")
    ap.add_argument("--source", help="only sources whose PDF path contains this")
    ap.add_argument("--gap", type=float, default=GAP / 60, help="minutes of silence that end a stretch (10)")
    ap.add_argument("--pages", action="store_true", help="each page's time too")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    dirs = [DATA / a.edition] if a.edition else sorted(p.parent for p in DATA.glob("*/activity"))
    events = read(dirs, a.since, a.until, a.source)
    if not events:
        raise SystemExit("no activity logged" + (" in that range" if a.since or a.until else ""))
    r = report(events, a.gap * 60, a.pages)
    if a.json:
        print(json.dumps(r, indent=1, default=str))
    else:
        show(r)


if __name__ == "__main__":
    main()
