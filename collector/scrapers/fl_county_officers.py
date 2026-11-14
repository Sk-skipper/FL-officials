"""Statewide rosters of county officials, published by the associations every county's officers belong to.

  * Florida Sheriffs Association, "Sheriff Directory": all 67 sheriffs, with portraits.
  * Florida Clerks of Court Operations Corporation (a state-created body all 67 clerks belong to): every clerk.
  * Florida Association of Counties directory, "Commissioners/Council Members/Mayors": county commissioners.

Associations update their lists after elections, sometimes months later. The counties directory in particular
keeps some former commissioners, so a county is only published when its list matches a real board size (see
hold_back_stale_counties). These sources are used only for counties
without a more direct source: counties listed in config "skip_counties" (Broward and Miami-Dade, whose Supervisors
of Elections publish every office) are left out.
"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from collector.geo import canonical_county
from collector.normalize import clean_text
from collector.scrapers.base import BaseScraper, FetchError

_SUFFIX = re.compile(r",?\s*\b(Esq|CPA|CFA|MBA|Ph\.?D|CFE|CGFO|CPM|CCF)\.?$", re.I)


def _person(raw: str) -> str:
    name = clean_text(raw)
    while _SUFFIX.search(name):
        name = _SUFFIX.sub("", name).strip(" ,")
    if name.isupper() or sum(c.isupper() for c in name) > 0.7 * sum(c.isalpha() for c in name):
        name = re.sub(r"\b([A-Za-z])([A-Za-z']*)", lambda m: m.group(1).upper() + m.group(2).lower(), name)
        name = re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), name)
        name = re.sub(r"\b(Ii|Iii|Iv)\b", lambda m: m.group(1).upper(), name)
    return name


def _county(raw: str) -> str | None:
    return canonical_county(re.sub(r"\s+County\b.*$", "", clean_text(raw), flags=re.I))


def parse_sheriffs(html: str, source_url: str, skip: set[str]) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    records = []
    for card in soup.select("a.card\\:post"):
        heading = card.select_one(".card\\:post\\:\\:heading")
        role = card.select_one(".card\\:post\\:\\:role")
        if not heading or not role:
            continue
        county = _county(role.get_text())
        name = re.sub(r"^Sheriff\s+", "", clean_text(heading.get_text()))
        if not county:
            records.append({"name": name, "source_url": source_url, "_error": f"Unknown county '{role.get_text(strip=True)}'"})
            continue
        if county in skip:
            continue
        img = card.select_one("img[src]")
        records.append({
            "name": re.sub(r"^Dr\.?\s+", "", name), "office_title": "Sheriff", "government_level": "county",
            "jurisdiction": f"{county} County", "county": county, "selection_method": "elected",
            "photo_url": img["src"] if img else None, "official_website": card.get("href"), "source_url": source_url,
        })
    return records


_CLERK = re.compile(r"^(?P<county>.+?) County Clerk of (?:the )?Courts?\b.*?\s[-–—]\s+(?P<name>.+)$", re.I)


def parse_clerks(html: str, source_url: str, skip: set[str]) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    records = []
    for link in soup.select("a[href]"):
        m = _CLERK.match(clean_text(link.get_text(" ")))
        if not m:
            continue
        county = canonical_county(m["county"])
        if not county or county in skip:
            continue
        records.append({
            "name": _person(m["name"]), "office_title": "Clerk of the Circuit Court", "government_level": "county",
            "jurisdiction": f"{county} County", "county": county, "selection_method": "elected",
            "official_website": urljoin(source_url, link["href"]), "source_url": source_url,
        })
    return records


FAC_TITLES = {"commissioner": "County Commissioner", "council member": "County Council Member",
              "councilmember": "County Council Member", "mayor": "County Mayor", "chair": "County Commissioner",
              "vice chair": "County Commissioner", "chairman": "County Commissioner"}


def parse_fac(html: str, source_url: str, skip: set[str]) -> tuple[list[dict], list[str]]:
    """One page of the directory. Returns the records and the links to further pages."""
    soup = BeautifulSoup(html, "lxml")
    records = []
    for box in soup.select(".dirResultsBox"):
        name_el, pos_el, addr_el = (box.select_one(c) for c in (".dirEntryName", ".dirEntryPosition", ".dirEntryAddress"))
        if not name_el or not addr_el:
            continue
        raw = clean_text(name_el.get_text(" "))
        last, _, first = raw.partition(",")
        name = _person(f"{first} {last}" if first else raw)
        county = _county(addr_el.get_text("|").split("|")[0])
        position = clean_text(pos_el.get_text(" ")).lower() if pos_el else ""
        title = FAC_TITLES.get(position)
        if not county or county in skip or not title:
            continue  # municipal members of the association, staff, or a county with its own source
        img = box.select_one("img[src]")
        email = box.select_one("a[href^='mailto:']")
        phone = box.select_one(".dirPhone")
        records.append({
            "name": name, "office_title": title, "government_level": "county", "jurisdiction": f"{county} County",
            "county": county, "selection_method": "elected", "source_url": source_url,
            "photo_url": img["src"] if img else None, "email": email["href"] if email else None,
            "phone": clean_text(phone.get_text()) if phone else None,
            "seat_label": "Chair" if position in ("chair", "chairman") else "Vice Chair" if position == "vice chair" else None,
        })
    pages = sorted({urljoin(source_url, a["href"]) for a in soup.select("a[href*='cpage=']")})
    return records, pages


class _Base(BaseScraper):
    @property
    def skip(self) -> set[str]:
        return set(self.config.get("skip_counties") or [])


class SheriffsScraper(_Base):
    def collect(self) -> list[dict]:
        return parse_sheriffs(self.client.get(self.source_url), self.source_url, self.skip)


class ClerksScraper(_Base):
    def collect(self) -> list[dict]:
        return parse_clerks(self.client.get(self.source_url), self.source_url, self.skip)


def hold_back_stale_counties(records: list[dict], sizes: set[int]) -> list[dict]:
    """The directory keeps some former members. A county whose list doesn't match a real board size (5 or 7
    commissioners) is held back, with a row for the report, rather than published with someone who has left."""
    by_county: dict[str, list[dict]] = {}
    for r in records:
        by_county.setdefault(r["county"], []).append(r)
    out = []
    for county, people in sorted(by_county.items()):
        members = [r for r in people if r["office_title"] != "County Mayor"]
        if len(members) in sizes:
            out += people
        else:
            out.append({"name": f"{county} County", "source_url": people[0]["source_url"],
                        "_error": f"{county} County: the directory lists {len(members)} commissioners, which matches no board "
                                  f"size ({', '.join(map(str, sorted(sizes)))}); it probably still lists former members, so "
                                  "this county was held back"})
    return out


class FACScraper(_Base):
    def collect(self) -> list[dict]:
        return hold_back_stale_counties(self._all(), set(self.config.get("board_sizes") or [5, 7]))

    def _all(self) -> list[dict]:
        records, pages = parse_fac(self.client.get(self.source_url), self.source_url, self.skip)
        seen = {self.source_url}
        queue = [p for p in pages if p not in seen]
        while queue:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            if len(seen) > 60:
                raise FetchError("The directory has more pages than expected; check the source before collecting it.")
            more, links = parse_fac(self.client.get(url), self.source_url, self.skip)
            records += more
            queue += [p for p in links if p not in seen]
        return records
