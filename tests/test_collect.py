"""Collector tests: change detection, safety rules and the review report."""
import json
from datetime import datetime, timezone

import pytest

from collector.collect import run
from tests.conftest import make_raw

DAY1 = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)
DAY2 = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)

SENATE = make_raw()
WHITFIELD = make_raw(name="Whitfield, Thomas", party="R", district="3", counties=["Leon"])
OKAFOR = make_raw(name="Okafor, Daniel", district="7")


class Fake:
    def __init__(self, rows=None, error=None):
        self.rows, self.error = rows or [], error

    def collect(self):
        if self.error:
            raise self.error
        return [dict(r) for r in self.rows]


@pytest.fixture
def files(tmp_path):
    sources = tmp_path / "sources.json"
    sources.write_text(json.dumps([
        {"key": "fl_senate", "name": "Florida Senate", "url": "https://www.flsenate.gov/Senators",
         "level": "state", "scraper": "fl_senate"},
        {"key": "off", "name": "Disabled", "url": "https://x.gov", "level": "state", "scraper": "fl_house",
         "enabled": False},
    ]))
    return sources, tmp_path / "collected.json"


def collect(files, rows=None, error=None, now=DAY1, **kwargs):
    sources, collected = files
    return run(sources, collected, scraper_factory=lambda *a: Fake(rows, error), now=now, **kwargs)


def stored(files):
    return json.loads(files[1].read_text())["sources"]


def test_first_run_stores_records_and_reports_them_as_new(files):
    outcome = collect(files, [SENATE, WHITFIELD])
    assert outcome["changed"] is True and outcome["failed"] == []
    state = stored(files)["fl_senate"]
    assert list(stored(files)) == ["fl_senate"]  # disabled sources are skipped
    assert state["status"] == "success"
    assert [r["id"] for r in state["records"]] == [
        "state-senator-district-12-ana-rivera", "state-senator-district-3-thomas-whitfield"]
    record = state["records"][0]
    assert (record["full_name"], record["party"], record["last_verified"], record["updated_on"]) == (
        "Ana M. Rivera", "Democratic", "2026-11-01", "2026-11-01")
    assert "**New**" in outcome["report"] and "Ana M. Rivera (State Senator, District 12)" in outcome["report"]


def test_a_repeat_run_with_no_news_is_not_a_change(files):
    collect(files, [SENATE, WHITFIELD])
    outcome = collect(files, [SENATE, WHITFIELD], now=DAY2)
    assert outcome["changed"] is False
    record = stored(files)["fl_senate"]["records"][0]
    assert record["last_verified"] == "2026-11-02"   # confirmed again today
    assert record["updated_on"] == "2026-11-01"      # but its details have not changed
    assert "No data changed." in outcome["report"]


def test_edits_and_departures_are_listed_for_review(files):
    collect(files, [SENATE, WHITFIELD, OKAFOR])
    outcome = collect(files, [make_raw(phone="(850) 487-9999"), OKAFOR], now=DAY2)
    assert outcome["changed"] is True
    report = outcome["report"]
    assert "phone: `(850) 487-5012` → `(850) 487-9999`" in report
    assert "No longer listed" in report and "Thomas Whitfield" in report
    assert stored(files)["fl_senate"]["records"][0]["updated_on"] == "2026-11-02"


def test_a_failing_source_keeps_its_previous_records(files):
    collect(files, [SENATE, WHITFIELD])
    outcome = collect(files, error=RuntimeError("HTTP 503 for the roster"), now=DAY2)
    state = stored(files)["fl_senate"]
    assert outcome["failed"] == ["fl_senate"]
    assert state["status"] == "failed" and "HTTP 503" in state["last_error"]
    assert len(state["records"]) == 2
    assert state["last_successful_collection"] == DAY1.isoformat(timespec="seconds")
    assert "previous records are still published" in outcome["report"]


def test_a_sudden_drop_is_treated_as_a_broken_page(files):
    collect(files, [SENATE, WHITFIELD, OKAFOR])
    outcome = collect(files, [SENATE], now=DAY2)
    state = stored(files)["fl_senate"]
    assert state["status"] == "failed" and "Only 1 records were found, compared with 3" in state["last_error"]
    assert len(state["records"]) == 3
    assert outcome["failed"] == ["fl_senate"]


def test_an_empty_page_is_a_failure(files):
    outcome = collect(files, [])
    assert outcome["failed"] == ["fl_senate"]
    assert "layout may have changed" in stored(files)["fl_senate"]["last_error"]


def test_unreadable_rows_are_reported_not_stored(files):
    outcome = collect(files, [SENATE, make_raw(name="Vacant"), {"county": "Baker", "_error": "no name found"}])
    state = stored(files)["fl_senate"]
    assert state["status"] == "partial" and len(state["records"]) == 1
    assert "no name found" in outcome["report"] and "vacant" in outcome["report"]


def test_possible_duplicates_are_flagged(files):
    outcome = collect(files, [make_raw(name="Smith, Robert"), make_raw(name="Smith, Rob")])
    assert "Possible duplicates" in outcome["report"]
    assert "Robert Smith" in outcome["report"] and "Rob Smith" in outcome["report"]


def test_only_flag_leaves_other_sources_untouched(files, tmp_path):
    sources, collected = files
    data = json.loads(sources.read_text())
    data.append({"key": "fl_house", "name": "Florida House", "url": "https://www.flhouse.gov/Representatives",
                 "level": "state", "scraper": "fl_house"})
    sources.write_text(json.dumps(data))
    collect(files, [SENATE])
    before = stored(files)["fl_senate"]
    collect(files, [OKAFOR], now=DAY2, only="fl_house")
    assert stored(files)["fl_senate"] == before
    with pytest.raises(SystemExit):
        collect(files, [SENATE], only="nope")
