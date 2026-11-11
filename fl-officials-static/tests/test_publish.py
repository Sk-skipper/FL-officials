"""Publish tests: corrections, hand-added officials, output files."""
import csv
import io
import json
from datetime import datetime, timezone

import pytest

from collector.publish import PublishError, build, publish

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
SENATOR_ID = "state-senator-district-12-ana-rivera"


def collected():
    return {"sources": {"fl_senate": {
        "name": "Florida Senate", "url": "https://www.flsenate.gov/Senators", "level": "state",
        "status": "success", "last_attempt": "2026-11-10T09:00:00+00:00",
        "last_successful_collection": "2026-11-10T09:00:00+00:00", "last_error": None,
        "records": [{
            "id": SENATOR_ID, "full_name": "Ana M. Rivera", "first_name": "Ana", "middle_name": "M.",
            "last_name": "Rivera", "office_title": "State Senator", "government_level": "state",
            "selection_method": "elected", "party": "Democratic", "district": "12", "district_number": 12,
            "jurisdiction": "Florida", "statewide": False, "county": None, "counties": ["Broward", "Palm Beach"],
            "municipality": None, "phone": "(850) 487-5012", "email": None,
            "official_website": "https://www.flsenate.gov/Senators/S12",
            "source_url": "https://www.flsenate.gov/Senators", "last_verified": "2026-11-10",
            "updated_on": "2026-11-01",
        }],
    }}}


MAYOR = {
    "name": "Samuel Brooks", "office_title": "Mayor", "government_level": "municipal",
    "selection_method": "elected", "party": "Nonpartisan", "jurisdiction": "West Park", "county": "Broward",
    "municipality": "West Park", "phone": "954-519-0100",
    "source_url": "https://www.cityofwestpark.example.gov/commission", "source_name": "City of West Park",
    "last_verified": "2026-11-09",
}


def run_build(manual=None, corrections=None, site=None, env=None):
    return build(collected(), {"officials": manual or []}, corrections or {}, site or {}, NOW, env or {})


def test_collected_records_are_published_with_their_source():
    officials, sources, meta, warnings = run_build()
    record = officials["officials"][0]
    assert (record["source_name"], record["source_directory_url"], record["verification_status"]) == (
        "Florida Senate", "https://www.flsenate.gov/Senators", "source_verified")
    assert sources[0]["records_collected"] == 1
    assert meta["by_level"] == {"federal": 0, "state": 1, "county": 0, "municipal": 0}
    assert meta["last_data_update"] == "2026-11-10T09:00:00+00:00"
    assert len(meta["counties"]) == 67
    assert warnings == []


def test_hand_added_officials_are_validated_and_labelled():
    officials, *_ = run_build(manual=[MAYOR])
    mayor = next(r for r in officials["officials"] if r["last_name"] == "Brooks")
    assert mayor["id"] == "mayor-west-park-samuel-brooks"
    assert (mayor["verification_status"], mayor["source_name"], mayor["phone"]) == (
        "manual", "City of West Park", "(954) 519-0100")
    with pytest.raises(PublishError, match="entry 1"):
        run_build(manual=[{**MAYOR, "county": "Gotham"}])
    with pytest.raises(PublishError, match="last_verified"):
        run_build(manual=[{**MAYOR, "last_verified": "yesterday"}])


def test_corrections_are_applied_and_validated():
    officials, *_ = run_build(corrections={
        "_example": {"phone": "anything"},  # entries starting with _ are ignored
        SENATOR_ID: {"phone": "850.487.7777", "email": "Rivera.Ana@FLSenate.gov", "note": "Confirmed with the office"},
    })
    record = officials["officials"][0]
    assert (record["phone"], record["email"]) == ("(850) 487-7777", "rivera.ana@flsenate.gov")
    assert record["verification_status"] == "corrected"
    assert record["correction_note"] == "Confirmed with the office"


def test_a_correction_can_clear_a_wrong_value():
    officials, *_ = run_build(corrections={SENATOR_ID: {"phone": None}})
    assert officials["officials"][0]["phone"] is None


@pytest.mark.parametrize("fields,message", [
    ({"phone": "12"}, "not a valid phone"),
    ({"email": "not an email"}, "not a valid email"),
    ({"last_name": ""}, "cannot be empty"),
    ({"favourite_color": "blue"}, "cannot be corrected"),
])
def test_bad_corrections_stop_the_publish(fields, message):
    with pytest.raises(PublishError, match=message):
        run_build(corrections={SENATOR_ID: fields})


def test_a_correction_for_a_departed_official_is_a_warning():
    *_, warnings = run_build(corrections={"state-senator-district-99-gone-away": {"phone": "850-487-1111"}})
    assert "no record with id 'state-senator-district-99-gone-away'" in warnings[0]


def test_report_link_defaults_to_the_repository_issues():
    *_, meta, _ = run_build(env={"GITHUB_REPOSITORY": "someone/fl-officials", "GITHUB_SERVER_URL": "https://github.com"})
    assert meta["report_url"] == "https://github.com/someone/fl-officials/issues/new?template=correction.yml"
    *_, meta, _ = run_build(site={"report_url": "https://example.org/report"})
    assert meta["report_url"] == "https://example.org/report"


def test_coverage_is_reported_honestly():
    *_, meta, _ = run_build()
    rows = {r["office_title"]: r for r in meta["coverage"]["rows"]}
    assert (rows["State Senator"]["collected"], rows["State Senator"]["expected"]) == (1, 40)
    assert meta["coverage"]["tracked_percent"] == round(1 / 257 * 100, 1)
    assert any("commissioners" in item for item in meta["coverage"]["not_yet_covered"])


def test_publish_writes_all_site_files(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "collected.json").write_text(json.dumps(collected()))
    (data / "manual_officials.json").write_text(json.dumps({"officials": [MAYOR]}))
    out = tmp_path / "site-data"
    publish(data, out, NOW, env={})
    assert sorted(p.name for p in out.iterdir()) == ["meta.json", "officials.csv", "officials.json", "sources.json"]
    payload = json.loads((out / "officials.json").read_text())
    assert payload["metadata"]["record_count"] == 2
    assert payload["metadata"]["verification_status"] == {"source_verified": 1, "manual": 1}
    rows = list(csv.DictReader(io.StringIO((out / "officials.csv").read_text())))
    assert [r["last_name"] for r in rows] == ["Brooks", "Rivera"]
    assert rows[1]["counties"] == "Broward; Palm Beach"
    assert rows[0]["email"] == ""  # missing stays empty


def test_invalid_json_gives_a_clear_error(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "corrections.json").write_text('{"oops": ')
    with pytest.raises(PublishError, match="corrections.json is not valid JSON"):
        publish(data, tmp_path / "out", NOW, env={})
