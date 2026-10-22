# /// script
# requires-python = ">=3.11"
# dependencies = ["requests"]
# ///
"""Philhar's LilyPond zips for the kept string works, from the Wayback Machine.

    uv run experiments/philhar-mss/fetch_lily.py [~/Data/manuscript-labeler/philhar-site]

One folder per work: <root>/<work>/<zip> and <root>/<work>/unpacked/.
A zip already in the survey's sample (<root>/zips/...) is copied, not
fetched again. At most one request a second. Writes <root>/<work>/SOURCE.json
with the capture URL and SHA-256.
"""

import hashlib
import json
import shutil
import sys
import time
import zipfile
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
SURVEY = HERE.parents[1] / "reports/2026-10-20-philhar-site/philhar-site.json"

# work folder -> zip path on the site (from the survey)
WORKS = {
    "boccherini-G83": "boccherini/trios/g83/11018-1-Boccherini-Trio-G83-lily.zip",
    "boccherini-G84": "boccherini/trios/g84/11018-2-Boccherini-Trio-G84-lily.zip",
    "boccherini-G85": "boccherini/trios/g85/11018-3-Boccherini-Trio-G85-lily.zip",
    "boccherini-G86": "boccherini/trios/g86/11018-4-Boccherini-Trio-G86-lily.zip",
    "boccherini-G87": "boccherini/trios/g87/11018-5-Boccherini-Trio-G87-lily.zip",
    "boccherini-G88": "boccherini/trios/g88/11018-6-Boccherini-Trio-G88-lily.zip",
    **{f"campioni-op7-{n}": f"campioni/13021-{n}-Campioni-Op7-Duo-{n}-LYS.zip" for n in range(1, 7)},
    "giardini-duo-F": "giardini/Duo-vl-vc/13023b-Giardini-Duo-Vl-Vc-lily.zip",
    "haydn-m-MH411": "haydn-m/MH-411/12005-HaydnM-Quintette-MH411-Lily.zip",
}


def captures() -> dict[str, str]:
    d = json.loads(SURVEY.read_text())
    return {z["zip"]: z["archived"] for s in d["sets"] for z in s["lilypond"]}


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "~/Data/manuscript-labeler/philhar-site").expanduser()
    cap = captures()
    s = requests.Session()
    s.headers["User-Agent"] = "manuscript-labeler (jsundram; research; 1 req/s)"
    for work, path in WORKS.items():
        folder = root / work
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / Path(path).name
        ts = cap[path]
        url = f"https://web.archive.org/web/{ts}id_/https://le-concert.pagesperso-orange.fr/{path}"
        sample = root / "zips" / path
        how = "kept"
        if not dest.exists():
            if sample.exists():
                shutil.copy2(sample, dest)
                how = f"copied from {sample.relative_to(root)}"
            else:
                r = s.get(url, timeout=120)
                time.sleep(1.1)
                r.raise_for_status()
                if not r.content.startswith(b"PK"):
                    sys.exit(f"{work}: not a zip from {url}")
                dest.write_bytes(r.content)
                how = "fetched"
        data = dest.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        unpacked = folder / "unpacked"
        if not unpacked.exists():
            with zipfile.ZipFile(dest) as z:
                for name in z.namelist():   # no absolute paths or .. in members
                    if name.startswith("/") or ".." in Path(name).parts:
                        sys.exit(f"{work}: unsafe member {name}")
                z.extractall(unpacked)
        (folder / "SOURCE.json").write_text(json.dumps({
            "work": work, "zip": dest.name, "site_path": path, "capture": ts, "url": url,
            "bytes": len(data), "sha256": sha, "licence": "CC BY-NC-SA (Editions Le Concert, Philhar)",
        }, indent=1) + "\n")
        print(f"{work:20s} {len(data):8d} {sha[:12]} {how}")


if __name__ == "__main__":
    main()
