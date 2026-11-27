"""When state, federal and county officials took office, from the "assumed office" line of their Wikipedia infobox.

    python tools/wikipedia_terms.py          # reads site/data/officials.json, writes data/wikipedia_terms.json

Election records date a win, not an appointment: an Attorney General or sheriff the Governor appointed shows up only
once they stand for election. The infobox gives the date they actually took the office, and who appointed them.

An article is used only when it passes tools/wikipedia.py's checks (first and last name in the title; the office
and Florida in its description) or is already linked in data/wikipedia.json. In that article, only an infobox entry
with no end date (a current office) whose title names this office (and district, where there is one) is used. Each
value keeps the article URL; tools/derive_tenure.py labels it as Wikipedia.
"""
import json
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from wikipedia import API, api, candidates, matches  # noqa: E402

OUT = ROOT / "data" / "wikipedia_terms.json"
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}
# What a current-office line must say for each of our offices.
OFFICE_PATTERNS = [
    (r"^State Representative", r"florida house of representatives"),
    (r"^State Senator", r"florida senate"),
    (r"^U\.S\. Representative|^Representative in Congress", r"(u\.s\.|united states) house of representatives|congress"),
    (r"^U\.S\. Senator", r"united states senat|u\.s\. senat"),
    (r"^Lieutenant Governor", r"lieutenant governor of florida"),
    (r"^Governor", r"^governor of florida"),
    (r"^Attorney General", r"attorney general of florida|florida attorney general"),
    (r"Chief Financial Officer", r"chief financial officer"),
    (r"Agriculture", r"agriculture"),
    (r"Justice", r"supreme court of florida|florida supreme court"),
    (r"District Court of Appeal", r"district court of appeal"),
    (r"Sheriff", r"sheriff"),
    (r"Mayor", r"mayor"),
    (r"State Attorney", r"state attorney"),
    (r"Public Defender", r"public defender"),
    (r"Clerk", r"clerk"),
    (r"Property Appraiser", r"property appraiser"),
    (r"Tax Collector", r"tax collector"),
    (r"Supervisor of Elections", r"supervisor of elections"),
    (r"Commissioner", r"commission"),
    (r"School Board", r"school board"),
    (r"Superintendent", r"superintendent"),
]


def fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def clean(value: str) -> str:
    value = re.sub(r"<ref[^>]*/>|<ref.*?</ref>|<!--.*?-->", "", value, flags=re.S)
    value = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", value)
    return re.sub(r"\s+", " ", value).strip()


def parse_date(value: str):
    """(year, iso date or None) from '{{start date|2025|2|17}}', 'February 17, 2025', '2025'."""
    m = re.search(r"\{\{\s*start date(?: and age)?\s*\|\s*(\d{4})\s*(?:\|\s*(\d{1,2})\s*(?:\|\s*(\d{1,2}))?)?", value, re.I)
    if m:
        y, mo, d = m.group(1), m.group(2), m.group(3)
        return int(y), (f"{y}-{int(mo):02d}-{int(d):02d}" if mo and d else None)
    v = fold(clean(value))
    m = re.search(r"([a-z]+)\s+(\d{1,2}),?\s+(\d{4})", v) or re.search(r"(\d{1,2})\s+([a-z]+)\s+(\d{4})", v)
    if m:
        a, b, y = m.groups()
        month, day = (a, b) if a in MONTHS else (b, a)
        if month in MONTHS:
            return int(y), f"{y}-{MONTHS[month]:02d}-{int(day):02d}"
    m = re.search(r"\b(19|20)\d\d\b", v)
    return (int(m.group(0)), None) if m else (None, None)


def infobox_offices(wikitext: str) -> list[dict]:
    fields: dict[str, dict] = {}
    for m in re.finditer(r"^\s*\|\s*(office|title|assumed_office|term_start|term_end|appointer|appointed|district|"
                         r"constituency|state)(\d*)[ \t]*=[ \t]*(.*)$", wikitext, re.M):
        key, n, value = m.group(1), m.group(2) or "0", m.group(3)
        fields.setdefault(n, {})[key] = value
    out = []
    for n, f in sorted(fields.items(), key=lambda kv: int(kv[0])):
        start = f.get("assumed_office") or f.get("term_start")
        if not start or clean(f.get("term_end") or ""):
            continue  # no start, or an office they have left
        office = clean(f.get("office") or f.get("title") or "")
        year, iso = parse_date(start)
        if not year:
            continue
        out.append({"office": office, "where": clean(" ".join(f.get(k, "") for k in ("district", "constituency", "state"))),
                    "year": year, "date": iso, "appointer": clean(f.get("appointer") or f.get("appointed") or "") or None})
    return out


def office_matches(r: dict, entry: dict) -> bool:
    title, text = r["office_title"], fold(f"{entry['office']} {entry['where']}")
    pattern = next((p for t, p in OFFICE_PATTERNS if re.search(t, title)), None)
    if not pattern or not re.search(pattern, text):
        return False
    if pattern in ("florida house of representatives", "florida senate") or "congress" in pattern:
        n = re.findall(r"\b(\d{1,3})(?:st|nd|rd|th)?\b", text)
        if not r.get("district") or str(int(r["district"])) not in n:
            return False
    if pattern in ("sheriff", "mayor", "clerk", "property appraiser", "tax collector", "supervisor of elections",
                   "commission", "school board", "superintendent", "state attorney", "public defender"):
        place = fold(r.get("municipality") or r.get("county") or "")
        if not place or place not in text:
            return False
    return True


def wikitext(title: str) -> str:
    pages = api(API, action="query", prop="revisions", rvprop="content", rvslots="main", titles=title,
                redirects=1).get("query", {}).get("pages", [])
    if not pages or "revisions" not in pages[0]:
        return ""
    return pages[0]["revisions"][0]["slots"]["main"]["content"]


def main() -> None:
    officials = json.loads((ROOT / "site/data/officials.json").read_text(encoding="utf-8"))["officials"]
    known = json.loads((ROOT / "data/wikipedia.json").read_text(encoding="utf-8"))
    previous = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    rejected = set(previous.get("_rejected", []))
    targets = [r for r in officials
               if r["government_level"] in ("state", "federal")
               or (r["government_level"] == "county" and not re.search(r"Judge|School Board|Soil|District", r["office_title"])
                   and not r.get("special_district"))]
    out: dict = {}
    for i, r in enumerate(targets, 1):
        if r["id"] in rejected:
            continue
        url = (known.get(r["id"]) or {}).get("wikipedia_url")
        try:
            if url:
                title = unquote(url.rsplit("/wiki/", 1)[1]).replace("_", " ")
            else:
                pages = [p for p in candidates(r) if matches(r, p)]
                if len(pages) != 1:
                    continue  # none, or more than one plausible article: leave it
                title, url = pages[0]["title"], pages[0].get("fullurl") or f"https://en.wikipedia.org/wiki/{pages[0]['title'].replace(' ', '_')}"
            entries = [e for e in infobox_offices(wikitext(title)) if office_matches(r, e)]
        except Exception as exc:  # network trouble on one article shouldn't stop the run
            print(f"  {r['id']}: {exc}", file=sys.stderr)
            continue
        if entries:
            e = min(entries, key=lambda e: e["year"])
            out[r["id"]] = {"name": r["full_name"], "wikipedia_url": url, "infobox_office": e["office"],
                            "assumed_office": e["date"] or str(e["year"]), "year": e["year"],
                            **({"appointed_by": e["appointer"]} if e["appointer"] else {})}
        if i % 50 == 0:
            print(f"  {i}/{len(targets)}: {len(out)} found", file=sys.stderr)
    OUT.write_text(json.dumps({"_how_to": "Generated by tools/wikipedia_terms.py; see its docstring. Add a record id to "
                                          "_rejected to stop using its article.", "_rejected": sorted(rejected),
                               **dict(sorted(out.items()))}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(out)} of {len(targets)} officials have a current-office start date on Wikipedia", file=sys.stderr)


if __name__ == "__main__":
    main()
