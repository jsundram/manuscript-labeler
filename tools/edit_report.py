# /// script
# requires-python = ">=3.11"
# ///
"""How much the editor changed detection's proposals, page by page: the
measure of the editor's time, read from the labels themselves.

    uv run tools/edit_report.py <edition-repo> [--all] [SOURCE[:PAGES] ...]

By default, the pages in experiments/barlines/test_pages.json (pages no
model had seen when they were annotated). SOURCE is a PDF's name without
.pdf, PAGES a list like 3,11 or 3-6; --all, every reviewed page.

A bar line or staff the editor never touched keeps `auto: true`; one
moved, added, or edited in any way (its kind, its bar count, "movement
ends here"; a staff's ends, crop or signature, which marking a page
reviewed also writes) has it false; one deleted is recorded on its
staff (`rejected`). So "changed" counts every edit, not only moves: an
upper bound on fixing detection. Only reviewed pages count. A page opened before the models
being measured were installed got its proposals from the earlier ones.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def pages_arg(spec: str) -> list[int]:
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b or a) + 1))
    return out


def page_counts(p: dict) -> dict:
    staves = [s for s in p.get("systems", []) if s.get("role", "part") == "part"]
    bars = [b for s in staves for b in s.get("barlines", [])]
    return {"staves": len(staves), "staves changed": sum(1 for s in staves if not s.get("auto")),
            "staves deleted": len(p.get("rejected_staves", [])),
            "bar lines": len(bars), "kept as detected": sum(1 for b in bars if b.get("auto")),
            "changed": sum(1 for b in bars if not b.get("auto")),
            "deleted": sum(len(s.get("rejected", [])) for s in staves)}


def main():
    args = sys.argv[1:]
    edition = Path(args.pop(0))
    every = "--all" in args
    args = [a for a in args if a != "--all"]
    want: dict[str, list[int] | None] = {}
    for a in args:
        src, _, pg = a.partition(":")
        want[src] = pages_arg(pg) if pg else None
    if not want and not every:
        want = json.loads((ROOT / "experiments" / "barlines" / "test_pages.json").read_text())["pages"]
    totals: dict[str, dict] = {}
    for lp in sorted(edition.glob("sources/**/*.labels.json")):
        src = lp.name.removesuffix(".labels.json")
        if not every and src not in want:
            continue
        doc = json.loads(lp.read_text())
        for n, p in sorted(doc["pages"].items(), key=lambda kv: int(kv[0])):
            if p.get("status") != "reviewed" or p.get("kind") != "music":
                continue
            if not every and want[src] is not None and int(n) not in want[src]:
                continue
            c = page_counts(p)
            t = totals.setdefault(src, {k: 0 for k in c} | {"pages": 0})
            t["pages"] += 1
            for k, v in c.items():
                t[k] += v
            kept = c["kept as detected"] / c["bar lines"] if c["bar lines"] else 0
            print(f"{src} p{n} ({p.get('part')}): {c['bar lines']} bar lines, {kept:.0%} kept as detected, "
                  f"{c['changed']} changed (moved, added or edited), {c['deleted']} deleted; "
                  f"{c['staves changed']} of {c['staves']} staves changed")
    if not totals:
        print("no reviewed pages to report")
    for src, t in totals.items():
        kept = t["kept as detected"] / t["bar lines"] if t["bar lines"] else 0
        print(f"\n{src}: {t['pages']} pages, {t['bar lines']} bar lines, {kept:.0%} kept as detected, "
              f"{t['changed']} changed (moved, added or edited), {t['deleted']} deleted; "
              f"{t['staves changed']} of {t['staves']} staves changed, {t['staves deleted']} deleted")


if __name__ == "__main__":
    main()
