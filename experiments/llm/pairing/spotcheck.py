# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow", "verovio"]
# ///
"""A page for the editor to spot-check the Opus check's answers
(check_leftout.py): for a sample of its answers, the staff as Opus saw it,
the bars it accepted or rejected, the score's bars as Opus read them, its
working and insights, a link to the page in the labeler, and buttons:
right, wrong, can't tell. The verdicts stay in the browser (localStorage)
and are copied out as JSON with the page's button.

    uv run experiments/llm/pairing/spotcheck.py [--accepted 10] [--rejected 3] [--seed 0]

Writes experiments/llm/pairing/spotcheck.html (the staves' pictures in it).
Leaves out KHM 587, whose answers the editor's fixed pages already score.
"""

import argparse
import base64
import html
import json
import random
import urllib.request
from urllib.parse import quote
from pathlib import Path

import check_leftout as cl
import engrave

HERE = Path(__file__).resolve().parent
LABELER = "http://localhost:8050"


def labeler_ids() -> dict[str, str]:
    """{PDF path: the labeler's id for it}, from the running labeler's source list."""
    try:
        d = json.load(urllib.request.urlopen(f"{LABELER}/api/sources", timeout=5))
    except OSError:
        return {}
    out = {}
    for s in d["sources"]:
        pdf = s["pdf"]
        out[Path(pdf.split(":", 1)[-1]).name] = pdf  # a PDF's file name is enough to tell them apart here
    return out


def card(i: int, r: dict, ids: dict) -> str:
    """One staff: the stacked picture and its prompt, word for word (what Opus is now asked), its three
    questions; Opus's earlier answer (to the yes/no question, with a text of the bars) shown once answered."""
    pdf = next(p for p, names in cl.pairing.sources().items() if r["source"] in names)
    page = int(r["staff"][1:].split("-")[0])
    link = f"{LABELER}/#pdf={quote(ids[pdf.name], safe=':/')}&page={page}" if pdf.name in ids else None
    img, text = cl.prompt(r, "stacked")
    f, l = r["claim"]
    verdict = "accepted" if r["right"] else "rejected"
    key = f"{r['source']}/{r['staff']}"
    group = lambda q, opts: (f'<div class="buttons" data-q="{q}"><span class="q">{q}:</span>' +
                             "".join(f'<button data-v="{html.escape(o)}">{html.escape(o)}</button>' for o in opts) + "</div>")
    return f"""
<section class="card" data-key="{html.escape(key)}">
  <h2>{i}. {html.escape(cl.title(r['quartet']))}, movement {r['movement']}, {cl.pc.NAMES.get(r['part'], r['part'])}
    <span class="src">{html.escape(r['source'])} · page {page}, staff {int(r['staff'].split('-')[1]) + 1} from the top</span></h2>
  <img class="staff" src="data:image/png;base64,{img['source']['data']}" alt="the manuscript's line over the proposed bars">
  <details><summary>Opus's prompt, word for word</summary><pre class="prompt">{html.escape(text['text'])}</pre></details>
  <p class="ask"><b>Is the top line the same music as the bottom line?</b> Where does the top begin and end, against the bottom's first and last bars?</p>
  {group("top", cl.TOP)}
  {group("start", cl.START)}
  {group("end", cl.END)}
  {group("middle", ["the same music", "different", "can't tell"])}
  <div class="buttons"><input class="note" placeholder="anything that made it hard, or what's different"></div>
  <div class="reveal">
    <p>The pairing proposed bars {f}–{l} (the bottom line). Opus, asked earlier whether those bars were exactly right
      (with the score as text, no picture of it), <b class="{verdict}">{verdict}</b> them.</p>
    <details><summary>Opus's working</summary><p>{html.escape(r['working'] or '')}</p></details>
    <details open><summary>Opus's insights</summary><p>{html.escape(r['insights'] or '')}</p></details>
  </div>
  {f'<p class="more">More context, which Opus doesn&#39;t have: <a href="{link}" target="_blank">the page in the labeler</a>.</p>' if link else ''}
</section>"""


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Opus check spot-check</title>
<style>
:root { --bg: #fff; --fg: #1d1d1f; --muted: #6e6e73; --line: #d2d2d7; --shade: #fff4c2; --ok: #1a7f37; --no: #b42318; --card: #fafafa; }
@media (prefers-color-scheme: dark) { :root { --bg: #161618; --fg: #f2f2f2; --muted: #a1a1a6; --line: #3a3a3c; --shade: #4a4120; --ok: #4ac26b; --no: #ff6b5e; --card: #1f1f22; } }
body { background: var(--bg); color: var(--fg); font: 15px/1.45 -apple-system, system-ui, sans-serif; margin: 0 auto; max-width: 1100px; padding: 16px; }
h1 { font-size: 20px; margin: 8px 0; } h2 { font-size: 16px; margin: 0 0 6px; } .src { color: var(--muted); font-weight: normal; font-size: 13px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 14px; margin: 14px 0; }
.card.done { border-color: var(--ok); }
img { width: 100%; height: auto; background: #fff; border-radius: 4px; } h3 { font-size: 14px; margin: 12px 0 4px; }
.prompt { white-space: pre-wrap; font: 12.5px/1.5 ui-monospace, monospace; background: var(--bg); border: 1px solid var(--line); border-radius: 6px; padding: 10px; max-height: 340px; overflow: auto; }
.reveal { display: none; border-top: 1px dashed var(--line); margin-top: 8px; } .card.done .reveal { display: block; } .more { color: var(--muted); font-size: 13px; }
.accepted { color: var(--ok); } .rejected { color: var(--no); }
.buttons { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 8px 0; }
.q { color: var(--muted); min-width: 52px; } button { font: 13px/1.3 inherit; padding: 5px 10px; border-radius: 6px; border: 1px solid var(--line); background: var(--bg); color: var(--fg); cursor: pointer; }
button.on { background: var(--fg); color: var(--bg); }
.note { flex: 1; min-width: 200px; font: inherit; padding: 6px; border-radius: 6px; border: 1px solid var(--line); background: var(--bg); color: var(--fg); }
details { margin: 6px 0; } summary { cursor: pointer; color: var(--muted); }
#out { width: 100%; height: 90px; font: 12px ui-monospace, monospace; background: var(--bg); color: var(--fg); border: 1px solid var(--line); border-radius: 6px; }
.bar { position: sticky; top: 0; background: var(--bg); padding: 8px 0; border-bottom: 1px solid var(--line); display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
</style></head><body>
<div class="bar"><h1>Opus check: spot-check</h1><span id="count"></span><button id="copy">Copy verdicts</button></div>
<p>Each staff: the manuscript's line on top, the bars the pairing proposed engraved underneath. Answer the questions, the ones Opus is now asked (its prompt, word for word, is under each picture). The proposal is right when the top line has music you can read, begins at or partway into the first bar, ends at or partway through the last, and the music between is the same. Then Opus's earlier answer appears. Your verdicts are kept in this browser; when you're done, press <b>Copy verdicts</b> and paste them back to Claude.</p>
%CARDS%
<p>Verdicts (also what Copy puts on the clipboard):</p><textarea id="out" readonly></textarea>
<script>
const KEY = 'opus-spotcheck-v5';
const TOP0 = %TOP0%;
let saved = {}; try { saved = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) {}
const cards = [...document.querySelectorAll('.card')];
function render() {
  let n = 0;
  for (const c of cards) {
    const v = saved[c.dataset.key] || {};
    c.querySelectorAll('[data-q]').forEach((g) => g.querySelectorAll('button').forEach((b) => b.classList.toggle('on', b.dataset.v === v[g.dataset.q])));
    c.querySelector('.note').value = v.note || '';
    const done = !!(v.top && (v.top !== TOP0 || (v.start && v.end && v.middle)));
    c.classList.toggle('done', done); n += done;
  }
  document.getElementById('count').textContent = `${n} of ${cards.length} done`;
  document.getElementById('out').value = JSON.stringify(saved);
  try { localStorage.setItem(KEY, JSON.stringify(saved)); } catch (e) {}
}
for (const c of cards) {
  const k = c.dataset.key;
  c.querySelectorAll('[data-q]').forEach((g) => g.querySelectorAll('button').forEach((b) => b.onclick = () => { saved[k] = { ...(saved[k] || {}), [g.dataset.q]: b.dataset.v, at: new Date().toISOString() }; render(); }));
  c.querySelector('.note').oninput = (e) => { saved[k] = { ...(saved[k] || {}), note: e.target.value }; render(); };
}
document.getElementById('copy').onclick = async () => {
  const t = JSON.stringify(saved);
  try { await navigator.clipboard.writeText(t); document.getElementById('copy').textContent = 'Copied'; }
  catch (e) { const o = document.getElementById('out'); o.select(); document.execCommand('copy'); }
};
render();
</script></body></html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--accepted", type=int, default=10)
    ap.add_argument("--rejected", type=int, default=3)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    rows = [json.loads(s) for s in (HERE / "results" / "cli-check-claude-opus-5-5-high.jsonl").read_text().splitlines()]
    rows = [r for r in rows if r.get("text") == 2 and r["source"] != "G213-KHM587" and r["right"] is not None]
    judged = set()
    for v in HERE.glob("results/spotcheck-verdicts-*.json"):
        judged |= set(json.loads(v.read_text()))
    rows = [r for r in rows if f"{r['source']}/{r['staff']}" not in judged]
    rng = random.Random(a.seed)
    pick = lambda rs, k: rng.sample(rs, min(k, len(rs)))
    sample = pick([r for r in rows if r["right"]], a.accepted) + pick([r for r in rows if not r["right"]], a.rejected)
    rng.shuffle(sample)
    ids = labeler_ids()
    out = HERE / "spotcheck.html"
    out.write_text(PAGE.replace("%TOP0%", json.dumps(cl.TOP[0])).replace("%CARDS%", "".join(card(i + 1, r, ids) for i, r in enumerate(sample))))
    print(f"{len(sample)} staves -> {out}" + ("" if ids else " (the labeler isn't running: no links)"))


if __name__ == "__main__":
    main()
