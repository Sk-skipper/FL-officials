"""Collect every source in data/sources.json and update data/collected.json.

    python -m collector.collect                      # all enabled sources
    python -m collector.collect --only fl_senate     # one source
    python -m collector.collect --report report.md   # also write a review report

Safety rules:
  * a source that fails keeps its previous records
  * a source that suddenly returns fewer than half its usual records is
    treated as broken, and its previous records are kept
  * rows that cannot be read are reported, never guessed
  * every change (added, removed, edited) is listed in the report, which the
    GitHub workflow uses as the body of a pull request for a person to review
"""
import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from collector.dedupe import dedupe_batch, find_duplicate_candidates
from collector.scrapers.registry import build_scraper
from collector.validate import validate_record

logger = logging.getLogger("collect")

ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = ROOT / "data" / "sources.json"
COLLECTED_FILE = ROOT / "data" / "collected.json"

# Fields that change on every successful run and are not, by themselves, news.
VOLATILE_RECORD_FIELDS = {"last_verified", "updated_on"}
SUSPICIOUS_DROP = 0.5


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


@dataclass
class SourceResult:
    key: str
    name: str
    status: str = "failed"
    found: int = 0
    kept: int = 0
    with_photo: int = 0
    added: list = field(default_factory=list)
    removed: list = field(default_factory=list)
    changed: list = field(default_factory=list)
    failed_rows: list = field(default_factory=list)
    duplicates_dropped: int = 0
    error: str | None = None
    kept_previous: bool = False


def _substance(record: dict) -> dict:
    return {k: v for k, v in record.items() if k not in VOLATILE_RECORD_FIELDS}


def compare(old_records: list[dict], new_records: list[dict]):
    old = {r["id"]: r for r in old_records}
    new = {r["id"]: r for r in new_records}
    added = [new[i] for i in new if i not in old]
    removed = [old[i] for i in old if i not in new]
    changed = []
    for record_id, record in new.items():
        if record_id not in old:
            continue
        before, after = _substance(old[record_id]), _substance(record)
        diffs = {f: (before.get(f), after.get(f)) for f in sorted(set(before) | set(after))
                 if before.get(f) != after.get(f)}
        if diffs:
            changed.append((record, diffs))
    return added, removed, changed


def collect_source(source: dict, previous: dict, scraper_factory: Callable, now: datetime) -> tuple[dict, SourceResult]:
    """Run one source. Returns its new state for collected.json and a result for the report."""
    now_iso = now.isoformat(timespec="seconds")
    today = now.date().isoformat()
    previous_records = previous.get("records", [])
    result = SourceResult(key=source["key"], name=source["name"])
    state = {
        "name": source["name"],
        "url": source["url"],
        "level": source["level"],
        "status": "failed",
        "last_attempt": now_iso,
        "last_successful_collection": previous.get("last_successful_collection"),
        "last_error": None,
        "records": previous_records,
    }

    try:
        raws = scraper_factory(source["scraper"], source["url"], source.get("config") or {}).collect()
    except Exception as exc:  # one broken source must never stop the others
        logger.exception("%s failed", source["key"])
        result.error = state["last_error"] = f"{type(exc).__name__}: {exc}"[:500]
        result.kept_previous = bool(previous_records)
        result.kept = len(previous_records)
        return state, result

    result.found = len(raws)
    valid = []
    for raw in raws:
        error = raw.get("_error")
        record = None
        if not error:
            record, error = validate_record(raw)
        if record is None:
            shown = {k: v for k, v in raw.items() if k != "_error" and isinstance(v, (str, int, bool)) and v != ""}
            result.failed_rows.append({"error": error, "row": shown})
        else:
            valid.append(record)
    unique, result.duplicates_dropped = dedupe_batch(valid)

    if not unique:
        result.error = state["last_error"] = (
            "No valid records were found. The page layout may have changed, or the page may need JavaScript."
        )
    elif previous_records and len(unique) < SUSPICIOUS_DROP * len(previous_records):
        result.error = state["last_error"] = (
            f"Only {len(unique)} records were found, compared with {len(previous_records)} last time. "
            "The previous records were kept. Check the source page."
        )
    else:
        old_by_id = {r["id"]: r for r in previous_records}
        new_records = []
        for record in unique:
            data = {"id": record.record_id, **record.model_dump(), "last_verified": today}
            old = old_by_id.get(data["id"])
            unchanged = old is not None and _substance(old) == _substance(data)
            data["updated_on"] = old.get("updated_on", today) if unchanged else today
            new_records.append(data)
        new_records.sort(key=lambda r: r["id"])
        result.added, result.removed, result.changed = compare(previous_records, new_records)
        result.status = state["status"] = "partial" if result.failed_rows else "success"
        state["last_successful_collection"] = now_iso
        state["records"] = new_records
        if result.failed_rows:
            state["last_error"] = result.error = f"{len(result.failed_rows)} row(s) could not be read"
        result.kept = len(new_records)
        result.with_photo = sum(1 for r in new_records if r.get("photo_url"))
        return state, result

    result.kept_previous = bool(previous_records)
    result.kept = len(previous_records)
    result.with_photo = sum(1 for r in previous_records if r.get("photo_url"))
    return state, result


def _canonical(collected: dict) -> dict:
    """What counts as a real change: records and source status, not timestamps."""
    return {
        key: {"status": s.get("status"), "records": [_substance(r) for r in s.get("records", [])]}
        for key, s in collected.get("sources", {}).items()
    }


def _label(record: dict) -> str:
    place = f"District {record['district']}" if record.get("district") else record.get("jurisdiction")
    return f"{record['full_name']} ({record['office_title']}, {place})"


def write_report(results: list[SourceResult], duplicates: list[tuple], by_id: dict, changed: bool) -> str:
    lines = ["## Collection report", ""]
    if changed:
        lines += ["Official sources show changes. Review them below, then **merge** this pull request to publish "
                  "them, or **close** it to discard them.", ""]
    else:
        lines += ["No data changed.", ""]
    lines += ["| Source | Result | Records | With photo | Added | Removed | Changed | Unreadable rows |",
              "|---|---|---:|---:|---:|---:|---:|---:|"]
    labels = {"success": "OK", "partial": "OK, some rows unreadable", "failed": "Failed"}
    for r in results:
        lines.append(f"| {r.name} | {labels.get(r.status, r.status)} | {r.kept} | {r.with_photo} | {len(r.added)} | "
                     f"{len(r.removed)} | {len(r.changed)} | {len(r.failed_rows)} |")
    lines.append("")

    for r in results:
        if not (r.error or r.added or r.removed or r.changed or r.failed_rows):
            continue
        lines += [f"### {r.name}", ""]
        if r.error:
            lines.append(f"> {r.error}" + (" The previous records are still published." if r.kept_previous else ""))
            lines.append("")
        if r.added:
            lines += ["**New**", ""] + [f"- {_label(x)}" for x in r.added] + [""]
        if r.removed:
            lines += ["**No longer listed** (they may have left office; check before merging)", ""]
            lines += [f"- {_label(x)}" for x in r.removed] + [""]
        if r.changed:
            lines += ["**Changed**", ""]
            for record, diffs in r.changed:
                parts = "; ".join(f"{f}: `{a}` → `{b}`" for f, (a, b) in diffs.items())
                lines.append(f"- {_label(record)}: {parts}")
            lines.append("")
        if r.failed_rows:
            lines += ["<details><summary>Rows that could not be read</summary>", ""]
            lines += [f"- {row['error']}: `{json.dumps(row['row'], ensure_ascii=False)[:200]}`"
                      for row in r.failed_rows[:50]]
            lines += ["", "</details>", ""]

    if duplicates:
        lines += ["### Possible duplicates", "", "These look like the same person listed twice. "
                  "If so, fix the source or add a correction.", ""]
        for a, b, score in duplicates:
            lines.append(f"- {_label(by_id[a])} and {_label(by_id[b])} ({round(score * 100)}% similar)")
        lines.append("")
    return "\n".join(lines)


def run(sources_file: Path = SOURCES_FILE, collected_file: Path = COLLECTED_FILE, only: str | None = None,
        scraper_factory: Callable = build_scraper, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    sources = [s for s in load_json(sources_file, []) if s.get("enabled", True)]
    if only:
        if only not in {s["key"] for s in sources}:
            raise SystemExit(f"No enabled source with key '{only}' in {sources_file.name}")
    previous = load_json(collected_file, {"sources": {}})
    previous_sources = previous.get("sources", {})

    new_sources: dict[str, dict] = {}
    results: list[SourceResult] = []
    for source in sources:
        if only and source["key"] != only:
            if source["key"] in previous_sources:
                new_sources[source["key"]] = previous_sources[source["key"]]
            continue
        logger.info("Collecting %s", source["name"])
        state, result = collect_source(source, previous_sources.get(source["key"], {}), scraper_factory, now)
        new_sources[source["key"]] = state
        results.append(result)
        logger.info("%s: %s, %d records", source["name"], result.status, result.kept)

    collected = {"sources": new_sources}
    changed = _canonical(collected) != _canonical(previous)
    write_json(collected_file, collected)

    all_records = [r for s in new_sources.values() for r in s["records"]]
    by_id = {r["id"]: r for r in all_records}
    duplicates = find_duplicate_candidates(all_records)
    return {
        "changed": changed,
        "failed": [r.key for r in results if r.status == "failed"],
        "report": write_report(results, duplicates, by_id, changed),
        "results": results,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", default="", help="collect a single source by its key")
    parser.add_argument("--report", default="", help="write a Markdown report to this file")
    args = parser.parse_args()

    outcome = run(only=args.only.strip() or None)
    if args.report:
        Path(args.report).write_text(outcome["report"], encoding="utf-8")
    print(outcome["report"])

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as fh:
            fh.write(f"changed={'true' if outcome['changed'] else 'false'}\n")
            fh.write(f"failed={'true' if outcome['failed'] else 'false'}\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
