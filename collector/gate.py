"""Decide whether a collection run should show as failed, and name every failing source.

    python -m collector.gate report.json          # prints GitHub ::error:: / ::warning:: lines; exits 1 to fail the run

A red run has to mean something a person should fix today, or it gets ignored:
  * a statewide or county-wide source failing fails the run on the first day: it covers a whole county or more;
  * a city or town source failing is a warning: one council's previous list stays published, and with 200+ city
    websites a few are always mid-redesign. Each warning says how long it has been failing, newest first;
  * a site that refuses us (robots.txt, or HTTP 401/403) is a warning too: that's the site's choice and nothing to
    fix here.
"""
import json
import sys
from datetime import date


def classify(rows: list[dict], today: date) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    failing = [r for r in rows if r["status"] == "failed"]
    failing.sort(key=lambda r: (r.get("failing_since") or "9999"), reverse=True)  # newest failures first
    for r in failing:
        since = r.get("failing_since")
        days = (today - date.fromisoformat(since)).days + 1 if since else 1
        age = "new today" if days <= 1 else f"failing {days} days, since {since}"
        error = (r.get("error") or "").replace("\n", " ")[:300]
        line = f"{r['name']} ({r['key']}): {age}. {error}"
        refused = "robots.txt disallows" in error or "HTTP 403" in error or "HTTP 401" in error
        if r.get("level") in ("state", "federal", "county") and not refused:
            errors.append(line)
        else:
            warnings.append(line)
    for r in rows:
        if r.get("held"):
            warnings.append(f"{r['name']} ({r['key']}): held for review, {r['removed']} removed and {r['added']} added; "
                            "see the pull request.")
    return errors, warnings


def main() -> None:
    rows = json.loads(open(sys.argv[1], encoding="utf-8").read())
    errors, warnings = classify(rows, date.today())
    for line in errors:
        print(f"::error::{line}")
    for line in warnings:
        print(f"::warning::{line}")
    failed = sum(1 for r in rows if r["status"] == "failed")
    print(f"{len(rows)} sources: {failed} failed ({len(errors)} statewide or county-wide), "
          f"{sum(1 for r in rows if r.get('held'))} held for review.")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
