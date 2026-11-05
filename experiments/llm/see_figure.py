# /// script
# requires-python = ">=3.11"
# dependencies = ["matplotlib"]
# ///
"""The seeing test's figures: every model's d' for grace notes and double
stops (see_test.py's logs), beside D5's own reading and the Opus readers'
first reading of the same bars, counted the same way (does the reading
have a grace note, a chord, in the bar).

    uv run experiments/llm/see_figure.py <edition-copy> <edition> <out-dir>

d' = z(hit rate) - z(false-alarm rate), each rate with the log-linear
correction ((n + 0.5) / (N + 1)), so a rate of 0 or 1 stays finite.
Writes see-dprime.jpg, see-rates.jpg and see-table.md to <out-dir>.
"""

import json
import re
import sys
from pathlib import Path
from statistics import NormalDist

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

Z = NormalDist().inv_cdf
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#dddcd7", "#fcfcfb"
SERIES = {"grace": ("#2a78d6", "grace notes"), "chord": ("#eb6834", "double stops")}
MODELS = [  # (log name, label, kind)
    ("see-qwen3.6-27b-fp8-nothink", "Qwen3.6-27B (no thinking)", "look"),
    ("see-muse-glimmer-30b", "Muse Glimmer 30B", "look"),
    ("see-gemma-4-31b-it", "Gemma 4 31B", "look"),
    ("see-claude-opus-5-5-high", "Opus 5.5", "look"),
    ("d5", "musvit-D5, its reading", "read"),
    ("opus", "Opus readers, first reading", "read"),
]


SHORT = {"Qwen3.6-27B (no thinking)": "Qwen", "Muse Glimmer 30B": "Glimmer", "Gemma 4 31B": "Gemma",
         "Opus 5.5": "Opus, one look", "musvit-D5, its reading": "D5", "Opus readers, first reading": "Opus readers"}


def counts(s: str | None) -> dict:
    return {"grace": len(re.findall(r"(^| )g[<A-G]", s or "")), "chord": len(re.findall(r"<", s or ""))}


def rates(said: list[tuple[bool, bool]]) -> dict:
    """[(there, said)] -> hits, false alarms, d'."""
    pos = [s for t, s in said if t]
    neg = [s for t, s in said if not t]
    h, f = sum(pos), sum(neg)
    hit, fa = (h + 0.5) / (len(pos) + 1), (f + 0.5) / (len(neg) + 1)
    return {"hits": h, "there": len(pos), "false": f, "absent": len(neg), "hit": h / len(pos), "fa": f / len(neg),
            "d": Z(hit) - Z(fa)}


def main():
    copy, edition, out = map(Path, sys.argv[1:4])
    run = next(edition.glob("build/encode/Op48-4-I-*"))
    d5 = {(b["part"], b["bar"]): b for b in json.loads((run / "d5/reading-vs-final.json").read_text())["against"]["bars"]}
    opus = {(b["part"], b["bar"]): b for b in json.loads((run / "d5/read-vs-final.json").read_text())["bars"]}
    results = {}
    # the test's bars, from the Opus run (every question answered)
    test = {(e["part"], e["bar"]) for e in map(json.loads, (copy / "build/see-claude-opus-5-5-high.jsonl").read_text().splitlines())}
    for name, label, kind in MODELS:
        if kind == "look":
            log = copy / "build" / f"{name}.jsonl"
            if not log.exists():
                continue
            es = [e for e in map(json.loads, log.read_text().splitlines()) if e.get("answer")]
            results[label] = {q: rates([(e["true"] > 0, e["answer"]["count"] > 0) for e in es if e["question"] == q])
                              for q in SERIES}
        else:
            src = d5 if name == "d5" else opus
            results[label] = {q: rates([(counts(d5[k]["ours"])[q] > 0, counts(src[k]["read"])[q] > 0) for k in sorted(test)])
                              for q in SERIES}
    labels = [l for _, l, _ in MODELS if l in results]
    plt.rcParams.update({"font.family": "sans-serif", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": MUTED,
                         "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK})

    # Figure 1: d' per model, one row each; one look above, full readings below
    fig, ax = plt.subplots(figsize=(7.5, 3.6), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    ys = {l: len(labels) - i - (0.6 if i >= sum(k == "look" for _, x, k in MODELS if x in results) else 0)
          for i, l in enumerate(labels)}
    for l in labels:
        y = ys[l]
        ds = [results[l][q]["d"] for q in SERIES]
        ax.plot(ds, [y, y], color=GRID, lw=2, zorder=1)
        for q, (color, _) in SERIES.items():
            ax.scatter(results[l][q]["d"], y, s=64, color=color, edgecolor=SURFACE, linewidth=2, zorder=3)
    ax.axvline(0, color=MUTED, lw=1, ls=(0, (2, 3)))
    ax.text(0.05, max(ys.values()) + 0.55, "can't tell them apart", color=MUTED, fontsize=8.5, va="bottom")
    ax.set_yticks(list(ys.values()), labels)
    ax.set_xlim(-0.8, 4.2)
    ax.set_ylim(min(ys.values()) - 0.7, max(ys.values()) + 1.0)
    ax.set_xlabel("d′: how well it tells bars with the mark from bars without")
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    split = (min(y for l, y in ys.items() if l in labels[:sum(k == "look" for _, x, k in MODELS if x in results)])
             + max(y for l, y in ys.items() if l in labels[sum(k == "look" for _, x, k in MODELS if x in results):])) / 2
    ax.axhline(split, color=GRID, lw=0.8)
    ax.text(4.15, split + 0.15, "one look, one question", ha="right", va="bottom", color=MUTED, fontsize=8.5)
    ax.text(4.15, split - 0.15, "a whole reading", ha="right", va="top", color=MUTED, fontsize=8.5)
    handles = [plt.Line2D([], [], marker="o", ls="", color=c, markersize=8, label=n) for c, n in SERIES.values()]
    ax.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.45, 1.0), ncol=2, frameon=False)
    fig.tight_layout()
    fig.savefig(out / "see-dprime.jpg", dpi=160, facecolor=SURFACE, pil_kwargs={"quality": 92})

    # Figure 2: hit rate against false-alarm rate, one panel per question
    fig, axes = plt.subplots(1, 2, figsize=(8, 4), facecolor=SURFACE, sharey=True)
    for ax, (q, (color, name)) in zip(axes, SERIES.items()):
        ax.set_facecolor(SURFACE)
        ax.plot([0, 1], [0, 1], color=MUTED, lw=1, ls=(0, (2, 3)))
        for d in (1, 2, 3):  # curves of equal d'
            xs = [i / 200 for i in range(1, 200)]
            ax.plot(xs, [NormalDist().cdf(Z(x) + d) for x in xs], color=GRID, lw=0.8, zorder=0)
        for l in labels:
            r = results[l][q]
            ax.scatter(r["fa"], r["hit"], s=56, color=color, edgecolor=SURFACE, linewidth=2, zorder=3)
            right = r["fa"] < 0.6  # the label on the side away from the panel's edge
            ax.annotate(SHORT.get(l, l), (r["fa"], r["hit"]), xytext=(7 if right else -7, -3),
                        textcoords="offset points", fontsize=8, color=INK, ha="left" if right else "right")
        ax.set_xlim(-0.02, 1.0)
        ax.set_ylim(-0.02, 1.05)
        ax.set_title(name, color=INK, fontsize=10, loc="left")
        ax.set_xlabel("said so where there is none")
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    axes[0].set_ylabel("said so where there is one")
    fig.tight_layout()
    fig.savefig(out / "see-rates.jpg", dpi=160, facecolor=SURFACE, pil_kwargs={"quality": 92})

    rows = ["| | grace: said so, there | none there, said one | d′ | double stop: said so, there | none there, said one | d′ |",
            "|---|---|---|---|---|---|---|"]
    for l in labels:
        g, c = results[l]["grace"], results[l]["chord"]
        rows.append(f"| {l} | {g['hits']} of {g['there']} | {g['false']} of {g['absent']} | {g['d']:.2f} "
                    f"| {c['hits']} of {c['there']} | {c['false']} of {c['absent']} | {c['d']:.2f} |")
    (out / "see-table.md").write_text("\n".join(rows) + "\n")
    print("\n".join(rows))


if __name__ == "__main__":
    main()
