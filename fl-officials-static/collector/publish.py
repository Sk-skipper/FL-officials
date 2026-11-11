"""Build the files the website reads, from the collected data plus your edits.

    python -m collector.publish

Inputs (all in data/):
  collected.json         written by the collector; do not edit by hand
  manual_officials.json  officials you add yourself, e.g. county commissioners
  corrections.json       fixes to individual records, keyed by record id
  site.json              optional settings (report link, contact email)

Outputs (in site/data/): officials.json, officials.csv, sources.json, meta.json

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

from collector.geo import FLORIDA_COUNTIES
from collector.normalize import normalize_email, normalize_party, normalize_phone, normalize_url, parse_district
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
    ("state", "State Senator", 40),
    ("state", "State Representative", 120),
    ("county", "Supervisor of Elections", 67),
]
NOT_YET_COVERED = [
    "Governor, Lieutenant Governor and Cabinet",
    "County commissioners",
    "Sheriffs, clerks of court, property appraisers and tax collectors",
    "School board members",
    "Judges and state attorneys",
    "Mayors, city commissioners and council members (Florida has more than 400 municipalities)",
]

CSV_COLUMNS = [
    "id", "full_name", "first_name", "middle_name", "last_name", "office_title", "government_level",
    "selection_method", "party", "district", "jurisdiction", "county", "municipality", "counties",
    "phone", "email", "official_website", "verification_status", "last_verified", "source_name", "source_url",
]

REQUIRED = {"full_name", "last_name", "office_title", "jurisdiction"}
TEXT_FIELDS = {"full_name", "first_name", "middle_name", "last_name", "office_title", "jurisdiction", "municipality"}
CORRECTABLE = TEXT_FIELDS | {"party", "district", "phone", "email", "official_website", "selection_method"}
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


def build(collected: dict, manual: dict, corrections: dict, site: dict, now: datetime, env: dict | None = None):
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
        records.append({
            "id": validated.record_id, **validated.model_dump(), "last_verified": verified,
            "updated_on": verified, "source_name": entry.get("source_name") or "Added by hand",
            "source_directory_url": None, "verification_status": "manual",
        })

    unique = []
    for record in records:
        if record["id"] in seen:
            warnings.append(f"'{record['id']}' appears twice; the second copy was skipped")
            continue
        seen.add(record["id"])
        unique.append(record)
    by_id = {r["id"]: r for r in unique}

    for record_id, fields in corrections.items():
        if record_id.startswith("_"):
            continue  # examples and comments
        if not isinstance(fields, dict):
            raise PublishError(f"corrections.json, '{record_id}': expected an object of field values")
        if record_id not in by_id:
            warnings.append(f"corrections.json: no record with id '{record_id}' (the official may have left office)")
            continue
        _correct(by_id[record_id], fields, record_id)

    for record in unique:
        record.setdefault("correction_note", None)
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
