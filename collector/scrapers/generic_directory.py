"""Config-driven scraper for county and municipal directories.

Every county and city publishes its officials differently, so these sources
are added one at a time by an administrator, each with CSS selectors for
that site. Example `config` for a data source:

    {
      "row_selector": "table.commission tbody tr",
      "fields": {
        "name": "td:nth-of-type(1)",
        "title": "td:nth-of-type(2)",
        "district": "td:nth-of-type(3)",
        "phone": "td:nth-of-type(4)",
        "email": "a[href^='mailto:']",
        "website": "td:nth-of-type(1) a"
      },
      "default_title": "County Commissioner",
      "title_must_contain": ["Commissioner", "Mayor"],
      "county": "Broward",
      "municipality": null,
      "party": "Nonpartisan",
      "selection_method": "elected",
      "requires_js": false
    }

Only "row_selector", "fields.name" and "county" are required. Use
"selection_method": "appointed" for sources that list appointed officials
such as city managers, so they are labelled correctly.
"""
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from collector.normalize import clean_text
from collector.scrapers.base import BaseScraper


class SourceConfigError(Exception):
    pass


def _field(row: Tag, selector: str | None, base_url: str, kind: str = "text") -> str | None:
    if not selector:
        return None
    node = row.select_one(selector)
    if node is None:
        return None
    href = node.get("href") if node.name == "a" else None
    if kind == "email" and href and href.lower().startswith("mailto:"):
        return href
    if kind == "phone" and href and href.lower().startswith("tel:"):
        return href
    if kind == "url":
        return urljoin(base_url, href) if href else None
    return clean_text(node.get_text(" ")) or None


def parse_generic_directory(html: str, base_url: str, config: dict, government_level: str) -> list[dict]:
    row_selector = config.get("row_selector")
    fields = config.get("fields") or {}
    county = config.get("county")
    if not row_selector or not fields.get("name") or not county:
        raise SourceConfigError("config needs row_selector, fields.name and county")
    municipality = config.get("municipality")
    if government_level == "municipal" and not municipality:
        raise SourceConfigError("a municipal source needs config.municipality")

    must_contain = [t.lower() for t in config.get("title_must_contain") or []]
    soup = BeautifulSoup(html, "lxml")
    records = []
    for row in soup.select(row_selector):
        name = _field(row, fields["name"], base_url)
        if not name:
            continue
        title = _field(row, fields.get("title"), base_url) or config.get("default_title")
        if not title:
            records.append({"name": name, "source_url": base_url, "_error": f"No office title found for {name}"})
            continue
        if must_contain and not any(t in title.lower() for t in must_contain):
            continue
        records.append({
            "name": name,
            "office_title": title,
            "government_level": government_level,
            "selection_method": config.get("selection_method", "unknown"),
            "party": _field(row, fields.get("party"), base_url) or config.get("party"),
            "district": _field(row, fields.get("district"), base_url),
            "jurisdiction": municipality or f"{county} County",
            "county": county,
            "municipality": municipality,
            "phone": _field(row, fields.get("phone"), base_url, "phone"),
            "email": _field(row, fields.get("email"), base_url, "email"),
            "official_website": _field(row, fields.get("website"), base_url, "url"),
            "source_url": base_url,
        })
    return records


class GenericDirectoryScraper(BaseScraper):
    government_level = "county"

    def collect(self) -> list[dict]:
        return self.fetch_and_parse(
            self.source_url,
            lambda html: parse_generic_directory(html, self.source_url, self.config, self.government_level),
        )


class CountyDirectoryScraper(GenericDirectoryScraper):
    government_level = "county"


class MunicipalDirectoryScraper(GenericDirectoryScraper):
    government_level = "municipal"
