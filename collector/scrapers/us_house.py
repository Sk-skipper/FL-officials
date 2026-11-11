"""U.S. House directory: https://www.house.gov/representatives"""
import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from collector.normalize import clean_text
from collector.scrapers.base import BaseScraper
from collector.scrapers.congress import add_house_photos, fetch_legislators

logger = logging.getLogger(__name__)

_DEFAULT_COLUMNS = ["district", "name", "party", "office room", "phone", "committee assignment"]


def parse_us_house(html: str, base_url: str, state: str = "Florida") -> list[dict]:
    """The by-state view has one table per state, captioned with the state name."""
    soup = BeautifulSoup(html, "lxml")
    records = []
    for table in soup.find_all("table"):
        caption = table.find("caption")
        if caption is None or clean_text(caption.get_text(" ")).lower() != state.lower():
            continue
        headers = [clean_text(th.get_text(" ")).lower() for th in table.select("thead th")]
        columns = headers if "name" in headers and "district" in headers else _DEFAULT_COLUMNS
        for row in table.select("tbody tr") or table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 3:
                continue
            values = {col: cells[i] for i, col in enumerate(columns) if i < len(cells)}
            name_cell = values.get("name")
            name = clean_text(name_cell.get_text(" ")) if name_cell else ""
            if not name or "vacan" in name.lower():
                continue
            link = name_cell.find("a", href=True)
            records.append({
                "name": name,
                "office_title": "U.S. Representative",
                "government_level": "federal",
                "selection_method": "elected",
                "party": clean_text(values["party"].get_text(" ")) if "party" in values else None,
                "district": clean_text(values["district"].get_text(" ")) if "district" in values else None,
                "jurisdiction": "Florida",
                "phone": clean_text(values["phone"].get_text(" ")) if "phone" in values else None,
                "official_website": urljoin(base_url, link["href"]) if link else None,
                "source_url": base_url,
            })
    return records


class USHouseScraper(BaseScraper):
    def collect(self) -> list[dict]:
        records = self.fetch_and_parse(self.source_url, lambda html: parse_us_house(html, self.source_url))
        try:
            add_house_photos(records, fetch_legislators(self.client))
        except Exception as exc:  # photos are a bonus: never lose the directory because they failed
            logger.warning("Could not add U.S. House photos (%s: %s)", type(exc).__name__, exc)
        return records
