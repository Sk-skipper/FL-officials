"""Build the files the website reads, from the collected data plus your edits.

    python -m collector.publish

Inputs (all in data/):
  collected.json         written by the collector; do not edit by hand
  manual_officials.json  officials you add yourself, e.g. county commissioners
  corrections.json       fixes to individual records, keyed by record id
  profiles.json          portraits, bio facts and missing contact details (tools/enrich.py)
  wikipedia.json         last-resort portraits, birth dates and article links (tools/wikipedia.py)
  districts.json         which counties each congressional / Florida House district covers
  vacancies.json         seats that are currently empty
  special_districts.json special districts (water control, hospital, children's services...)
  site.json              optional settings (report link, contact email)

Outputs (in site/data/): officials.json, officials.csv, sources.json, meta.json (which also carries the special districts)

Exits with an error if a correction or a hand-added record is invalid, so a
bad edit stops the deploy instead of reaching the public site.
"""
import csv
import io
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from collector.geo import FLORIDA_COUNTIES, canonical_county
from collector.normalize import (
    normalize_email,
    normalize_party,
    normalize_phone,
    normalize_photo_url,
    normalize_url,
    parse_district,
)
from collector.validate import validate_record

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE_DATA = ROOT / "site" / "data"

LEVELS = ("federal", "state", "county", "municipal")

# Seats that exist for each office with a source. A vacancy can leave
# "collected" one or two below "expected".
EXPECTED_SEATS = [
    ("federal", "U.S. Senator", 2),
    ("federal", "U.S. Representative", 28),
    ("state", "Governor", 1),
    ("state", "Lieutenant Governor", 1),
    ("state", "Attorney General", 1),
    ("state", "Chief Financial Officer", 1),
    ("state", "Commissioner of Agriculture", 1),
    ("state", "State Senator", 40),
    ("state", "State Representative", 120),
    ("county", "Supervisor of Elections", 67),
    ("county", "Sheriff", 67),
    ("county", "Clerk of the Circuit Court", 67),
]
NOT_YET_COVERED = [
    "County commissioners in 35 of the 65 counties outside Broward and Miami-Dade: the Florida Association of Counties "
    "directory lists the wrong number of members for them (it keeps some former commissioners), so they are held back",
    "Property appraisers and tax collectors outside Broward and Miami-Dade (no statewide list names them)",
    "School boards outside Broward, Miami-Dade, Charlotte, Citrus, Escambia, Holmes, Jackson, Liberty, Orange, Palm Beach and "
    "Sumter (most district websites load their board pages with JavaScript), and school superintendents",
    "Judges outside Broward and Miami-Dade and the 1st, 2nd, 5th and 6th District Courts of Appeal",
    "Mayors and councils outside Broward and Miami-Dade counties (Florida has 411 municipalities; the League of Cities "
    "directory only answers its own website's search box)",
    "Broward: Cooper City, Dania Beach and Lauderhill councils; Hallandale Beach, Lauderdale Lakes, Plantation, Sea Ranch Lakes, Sunrise, "
    "West Park and Weston list only their mayor (their websites refuse automated requests or could not be read)",
    "Miami-Dade: Doral, Hialeah, Hialeah Gardens, Indian Creek, Miami Shores, Miami Springs, South Miami and Sunny Isles Beach councils, "
    "the mayors of Miami Lakes and North Miami, and one or two seats in Cutler Bay, Medley, North Miami and West Miami",
    "Board members of most special districts, and special districts outside Broward and Miami-Dade (the state's official list "
    "refuses automated requests)",
    "Appointed state boards and commissions",
]

BIO_TEXT = {"born", "serving_since", "term_ends", "next_election", "summary", "note"}
BIO_FIELDS = BIO_TEXT | {"previously"}

CSV_COLUMNS = [
    "id", "full_name", "first_name", "middle_name", "last_name", "office_title", "government_level",
    "selection_method", "party", "district", "jurisdiction", "county", "municipality", "counties",
    "phone", "email", "official_website", "photo_url", "verification_status", "last_verified", "source_name", "source_url",
]

REQUIRED = {"full_name", "last_name", "office_title", "jurisdiction"}
TEXT_FIELDS = {"full_name", "first_name", "middle_name", "last_name", "office_title", "jurisdiction", "municipality"}
CORRECTABLE = TEXT_FIELDS | {"party", "district", "phone", "email", "official_website", "photo_url", "selection_method"}
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class PublishError(Exception):
    pass


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PublishError(f"{path.name} is not valid JSON (line {exc.lineno}): {exc.msg}") from exc


def _correct(record: dict, fields: dict, record_id: str) -> None:
    where = f"corrections.json, '{record_id}'"
    for name, value in fields.items():
        if name == "note":
            record["correction_note"] = str(value)
            continue
        if name not in CORRECTABLE:
            raise PublishError(f"{where}: '{name}' cannot be corrected. Allowed: {', '.join(sorted(CORRECTABLE))}, note")
        if value in (None, ""):
            if name in REQUIRED:
                raise PublishError(f"{where}: '{name}' cannot be empty")
            record[name] = None
            if name == "district":
                record["district_number"] = None
            continue
        value = str(value).strip()
        if name == "phone":
            clean = normalize_phone(value)
        elif name == "email":
            clean = normalize_email(value)
        elif name == "official_website":
            clean = normalize_url(value)
        elif name == "photo_url":
            clean = normalize_photo_url(value)
        elif name == "party":
            clean = normalize_party(value)
        elif name == "selection_method":
            clean = value if value in ("elected", "appointed", "unknown") else None
        elif name == "district":
            clean, record["district_number"] = parse_district(value)
        else:
            clean = value
        if not clean:
            raise PublishError(f"{where}: {value!r} is not a valid {name.replace('_', ' ')}")
        record[name] = clean
    record["verification_status"] = "corrected"


def _clean_bio(bio: object, where: str) -> dict:
    if not isinstance(bio, dict):
        raise PublishError(f"{where}: bio must be an object")
    clean = {}
    for key, value in bio.items():
        if key not in BIO_FIELDS:
            raise PublishError(f"{where}: unknown bio field '{key}'. Allowed: {', '.join(sorted(BIO_FIELDS))}")
        if key == "previously":
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise PublishError(f"{where}: bio.previously must be a list of text")
            clean[key] = [v.strip() for v in value if v.strip()]
        elif isinstance(value, str) and value.strip():
            clean[key] = value.strip()
        elif value is not None:
            raise PublishError(f"{where}: bio.{key} must be text")
    return clean


def _apply_profiles(by_id: dict, profiles: dict, warnings: list[str]) -> None:
    """Fill gaps from data/profiles.json. Values the source published always win."""
    for record_id, profile in profiles.items():
        if record_id.startswith("_"):
            continue
        record = by_id.get(record_id)
        if record is None:
            continue  # profiles are generated for everyone collected; a departed official just has none
        where = f"profiles.json, '{record_id}'"
        for field, clean in (("photo_url", normalize_photo_url), ("phone", normalize_phone), ("email", normalize_email),
                             ("party", normalize_party)):
            if profile.get(field) and not record.get(field):
                record[field] = clean(profile[field])
        if profile.get("bio"):
            record["bio"] = {**_clean_bio(profile["bio"], where), **(record.get("bio") or {})}
        sources = [s for s in profile.get("sources", []) if isinstance(s, dict) and s.get("name")]
        if sources:
            record["bio_sources"] = sources


def _apply_wikipedia(by_id: dict, wiki: dict) -> None:
    """Last resort, after official sources and profiles: a Commons portrait, a birth date, an article link."""
    for record_id, entry in wiki.items():
        record = by_id.get(record_id)
        if record_id.startswith("_") or record is None or not isinstance(entry, dict):
            continue
        if entry.get("wikipedia_url", "").startswith("https://en.wikipedia.org/"):
            record["wikipedia_url"] = entry["wikipedia_url"]
        if entry.get("photo_url") and not record.get("photo_url"):
            photo = normalize_photo_url(entry["photo_url"])
            credit = entry.get("photo_credit") or {}
            if photo and credit.get("license"):
                record["photo_url"] = photo
                record["photo_credit"] = {k: credit.get(k) for k in ("source", "author", "license", "license_url", "file_url")}
        born = entry.get("born")
        if born and DATE.match(born) and not (record.get("bio") or {}).get("born"):
            record["bio"] = {**(record.get("bio") or {}), "born": born}
            record["bio_sources"] = [*(record.get("bio_sources") or []),
                                     {"name": "Wikidata", "url": "https://www.wikidata.org/"}]


def _apply_districts(records: list[dict], districts: dict) -> None:
    """Give district-based officials the counties their district covers, when their source didn't say."""
    for record in records:
        table = districts.get(record.get("office_title"))
        if not isinstance(table, dict) or record.get("counties") or record.get("county") or record.get("statewide"):
            continue
        found = (table.get("districts") or {}).get(record.get("district") or "")
        if found:
            record["counties"] = [c for c in (canonical_county(n) for n in found) if c]
            record["counties_source"] = table.get("source")


def _vacancies(raw: dict) -> list[dict]:
    out = []
    for index, entry in enumerate(raw.get("vacancies", []), start=1):
        if not entry.get("office_title") or not entry.get("source_url"):
            raise PublishError(f"vacancies.json, entry {index}: office_title and source_url are required")
        counties = [c for c in (canonical_county(n) for n in entry.get("counties") or []) if c]
        out.append({
            "office_title": entry["office_title"], "government_level": entry.get("government_level"),
            "district": entry.get("district"), "seat_label": entry.get("seat_label"),
            "jurisdiction": entry.get("jurisdiction"), "counties": counties,
            "note": entry.get("note"), "source_url": entry["source_url"],
        })
    return out

_FILL = ("party", "phone", "email", "official_website", "photo_url", "district", "district_number", "seat_label",
         "middle_name", "bio")
LEADERSHIP = {"Mayor": 0, "Council President": 0, "Chair": 0, "Vice Mayor": 1, "Deputy Mayor": 1,
              "Council Vice President": 1, "Vice Chair": 1}


def _fill(kept: dict, other: dict) -> None:
    for field in _FILL:
        if not kept.get(field) and other.get(field):
            kept[field] = other[field]


def _person_key(record: dict) -> tuple:
    last = re.sub(r"[^a-z]", "", (record.get("last_name") or "").lower())
    return record.get("municipality"), last, (record.get("first_name") or " ")[0].lower()


def _merge_municipal(records: list[dict]) -> tuple[list[dict], dict[str, str]]:
    """A council member can be listed by the city's own site and by the county's GIS, with different titles
    ("Vice Mayor" vs "Commissioner, District 4"). Keep one record: the leadership title wins, and the record
    that has no district takes it from the other. Returns the records and {dropped id: kept id}."""
    groups: dict[tuple, list[dict]] = {}
    for record in records:
        if record["government_level"] == "municipal" and record.get("municipality"):
            groups.setdefault(_person_key(record), []).append(record)
    aliases, dropped = {}, set()
    for group in groups.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda r: (LEADERSHIP.get(r["office_title"], 9), r["verification_status"] == "manual",
                                  not r.get("district")))
        kept = group[0]
        for other in group[1:]:
            _fill(kept, other)
            aliases[other["id"]] = kept["id"]
            dropped.add(id(other))
    return [r for r in records if id(r) not in dropped], aliases


SPECIAL_AREAS = {"mapped", "countywide", "regional"}


def _special_districts(raw: dict) -> list[dict]:
    out, keys = [], set()
    for index, entry in enumerate(raw.get("districts", []), start=1):
        where = f"special_districts.json, entry {index}"
        for field in ("key", "name", "type", "area", "status"):
            if not str(entry.get(field) or "").strip():
                raise PublishError(f"{where}: '{field}' is required")
        if entry["key"] in keys:
            raise PublishError(f"{where}: key '{entry['key']}' is used twice")
        if entry["area"] not in SPECIAL_AREAS:
            raise PublishError(f"{where}: area must be one of {', '.join(sorted(SPECIAL_AREAS))}")
        keys.add(entry["key"])
        sources = [s for s in entry.get("sources", []) if isinstance(s, dict) and normalize_url(s.get("url"))]
        if not sources:
            raise PublishError(f"{where}: at least one source with a link is required")
        out.append({
            "key": entry["key"], "name": entry["name"], "type": entry["type"], "area": entry["area"],
            "county": canonical_county(entry.get("county") or "") if entry.get("county") else None,
            "area_note": entry.get("area_note"), "status": entry["status"], "board": entry.get("board"),
            "phone": normalize_phone(entry.get("phone")), "website": normalize_url(entry.get("website")),
            "note": entry.get("note"), "sources": sources,
        })
    return out


def build(collected: dict, manual: dict, corrections: dict, site: dict, now: datetime, env: dict | None = None,
          profiles: dict | None = None, districts: dict | None = None, vacancies: dict | None = None,
          wikipedia: dict | None = None, special: dict | None = None):
    env = os.environ if env is None else env
    warnings: list[str] = []
    records: list[dict] = []
    seen: set[str] = set()

    for state in collected.get("sources", {}).values():
        for raw in state.get("records", []):
            record = dict(raw)
            record.update(source_name=state["name"], source_directory_url=state["url"],
                          verification_status="source_verified")
            records.append(record)

    for index, entry in enumerate(manual.get("officials", []), start=1):
        validated, error = validate_record(entry)
        if validated is None:
            raise PublishError(f"manual_officials.json, entry {index}: {error}")
        verified = entry.get("last_verified")
        if verified and not DATE.match(str(verified)):
            raise PublishError(f"manual_officials.json, entry {index}: last_verified must look like 2026-11-10")
        record = {
            "id": validated.record_id, **validated.model_dump(), "last_verified": verified,
            "updated_on": verified, "source_name": entry.get("source_name") or "Added by hand",
            "source_directory_url": None, "verification_status": "manual",
        }
        if entry.get("seat_label"):
            record["seat_label"] = str(entry["seat_label"]).strip()
        if entry.get("bio"):
            record["bio"] = _clean_bio(entry["bio"], f"manual_officials.json, entry {index}")
        records.append(record)

    unique = []
    first: dict[str, dict] = {}
    for record in records:
        if record["id"] in seen:
            kept = first[record["id"]]
            if record["verification_status"] == "manual" or kept["verification_status"] == "manual":
                warnings.append(f"'{record['id']}' appears twice; the second copy was skipped")
            _fill(kept, record)  # two official sources list the same person in the same seat
            continue
        seen.add(record["id"])
        first[record["id"]] = record
        unique.append(record)
    unique, aliases = _merge_municipal(unique)
    by_id = {r["id"]: r for r in unique}
    by_id.update({alias: by_id[target] for alias, target in aliases.items()})

    _apply_profiles(by_id, profiles or {}, warnings)
    _apply_wikipedia(by_id, wikipedia or {})
    _apply_districts(unique, districts or {})

    for record_id, fields in corrections.items():
        if record_id.startswith("_"):
            continue  # examples and comments
        if not isinstance(fields, dict):
            raise PublishError(f"corrections.json, '{record_id}': expected an object of field values")
        if record_id not in by_id:
            warnings.append(f"corrections.json: no record with id '{record_id}' (the official may have left office)")
            continue
        _correct(by_id[record_id], fields, record_id)

    special_districts = _special_districts(special or {})
    special_keys = {d["key"] for d in special_districts}
    for record in unique:
        if record.get("special_district") and record["special_district"] not in special_keys:
            raise PublishError(f"'{record['id']}': special_district '{record['special_district']}' is not in special_districts.json")
    for record in unique:
        record.setdefault("correction_note", None)
        record.setdefault("seat_label", None)
        record.setdefault("bio", None)
        record.setdefault("photo_credit", None)
        record.setdefault("wikipedia_url", None)
    unique.sort(key=lambda r: (r["last_name"].lower(), (r.get("first_name") or "").lower(), r["id"]))

    by_level = {level: sum(r["government_level"] == level for r in unique) for level in LEVELS}
    statuses: dict[str, int] = {}
    for record in unique:
        statuses[record["verification_status"]] = statuses.get(record["verification_status"], 0) + 1

    coverage_rows, collected_total, expected_total = [], 0, 0
    for level, title, expected in EXPECTED_SEATS:
        count = sum(r["government_level"] == level and r["office_title"] == title for r in unique)
        coverage_rows.append({"government_level": level, "office_title": title, "collected": count,
                              "expected": expected, "percent": round(min(count / expected, 1) * 100, 1)})
        collected_total += min(count, expected)
        expected_total += expected

    sources = []
    for key, state in collected.get("sources", {}).items():
        sources.append({
            "key": key, "name": state["name"], "url": state["url"], "level": state["level"],
            "status": state.get("status"), "last_attempt": state.get("last_attempt"),
            "last_successful_collection": state.get("last_successful_collection"),
            "records_collected": len(state.get("records", [])), "last_error": state.get("last_error"),
        })
    sources.sort(key=lambda s: (LEVELS.index(s["level"]) if s["level"] in LEVELS else 9, s["name"]))
    successes = [s["last_successful_collection"] for s in sources if s["last_successful_collection"]]

    report_url = (site.get("report_url") or "").strip()
    if not report_url and env.get("GITHUB_REPOSITORY"):
        server = env.get("GITHUB_SERVER_URL", "https://github.com")
        report_url = f"{server}/{env['GITHUB_REPOSITORY']}/issues/new?template=correction.yml"

    generated = now.isoformat(timespec="seconds")
    meta = {
        "generated_at": generated,
        "last_data_update": max(successes) if successes else None,
        "total": len(unique),
        "by_level": by_level,
        "counties": FLORIDA_COUNTIES,
        "coverage": {
            "rows": coverage_rows,
            "tracked_percent": round(collected_total / expected_total * 100, 1),
            "not_yet_covered": NOT_YET_COVERED,
            "explanation": (
                "The percentage counts only offices that have a source. It is not a share of every elected "
                "official in Florida: offices in the 'not yet covered' list are absent until they are added."
            ),
        },
        "vacancies": _vacancies(vacancies or {}),
        "special_districts": special_districts,
        "municipalities": sorted({r["municipality"] for r in unique if r.get("municipality")}),
        "report_url": report_url or None,
        "contact_email": (site.get("contact_email") or "").strip() or None,
    }
    officials = {
        "metadata": {
            "export_timestamp": generated,
            "data_source": "Florida Government Officials Directory, compiled from official government websites",
            "record_count": len(unique),
            "verification_status": statuses,
            "note": "Empty fields mean the source did not publish that information.",
        },
        "officials": unique,
    }
    return officials, sources, meta, warnings


def to_csv(records: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for record in records:
        row = {k: ("" if record.get(k) is None else record.get(k)) for k in CSV_COLUMNS}
        row["counties"] = "; ".join(record.get("counties") or [])
        writer.writerow(row)
    return buffer.getvalue()


def publish(data_dir: Path = DATA, out_dir: Path = SITE_DATA, now: datetime | None = None, env: dict | None = None):
    officials, sources, meta, warnings = build(
        load_json(data_dir / "collected.json", {"sources": {}}),
        load_json(data_dir / "manual_officials.json", {"officials": []}),
        load_json(data_dir / "corrections.json", {}),
        load_json(data_dir / "site.json", {}),
        now or datetime.now(timezone.utc),
        env,
        profiles=load_json(data_dir / "profiles.json", {}),
        districts=load_json(data_dir / "districts.json", {}),
        vacancies=load_json(data_dir / "vacancies.json", {}),
        wikipedia=load_json(data_dir / "wikipedia.json", {}),
        special=load_json(data_dir / "special_districts.json", {}),
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    dump = lambda obj: json.dumps(obj, indent=1, ensure_ascii=False) + "\n"  # noqa: E731
    (out_dir / "officials.json").write_text(dump(officials), encoding="utf-8")
    (out_dir / "officials.csv").write_text(to_csv(officials["officials"]), encoding="utf-8")
    (out_dir / "sources.json").write_text(dump(sources), encoding="utf-8")
    (out_dir / "meta.json").write_text(dump(meta), encoding="utf-8")
    return officials, warnings


def main() -> None:
    try:
        officials, warnings = publish()
    except PublishError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    for warning in warnings:
        print(f"Warning: {warning}")
    print(f"Published {officials['metadata']['record_count']} records to site/data/")


if __name__ == "__main__":
    main()
