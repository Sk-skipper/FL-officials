"""Find a city's council roster page, for adding it as a "city_roster" source in data/sources.json.

    python tools/find_council_pages.py cities.json > found.json

cities.json is a list of {"municipality", "county", "homepage"}. For each city this fetches the homepage
(obeying robots.txt), follows links that look like the commission or council page, runs the city_roster
extractor on each, and reports the page that names the most seat holders. Review the output before
adding sources: the extractor is a heuristic, and this only suggests.
"""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from collector.scrapers.base import FetchError, PoliteHttpClient  # noqa: E402
from collector.scrapers.city_roster import find_cards, find_members, page_lines  # noqa: E402
from collector.scrapers.registry import user_agent  # noqa: E402

LINK = re.compile(r"(city|town|village)?\s*(commission|council)|elected officials|mayor\b|commissioners|councilmembers"
                  r"|government", re.I)
SKIP = re.compile(r"agenda|minutes|meeting|video|calendar|advisory|board|committee|election|\.pdf$|youth|pension", re.I)


def candidates(client: PoliteHttpClient, homepage: str, html: str | None = None) -> list[str]:
    html = html or client.get(homepage)
    soup = BeautifulSoup(html, "lxml")
    host = urlsplit(homepage).netloc.removeprefix("www.")
    urls = []
    for a in soup.select("a[href]"):
        text = " ".join(a.get_text(" ").split())
        href = urljoin(homepage, a["href"]).split("#")[0]
        if host not in urlsplit(href).netloc or SKIP.search(text) or SKIP.search(href):
            continue
        if LINK.search(text) or LINK.search(href):
            score = 2 if re.search(r"commission|council", text, re.I) else 1
            urls.append((score, href))
    seen, out = set(), []
    for _, url in sorted(urls, key=lambda x: -x[0]):
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out[:8]


def best_page(city: dict) -> dict:
    client = PoliteHttpClient(user_agent(), delay_seconds=1, timeout_seconds=20, max_retries=1)
    member = "Councilmember" if "council" in city.get("body", "").lower() else "Commissioner"
    result = {**city, "best": None, "members": [], "tried": []}
    try:
        urls = candidates(client, city["homepage"])
    except FetchError as exc:
        result["error"] = str(exc)
        return result
    queue, seen = list(urls), set()
    while queue and len(seen) < 16:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            html = client.get(url)
        except FetchError as exc:
            result["tried"].append({"url": url, "error": str(exc)[:120]})
            continue
        members = find_cards(html, url, member) or find_members(page_lines(html, url=url), member)
        result["tried"].append({"url": url, "found": len(members)})
        if len(members) > len(result["members"]):
            result["best"], result["members"] = url, members
        if len(members) < 3 and url in urls:  # one level deeper: "Government" -> "City Commission"
            queue += [u for u in candidates(client, url, html) if re.search(r"commission|council|mayor|elected", u, re.I)][:4]
    return result


def main() -> None:
    cities = json.loads(Path(sys.argv[1]).read_text())
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(best_page, cities))
    print(json.dumps(results, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
