"""U.S. Senate. The Senate publishes a machine-readable contact list, which is
more reliable than scraping the HTML at https://www.senate.gov/senators/."""
from bs4 import BeautifulSoup

from collector.normalize import clean_text
from collector.scrapers.base import BaseScraper

DEFAULT_DATA_URL = "https://www.senate.gov/general/contact_information/senators_cfm.xml"


def _text(member, tag: str) -> str:
    node = member.find(tag)
    return clean_text(node.get_text()) if node else ""


def parse_us_senate(xml: str, data_url: str, state: str = "FL") -> list[dict]:
    soup = BeautifulSoup(xml, "xml")
    records = []
    for member in soup.find_all("member"):
        if _text(member, "state").upper() != state:
            continue
        first, last = _text(member, "first_name"), _text(member, "last_name")
        if not first or not last:
            continue
        records.append({
            "name": f"{last}, {first}",
            "office_title": "U.S. Senator",
            "government_level": "federal",
            "selection_method": "elected",
            "party": _text(member, "party"),
            "jurisdiction": "Florida",
            "statewide": True,
            "phone": _text(member, "phone"),
            # <email> holds a contact-form URL for most senators; the validator
            # keeps it only if it is a real address.
            "email": _text(member, "email"),
            "official_website": _text(member, "website"),
            "source_url": data_url,
        })
    return records


class USSenateScraper(BaseScraper):
    def collect(self) -> list[dict]:
        url = self.config.get("data_url") or DEFAULT_DATA_URL
        return parse_us_senate(self.client.get(url), url)
