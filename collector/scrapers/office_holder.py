"""A one-person office's own website: who holds it (tax collector, property appraiser, superintendent...).

These offices' homepages name the holder next to the title: "Tax Collector Jane Doe", "Jane Doe, CFC, Tax
Collector", "Superintendent Dr. John Smith". This reads the homepage, and if the name isn't there, one linked
"About" / "Meet the..." page on the same site. The name mentioned most often wins.

    "config": {"county": "Lake", "office_title": "Tax Collector", "label": "Tax Collector"}

"label" is the wording to look for (a regular expression; defaults to office_title). Optional "jurisdiction"
(defaults to "<county> County") and "government_level" (defaults to county). A page with no name next to the title
fails, so a redesign is noticed rather than read wrongly.
"""
import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from collector.scrapers.base import BaseScraper, FetchError
from collector.scrapers.city_roster import NAME, _clean_name, page_lines

# Words that show a match is a phrase ("Welcome to the County Tax Collector"), not a person's name.
NOT_A_PERSON = re.compile(
    r"(?i)\b(county|counties|welcome|the|official|about|get|services?|offices?|news|announces?|watch|video|learn|more|"
    r"meet|your|our|please|awards?|earns|outage|stop|employment|deputy|centers?|website|florida|state|tax|collector|"
    r"property|appraiser|home|contact|online|pay|renew|department|schools?|district|public|superintendent|board|"
    r"purple|heart|veterans?|elections?|clerk|sheriff|message|from|letter|former|president|planning|session|region|"
    r"instructional|committee|search|interim|chief|assistant)\b")
ABOUT = re.compile(r"(?i)about|meet|biograph|\bbio\b|leadership|office of the")
CREDENTIALS = r"(?:CFC|CFA|AAS|CCF|Ed\.?\s?D\.?|Ph\.?\s?D\.?|J\.?D\.?|MBA|M\.?Ed\.?)"


def find_holder(lines: list[str], label: str) -> dict[str, int]:
    """Names written next to the office label, with how often each appears."""
    before = re.compile(rf"(?:{label})\s*[,:–—-]?\s+(?:Honorable\s+|Dr\.\s+)?(?P<n>{NAME})")
    after = re.compile(rf"(?:Dr\.\s+)?(?P<n>{NAME})\s*(?:,?\s*{CREDENTIALS})*\s*[,–—-]?\s*(?:Your\s+)?(?:[A-Z][a-z.]+\s+)*?(?:County\s+)?(?:{label})\b")
    votes: dict[str, int] = {}
    for line in lines:
        for pattern in (before, after):
            for m in pattern.finditer(line):
                name = _clean_name(m["n"], strict=False)
                if name and not NOT_A_PERSON.search(name) and 2 <= len(name.split()) <= 4:
                    votes[name] = votes.get(name, 0) + 1
    return votes


def pick(votes: dict[str, int]) -> str | None:
    return max(votes, key=lambda n: (votes[n], len(n))) if votes else None


class OfficeHolderScraper(BaseScraper):
    def collect(self) -> list[dict]:
        cfg = self.config
        label = cfg.get("label") or re.escape(cfg["office_title"])
        home = self.client.get(self.source_url)
        votes, where = find_holder(page_lines(home, None, self.source_url), label), self.source_url
        if not votes:
            host = urlsplit(self.source_url).netloc
            for a in BeautifulSoup(home, "lxml").select("a[href]"):
                href = urljoin(self.source_url, a["href"]).split("#")[0]
                if urlsplit(href).netloc != host or not ABOUT.search(f"{a.get_text(' ')} {href}"):
                    continue
                try:
                    votes = find_holder(page_lines(self.client.get(href), None, href), label)
                except FetchError:
                    continue
                if votes:
                    where = href
                    break
        name = pick(votes)
        if not name:
            raise FetchError(f"No name was found next to '{cfg['office_title']}' on the homepage or its About page; "
                             "the site may have changed.")
        county = cfg["county"]
        return [{"name": name, "office_title": cfg["office_title"], "government_level": cfg.get("government_level") or "county",
                 "selection_method": "elected", "county": county, "jurisdiction": cfg.get("jurisdiction") or f"{county} County",
                 "official_website": self.source_url, "source_url": where,
                 **({"party": "Nonpartisan"} if cfg.get("nonpartisan") else {})}]
