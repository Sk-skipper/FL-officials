"""A county Supervisor of Elections' "Elected Officials" page: who holds each county office.

Every Supervisor of Elections lists the people on its county's ballot, but each site has its own layout. They
share one anchor: an office holder's name is followed by their party, "Chip Simmons (Republican)", "Gwen Marshall
(DEM)". This scraper finds those names and takes the office from the nearest office title above them:

    Sheriff                       County Commissioner, District 3
    Chip Simmons (Republican)     Jane Doe (R)

Only county offices are kept: the commission, constitutional officers, school board and superintendent. Federal
and state offices, judges and city offices come from other sources. Config: {"county": "Leon"}. A page that yields
fewer than "min_records" (default 4) county officials fails, so a redesigned page is noticed, not half-read.
"""
import re

from collector.normalize import clean_text
from collector.scrapers.base import BaseScraper, FetchError
from collector.scrapers.city_roster import NAME, _clean_name, page_lines

PARTY = (r"Republican|Republican Party|Democrat(?:ic)?|Democratic Party|REP|DEM|NPA|No Party Affiliation|Nonpartisan|"
         r"Non-?Partisan|NOP|NON|Independent|IND|Libertarian|LPF|R|D|I")
_HOLDER = re.compile(rf"^(?:(?:Commissioner|Sheriff|Honorable|Hon\.|Dr\.|Mr\.|Mrs\.|Ms\.)\s+)?(?P<name>{NAME})\s*[,-]?\s*\(\s*(?P<party>{PARTY})\s*\)", re.I)
_PARTY_ONLY = re.compile(rf"^\(\s*(?:{PARTY})\s*\)$", re.I)
_INLINE = re.compile(rf"^(?P<office>[A-Z][^:]{{3,80}}?)\s*[:–—-]\s+(?P<rest>{NAME}\s*\(\s*(?:{PARTY})\s*\).*)$")
_PARTY_NAME = {"r": "Republican", "rep": "Republican", "republican": "Republican", "republican party": "Republican",
               "d": "Democratic", "dem": "Democratic", "democrat": "Democratic", "democratic": "Democratic",
               "democratic party": "Democratic", "npa": "No Party Affiliation", "no party affiliation": "No Party Affiliation",
               "i": "Independent", "ind": "Independent", "independent": "Independent", "lpf": "Libertarian",
               "libertarian": "Libertarian"}
_DISTRICT = re.compile(r"\b(?:District|Dist\.?|Seat|Group)\s*#?\s*(\d{1,2})\b", re.I)


def office_for(label: str, county: str) -> dict | None:
    """Map an office title as printed to a record's office fields, or None for offices handled elsewhere."""
    t = clean_text(label)
    low = t.lower()
    if re.search(r"\b(u\.?s\.?|united states|congress|state senat|state rep|house of rep|governor|attorney general|"
                 r"chief financial|agriculture|judge|justice|court of appeal|city|town|village|municipal|mayor of|"
                 r"council(?!.*county)|soil|water|hospital|mosquito|fire|port|drainage|improvement|community development|"
                 r"supervisor of elections|state attorney|public defender)\b", low):
        return None
    district = (m.group(1) if (m := _DISTRICT.search(t)) else None)
    base = {"government_level": "county", "county": county, "jurisdiction": f"{county} County"}
    if re.search(r"county commission|board of county commissioners|^commissioner\b|county council", low):
        title = "County Council Member" if "council" in low else "County Commissioner"
        return {**base, "office_title": title, "district": district}
    if re.search(r"school board", low):
        return {**base, "office_title": "School Board Member", "jurisdiction": f"{county} County Public Schools",
                "district": district, "seat_label": f"District {district}" if district else None}
    if "superintendent" in low:
        return {**base, "office_title": "Superintendent of Schools", "jurisdiction": f"{county} County Public Schools"}
    if re.match(r"^(county )?sheriff\b", low):
        return {**base, "office_title": "Sheriff"}
    if "property appraiser" in low:
        return {**base, "office_title": "Property Appraiser"}
    if "tax collector" in low:
        return {**base, "office_title": "Tax Collector"}
    if re.search(r"clerk of (the )?(circuit )?courts?|clerk & comptroller|clerk and comptroller", low):
        return {**base, "office_title": "Clerk of the Circuit Court"}
    if re.search(r"county mayor|^mayor$", low):
        return {**base, "office_title": "County Mayor"}
    return None


def _is_label(line: str) -> bool:
    return len(line) <= 90 and not _HOLDER.match(line) and bool(re.search(
        r"commission|school board|superintendent|sheriff|appraiser|tax collector|clerk|mayor|council|judge|senat|"
        r"represent|governor|attorney|defender|supervisor|congress|district|seat|group", line, re.I))


def parse_officeholders(html: str, source_url: str, county: str, min_records: int = 4) -> list[dict]:
    raw = page_lines(html, url=source_url)
    # "Kathleen Smith" / "(Republican)" on two lines reads as one.
    lines = []
    for line in raw:
        if lines and _PARTY_ONLY.match(line) and not _HOLDER.match(lines[-1]):
            lines[-1] = f"{lines[-1]} {line}"
        else:
            lines.append(line)
    records, seen = [], set()
    for i, line in enumerate(lines):
        label, holder_text = None, line
        if (m := _INLINE.match(line)) and _is_label(m["office"]):
            label, holder_text = m["office"], m["rest"]
        h = _HOLDER.match(holder_text)
        if not h:
            continue
        if label is None:
            # Nearest office title above: the line just before, or a heading a few lines up ("Sheriff" / "Website").
            at = next((j for j in range(i - 1, max(i - 5, -1), -1) if _is_label(lines[j])), None)
            label = lines[at] if at is not None else None
            # A bare "District 3" line under a heading such as "County Commission": read them together.
            if label and _DISTRICT.fullmatch(label.strip()) and at > 0 and _is_label(lines[at - 1]):
                label = f"{lines[at - 1]} {label}"
        if not label:
            continue
        office = office_for(label, county)
        name = _clean_name(h["name"], strict=False)
        if not office or not name:
            continue
        key = (office["office_title"], office.get("district"), name.lower())
        if key in seen:
            continue
        seen.add(key)
        party = _PARTY_NAME.get(h["party"].lower(), "Nonpartisan" if "partisan" in h["party"].lower() or h["party"].upper() in ("NOP", "NON") else None)
        if office["office_title"] in ("School Board Member", "Superintendent of Schools") and party is None:
            party = "Nonpartisan"
        records.append({"name": name, "party": party, "selection_method": "elected", "source_url": source_url, **office})
    if len(records) < min_records:
        raise FetchError(f"Only {len(records)} county officials were recognised on the page (expected at least {min_records}); "
                         "the page may have changed or may load its list with JavaScript.")
    return records


class SOEOfficeHoldersScraper(BaseScraper):
    def collect(self) -> list[dict]:
        return parse_officeholders(self.client.get(self.source_url), self.source_url, self.config["county"],
                                   int(self.config.get("min_records") or 4))
