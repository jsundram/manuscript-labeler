"""Build the explainer page (explainer.html) from explain.py's JSON files.

    python3 experiments/musvit/explainer.py manifest.json --out page.html

manifest.json lists the staves, the first with "lead": true (the worked
example; explain.py run without --light), the rest a gallery:
    [{"id": "va-27", "path": "va-27.json", "title": "Viola 27-29", "caption": "...", "lead": true}, ...]
Paths are relative to the manifest. The page carries everything inline.
"""

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--template", type=Path, default=HERE / "explainer.html")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    items = json.loads(a.manifest.read_text())
    scripts = []
    for it in items:
        data = (a.manifest.parent / it["path"]).read_text().replace("</", "<\\/")
        scripts.append(f'<script type="application/json" id="ex-{it["id"]}">{data}</script>')
    manifest = json.dumps([{k: v for k, v in it.items() if k != "path"} for it in items])
    page = a.template.read_text().replace("<!--EXAMPLES-->", "\n".join(scripts)).replace("/*MANIFEST*/[]", manifest)
    a.out.write_text(page)
    print(f"wrote {a.out} ({a.out.stat().st_size / 1e6:.1f} MB, {len(items)} staves)")


if __name__ == "__main__":
    main()
