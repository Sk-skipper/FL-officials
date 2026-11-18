"""Find official portraits for people who have none, and save them to data/photos.json.

    python -m collector.publish            # so site/data/officials.json is current
    python tools/find_photos.py            # ~20 minutes; polite, robots.txt respected

Two passes, both reading only official pages:

1. Judges: each judicial circuit's own judge directory (CIRCUIT_PAGES). A judge's portrait is taken from the directory
   when it names them, otherwise from the judge's own page linked from the directory.
2. Everyone else with an "official website" (a clerk's, tax collector's or superintendent's site, a council member's
   own page): that page, then up to three of its "About" / "Meet" pages.

Matching uses collector.scrapers.city_roster.match_photos (an image that names the person, or sits alone in their
card; logos, seals and flyers skipped; group photos never used). On a page that is clearly the person's own (their
surname is in its address), the first portrait-like image in the main content is used.

Publish uses this file only to fill a missing photo; a photo from the official roster always wins. Keyed by record id,
so when someone leaves office their entry is simply ignored. Re-run after collections that add new people.
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
from collector.scrapers.base import FetchError, HostSchedule, PoliteHttpClient, RobotsDisallowed  # noqa: E402
from collector.scrapers.city_roster import _NOT_A_HEADSHOT, _fold, _img_src, match_photos  # noqa: E402
from collector.scrapers.registry import user_agent  # noqa: E402

OUT = ROOT / "data" / "photos.json"
SCHEDULE = HostSchedule()
CIRCUIT_PAGES = {
    1: ["https://www.firstjudicialcircuit.org/judges"],
    2: ["https://2ndcircuit.leoncountyfl.gov/circuitJudges.php"],
    3: ["https://thirdcircuitfl.org/judges-page/"],
    4: ["https://www.jud4.org/circuit-and-county-judges-of-the-fourth-judicial-circuit", "https://www.jud4.org/duval-county-judges-biographies"],
    5: ["https://www.circuit5.org/courts-judges/"],
    6: ["https://www.jud6.org/judges/"],
    7: ["https://www.circuit7.org/judges-overview/"],
    8: ["https://circuit8.org/circuit-judges/"],
    9: ["https://www.ninthcircuit.org/judges"],
    10: ["https://www.jud10.flcourts.org/gallery/judges"],
    11: ["https://www.jud11.flcourts.org/About-the-Court/Judges/Judicial-Directory"],
    12: ["https://www.jud12.flcourts.org/About/Judges"],
    13: ["https://www.fljud13.org/Directory/Judges"],
    14: ["https://www.jud14.flcourts.org/judges"],
    15: ["https://www.15thcircuit.com/judges"],
    16: ["https://keyscourts.net/judges-of-the-16th-circuit/"],
    17: ["https://www.17th.flcourts.org/judiciary/"],
    18: ["https://flcourts18.org/directory/"],
    19: ["https://www.circuit19.org/judges/"],
    20: ["https://www.ca.cjis20.org/About-The-Court/judiciary.aspx"],
}
ABOUT = re.compile(r"(?i)\babout\b|\bmeet\b|biograph|\bbio\b|leadership|elected|our[- ](clerk|tax|appraiser|superintendent)")
# On a person's own page only the obvious non-portraits are skipped (class names like "header-image" are fine here).
OWN_PAGE_SKIP = re.compile(r"(?i)logo|seal|icon|facebook|twitter|instagram|youtube|linkedin|social|signature|\bsig\b|"
                           r"building|courthouse|justice center|flag|map\b|banner|qr|coming(?:[ _-]|%20)*soon|webex|zoom|inline-images|placeholder|no[ _-]?image|\.svg(\?|$)|^data:")
BROWARD_MD = {"Broward": 17, "Miami-Dade": 11}


def client() -> PoliteHttpClient:
    return PoliteHttpClient(user_agent(), 1.5, 25, 0, schedule=SCHEDULE)


def fetch(url: str, render: bool = False) -> str | None:
    try:
        return client().get_rendered(url) if render else client().get(url)
    except (FetchError, RobotsDisallowed):
        return None


def own_page_photo(html: str, url: str, name: str = "") -> str | None:
    """On a person's own page: the image that names them, else the first portrait-like image in the main content."""
    if name:
        person = [{"name": name}]
        match_photos(html, url, person)
        if person[0].get("photo_url"):
            return person[0]["photo_url"]
    soup = BeautifulSoup(html, "lxml")
    # Only the site's own banner and menus; an article's <header> often holds the portrait.
    for junk in soup.select("body > header, body > nav, body > footer, nav, [role=banner], [role=navigation], [role=contentinfo]"):
        junk.decompose()
    main = soup.select_one("main, article, [role=main], #content, .content") or soup.body
    for img in (main.select("img") if main else []):
        src = _img_src(img, url)
        if not src or OWN_PAGE_SKIP.search(f"{src} {img.get('alt', '')}"):
            continue
        try:
            if int(img.get("width") or 999) < 80 or int(img.get("height") or 999) < 80:
                continue
        except ValueError:
            pass
        return re.sub(r"^http://", "https://", src)
    return None


def surname(name: str) -> str:
    parts = [p for p in re.split(r"[\s.,]+", name) if p and not re.fullmatch(r"(?i)jr|sr|ii|iii|iv", p)]
    return _fold(parts[-1]) if parts else ""


def circuit_of(r: dict) -> int | None:
    m = re.match(r"(\d+)\w\w Judicial Circuit", r.get("jurisdiction") or "")
    if m:
        return int(m.group(1))
    return BROWARD_MD.get(r.get("county")) if re.search(r"(?i)judge", r["office_title"]) else None


def find_judges(circuit: int, judges: list[dict]) -> dict[str, dict]:
    found: dict[str, dict] = {}
    links: list[tuple[str, str]] = []
    for url in CIRCUIT_PAGES[circuit]:
        for render in (False, True):
            html = fetch(url, render)
            if not html:
                continue
            people = [{"name": j["full_name"]} for j in judges if j["id"] not in found]
            match_photos(html, url, people)
            for j, p in zip([j for j in judges if j["id"] not in found], people):
                if p.get("photo_url"):
                    found[j["id"]] = {"photo_url": p["photo_url"], "source_url": url}
            host = urlsplit(url).netloc.removeprefix("www.")
            links += [(urljoin(url, a["href"]).split("#")[0], _fold(a.get_text(" ") + " " + a["href"]))
                      for a in BeautifulSoup(html, "lxml").select("a[href]") if host in urlsplit(urljoin(url, a["href"])).netloc]
            if found or sum(1 for j in judges if surname(j["full_name"]) in _fold(html)) > len(judges) / 3:
                break  # the directory lists the judges without JavaScript
    # A judge's own page, linked from the directory: its address or link text names them.
    for j in judges:
        if j["id"] in found:
            continue
        last, first = surname(j["full_name"]), _fold(j["first_name"])
        page = next((u for u, text in links if last and last in _fold(u) and (first in text or first in _fold(u))), None)
        if not page:
            continue
        html = fetch(page)
        photo = own_page_photo(html, page, j["full_name"]) if html else None
        if not photo:  # portraits some sites add with JavaScript
            html = fetch(page, render=True)
            photo = own_page_photo(html, page, j["full_name"]) if html else None
        if photo:
            found[j["id"]] = {"photo_url": photo, "source_url": page}
    return found


def find_on_site(r: dict) -> dict | None:
    url = r.get("official_website")
    if not url or not url.startswith("http"):
        return None
    html = fetch(url)
    if not html:
        return None
    last = surname(r["full_name"])
    if last and last in _fold(urlsplit(url).path):  # the person's own page
        photo = own_page_photo(html, url, r["full_name"])
        if photo:
            return {"photo_url": photo, "source_url": url}
    person = [{"name": r["full_name"]}]
    match_photos(html, url, person)
    if person[0].get("photo_url"):
        return {"photo_url": person[0]["photo_url"], "source_url": url}
    host = urlsplit(url).netloc
    abouts = [urljoin(url, a["href"]).split("#")[0] for a in BeautifulSoup(html, "lxml").select("a[href]")
              if ABOUT.search(a.get_text(" ") + " " + a["href"]) and urlsplit(urljoin(url, a["href"])).netloc == host]
    for page in list(dict.fromkeys(abouts))[:3]:
        sub = fetch(page)
        if not sub:
            continue
        person = [{"name": r["full_name"]}]
        match_photos(sub, page, person)
        if person[0].get("photo_url"):
            return {"photo_url": person[0]["photo_url"], "source_url": page}
    return None


def main() -> None:
    judges_only = "--judges" in sys.argv
    officials = json.loads((ROOT / "site/data/officials.json").read_text(encoding="utf-8"))["officials"]
    missing = [r for r in officials if not r.get("photo_url")]
    judges = [r for r in missing if re.search(r"(?i)judge", r["office_title"]) and circuit_of(r)]
    others = [] if judges_only else [r for r in missing if r not in judges and r.get("official_website")
                                     and r.get("verification_status") != "unconfirmed"]
    print(f"{len(judges)} judges and {len(others)} others without a photo", file=sys.stderr)
    result: dict[str, dict] = {}
    if judges_only and OUT.exists():  # keep what earlier runs found for everyone else
        result = {k: v for k, v in json.loads(OUT.read_text(encoding="utf-8")).items() if not k.startswith("_")}
    by_circuit: dict[int, list[dict]] = {}
    for j in judges:
        by_circuit.setdefault(circuit_of(j), []).append(j)
    with ThreadPoolExecutor(max_workers=8) as pool:
        for found in pool.map(lambda item: find_judges(*item), by_circuit.items()):
            result.update(found)
        print(f"judges: {len(result)} found", file=sys.stderr)
        for r, found in zip(others, pool.map(find_on_site, others)):
            if found:
                result[r["id"]] = found
    # A portrait used for two people is not a portrait.
    counts: dict[str, int] = {}
    for v in result.values():
        counts[v["photo_url"]] = counts.get(v["photo_url"], 0) + 1
    result = {k: v for k, v in sorted(result.items()) if counts[v["photo_url"]] == 1}
    OUT.write_text(json.dumps({"_how_to": "Generated by tools/find_photos.py: portraits from official pages, used only "
                                          "where the collected record has none.", **result}, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(f"Wrote {len(result)} photos to {OUT.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
