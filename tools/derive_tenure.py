"""Derive time in office, earlier offices and the next election for each official, from state election records.

    python tools/derive_tenure.py [--counties Pasco,Leon,Broward]   # writes data/tenure.json and data/tenure_review.json

Input: data/elections/history.tsv (tools/election_history.py) and site/data/officials.json.

1. Match: each official is linked to one person in the election records (a hashed voter id, the same across every
   election they ran in). Candidates are limited to the same office and the same county, district or circuit; the
   name must agree on surname and on first name (exactly, as a common nickname, as their middle name, or as an
   initial). A matching seat number adds weight. One clear winner is a match; two or more plausible people, or a
   name found only under another office, go to the review file -- nothing is filled in for them.
2. Derive, only for matched officials:
   - serving_since: the first win of the current continuous run in this office (a gap longer than one term ends a
     run). If the run reaches the start of the records (1996) or an election with no recorded outcome, it is
     "since at least" that year.
   - previously: other offices this same person won before the current run, as spans.
   - next_election: the seat's regular cycle: the last regular (not special) win plus the office's term. Nonpartisan
     seats (judges, school boards) are decided on the August primary ballot. Term limits (8 consecutive years for the
     Legislature, Governor and Cabinet) mark the next election as one the person cannot run in.
Each derived value records how it was derived. Appointments (vacancies filled by the Governor) are not in these records.
"""
import csv
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TODAY = date.today()
WON = {"elected", "unopposed", "retained"}
RECORDS_START = 1996

COUNTY_CODE = {
    "Alachua": "ALA", "Baker": "BAK", "Bay": "BAY", "Bradford": "BRA", "Brevard": "BRE", "Broward": "BRO", "Calhoun": "CAL",
    "Charlotte": "CHA", "Citrus": "CIT", "Clay": "CLA", "Collier": "CLL", "Columbia": "CLM", "Miami-Dade": "DAD", "DeSoto": "DES",
    "Dixie": "DIX", "Duval": "DUV", "Escambia": "ESC", "Flagler": "FLA", "Franklin": "FRA", "Gadsden": "GAD", "Gilchrist": "GIL",
    "Glades": "GLA", "Gulf": "GUL", "Hamilton": "HAM", "Hardee": "HAR", "Hendry": "HEN", "Hernando": "HER", "Highlands": "HIG",
    "Hillsborough": "HIL", "Holmes": "HOL", "Indian River": "IND", "Jackson": "JAC", "Jefferson": "JEF", "Lafayette": "LAF",
    "Lake": "LAK", "Lee": "LEE", "Leon": "LEO", "Levy": "LEV", "Liberty": "LIB", "Madison": "MAD", "Manatee": "MAN",
    "Marion": "MRN", "Martin": "MRT", "Monroe": "MON", "Nassau": "NAS", "Okaloosa": "OKA", "Okeechobee": "OKE", "Orange": "ORA",
    "Osceola": "OSC", "Palm Beach": "PAL", "Pasco": "PAS", "Pinellas": "PIN", "Polk": "POL", "Putnam": "PUT", "Santa Rosa": "SAN",
    "Sarasota": "SAR", "Seminole": "SEM", "St. Johns": "STJ", "St. Lucie": "STL", "Sumter": "SUM", "Suwannee": "SUW",
    "Taylor": "TAY", "Union": "UNI", "Volusia": "VOL", "Wakulla": "WAK", "Walton": "WAL", "Washington": "WAS"}

# (pattern for our office title, election-record office, scope, term years, nonpartisan, term-limit years)
OFFICES = [
    (r"^U\.S\. Senator$", "United States Senator", "state", 6, False, None),
    (r"^U\.S\. Representative$", "United States Representative", "district", 2, False, None),
    (r"^State Senator$", "State Senator", "district", 4, False, 8),
    (r"^State Representative$", "State Representative", "district", 2, False, 8),
    (r"^Governor$", "Governor", "state", 4, False, 8),
    (r"^Attorney General$", "Attorney General", "state", 4, False, 8),
    (r"^Chief Financial Officer$", "Chief Financial Officer", "state", 4, False, 8),
    (r"^Commissioner of Agriculture$", "Commissioner of Agriculture", "state", 4, False, 8),
    # Merit retention for justices and appellate judges is on the November general ballot (Art. V, s. 10), not the
    # August primary where trial judges' nonpartisan races are, so these are not marked nonpartisan-primary.
    (r"^(Chief )?Justice of the Florida Supreme Court$", "Supreme Court Justice", "state", 6, False, None),
    (r"District Court of Appeal", "District Court of Appeal", "state", 6, False, None),
    (r"^Circuit Judge$", "Circuit Judge", "circuit", 6, True, None),
    (r"^State Attorney$", "State Attorney", "circuit", 4, False, None),
    (r"^Public Defender$", "Public Defender", "circuit", 4, False, None),
    (r"^County Court Judge$", "County Judge", "county", 6, True, None),
    (r"^County (Commissioner|Council Member)$", "Board of County Commissioners", "county", 4, False, None),
    (r"^County Mayor$", "Mayor", "county", 4, True, None),
    (r"^School Board Member$", "School Board", "county", 4, True, None),
    (r"^Superintendent of Schools$", "Superintendent of Schools", "county", 4, False, None),
    (r"^Sheriff$", "Sheriff", "county", 4, False, None),
    (r"^Clerk of the Circuit Court$", "Clerk of the Circuit Court", "county", 4, False, None),
    (r"^Property Appraiser$", "Property Appraiser", "county", 4, False, None),
    (r"^Tax Collector$", "Tax Collector", "county", 4, False, None),
    (r"^Supervisor of Elections$", "Supervisor of Elections", "county", 4, False, None),
]
NICKNAMES = {
    "bill": "william", "will": "william", "billy": "william", "bob": "robert", "rob": "robert", "bobby": "robert", "jim": "james",
    "jimmy": "james", "mike": "michael", "dave": "david", "dan": "daniel", "danny": "daniel", "tom": "thomas", "tommy": "thomas",
    "joe": "joseph", "joey": "joseph", "chris": "christopher", "matt": "matthew", "steve": "stephen", "tony": "anthony",
    "rick": "richard", "rich": "richard", "dick": "richard", "ken": "kenneth", "kenny": "kenneth", "ron": "ronald",
    "ronnie": "ronald", "don": "donald", "larry": "lawrence", "jerry": "gerald", "greg": "gregory", "jeff": "jeffrey",
    "pat": "patrick", "sam": "samuel", "ted": "edward", "ed": "edward", "eddie": "edward", "fred": "frederick", "frank": "francis",
    "chuck": "charles", "charlie": "charles", "andy": "andrew", "drew": "andrew", "nick": "nicholas", "ben": "benjamin",
    "alex": "alexander", "kathy": "katherine", "kate": "katherine", "katie": "katherine", "beth": "elizabeth", "liz": "elizabeth",
    "betty": "elizabeth", "sue": "susan", "jenny": "jennifer", "jen": "jennifer", "debbie": "deborah", "deb": "deborah",
    "cindy": "cynthia", "patty": "patricia", "pam": "pamela", "barb": "barbara", "vicki": "victoria", "vickie": "victoria",
    "tim": "timothy", "jack": "john", "johnny": "john", "jon": "jonathan", "hank": "henry", "harry": "henry", "walt": "walter",
    "al": "albert", "ray": "raymond", "russ": "russell", "doug": "douglas", "phil": "philip", "gene": "eugene", "vince": "vincent",
}


def fold(text: str) -> str:
    return re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower())


def canon(first: str) -> str:
    """The given name alone: 'Michael A.' -> michael, 'Sherwood "Chip"' -> sherwood, 'W. Greg' -> greg."""
    tokens = [fold(t) for t in re.sub(r"[\"\u201c\u201d(].*?[\"\u201c\u201d)]", " ", first or "").split()]
    tokens = [t for t in tokens if t]
    named = [t for t in tokens if len(t) > 1]
    f = named[0] if named else (tokens[0] if tokens else "")
    return NICKNAMES.get(f, f)


SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def surname_tokens(last: str) -> frozenset:
    return frozenset(t for t in (fold(p) for p in re.split(r"[\s-]+", last or "")) if t and t not in SUFFIXES)


def one_surname(sets: list) -> bool:
    """Surnames that chain together by a shared part: Cabrera / Busatta Cabrera / Busatta; Bauer Jr. / Bauer Jr."""
    sets = [x for x in sets if x]
    if not sets:
        return False
    joined, rest = set(sets[0]), sets[1:]
    while rest:
        nxt = [x for x in rest if x & joined]
        if not nxt:
            return False
        for x in nxt:
            joined |= x
            rest.remove(x)
    return True


def surname_ok(ours: str, theirs: str) -> bool:
    a, b = fold(ours), fold(theirs)
    if not a or not b:
        return False
    if a == b:
        return True
    pa = {fold(p) for p in re.split(r"[\s-]+", ours) if len(fold(p)) > 2}
    pb = {fold(p) for p in re.split(r"[\s-]+", theirs) if len(fold(p)) > 2}
    return bool(pa & pb)  # "Cameron-Cepeda" / "Cameron Cepeda" / "Cepeda"


def first_score(r: dict, row: dict) -> int:
    ours = canon(r.get("first_name") or r["full_name"].split()[0])
    first, middle = canon(row["first"]), canon(row["middle"])
    if not ours:
        return 0
    if ours == first:
        return 3
    if ours == middle:
        return 2  # goes by their middle name
    if len(ours) >= 3 and (first.startswith(ours) or ours.startswith(first)) and first:
        return 2
    if len(ours) == 1 and first.startswith(ours):
        return 1
    return 0


def num(text) -> int | None:
    m = re.search(r"\d+", str(text or ""))
    return int(m.group()) if m else None


def circuit_of(r: dict) -> int | None:
    m = re.match(r"(\d+)\w\w Judicial Circuit", r.get("jurisdiction") or "")
    return int(m.group(1)) if m else {"Broward": 17, "Miami-Dade": 11}.get(r.get("county"))


# Special districts in the records, with the term state law sets for each kind (None: set by each district's act).
SPECIAL_OFFICES = {"Community Development District": 4, "Fire Protection Districts": 4, "Soil & Water Conservation Districts": 4,
                   "Water Control Districts": None, "Special Tax Districts": None, "Mosquito Control Districts": None,
                   "Hospital Authority": None, "Port Authority": None, "Airport Authority": None, "Library District": None,
                   "County Development": None, "County Miscellaneous Boards": None, "Local Miscellaneous or Other": None}
CITY_OFFICES = ("City Commissioner/Council", "Mayor")


def office_for(r: dict):
    if r.get("special_district"):
        return tuple(SPECIAL_OFFICES), "county", None, True, None
    if r["government_level"] == "municipal":
        return CITY_OFFICES, "county", None, True, None  # city terms vary by charter (2-4 years)
    for pattern, office, scope, term, nonpartisan, limit in OFFICES:
        if re.search(pattern, r["office_title"]):
            return office, scope, term, nonpartisan, limit
    return None


def is_office(row: dict, office) -> bool:
    return row["office"] in office if isinstance(office, tuple) else row["office"] == office


def in_scope(r: dict, row: dict, scope: str) -> bool:
    if scope == "state":
        return True
    if scope == "district":
        return True  # district numbers change with redistricting; the seat number only adds weight
    if scope == "circuit":
        return num(row["juris1"]) == circuit_of(r)
    counties = [r["county"]] if r.get("county") else (r.get("counties") or [])
    return row["county"] in {COUNTY_CODE.get(c) for c in counties}


def general_day(year: int) -> date:
    nov1 = date(year, 11, 1)
    first_monday = nov1 + timedelta(days=(0 - nov1.weekday()) % 7)
    return first_monday + timedelta(days=1)


def label(row: dict) -> str:
    office = row["office"]
    seat = num(row["juris1"]) if office in ("United States Representative", "State Senator", "State Representative") else None
    if office in ("Circuit Judge", "State Attorney", "Public Defender"):
        return f"{office}, {num(row['juris1'])}th Judicial Circuit".replace("1th", "1st").replace("2th", "2nd").replace("3th", "3rd")\
            .replace("11st", "11th").replace("12nd", "12th").replace("13rd", "13th")
    county = next((name for name, code in COUNTY_CODE.items() if code == row["county"]), "")
    if row["level"] == "LOC" and county:
        return f"{office}, {county} County"
    return f"{office}, District {seat}" if seat else office


def derive(r: dict, rows: list[dict], office: str, term: int, nonpartisan: bool, limit: int | None) -> dict:
    won = sorted([x for x in rows if x["outcome"] in WON], key=lambda x: x["date"])
    same = [x for x in won if is_office(x, office)]
    years = sorted({int(x["date"][:4]) for x in same})
    out: dict = {"wins_in_office": years}
    if not years:
        return out
    if term is None:
        # Term set by statute for this kind of district, else by the spacing of this person's own re-elections.
        statutory = {SPECIAL_OFFICES.get(x["office"]) for x in same} - {None}
        gaps = [b - a for a, b in zip(years, years[1:]) if 2 <= b - a <= 4]
        term = statutory.pop() if len(statutory) == 1 else (min(gaps) if gaps else None)
        out["term_basis"] = "state law for this kind of district" if statutory or (len({SPECIAL_OFFICES.get(x["office"]) for x in same} - {None}) == 1) \
            else ("spacing of their own re-elections" if term else None)
    if term is None:
        start = years[-1]
        out["serving_since"] = {"year": start, "at_least": True, "link": "voter id",
                                "basis": "most recent win in this office; the term length isn't known, so earlier service isn't joined up"}
        out["next_election"] = {"year": None, "basis": "this office's term is set by its charter or act and isn't in the records"}
        return out
    # The current continuous run: walk back from the latest win while each gap is no longer than one term.
    run = [years[-1]]
    for y in reversed(years[:-1]):
        if run[0] - y <= term:
            run.insert(0, y)
        else:
            break
    start = run[0]
    unrecorded = any(is_office(x, office) and x["outcome"] == "not recorded" and int(x["date"][:4]) >= start - term for x in rows)
    first_row = next((x for x in same if int(x["date"][:4]) == start), same[0])
    out["serving_since"] = {"year": start, "at_least": start - term < RECORDS_START or unrecorded,
                            "link": first_row.get("link", "voter id"),
                            "basis": "first win of continuous service in this office, Florida Division of Elections records"}
    if isinstance(office, str) and re.search(r"Judge|Justice|Court", office):
        # Most Florida judges are appointed by the Governor and first appear on the ballot a year or two later; a
        # blind check against court bios found the first win 1-3 years after the bench start for 10 of 11 judges.
        out["serving_since"].update(at_least=True, basis="first time on the ballot for this seat (Florida Division of "
                                    "Elections records); judges are usually appointed by the Governor first, so most "
                                    "took the bench a year or more before this")
    # Earlier offices this same person won, before the current run began.
    spans: dict[str, list[int]] = defaultdict(list)
    links: dict[str, set] = defaultdict(set)
    for x in won:
        y = int(x["date"][:4])
        if not is_office(x, office) and y < start:
            spans[label(x)].append(y)
            links[label(x)].add(x.get("link", "voter id"))
    out["previously"] = [{"office": k, "from": min(v), "last_won": max(v), "link": "voter id" if "voter id" in links[k] else "name"}
                         for k, v in sorted(spans.items(), key=lambda kv: -max(kv[1]))]
    # Next election: anchored to the last regular (general-cycle) win in this run.
    regular = [int(x["date"][:4]) for x in same if x["kind"] == "general" and int(x["date"][:4]) >= start]
    if office == "United States Senator" and regular:
        # Florida's two Senate seats are elected in fixed years (Class 1: 2018, 2024, 2030; Class 3: 2016, 2022, 2028).
        # A win in any other year was a special election for the rest of a term: the seat's next regular year follows it.
        anchor = max(regular)
        if anchor % 6 not in (2018 % 6, 2016 % 6):
            nxt = next(y for y in range(anchor + 1, anchor + 7) if y % 6 in (2018 % 6, 2016 % 6))
            day = general_day(nxt)
            out["next_election"] = {"year": nxt, "date": day.isoformat(), "ballot": "November general",
                                    "basis": f"won the {anchor} special election for the rest of a term; the seat's regular election is {nxt}"}
            return out
    if regular:
        anchor = max(regular)
        nxt = anchor + term
        if general_day(nxt) < TODAY:
            # The seat's regular election has already happened and this person didn't win it: they are leaving office.
            ran = [x for x in rows if is_office(x, office) and int(x["date"][:4]) == nxt]
            out["next_election"] = {"year": None, "leaving": True, "seat_election": nxt,
                                    "basis": f"{term}-year term won in {anchor}; the seat was on the {nxt} ballot and "
                                             + ("they did not win it" if ran else "they were not on it")
                                             + (" (term-limited)" if limit and nxt - start >= limit else "")}
            return out
        day = general_day(nxt) - timedelta(days=77) if nonpartisan else general_day(nxt)
        ne = {"year": nxt, "date": day.isoformat(), "ballot": "August primary (nonpartisan)" if nonpartisan else "November general",
              "basis": f"{term}-year term; last regular election won {anchor}"}
        if limit and nxt - start >= limit:
            ne["term_limited"] = True  # 8 consecutive years by the end of this term: cannot appear on that ballot
        out["next_election"] = ne
    else:
        out["next_election"] = {"year": None, "basis": "won only a special election; the seat's regular cycle isn't in these records"}
    return out


def name_linked(r: dict, rows: list[dict], office: str, scope: str, by_last: dict) -> list[dict]:
    """The same person's records from before 2012 (no voter id): same surname and first name, and either the same office
    and seat as now, or any office in a county where their voter-id records place them. Marked link="name"."""
    counties = {x["county"] for x in rows if x["county"]} | {COUNTY_CODE.get(c) for c in [r.get("county"), *(r.get("counties") or [])] if c}
    seats = {(x["juris1"].lstrip("0"), x["juris2"].lstrip("0")) for x in rows if is_office(x, office)}
    out = []
    for row in by_last.get(fold(r["last_name"]), []):
        if first_score(r, row) < 3 and not row["person"].startswith("n"):
            continue  # another voter id: only an exact first name (or its nickname) counts
        if first_score(r, row) < 2:
            continue
        same_seat = is_office(row, office) and in_scope(r, row, scope) and (
            scope in ("state", "county") or (row["juris1"].lstrip("0"), row["juris2"].lstrip("0")) in seats)
        nearby = row["county"] in counties if row["county"] else False
        if (same_seat or nearby) and row["person"] not in {x["person"] for x in rows}:
            out.append({**row, "link": "name"})
    return out


def same_person(keys: list[str], by_person: dict, office: str, scope: str = "county") -> bool:
    """Several voter-record keys, one name, one seat (and at most one county): the same person who re-registered, or
    their records before and after voter ids began in 2012. Different people would have to share a name and have won
    the very same seat. Blank counties in the records are ignored."""
    firsts, lasts, seats, counties = set(), [], set(), set()
    for k in keys:
        rows = [x for x in by_person[k] if is_office(x, office) and x["outcome"] in WON]
        firsts |= {canon(x["first"]) for x in rows}
        lasts += [surname_tokens(x["last"]) for x in rows]
        seats |= {(x["juris1"].lstrip("0"), x["juris2"].lstrip("0")) for x in rows}
        counties |= {x["county"] for x in rows if x["level"] == "LOC" and x["county"]}
        if scope in ("district", "state"):  # district numbers change with redistricting: compare home counties instead
            counties |= {x["county"] for x in rows if x["county"]}
    if scope in ("district", "state"):
        return len(firsts) == 1 and one_surname(lasts) and len(counties) <= 2  # one home county (two at most, for a move across a line)
    names = len(firsts) == 1 and one_surname(lasts)
    if len([k for k in keys if not k.startswith("n")]) <= 1 and names and len(counties) <= 1:
        # Records before 2012 (name keys) and one voter id after: one person whose seat number changed (redistricting,
        # a move to an at-large seat). Name keys already share name, county and office.
        return True
    return names and len(seats) == 1 and len(counties) <= 1


MONTHS = {"jan": "January", "feb": "February", "mar": "March", "apr": "April", "may": "May", "jun": "June", "jul": "July",
          "aug": "August", "sep": "September", "oct": "October", "nov": "November", "dec": "December"}


def apply_wikipedia_terms(tenure: dict, officials: list[dict]) -> None:
    """The date each took office from the Wikipedia infobox (tools/wikipedia_terms.py). Election records date a
    win, not an appointment, so where Wikipedia's date is earlier (an appointee, or service before 1996) it wins."""
    path = ROOT / "data/wikipedia_terms.json"
    terms = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    ids = {r["id"] for r in officials}
    for rid, w in terms.items():
        if rid.startswith("_") or rid not in ids:
            continue
        out = tenure.setdefault(rid, {"match": {"method": "Wikipedia article", "score": None}})
        have = out.get("serving_since") or {}
        if have.get("year") and have["year"] <= w["year"] and not have.get("at_least"):
            continue  # the records already go back at least as far
        how = f"appointed by {w['appointed_by']}" if w.get("appointed_by") else "took office"
        when = w["assumed_office"]
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", when):
            d = date.fromisoformat(when)
            when = f"{d:%B} {d.day}, {d.year}"
        basis = f"Wikipedia: {how} {when}"
        if have.get("year"):
            basis += f"; first won election in this office {have['year']} (state election records)"
        out["serving_since"] = {"year": w["year"], "at_least": False, "link": "wikipedia", "basis": basis,
                                "source": w["wikipedia_url"], **({"appointed": True} if w.get("appointed_by") else {})}


def apply_roster_terms(tenure: dict, review: dict, officials: list[dict]) -> None:
    """City and special-district officials whose own pages state a term (tools/roster_terms.py): fills what the
    election records left empty, quoting the page."""
    terms = json.loads((ROOT / "data/roster_terms.json").read_text(encoding="utf-8")) if (ROOT / "data/roster_terms.json").exists() else {}
    by_id = {r["id"]: r for r in officials}
    for rid, t in terms.items():
        if rid.startswith("_") or rid not in by_id:
            continue
        r = by_id[rid]
        out = tenure.setdefault(rid, {"match": {"method": "the official's own page", "score": None}})
        cite = f"on {r.get('source_url')}"
        if t.get("since") and not out.get("serving_since"):
            since = t["since"]
            out["serving_since"] = {"year": since["year"], "at_least": since.get("at_least", True), "link": "official page",
                                    "basis": f"the official's page: \u201c{since['quote']}\u201d", "source": r.get("source_url")}
            if since.get("office") == "the council":
                out["serving_since"]["basis"] += " (service on the council, which may predate this office)"
        if t.get("term_ends") and not (out.get("next_election") or {}).get("year"):
            end = t["term_ends"]
            month = (end.get("month") or "")[:3]
            year = end["year"] - 1 if month == "jan" else end["year"]
            basis = f"the official's page: \u201c{end['quote']}\u201d; the election is held at or just before the end of the term"
            if year <= TODAY.year:
                basis += f". The term ends in {end['year']}: the page may not show this year's result yet"
            out["next_election"] = {"year": year, "basis": basis, "source": r.get("source_url"),
                                    "term_ends": f"{MONTHS.get(month, '')} {end['year']}".strip()}
        group = "special districts" if r.get("special_district") else "city"
        s = review["summary"].setdefault(group, {"matched": 0, "ambiguous": 0, "unmatched": 0})
        s["from official pages"] = s.get("from official pages", 0) + 1
        review["unmatched"] = [u for u in review["unmatched"] if u["id"] != rid]


def main() -> None:
    args = sys.argv[1:]
    only = set(args[args.index("--counties") + 1].split(",")) if "--counties" in args else None
    history = list(csv.DictReader((ROOT / "data/elections/history.tsv").open(encoding="utf-8"), delimiter="\t"))
    by_person: dict[str, list[dict]] = defaultdict(list)
    by_office: dict[str, list[dict]] = defaultdict(list)
    by_last: dict[str, list[dict]] = defaultdict(list)  # rows before voter ids (2012), by surname
    for row in history:
        by_person[row["person"]].append(row)
        by_last[fold(row["last"])].append(row)
        if row["outcome"] in WON:
            by_office[row["office"]].append(row)
    officials = json.loads((ROOT / "site/data/officials.json").read_text(encoding="utf-8"))["officials"]
    tenure, review = {}, {"ambiguous": [], "unmatched": [], "summary": {}}
    namesakes = Counter((fold(r["last_name"]), canon(r["first_name"]), r["office_title"]) for r in officials)
    for r in officials:
        spec = office_for(r)
        if not spec:
            continue
        office, scope, term, nonpartisan, limit = spec
        if only and scope in ("county", "circuit") and not ({r.get("county"), *(r.get("counties") or [])} & only):
            continue
        group = {"state": "state/federal", "district": "state/federal", "circuit": "judges", "county": "county"}[scope]
        if isinstance(office, str) and ("Judge" in office or "Justice" in office or "Court" in office):
            group = "judges"
        if r.get("special_district"):
            group = "special districts"
        elif r["government_level"] == "municipal":
            group = "city"
        candidates: dict[str, int] = {}
        blank_only: set[str] = set()  # people matched only on rows with no county (address withheld by law)
        seen_in_county: set[str] = set()
        for row in [x for o in (office if isinstance(office, tuple) else (office,)) for x in by_office[o]]:
            blank = scope == "county" and not row["county"]
            if not (blank or in_scope(r, row, scope)) or not surname_ok(r["last_name"], row["last"]):
                continue
            score = first_score(r, row)
            if not score or (blank and (score < 3 or namesakes[(fold(r["last_name"]), canon(r["first_name"]), r["office_title"])] > 1)):
                continue
            (blank_only if blank else seen_in_county).add(row["person"])
            if r.get("district") and num(row["juris2"] if scope == "circuit" else row["juris1"]) == num(r["district"]):
                score += 2
            candidates[row["person"]] = max(candidates.get(row["person"], 0), score)
        s = review["summary"].setdefault(group, {"matched": 0, "ambiguous": 0, "unmatched": 0})
        strong = sorted(((v, k) for k, v in candidates.items() if v >= 2), reverse=True)
        top = [k for v, k in strong if v == strong[0][0]] if strong else []
        if len(top) > 1 and same_person(top, by_person, office, scope):
            top = ["+".join(sorted(top))]  # one person under several voter ids (re-registered): combine their records
        if len(top) == 1:
            person = top[0]
            rows = [x for p in person.split("+") for x in by_person[p]]
            rows += name_linked(r, rows, office, scope, by_last)
            method = {5: "exact name + seat", 3: "exact name"}.get(strong[0][0], "nickname / middle name / initial")
            if set(person.split("+")) <= blank_only - seen_in_county:
                method += "; the records leave out the county (address withheld by law), and no other official has this name and office"
            tenure[r["id"]] = {"person": person.split("+")[0], "match": {"method": method, "score": strong[0][0],
                               **({"voter_records": len(person.split("+"))} if "+" in person else {})},
                               **derive(r, rows, office, term, nonpartisan, limit)}
            s["matched"] += 1
        elif strong:
            review["ambiguous"].append({"id": r["id"], "name": r["full_name"], "office": r["office_title"],
                                        "candidates": [{"person": k, "score": v} for v, k in strong[:5]]})
            s["ambiguous"] += 1
        else:
            review["unmatched"].append({"id": r["id"], "name": r["full_name"], "office": r["office_title"], "county": r.get("county")})
            s["unmatched"] += 1
    apply_roster_terms(tenure, review, officials)
    apply_wikipedia_terms(tenure, officials)
    (ROOT / "data/tenure.json").write_text(json.dumps({"_how_to": "Generated by tools/derive_tenure.py; see its docstring.",
                                                       "_as_of": TODAY.isoformat(), **tenure}, indent=1) + "\n", encoding="utf-8")
    (ROOT / "data/tenure_review.json").write_text(json.dumps(review, indent=1) + "\n", encoding="utf-8")
    for group, s in review["summary"].items():
        total = s["matched"] + s["ambiguous"] + s["unmatched"]
        print(f"{group:17} election records {s['matched']:4}/{total:<4}  ambiguous {s['ambiguous']:3}  unmatched {s['unmatched']:4}"
              f"  official pages {s.get('from official pages', 0):3}", file=sys.stderr)


if __name__ == "__main__":
    main()
