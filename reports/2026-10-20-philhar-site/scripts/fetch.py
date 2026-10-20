# /// script
# requires-python = ">=3.11"
# dependencies = ["requests"]
# ///
"""Polite Wayback fetcher: fetch.py <outdir> <path> [<path>...]; caches; 1 req/s.
Paths relative to the site root. Uses id_ (raw) snapshots near 20230929."""
import sys, time, pathlib, requests
out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "manuscript-labeler survey (jsundram, research; 1 req/s)"
for p in sys.argv[2:]:
    f = out / p.replace("/", "__")
    if f.exists() and f.stat().st_size > 0:
        continue
    url = f"https://web.archive.org/web/20230929061441id_/https://le-concert.pagesperso-orange.fr/{p}"
    for attempt in range(3):
        try:
            r = S.get(url, timeout=90, allow_redirects=True)
            break
        except Exception as e:
            print("ERR", p, e, file=sys.stderr); time.sleep(5); r = None
    time.sleep(1.1)
    if r is None: continue
    print(r.status_code, p, r.url, len(r.content))
    if r.status_code == 200:
        f.write_bytes(r.content)
