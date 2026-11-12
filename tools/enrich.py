"""Build data/profiles.json: portraits, basic bio facts and missing contact details for
collected officials, from public-domain datasets.

    python tools/enrich.py --congress PATH/congress-legislators --openstates PATH/openstates-people \
        [--house-dates PATH/house_dates.txt]

Sources (both public domain, both cloneable from GitHub):
  - unitedstates/congress-legislators  (Members of Congress: birthdays, terms, Bioguide ids)
  - openstates/people, data/fl/legislature  (Florida legislators: emails, birth dates, past roles)

Optional --house-dates: "district|name|YYYY-MM-DD" lines giving when each Florida House member
took office (copied from Ballotpedia's member list).

A dataset entry is only used when its district AND surname match the collected record, so a
stale dataset can never put one person's photo or birthday next to another person's name.
Values already in the collected record always win; this file only fills gaps. Re-run it after a
collection run that adds new people, then commit data/profiles.json.
"""
import argparse
import glob
import json
import re
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from collector.normalize import ascii_key  # noqa: E402

TODAY = date.today().isoformat()
CONGRESS_PHOTO = "https://unitedstates.github.io/images/congress/450x550/{}.jpg"
HOUSE_PHOTO = "https://www.flhouse.gov/FileStores/Web/Imaging/Member/{}.jpg"
CONGRESS_SOURCE = {"name": "congress-legislators (public domain)", "url": "https://github.com/unitedstates/congress-legislators"}
OPENSTATES_SOURCE = {"name": "Open States (public domain)", "url": "https://openstates.org/fl/"}
BALLOTPEDIA_SOURCE = {"name": "Ballotpedia: Florida House of Representatives", "url": "https://ballotpedia.org/Florida_State_House"}
CHAMBER = {"lower": "State Representative", "upper": "State Senator"}


def surname_matches(record: dict, last: str | None) -> bool:
    key = ascii_key(last or "")
    return bool(key) and key in ascii_key(record.get("full_name"))


def year(value) -> str:
    return str(value or "")[:4]


def iso(value) -> str | None:
    """YAML reads dates as date objects; keep them as YYYY-MM-DD text."""
    return str(value) if value else None


def congress_profiles(records: list[dict], congress_dir: Path) -> dict:
    people = yaml.safe_load((congress_dir / "legislators-current.yaml").read_text(encoding="utf-8"))
    people = [p for p in people if p["terms"][-1].get("state") == "FL"]
    out = {}
    for record in records:
        title = record["office_title"]
        if title not in ("U.S. Senator", "U.S. Representative"):
            continue
        kind = "sen" if title == "U.S. Senator" else "rep"
        for person in people:
            term = person["terms"][-1]
            if term["type"] != kind or not surname_matches(record, person["name"].get("last")):
                continue
            if kind == "rep" and str(term.get("district")) != record.get("district"):
                continue
            same = [t for t in person["terms"] if t["type"] == kind]
            first = iso(same[0]["start"])
            # A real break in service (not the few days between one Congress and the next)
            # restarts "serving since".
            for earlier, later in zip(same, same[1:]):
                if (date.fromisoformat(iso(later["start"])) - date.fromisoformat(iso(earlier["end"]))).days > 60:
                    first = iso(later["start"])
            previously = []
            if kind == "sen":
                for t in person["terms"]:
                    if t["type"] == "rep":
                        previously.append(f"U.S. Representative, Florida District {t['district']}")
            bio = {
                "born": iso(person.get("bio", {}).get("birthday")),
                "serving_since": first,
                "term_ends": iso(term["end"]) if iso(term["end"]) > TODAY else None,
                "previously": sorted(set(previously)),
            }
            out[record["id"]] = {
                "photo_url": CONGRESS_PHOTO.format(person["id"]["bioguide"]),
                "bio": {k: v for k, v in bio.items() if v},
                "sources": [CONGRESS_SOURCE],
            }
            break
    return out


def _openstates_people(openstates_dir: Path) -> list[dict]:
    files = glob.glob(str(openstates_dir / "data/fl/legislature/*.yml"))
    return [yaml.safe_load(Path(f).read_text(encoding="utf-8")) for f in files]


def _house_dates(path: Path | None) -> dict:
    found = {}
    if path and path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                district, name, when = line.strip().split("|")
                found[district] = (name, when)
    return found


def legislature_profiles(records: list[dict], openstates_dir: Path, house_dates: dict) -> dict:
    people = _openstates_people(openstates_dir)
    out = {}
    for record in records:
        chamber = {"State Representative": "lower", "State Senator": "upper"}.get(record["office_title"])
        if not chamber:
            continue
        district = record.get("district")
        entry: dict = {"bio": {}, "sources": []}

        if chamber == "lower" and (m := re.search(r"MemberId=(\d+)", record.get("official_website") or "")):
            entry["photo_url"] = HOUSE_PHOTO.format(m.group(1))
        # The Capitol office number follows the district: (850) 717-5XXX in the House, 487-50XX in the Senate.
        if district and district.isdigit():
            entry["phone"] = f"(850) 717-5{int(district):03d}" if chamber == "lower" else f"(850) 487-50{int(district):02d}"

        person = None
        for candidate in people:
            current = [r for r in candidate["roles"] if r["type"] == chamber and not r.get("end_date")]
            if current and current[-1].get("district") == district and surname_matches(record, candidate.get("family_name")):
                person = candidate
                break
        if person:
            if person.get("email"):
                entry["email"] = person["email"]
            if person.get("birth_date"):
                entry["bio"]["born"] = iso(person["birth_date"])
            same = sorted((r for r in person["roles"] if r["type"] == chamber), key=lambda r: iso(r.get("start_date")) or "")
            if same and same[0].get("start_date"):
                entry["bio"]["serving_since"] = iso(same[0]["start_date"])
            previously = []
            for role in person["roles"]:
                if role.get("end_date") and role["type"] in CHAMBER and role["type"] != chamber:
                    span = f"{year(role.get('start_date'))}–{year(role['end_date'])}".strip("–")
                    previously.append(f"{CHAMBER[role['type']]}, District {role['district']}" + (f" ({span})" if span else ""))
            if previously:
                entry["bio"]["previously"] = previously
            entry["sources"].append(OPENSTATES_SOURCE)

        if chamber == "lower" and district in house_dates:
            name, when = house_dates[district]
            if surname_matches(record, name.split()[-1] if not name.endswith("III") else name.split()[-2]):
                entry["bio"]["serving_since"] = when
                entry["sources"].append(BALLOTPEDIA_SOURCE)

        if not entry["bio"]:
            entry.pop("bio")
        if not entry["sources"]:
            entry.pop("sources")
        out[record["id"]] = entry
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--congress", type=Path, required=True)
    parser.add_argument("--openstates", type=Path, required=True)
    parser.add_argument("--house-dates", type=Path)
    args = parser.parse_args()

    collected = json.loads((ROOT / "data/collected.json").read_text(encoding="utf-8"))
    records = [r for state in collected["sources"].values() for r in state.get("records", [])]
    profiles = {}
    profiles.update(congress_profiles(records, args.congress))
    profiles.update(legislature_profiles(records, args.openstates, _house_dates(args.house_dates)))

    path = ROOT / "data/profiles.json"
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    # Hand-written entries (bios for local officials) are kept; generated ones are replaced.
    kept = {k: v for k, v in existing.items() if k.startswith("_") or v.get("hand_written")}
    merged = {**profiles, **kept}
    ordered = dict(sorted(merged.items(), key=lambda kv: (not kv[0].startswith("_"), kv[0])))
    path.write_text(json.dumps(ordered, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(profiles)} generated profiles and kept {len(kept)} hand-written entries")


if __name__ == "__main__":
    main()
