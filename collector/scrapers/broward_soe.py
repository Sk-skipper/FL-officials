"""Broward County Supervisor of Elections, "Elected Officials": one table of every office on a Broward ballot.

Used for the offices no other source covers: the state executives, Florida Supreme Court, Fourth District
Court of Appeal, the circuit and county judges, the State Attorney, the Public Defender and the county's
constitutional officers. Offices with their own, richer source are skipped (Congress, the Legislature,
the Supervisors of Elections, and the County Commission and School Board districts from Broward GIS).
"""
import re

from bs4 import BeautifulSoup, Tag

from collector.normalize import clean_text
from collector.scrapers.base import BaseScraper

FOURTH_DCA_COUNTIES = ["Broward", "Indian River", "Martin", "Okeechobee", "Palm Beach", "St. Lucie"]
CIRCUIT = "17th Judicial Circuit (Broward County)"
COUNTY = "Broward County"
SKIP = ("President", "Vice President", "US Senate", "US Congress", "State Senate", "State House",
        "Supervisor of Elections", "School Board")
STATEWIDE = {
    "Governor": "Governor", "Lieutenant Governor": "Lieutenant Governor", "Attorney General": "Attorney General",
    "Chief Financial Officer": "Chief Financial Officer",
    "Commissioner of Agriculture & Consumer Services": "Commissioner of Agriculture",
}
COUNTY_OFFICES = {"Sheriff", "Property Appraiser", "Tax Collector", "Clerk of the Circuit Court"}
_PARTY = re.compile(r"\((DEM|REP|NPA|IND|LPF|GRE|[A-Z]{3})\)")
_PHONE = re.compile(r"(\(?\d{3}\)?[\s.-]*\d{3}[\s.-]*\d{4})")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December"]


def _cell(row: Tag, cls: str) -> list[str]:
    cell = row.select_one(f"td.{cls}")
    if cell is None:
        return []
    for label in cell.select(".tablesaw-cell-label"):
        label.decompose()
    return [t for t in (clean_text(s) for s in cell.stripped_strings) if t]


def _next_election(status: list[str]) -> str | None:
    for line in status:
        m = re.search(r"Next Election:\s*(\d{1,2})/+(\d{4})", line)
        if m and 1 <= int(m.group(1)) <= 12:
            return f"{_MONTHS[int(m.group(1)) - 1]} {m.group(2)}"
    return None


def _office(name: str, district_text: str = "") -> dict | None:
    if name.startswith(SKIP) or name in SKIP:
        return None
    if name == "County Commission":
        # Broward GIS has the same seats with photos; this row adds the party, which GIS doesn't publish.
        m = re.search(r"DIST(?:RICT)?\s*(\d+)", district_text, re.I)
        return {"office_title": "County Commissioner", "government_level": "county", "jurisdiction": "Broward County",
                "district": m.group(1) if m else None, "county": "Broward"}
    if name in STATEWIDE:
        return {"office_title": STATEWIDE[name], "government_level": "state", "jurisdiction": "Florida", "statewide": True}
    if name == "Florida Supreme Court Chief Justice":
        return {"office_title": "Chief Justice of the Florida Supreme Court", "government_level": "state",
                "jurisdiction": "Florida", "statewide": True, "party": "Nonpartisan"}
    if name == "Florida Supreme Court Justice":
        return {"office_title": "Justice of the Florida Supreme Court", "government_level": "state",
                "jurisdiction": "Florida", "statewide": True, "party": "Nonpartisan"}
    if name.startswith("4th District Court of Appeal"):
        title = "Chief Judge" if "Chief" in name else "Judge"
        return {"office_title": f"{title}, Fourth District Court of Appeal", "government_level": "state",
                "jurisdiction": "Fourth District Court of Appeal", "counties": FOURTH_DCA_COUNTIES, "party": "Nonpartisan"}
    m = re.match(r"17th Judicial Circuit Judge Group (\d+)$", name)
    if m:
        return {"office_title": "Circuit Judge", "government_level": "county", "jurisdiction": CIRCUIT,
                "district": m.group(1), "seat_label": f"Group {m.group(1)}", "party": "Nonpartisan", "county": "Broward"}
    m = re.match(r"County Court Judge Group (\d+)$", name)
    if m:
        return {"office_title": "County Court Judge", "government_level": "county", "jurisdiction": "Broward County Court",
                "district": m.group(1), "seat_label": f"Group {m.group(1)}", "party": "Nonpartisan", "county": "Broward"}
    if name in ("State Attorney", "Public Defender"):
        return {"office_title": name, "government_level": "county", "jurisdiction": CIRCUIT, "county": "Broward"}
    if name in COUNTY_OFFICES:
        return {"office_title": name, "government_level": "county", "jurisdiction": COUNTY, "county": "Broward"}
    return {"_unknown": name}


def parse_broward_soe(html: str, source_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    records = []
    for row in soup.select("tr.ResultRow"):
        office_name = " ".join(_cell(row, "OfficeName"))
        office = _office(office_name, " ".join(_cell(row, "District")))
        if office is None:
            continue
        if "_unknown" in office:
            records.append({"name": office_name, "source_url": source_url,
                            "_error": f"Unrecognised office '{office_name}'; add it to collector/scrapers/broward_soe.py"})
            continue
        holder = [t for t in _cell(row, "OfficeHolder")]
        party = next((m.group(1) for t in holder if (m := _PARTY.search(t))), None)
        name = " ".join(t for t in holder if not _PARTY.fullmatch(t.strip()))
        name = re.sub(r"\b([A-Z]\.)(?=[A-Z][a-z])", r"\1 ", name)  # "Jeffrey R.Levenson"
        if not name or re.fullmatch(r"(?i)vacant|to be determined|tbd", name):
            continue  # an empty seat; data/vacancies.json lists those
        link = row.select_one("td.OfficeHolder a[href]")
        contact = _cell(row, "ContactInformation")
        phone = next((m.group(1) for t in contact if not t.lower().startswith("fax") and (m := _PHONE.search(t))), None)
        email = next((m.group(0) for t in contact if (m := _EMAIL.search(t))), None)
        status = _cell(row, "HolderStatus")
        appointed = any(t.strip().lower() == "appointed" for t in status)
        bio = {}
        if (when := _next_election(status)):
            bio["next_election"] = when
        records.append({
            "name": name, "party": party, **office,
            "selection_method": "appointed" if appointed else "elected",
            "official_website": link["href"] if link else None,
            "phone": phone, "email": email, "source_url": source_url, "bio": bio or None,
        })
    return records


class BrowardSOEScraper(BaseScraper):
    def collect(self) -> list[dict]:
        return parse_broward_soe(self.client.get(self.source_url), self.source_url)
