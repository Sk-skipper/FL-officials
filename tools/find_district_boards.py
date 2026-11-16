"""Find the board page of each special district that has a website, and who sits on the board.

    python -m collector.publish                 # builds site/data/meta.json, which lists the districts
    python tools/find_district_boards.py > boards.json
    python tools/find_district_boards.py --render --keys-file keys.txt   # headless Chromium, only these districts

For each district in meta.json with a website, this follows the homepage's links that look like the board page
("Board of Supervisors", "Commissioners", "Governing board"...), reads each page three ways (member cards, a
roster of "Title Name" lines, and name lines followed by a role line) and keeps the reading that finds a
believable board: 3 to 9 people. It only suggests: review the output, then add the good ones to
data/sources.json as city_roster sources (see README).
"""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from collector.scrapers.base import FetchError, HostSchedule, PoliteHttpClient  # noqa: E402
from collector.scrapers.city_roster import find_board, find_cards, find_members, page_lines  # noqa: E402
from collector.scrapers.registry import user_agent  # noqa: E402

BOARD_LINK = re.compile(r"board|supervisors|commissioners|governing|trustees|directors|officials|about", re.I)
SKIP = re.compile(r"meeting|agenda|minutes|budget|audit|calendar|\.pdf$|financ|bond|notice|record", re.I)
ROLES = r"^(chair|vice|supervisor|board supervisor|commissioner|secretary|assistant secretary|treasurer|member|trustee|director|president)"
SCHEDULE = HostSchedule()


def links(html: str, base: str) -> list[str]:
    host = urlsplit(base).netloc.removeprefix("www.")
    out = []
    for a in BeautifulSoup(html, "lxml").select("a[href]"):
        text = " ".join(a.get_text(" ").split())
        href = urljoin(base, a["href"]).split("#")[0]
        if host in urlsplit(href).netloc and BOARD_LINK.search(f"{text} {href}") and not SKIP.search(f"{text} {href}"):
            out.append(href)
    return list(dict.fromkeys(out))[:6]


def readings(html: str, url: str) -> list[tuple[str, list[dict]]]:
    lines = page_lines(html, url=url)
    return [("cards", find_cards(html, url, "Supervisor")), ("roster", find_members(lines, "Supervisor")),
            ("board", find_board(lines, ROLES, "Supervisor"))]


RENDER = "--render" in sys.argv


def check(district: dict) -> dict:
    client = PoliteHttpClient(user_agent(), 2, 30, 0, schedule=SCHEDULE)
    fetch = client.get_rendered if RENDER else client.get
    result = {"key": district["key"], "name": district["name"], "county": district.get("county"),
              "website": district["website"], "best": None}
    try:
        home = fetch(district["website"])
    except FetchError as exc:
        result["error"] = str(exc)[:120]
        return result
    pages = [(district["website"], home)]
    for url in links(home, district["website"]):
        try:
            pages.append((url, fetch(url)))
        except FetchError:
            continue
    best = None
    for url, html in pages:
        for method, members in readings(html, url):
            if 3 <= len(members) <= 9 and (best is None or len(members) > len(best["members"])):
                best = {"url": url, "method": method, "members": [
                    {"name": m["name"], "title": m["title"], "seat": m.get("seat")} for m in members]}
    result["best"] = best
    return result


def main() -> None:
    meta = json.loads((ROOT / "site/data/meta.json").read_text(encoding="utf-8"))
    todo = [d for d in meta.get("special_districts", []) if d.get("website")]
    args = sys.argv[1:]
    if "--keys-file" in args:  # one key per line; keys can contain spaces
        path = args[args.index("--keys-file") + 1]
        args = [k.strip() for k in Path(path).read_text().splitlines() if k.strip()]
    wanted = [a for a in args if not a.startswith("--")]
    if wanted:
        todo = [d for d in todo if d["key"] in wanted]
    with ThreadPoolExecutor(max_workers=4 if RENDER else 8) as pool:
        results = list(pool.map(check, todo))
    print(json.dumps(results, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
