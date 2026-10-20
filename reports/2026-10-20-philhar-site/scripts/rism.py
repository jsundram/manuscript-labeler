# /// script
# requires-python = ">=3.11"
# dependencies = ["requests"]
# ///
"""rism.py search "<query>" [fq ...]   |   rism.py source <id> [...]
Summarizes RISM Online records. 1 req/s. Caches under $CACHE (argv env)."""
import sys, time, json, os, pathlib, requests
S = requests.Session(); S.headers.update({"Accept": "application/ld+json", "User-Agent": "manuscript-labeler survey (1 req/s)"})
cache = pathlib.Path(os.environ.get("RISM_CACHE", ".")); cache.mkdir(parents=True, exist_ok=True)
def get(url, params=None):
    key = cache / (url.replace("https://rism.online/", "").replace("/", "_") + (("_" + "_".join(f"{k}={v}" for k, v in sorted(params.items()))) if params else "") )
    key = key.with_name(key.name[:200] + ".json")
    if key.exists(): return json.loads(key.read_text())
    r = S.get(url, params=params, timeout=60); time.sleep(1.0)
    r.raise_for_status(); key.write_text(r.text); return r.json()
def en(v):
    if not v: return ""
    for k in ("en", "none"):
        if k in v: return "; ".join(v[k])
    return "; ".join(next(iter(v.values())))
def person(url):
    try: return en(get(url).get("label"))
    except Exception: return url
def source(sid):
    d = get(f"https://rism.online/sources/{sid}")
    out = {"rism": sid, "label": en(d.get("label"))}
    for it in d.get("contents", {}).get("summary", []):
        out[en(it["label"])] = en(it.get("value"))
    mats = []
    for mg in d.get("materialGroups", {}).get("items", []):
        m = {en(it["label"]): en(it.get("value")) for it in mg.get("summary", [])}
        cps = [person(r["relatedTo"]["id"]) for r in mg.get("relationships", {}).get("items", []) if r.get("role", {}).get("value") == "scr"]
        if cps: m["copyist"] = cps
        mats.append(m)
    out["material"] = mats
    ext = []
    for r in (d.get("externalResources", {}) or {}).get("items", []):
        ext.append({"url": r.get("url"), "label": en(r.get("label")) if isinstance(r.get("label"), dict) else r.get("label")})
    for ex in (d.get("exemplars", {}) or {}).get("items", []):
        for r in (ex.get("externalResources", {}) or {}).get("items", []):
            ext.append({"url": r.get("url"), "label": en(r.get("label")) if isinstance(r.get("label"), dict) else r.get("label")})
        inst = ex.get("heldBy", {})
        out.setdefault("held", []).append(en(inst.get("label")) if isinstance(inst.get("label"), dict) else str(inst.get("id")))
    out["links"] = ext
    return out
def search(q, fqs):
    params = {"q": q, "mode": "sources", "rows": 40}
    if fqs: params["fq"] = fqs
    d = get("https://rism.online/search", params)
    res = [(it["id"].rsplit("/", 1)[1], en(it.get("label")), en(it.get("summary", {}).get("dateStatements", {}).get("value"))) for it in d.get("items", [])]
    return d.get("totalItems"), res
if __name__ == "__main__":
    if sys.argv[1] == "search":
        n, res = search(sys.argv[2], sys.argv[3:])
        print("total", n)
        for r in res: print(" ", *r, sep=" | ")
    else:
        for sid in sys.argv[2:]:
            print(json.dumps(source(sid), ensure_ascii=False, indent=1))
