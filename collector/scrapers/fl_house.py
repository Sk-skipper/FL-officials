"""Florida House roster: https://www.flhouse.gov/Representatives"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from collector.normalize import clean_text
from collector.scrapers.base import BaseScraper

_MEMBER_HREF = re.compile(r"MemberId=(\d+)", re.I)
_DISTRICT = re.compile(r"District:?\s*(\d{1,3})", re.I)
_PARTY = re.compile(r"\b(Republican|Democratic|Democrat|No Party Affiliation|NPA|Independent)\b|\((R|D)\)", re.I)
_HEADING = ["h1", "h2", "h3", "h4", "h5", "h6", "strong", "b"]
_NOT_A_PORTRAIT = re.compile(r"logo|icon|placeholder|spacer|blank|pixel|default|no[-_]?(photo|image)", re.I)


def _member_ids(node: Tag) -> set[str]:
    return {m.group(1) for a in node.find_all("a", href=_MEMBER_HREF) if (m := _MEMBER_HREF.search(a["href"]))}


def _card_for(link: Tag) -> Tag | None:
    """Smallest ancestor that mentions a district and belongs to one member only."""
    node: Tag | None = link
    for _ in range(6):
        if node is None:
            return None
        if len(_member_ids(node)) > 1:
            return None  # climbed into a container shared by several members
        if _DISTRICT.search(node.get_text(" ")):
            return node
        node = node.parent if isinstance(node.parent, Tag) else None
    return None


def _name_from(card: Tag, link: Tag) -> str:
    for tag in card.find_all(_HEADING):
        text = clean_text(tag.get_text(" "))
        if text and not _DISTRICT.search(text) and not _PARTY.fullmatch(text) and re.search(r"[A-Za-z]{2}", text):
            return text
    return clean_text(link.get_text(" "))


def _photo_from(card: Tag, base_url: str) -> str | None:
    """The member's portrait: the first image in the card that is not an icon or placeholder."""
    for img in card.find_all("img"):
        src = (img.get("src") or img.get("data-src") or "").strip()
        if src and not src.startswith("data:") and not _NOT_A_PORTRAIT.search(src):
            return urljoin(base_url, src)
    return None


def parse_fl_house(html: str, base_url: str) -> list[dict]:
    """Each member is a card containing a link with MemberId=<n>, a name,
    a party and a district number."""
    soup = BeautifulSoup(html, "lxml")
    records: dict[str, dict] = {}
    for link in soup.find_all("a", href=_MEMBER_HREF):
        member_id = _MEMBER_HREF.search(link["href"]).group(1)
        if member_id in records:
            continue
        card = _card_for(link)
        if card is None:
            continue
        text = clean_text(card.get_text(" "))
        name = _name_from(card, link)
        if not name or "vacant" in name.lower():
            continue
        party_match = _PARTY.search(text)
        records[member_id] = {
            "name": name,
            "office_title": "State Representative",
            "government_level": "state",
            "selection_method": "elected",
            "party": (party_match.group(1) or party_match.group(2)) if party_match else None,
            "district": _DISTRICT.search(text).group(1),
            "jurisdiction": "Florida",
            "official_website": urljoin(base_url, link["href"]),
            "photo_url": _photo_from(card, base_url),
            "source_url": base_url,
        }
    return list(records.values())


class FLHouseScraper(BaseScraper):
    def collect(self) -> list[dict]:
        return self.fetch_and_parse(self.source_url, lambda html: parse_fl_house(html, self.source_url))
