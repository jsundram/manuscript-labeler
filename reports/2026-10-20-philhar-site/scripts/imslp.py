# /// script
# requires-python = ">=3.11"
# dependencies = ["requests"]
# ///
"""imslp.py search "<q>" | imslp.py page "<title>" : read IMSLP wikitext via the public API (no login). 1 req/s."""
import sys, time, json, os, pathlib, re, requests
S = requests.Session(); S.headers["User-Agent"] = "manuscript-labeler survey (research; 1 req/s)"
cache = pathlib.Path(os.environ.get("IMSLP_CACHE", ".")); cache.mkdir(parents=True, exist_ok=True)
API = "https://imslp.org/api.php"
def get(params):
    key = cache / (re.sub(r"[^A-Za-z0-9]+", "_", json.dumps(params, sort_keys=True))[:180] + ".json")
    if key.exists(): return json.loads(key.read_text())
    r = S.get(API, params={**params, "format": "json"}, timeout=60); time.sleep(1.0); r.raise_for_status()
    key.write_text(r.text); return r.json()
if sys.argv[1] == "search":
    d = get({"action": "query", "list": "search", "srsearch": sys.argv[2], "srlimit": 15, "srnamespace": 0})
    for h in d["query"]["search"]: print(h["title"])
else:
    d = get({"action": "parse", "page": sys.argv[2], "prop": "wikitext", "redirects": 1})
    if "error" in d: print(d["error"]); sys.exit()
    t = d["parse"]["wikitext"]["*"]
    print(t[:int(sys.argv[3]) if len(sys.argv) > 3 else 6000])
