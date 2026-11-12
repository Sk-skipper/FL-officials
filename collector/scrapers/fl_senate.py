"""Florida Senate roster: https://www.flsenate.gov/Senators"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from collector.geo import parse_county_list
from collector.normalize import clean_text
from collector.scrapers.base import BaseScraper

# "/Senators/S12" or, since the 2026 term, "/Senators/2026-2028/S12".
_MEMBER_HREF = re.compile(r"/Senators/(?:\d{4}-\d{4}/)?[Ss](\d{1,2})(?:[/?#]|$)")
_NOT_A_PORTRAIT = re.compile(r"nophoto|placeholder|logo|icon", re.I)
_PARTY_CELL = re.compile(r"^\(?(R|D|NPA|I|Republican|Democrat|Democratic|Independent|No Party Affiliation)\)?$", re.I)


def parse_fl_senate(html: str, base_url: str) -> list[dict]:
    """Each senator is a table row whose name links to /Senators/S<district>."""
    soup = BeautifulSoup(html, "lxml")
    records: dict[str, dict] = {}
    for link in soup.find_all("a", href=_MEMBER_HREF):
        row = link.find_parent("tr")
        name = clean_text(link.get_text(" "))
        if row is None or not name or "vacant" in name.lower():
            continue
        district = _MEMBER_HREF.search(link["href"]).group(1)
        if district in records:
            continue

        party = None
        counties: list[str] = []
        for cell in row.find_all(["td", "th"]):
            if link in cell.descendants:
                continue
            text = clean_text(cell.get_text(" "))
            if not text or text.isdigit():
                continue
            if _PARTY_CELL.match(text):
                party = text
            else:
                found = parse_county_list(text)
                if len(found) > len(counties):
                    counties = found

        photo = None
        for img in row.find_all("img"):
            src = (img.get("src") or "").strip()
            if src and not src.startswith("data:") and not _NOT_A_PORTRAIT.search(src):
                photo = urljoin(base_url, src)
                break

        records[district] = {
            "name": name,
            "office_title": "State Senator",
            "government_level": "state",
            "selection_method": "elected",
            "party": party,
            "district": district,
            "jurisdiction": "Florida",
            "counties": counties,
            "official_website": urljoin(base_url, link["href"]),
            "photo_url": photo,
            "source_url": base_url,
        }
    return list(records.values())


class FLSenateScraper(BaseScraper):
    def collect(self) -> list[dict]:
        return self.fetch_and_parse(self.source_url, lambda html: parse_fl_senate(html, self.source_url))
