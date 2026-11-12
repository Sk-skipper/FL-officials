"""Fill gaps from Wikipedia: portraits (free-licensed Wikimedia Commons images only), birth dates
from Wikidata, and a link to the article. Writes data/wikipedia.json.

    python -m collector.publish            # builds site/data/officials.json, which this reads
    python tools/wikipedia.py              # only officials with no photo or no birth date
    python tools/wikipedia.py --review     # print every match so you can check it

An article is used only when ALL of these hold, so a namesake is never matched:
  * the article title contains the official's first and last name;
  * its Wikidata description or opening sentence names the office (judge, mayor, sheriff, ...);
  * and it mentions Florida or the official's county/city.
Images come from PageImages with the "free" licence filter, so fair-use pictures are never used, and
each keeps its author and licence so the site can credit it.

Official sources always win: publish only uses these values where a record has none of its own.
To reject a match, add the record id to "_rejected" in data/wikipedia.json; re-runs keep it rejected.
"""
import argparse
import json
import re
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "wikipedia.json"
API = "https://en.wikipedia.org/w/api.php"
COMMONS = "https://commons.wikimedia.org/w/api.php"
WIKIDATA = "https://www.wikidata.org/wiki/Special:EntityData/{}.json"
HEADERS = {"User-Agent": "fl-officials-directory/1.0 (https://github.com/; officials directory enrichment)"}
FREE = re.compile(r"^(cc0|cc[ -]by|public domain|pd|gfdl|attribution)", re.I)

OFFICE_WORDS = {
    "judge": ["judge", "jurist", "justice"],
    "justice": ["justice", "judge", "jurist"],
    "mayor": ["mayor", "politician", "commissioner"],
    "commissioner": ["commissioner", "politician", "mayor"],
    "councilmember": ["council", "politician"],
    "sheriff": ["sheriff", "law enforcement", "police"],
    "attorney": ["attorney", "prosecutor", "lawyer"],
    "defender": ["defender", "lawyer", "attorney"],
    "clerk": ["clerk", "politician"],
    "appraiser": ["appraiser", "politician"],
    "collector": ["collector", "politician"],
    "school board": ["school board", "educator", "politician"],
    "financial": ["financial officer", "politician"],
    "agriculture": ["agriculture", "politician"],
}


def fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()


def office_words(title: str) -> list[str]:
    t = fold(title)
    for key, words in OFFICE_WORDS.items():
        if key in t:
            return words
    return ["politician"]


def api(url: str, **params) -> dict:
    params.update(format="json", formatversion=2)
    for attempt in range(3):
        response = requests.get(url, params=params, headers=HEADERS, timeout=30)
        if response.status_code == 429:
            time.sleep(5 * (attempt + 1))
            continue
        response.raise_for_status()
        time.sleep(0.3)  # be gentle with the API
        return response.json()
    response.raise_for_status()
    return {}


def name_in_title(record: dict, title: str) -> bool:
    t = fold(title)
    return fold(record["last_name"]) in t and fold(record["first_name"]) in t


def candidates(record: dict) -> list[dict]:
    place = record.get("municipality") or record.get("county") or "Florida"
    query = f'"{record["first_name"]}" "{record["last_name"]}" Florida {place}'
    hits = api(API, action="query", list="search", srsearch=query, srlimit=5).get("query", {}).get("search", [])
    titles = [h["title"] for h in hits if name_in_title(record, h["title"])]
    if not titles:
        return []
    pages = api(API, action="query", titles="|".join(titles), prop="pageimages|description|extracts|pageprops|info",
                piprop="original|name", pilicense="free", exintro=1, explaintext=1, exsentences=2, inprop="url",
                redirects=1).get("query", {}).get("pages", [])
    return [p for p in pages if not p.get("missing")]


def matches(record: dict, page: dict) -> bool:
    text = fold(" ".join([page.get("description") or "", page.get("extract") or ""]))
    if not any(word in text for word in office_words(record["office_title"])):
        return False
    places = ["florida", fold(record.get("county") or ""), fold(record.get("municipality") or "")]
    return any(p and p in text for p in places)


def image_credit(file_name: str) -> dict | None:
    pages = api(COMMONS, action="query", titles=f"File:{file_name}", prop="imageinfo",
                iiprop="url|extmetadata", iiurlwidth=400).get("query", {}).get("pages", [])
    if not pages or "imageinfo" not in pages[0]:
        return None
    info = pages[0]["imageinfo"][0]
    meta = info.get("extmetadata", {})
    licence = (meta.get("LicenseShortName") or {}).get("value", "")
    if not FREE.match(licence):
        return None
    author = re.sub(r"<[^>]+>", "", (meta.get("Artist") or {}).get("value", "")).strip() or "Unknown author"
    return {
        "photo_url": info.get("thumburl") or info["url"],
        "photo_credit": {
            "source": "Wikimedia Commons", "author": author[:120], "license": licence,
            "license_url": (meta.get("LicenseUrl") or {}).get("value") or None,
            "file_url": info.get("descriptionurl"),
        },
    }


def birth_date(qid: str | None) -> str | None:
    if not qid:
        return None
    entity = requests.get(WIKIDATA.format(qid), headers=HEADERS, timeout=30).json()["entities"][qid]
    claims = entity.get("claims", {}).get("P569", [])
    for claim in claims:
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
        if value.get("precision", 0) >= 11:  # a full date, not just a year
            return value["time"][1:11]
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--review", action="store_true", help="print each match")
    parser.add_argument("--all", action="store_true", help="also look up officials who already have a photo and birth date")
    args = parser.parse_args()

    officials = json.loads((ROOT / "site/data/officials.json").read_text(encoding="utf-8"))["officials"]
    existing = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    rejected = set(existing.get("_rejected", []))
    out = {k: v for k, v in existing.items() if not k.startswith("_")}
    # Trial judges almost never have articles; skipping them saves ~90 lookups per run.
    todo = [r for r in officials if r["id"] not in rejected and r["id"] not in out
            and r["office_title"] not in ("Circuit Judge", "County Court Judge")
            and (args.all or not r.get("photo_url") or not (r.get("bio") or {}).get("born"))]
    print(f"Looking up {len(todo)} officials on Wikipedia...")
    for record in todo:
        try:
            page = next((p for p in candidates(record) if matches(record, p)), None)
        except requests.RequestException as exc:
            print(f"  skipped {record['full_name']}: {exc}")
            continue
        if not page:
            continue
        entry = {"name": record["full_name"], "wikipedia_url": page.get("fullurl")}
        if page.get("pageimage") and not record.get("photo_url"):
            credit = image_credit(page["pageimage"])
            if credit:
                entry.update(credit)
        if not (record.get("bio") or {}).get("born"):
            born = birth_date((page.get("pageprops") or {}).get("wikibase_item"))
            if born:
                entry["born"] = born
        out[record["id"]] = entry
        if args.review:
            print(f"  {record['full_name']} ({record['office_title']}) -> {page.get('title')}: {page.get('description')}"
                  f"{' [photo]' if entry.get('photo_url') else ''}{' [born ' + entry['born'] + ']' if entry.get('born') else ''}")

    result = {
        "_how_to": ("Generated by tools/wikipedia.py. Fills a photo, birth date or Wikipedia link only where the "
                    "official source gave none. Put a record id in _rejected to stop a wrong match being used."),
        "_generated": date.today().isoformat(),
        "_rejected": sorted(rejected),
        **dict(sorted(out.items())),
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(out)} matches ({sum('photo_url' in v for v in out.values())} with a photo) to data/wikipedia.json")


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
