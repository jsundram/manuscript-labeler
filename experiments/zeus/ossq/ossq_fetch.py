# /// script
# requires-python = ">=3.11"
# dependencies = ["browser-cookie3", "requests"]
# ///
"""Download the OSSQ manuscripts from IMSLP with your browser's IMSLP
session (so the browser check and your account apply as when you click).

    uv run experiments/zeus/ossq/ossq_fetch.py [--browser chrome|firefox|safari|edge|brave|arc] [--out ~/Downloads/ossq]

Open imslp.org once in that browser first (logged in), so its cookies are fresh.
"""

import argparse
from pathlib import Path

import browser_cookie3
import requests

FILES = [
    "PMLP674153-Andree_Elfrida_Kvartett_Strakar_Autograf.pdf",
    "PMLP674153-Andree_Elfrida_Kvartett_Strakar_Autograf_stammor.pdf",
    "PMLP1185886-F._Hensel_-_String_Quartet_Manuscript_Score.pdf",
    "PMLP905970-Maier_Rontgen_Amanda_Kvartett_Strakar_A_dur_partitur_autograf.pdf",
    "PMLP1188813-EMayer_String_Quartet_in_A_major_score_color_RISM464000310.pdf",
    "PMLP529322-EMayer_String_Quartet_in_E_minor_score_color_RISM464122223.pdf",
    "PMLP529322-EMayer_String_Quartet_in_E_minor_violin1_color_RISM464122224.pdf",
    "PMLP529322-EMayer_String_Quartet_in_E_minor_violin2_color_RISM464122224.pdf",
    "PMLP529322-EMayer_String_Quartet_in_E_minor_viola_color_RISM464122224.pdf",
    "PMLP529322-EMayer_String_Quartet_in_E_minor_cello_color_RISM464122224.pdf",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--browser", default=None, help="default: try every browser")
    ap.add_argument("--out", type=Path, default=Path.home() / "Downloads" / "ossq")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    jar = (getattr(browser_cookie3, a.browser) if a.browser else browser_cookie3.load)(domain_name="imslp.org")
    s = requests.Session()
    s.cookies = jar
    s.headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
    for f in FILES:
        dest = a.out / f
        if dest.exists() and dest.read_bytes()[:4] == b"%PDF":
            print(f"have {f}")
            continue
        try:  # stale cookies get the browser check's page, not JSON; a renamed file has no imageinfo
            info = s.get("https://imslp.org/api.php", params={
                "action": "query", "titles": f"File:{f}", "prop": "imageinfo", "iiprop": "url", "format": "json"}).json()
            url = "https:" + next(iter(info["query"]["pages"].values()))["imageinfo"][0]["url"]
        except (ValueError, KeyError, IndexError) as e:
            print(f"FAILED {f}: no file URL from IMSLP ({e!r})")
            continue
        r = s.get(url, timeout=300)
        if r.content[:4] != b"%PDF":
            print(f"FAILED {f}: got {r.headers.get('content-type')} from {r.url}")
            continue
        dest.write_bytes(r.content)
        print(f"got {f} ({len(r.content) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
