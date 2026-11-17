"""Circuit judges statewide, from the Florida Division of Elections' candidate download.

The Division publishes every judicial candidate for each election as a tab-delimited file
(https://dos.elections.myflorida.com/candidates/downloadcanlist.asp), with the circuit ("Juris1num"), the seat
("Juris2num", the group) and the outcome ("Elected", "Retained", or "Unopposed" for a candidate elected without
opposition). Circuit judges serve six-year terms, so the last three general elections cover every seat; for each
seat the most recent winner is kept.

Limits, stated on the site: judges appointed by the Governor since the seat's last election are not in these files
until they stand for election, and a judge who has left office stays listed until the seat is filled at an
election. Appellate judges and justices are left to other sources.

    "config": {"elections": ["20261103-GEN", "20241105-GEN", "20221108-GEN"], "skip_circuits": [11, 17]}
"""
import csv
import io

from collector.scrapers.base import BaseScraper, FetchError

WON = {"Elected", "Retained", "Unopposed"}
ORDINAL = {1: "st", 2: "nd", 3: "rd"}

# Florida's 20 judicial circuits (s. 26.021, Florida Statutes).
CIRCUITS = {
    1: ["Escambia", "Okaloosa", "Santa Rosa", "Walton"],
    2: ["Franklin", "Gadsden", "Jefferson", "Leon", "Liberty", "Wakulla"],
    3: ["Columbia", "Dixie", "Hamilton", "Lafayette", "Madison", "Suwannee", "Taylor"],
    4: ["Clay", "Duval", "Nassau"],
    5: ["Citrus", "Hernando", "Lake", "Marion", "Sumter"],
    6: ["Pasco", "Pinellas"],
    7: ["Flagler", "Putnam", "St. Johns", "Volusia"],
    8: ["Alachua", "Baker", "Bradford", "Gilchrist", "Levy", "Union"],
    9: ["Orange", "Osceola"],
    10: ["Hardee", "Highlands", "Polk"],
    11: ["Miami-Dade"],
    12: ["DeSoto", "Manatee", "Sarasota"],
    13: ["Hillsborough"],
    14: ["Bay", "Calhoun", "Gulf", "Holmes", "Jackson", "Washington"],
    15: ["Palm Beach"],
    16: ["Monroe"],
    17: ["Broward"],
    18: ["Brevard", "Seminole"],
    19: ["Indian River", "Martin", "Okeechobee", "St. Lucie"],
    20: ["Charlotte", "Collier", "Glades", "Hendry", "Lee"],
}


def circuit_name(n: int) -> str:
    return f"{n}{'th' if 10 < n < 14 else ORDINAL.get(n % 10, 'th')[-2:]} Judicial Circuit"


def parse_judges(files: list[str], source_url: str, skip: set[int] = frozenset()) -> list[dict]:
    """files: the downloads, newest election first. One record per (circuit, group): its latest winner."""
    seats: dict[tuple[int, int], dict] = {}
    for text in files:
        for row in csv.DictReader(io.StringIO(text), delimiter="\t"):
            if row.get("OfficeDesc") != "Circuit Judge" or row.get("StatusDesc") not in WON:
                continue
            try:
                circuit, group = int(row["Juris1num"]), int(row["Juris2num"])
            except (TypeError, ValueError):
                continue
            if circuit not in CIRCUITS or circuit in skip or (circuit, group) in seats:
                continue  # newest election wins: later files only fill seats not yet seen
            name = " ".join(p for p in (row.get("NameFirst"), row.get("NameMiddle"), row.get("NameLast")) if p and p.strip())
            counties = CIRCUITS[circuit]
            seats[(circuit, group)] = {
                "name": name.title() if name.isupper() else name, "office_title": "Circuit Judge",
                "government_level": "county", "selection_method": "elected", "party": "Nonpartisan",
                "jurisdiction": circuit_name(circuit), "district": str(group), "seat_label": f"Group {group}",
                "county": counties[0] if len(counties) == 1 else None, "counties": counties, "source_url": source_url}
    if len(seats) < 200:
        raise FetchError(f"Only {len(seats)} circuit judge seats were found (expected 500+); the download format may have changed.")
    return list(seats.values())


class FLJudgesScraper(BaseScraper):
    DOWNLOAD = "https://dos.elections.myflorida.com/candidates/extractCanList.asp"

    def collect(self) -> list[dict]:
        files = [self.client.post(self.DOWNLOAD, {"elecID": e, "office": "JUD", "status": "All", "cantype": "STA",
                                                  "FormSubmit": "Download Candidate List"})
                 for e in self.config.get("elections") or ["20261103-GEN", "20241105-GEN", "20221108-GEN"]]
        return parse_judges(files, self.source_url, {int(c) for c in self.config.get("skip_circuits") or []})
