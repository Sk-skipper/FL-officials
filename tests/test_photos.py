"""Portrait handling: validation, each source, the report column and corrections.
The people in these fixtures are fictional."""
import json
from datetime import datetime, timezone

import pytest

from collector.collect import SourceResult, collect_source, write_report
from collector.normalize import normalize_photo_url
from collector.publish import PublishError, build, to_csv
from collector.scrapers.base import FetchError
from collector.scrapers.congress import add_house_photos, add_senate_photos, house_members, photo_url
from collector.scrapers.fl_house import parse_fl_house
from collector.scrapers.fl_supervisors import parse_supervisor_page
from collector.scrapers.us_house import USHouseScraper
from collector.scrapers.us_senate import parse_us_senate
from collector.validate import validate_record
from tests.conftest import make_raw
from tests.test_scrapers import US_HOUSE_HTML, US_SENATE_XML

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)

LEGISLATORS = [
    {"id": {"bioguide": "H000001"}, "name": {"last": "Hartley"}, "terms": [{"type": "rep", "state": "FL", "district": 1}]},
    {"id": {"bioguide": "W000125"}, "name": {"last": "Wasserman Schultz"}, "terms": [{"type": "rep", "state": "FL", "district": 25}]},
    {"id": {"bioguide": "C000002"}, "name": {"last": "Castillo"}, "terms": [{"type": "sen", "state": "FL"}]},
    {"id": {"bioguide": "E000003"}, "name": {"last": "Elsewhere"}, "terms": [{"type": "rep", "state": "AL", "district": 1}]},
    # an old term followed by a new one: only the latest term counts
    {"id": {"bioguide": "M000004"}, "name": {"last": "Mover"},
     "terms": [{"type": "rep", "state": "FL", "district": 9}, {"type": "rep", "state": "GA", "district": 3}]},
]


# -- validation ---------------------------------------------------------------------------------
@pytest.mark.parametrize("raw, expected", [
    ("https://example.gov/photos/ana.jpg", "https://example.gov/photos/ana.jpg"),
    ("  https://example.gov/p.jpg  ", "https://example.gov/p.jpg"),
    ("http://example.gov/p.jpg", None),          # insecure: would break the secure page
    ("javascript:alert(1)", None),
    ("data:image/png;base64,AAAA", None),
    ("/relative/p.jpg", None),
    ("https://nodot", None),
    ("", None),
    (None, None),
])
def test_normalize_photo_url(raw, expected):
    assert normalize_photo_url(raw) == expected


def test_photo_url_passes_validation_and_bad_values_are_dropped_not_repaired():
    good, _ = validate_record(make_raw(photo_url="https://example.gov/ana.jpg"))
    assert good.photo_url == "https://example.gov/ana.jpg"
    bad, error = validate_record(make_raw(photo_url="http://example.gov/ana.jpg"))
    assert error is None and bad.photo_url is None  # the record is kept; only the photo is dropped
    assert validate_record(make_raw())[0].photo_url is None


# -- U.S. Senate ----------------------------------------------------------------------------------
def test_senate_photo_comes_from_the_bioguide_id():
    xml = US_SENATE_XML.replace("<party>R</party>", "<party>R</party><bioguide_id>C000002</bioguide_id>", 1)
    [record] = parse_us_senate(xml, "https://x.gov/senators.xml")
    assert record["photo_url"] == "https://unitedstates.github.io/images/congress/450x550/C000002.jpg"


def test_senate_without_a_bioguide_id_has_no_photo_instead_of_a_wrong_one():
    [record] = parse_us_senate(US_SENATE_XML, "https://x.gov/senators.xml")
    assert record["photo_url"] is None


def test_photo_url_rejects_malformed_ids():
    assert photo_url("C000002") and photo_url(" c000002 ").endswith("C000002.jpg")
    assert photo_url("../../etc") is None and photo_url("") is None and photo_url(None) is None


def test_senate_fallback_matches_by_surname():
    records = [{"name": "Castillo, Maria"}, {"name": "Unknown, Person"}]
    assert add_senate_photos(records, LEGISLATORS) == 1
    assert records[0]["photo_url"].endswith("C000002.jpg") and "photo_url" not in records[1]


# -- U.S. House -----------------------------------------------------------------------------------
def test_house_members_uses_each_persons_latest_term_in_the_right_state():
    members = house_members(LEGISLATORS)
    assert sorted(members) == ["1", "25"]  # not Alabama, not the senator, not someone who moved to Georgia


def test_house_photos_match_by_district_and_surname():
    records = [{"name": "Hartley, James", "district": "1st"}, {"name": "Wasserman Schultz, Debbie", "district": "District 25"}]
    assert add_house_photos(records, LEGISLATORS) == 2
    assert records[0]["photo_url"].endswith("H000001.jpg") and records[1]["photo_url"].endswith("W000125.jpg")


def test_a_stale_dataset_never_puts_one_persons_face_next_to_another_name():
    records = [{"name": "Newcomer, Alex", "district": "1"}]  # the seat changed hands; the dataset has not caught up
    assert add_house_photos(records, LEGISLATORS) == 0
    assert "photo_url" not in records[0]


class FakeClient:
    def __init__(self, pages: dict):
        self.pages = pages

    def get(self, url):
        value = self.pages[url]
        if isinstance(value, Exception):
            raise value
        return value


def _house(client):
    return USHouseScraper("https://www.house.gov/representatives", {}, client)


def test_house_scraper_adds_photos():
    from collector.scrapers.congress import LEGISLATORS_URL
    client = FakeClient({"https://www.house.gov/representatives": US_HOUSE_HTML, LEGISLATORS_URL: json.dumps(LEGISLATORS)})
    records = _house(client).collect()
    # The directory writes districts as "1st" and "25th"; they must still match the dataset's plain numbers.
    by_district = {r["district"]: r for r in records}
    assert by_district["1st"]["photo_url"].endswith("H000001.jpg")
    assert by_district["25th"]["photo_url"].endswith("W000125.jpg")
    assert len(records) == 2


def test_house_scraper_keeps_every_record_when_the_photo_dataset_is_unavailable():
    from collector.scrapers.congress import LEGISLATORS_URL
    for failure in (FetchError("HTTP 404"), "this is not json"):
        client = FakeClient({"https://www.house.gov/representatives": US_HOUSE_HTML, LEGISLATORS_URL: failure})
        records = _house(client).collect()
        assert len(records) == 2 and all(not r.get("photo_url") for r in records)


# -- Florida House --------------------------------------------------------------------------------
def test_fl_house_reads_the_portrait_and_resolves_relative_links():
    html = """
    <div class="team-box">
      <a href="/Sections/Representatives/details.aspx?MemberId=4801&LegislativeTermId=91"><img src="/FileStores/Web/Imaging/Member/4801.jpg"></a>
      <h5>Okafor, Daniel</h5><p>Republican &mdash; District: 101</p>
    </div>"""
    [record] = parse_fl_house(html, "https://www.flhouse.gov/Representatives")
    assert record["photo_url"] == "https://www.flhouse.gov/FileStores/Web/Imaging/Member/4801.jpg"
    assert validate_record(record)[0].photo_url == record["photo_url"]


@pytest.mark.parametrize("src", ["/images/logo.png", "/img/no-photo.gif", "/img/spacer.gif", "data:image/gif;base64,R0lGOD"])
def test_fl_house_ignores_icons_and_placeholders(src):
    html = f"""
    <div class="team-box"><a href="/Sections/Representatives/details.aspx?MemberId=1&LegislativeTermId=91"><img src="{src}"></a>
    <h5>Okafor, Daniel</h5><p>District: 101</p></div>"""
    [record] = parse_fl_house(html, "https://www.flhouse.gov/Representatives")
    assert record["photo_url"] is None


def test_fl_house_http_portrait_is_dropped_at_validation():
    html = """
    <div class="team-box"><a href="/Sections/Representatives/details.aspx?MemberId=1&LegislativeTermId=91"><img src="http://www.flhouse.gov/a.jpg"></a>
    <h5>Okafor, Daniel</h5><p>District: 101</p></div>"""
    [record] = parse_fl_house(html, "https://www.flhouse.gov/Representatives")
    assert validate_record(record)[0].photo_url is None


# -- Supervisors of Elections ---------------------------------------------------------------------
def test_supervisor_page_heading_is_not_mistaken_for_a_name():
    html = "<div><h2>Contact your Supervisor of Elections</h2><p>Office hours 8-5</p></div>"
    raw = parse_supervisor_page(html, "Alachua", "https://dos.elections.myflorida.com/supervisors/countyInfo.asp?county=ALA")
    assert "_error" in raw and "name" not in raw


# -- report, publish ------------------------------------------------------------------------------
def test_report_shows_how_many_records_have_a_photo():
    source = {"key": "t", "name": "Test source", "url": "https://x.gov", "level": "state", "scraper": "t"}
    raws = [make_raw(photo_url="https://example.gov/a.jpg"), make_raw(name="Okafor, Daniel", district="101")]

    class Scraper:
        def collect(self):
            return raws

    state, result = collect_source(source, {}, lambda *a: Scraper(), NOW)
    assert (result.kept, result.with_photo) == (2, 1)
    report = write_report([result], [], {}, True)
    assert "| With photo |" in report and "| Test source | OK | 2 | 1 |" in report


def _publish(corrections=None, collected_records=None):
    record = {"id": "state-senator-district-12-ana-rivera", "full_name": "Ana M. Rivera", "first_name": "Ana", "last_name": "Rivera",
              "office_title": "State Senator", "government_level": "state", "jurisdiction": "Florida"}
    collected = {"sources": {"s": {"name": "S", "url": "https://x.gov", "level": "state", "status": "success",
                                   "records": collected_records or [record]}}}
    return build(collected, {"officials": []}, corrections or {}, {}, NOW, env={})


def test_a_correction_can_set_or_remove_a_photo():
    officials, *_ = _publish({"state-senator-district-12-ana-rivera": {"photo_url": "https://example.gov/ana.jpg"}})
    assert officials["officials"][0]["photo_url"] == "https://example.gov/ana.jpg"
    officials, *_ = _publish({"state-senator-district-12-ana-rivera": {"photo_url": None}},
                             [{"id": "state-senator-district-12-ana-rivera", "full_name": "Ana M. Rivera", "first_name": "Ana",
                               "last_name": "Rivera", "office_title": "State Senator", "government_level": "state",
                               "jurisdiction": "Florida", "photo_url": "https://example.gov/wrong.jpg"}])
    assert officials["officials"][0]["photo_url"] is None


def test_a_correction_with_an_insecure_photo_link_stops_the_deploy():
    with pytest.raises(PublishError, match="photo url"):
        _publish({"state-senator-district-12-ana-rivera": {"photo_url": "http://example.gov/ana.jpg"}})


def test_csv_includes_the_photo_link():
    officials, *_ = _publish({"state-senator-district-12-ana-rivera": {"photo_url": "https://example.gov/ana.jpg"}})
    header, row = to_csv(officials["officials"]).splitlines()[:2]
    assert "photo_url" in header.split(",") and "https://example.gov/ana.jpg" in row
