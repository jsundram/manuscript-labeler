"""zeus-score/MODEL_CARD_MUSVIT.md as the labeler's web card (static/models/musvit.html), in zeus.html's style.

    python3 experiments/musvit/card.py
"""
import html
import re
from pathlib import Path
LAB = Path(__file__).resolve().parent.parent.parent
md = (LAB / "zeus-score/MODEL_CARD_MUSVIT.md").read_text()
md = re.sub(r"```bibtex\n.*?```", "(BibTeX in the Markdown card.)", md, flags=re.S)

def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", lambda m: f"<a href='{m.group(2) if m.group(2).startswith('http') else 'https://github.com/jsundram/manuscript-labeler/blob/main/zeus-score/' + m.group(2)}'>{m.group(1)}</a>", s)
    return s

blocks = re.split(r"\n\s*\n", md.strip())
title = blocks[0].lstrip("# ").strip()
out, section_open = [], False
for b in blocks[1:]:
    lines = b.splitlines()
    if b.startswith("## "):
        if section_open:
            out.append("</section>")
        out.append(f"<section class='card'><h2>{inline(b[3:].strip())}</h2>")
        section_open = True
    elif b.startswith(">"):
        out.append("<p class='lede'>" + inline(" ".join(l.lstrip("> ").strip() for l in lines)) + "</p>")
    elif lines[0].startswith("|"):
        rows = [[c.strip() for c in l.strip().strip("|").split("|")] for l in lines if not re.match(r"^\|[-:| ]+\|$", l.strip())]
        aligns = [c.strip().endswith(":") for c in lines[1].strip().strip("|").split("|")]
        head, body = rows[0], rows[1:]
        if all(not h for h in head):  # a key-value table
            out.append("<dl class='kv'>" + "".join(f"<dt>{inline(r[0])}</dt><dd>{inline(r[1])}</dd>" for r in body) + "</dl>")
        else:
            cls = lambda k: " class='n'" if k < len(aligns) and aligns[k] else ""
            t = "<div class='wide'><table><thead><tr>" + "".join(f"<th{cls(k)}>{inline(h)}</th>" for k, h in enumerate(head)) + "</tr></thead><tbody>"
            t += "".join("<tr>" + "".join(f"<td{cls(k)}>{inline(c)}</td>" for k, c in enumerate(r)) + "</tr>" for r in body)
            out.append(t + "</tbody></table></div>")
    elif lines[0].startswith("- "):
        items, cur = [], []
        for l in lines:
            if l.startswith("- "):
                if cur: items.append(" ".join(cur))
                cur = [l[2:].strip()]
            else:
                cur.append(l.strip())
        items.append(" ".join(cur))
        out.append("<ul>" + "".join(f"<li>{inline(i)}</li>" for i in items) + "</ul>")
    else:
        out.append(f"<p>{inline(' '.join(l.strip() for l in lines))}</p>")
if section_open:
    out.append("</section>")
# the opening paragraphs (before the first section) become the lede
page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>MuSViT reader D3 · model card</title><link rel="stylesheet" href="models.css">
<style>
.wide {{ overflow-x: auto; }}
.wide table {{ min-width: 640px; }}
td.n, th.n {{ text-align: right; padding-right: 12px; }}
</style></head>
<body><main><p><a href='index.html'>← all models</a></p>
<h1>{html.escape(title)}<span class='pill ok'>zeus-score's default since 1.2.0</span></h1>
<p class='links'><a href='https://github.com/jsundram/manuscript-labeler/tree/main/zeus-score'>zeus-score</a> (<a href='https://github.com/jsundram/manuscript-labeler/blob/main/zeus-score/MODEL_CARD_MUSVIT.md'>this card in Markdown</a>) · <a href='https://github.com/OMR-PRAIG-UA-ES/MuSViT'>MuSViT (PRAIG)</a> · <a href='https://github.com/jsundram/manuscript-labeler/tree/main/experiments/musvit'>experiments/musvit</a> (the reader, training, results) · <a href='zeus.html'>Zeus J's card</a></p>
{chr(10).join(out)}
<footer class="muted">Generated from zeus-score/MODEL_CARD_MUSVIT.md, 2026-10-18.</footer>
</main></body></html>
"""
(LAB / "static/models/musvit.html").write_text(page)
print("wrote static/models/musvit.html", len(page))
