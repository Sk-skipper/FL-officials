"""A council listed in a CivicPlus site's staff directory (/Directory.aspx?did=N).

About a third of Florida's city websites run on CivicPlus, whose staff directory lists each department's people as a
name line followed by a role line:

    Teresa Watkins Brown          Karen Chasez
    Ward 1 - Councilperson        Mayor - Seat 5 Term: 01/01/2023 to 12/31/2026

The role gives the title (Mayor, Vice Mayor, Deputy Mayor, otherwise the council's member title) and the seat
(Seat/District/Ward/Group N). Config: {"county", "municipality", "member_title", "seats"}; as with city_roster, a
page that yields more than two people fewer or more than "seats" fails instead of publishing a partial council.
"""
import re

from collector.scrapers.base import BaseScraper, FetchError
from collector.scrapers.city_roster import find_board, match_photos, page_lines

ROLE = (r"(?i)^(?:(?:ward|district|seat|group|at[- ]large)\s*\w*\s*[-–:,]\s*)?(?:mayor|vice[- ]mayor|deputy mayor|mayor pro tem|"
        r"council\s*(?:man|woman|women|member|person|president|chair)?|councilor|commissioner|city commissioner|alderman|chair)")
NOT_A_PERSON = re.compile(r"(?i)privacy|notice|vacant|unfilled|^un\b|department|directory|council|commission")
SEAT = re.compile(r"(?i)\b(seat|district|ward|group)\s*(?:no\.?|number|#)?\s*([0-9]+|[IVX]+|one|two|three|four|five|six|seven)\b")
WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}
ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7}


def title_of(role: str, member_title: str) -> str:
    r = role.lower()
    if re.search(r"vice[- ]?mayor", r):
        return "Vice Mayor"
    if "deputy mayor" in r:
        return "Deputy Mayor"
    if re.search(r"\bmayor\b", r) and not re.search(r"pro[- ]?tem", r):
        return "Mayor"
    return member_title


def seat_of(role: str) -> tuple[str | None, str | None]:
    m = SEAT.search(role)
    if not m:
        return None, None
    raw = m.group(2)
    number = WORDS.get(raw.lower()) or ROMAN.get(raw.upper()) or (int(raw) if raw.isdigit() else None)
    return (str(number), f"{m.group(1).title()} {number}") if number else (None, None)


def parse_directory(html: str, url: str, config: dict) -> list[dict]:
    member_title = config.get("member_title") or "Council Member"
    people = [m for m in find_board(page_lines(html, None, url), ROLE, member_title) if not NOT_A_PERSON.search(m["name"])]
    seats = int(config.get("seats") or 5)
    if not seats - 2 <= len(people) <= seats + 2:
        raise FetchError(f"Expected about {seats} council members in the directory but found {len(people)}.")
    match_photos(html, url, people)
    out = []
    for p in people:
        role = p.get("role") or ""
        district, label = seat_of(role)
        out.append({"name": p["name"], "office_title": title_of(role, member_title), "government_level": "municipal",
                    "selection_method": "elected", "party": "Nonpartisan", "jurisdiction": config["municipality"],
                    "municipality": config["municipality"], "county": config["county"], "district": district,
                    "seat_label": label, "photo_url": p.get("photo_url"), "source_url": url})
    return out


class CivicPlusDirectoryScraper(BaseScraper):
    def collect(self) -> list[dict]:
        return parse_directory(self.client.get(self.source_url), self.source_url, self.config)
