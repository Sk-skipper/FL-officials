"""Scraper tests using mocked HTML. No network access is needed.

The people in these fixtures are fictional. The markup mirrors the structure
each parser expects from its source.
"""
import pytest
import requests

from collector.validate import validate_record
from collector.scrapers.base import BaseScraper, FetchError, PoliteHttpClient, RobotsDisallowed
from collector.scrapers.fl_house import parse_fl_house
from collector.scrapers.fl_senate import parse_fl_senate
from collector.scrapers.fl_supervisors import parse_supervisor_index, parse_supervisor_page
from collector.scrapers.generic_directory import SourceConfigError, parse_generic_directory
from collector.scrapers.us_house import parse_us_house
from collector.scrapers.us_senate import parse_us_senate

FL_SENATE_HTML = """
<table id="Senators"><thead><tr><th>Senator</th><th>District</th><th>Party</th><th>Counties</th></tr></thead>
<tbody>
<tr><th><a class="senatorLink" href="/Senators/S1">Whitfield, Thomas</a></th><td>1</td><td>R</td>
    <td>Escambia, Santa Rosa, part of Okaloosa</td></tr>
<tr><th><a class="senatorLink" href="/Senators/S2">Vacant</a></th><td>2</td><td></td><td>Bay</td></tr>
<tr><th><a class="senatorLink" href="/Senators/S12">Rivera, Ana M.</a></th><td>12</td><td>D</td>
    <td>Broward and Palm Beach</td></tr>
</tbody></table>
<a href="/Senators/Find">Find your senator</a>
"""

FL_HOUSE_HTML = """
<div class="member-list">
  <div class="team-box">
    <a href="/Sections/Representatives/details.aspx?MemberId=4801&LegislativeTermId=91"><img alt="photo"></a>
    <h5>Okafor, Daniel</h5><p>Republican &mdash; District: 101</p>
    <a href="/Sections/Representatives/details.aspx?MemberId=4801&LegislativeTermId=91">Details</a>
  </div>
  <div class="team-box">
    <a href="/Sections/Representatives/details.aspx?MemberId=4802&LegislativeTermId=91"><h5>Lindqvist, Greta</h5></a>
    <p>Democrat</p><p>District: 7</p>
  </div>
  <div class="team-box">
    <a href="/Sections/Representatives/details.aspx?MemberId=4803&LegislativeTermId=91"><h5>Vacant</h5></a>
    <p>District: 9</p>
  </div>
</div>
"""

US_SENATE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<contact_information>
  <member><member_full>Castillo (R-FL)</member_full><last_name>Castillo</last_name><first_name>Maria</first_name>
    <party>R</party><state>FL</state><address>100 Hart Senate Office Building Washington DC 20510</address>
    <phone>(202) 224-0000</phone><email>https://www.castillo.senate.gov/contact</email>
    <website>https://www.castillo.senate.gov</website><class>Class I</class></member>
  <member><member_full>Other (D-GA)</member_full><last_name>Other</last_name><first_name>Someone</first_name>
    <party>D</party><state>GA</state><phone>(202) 224-1111</phone><website>https://www.other.senate.gov</website></member>
</contact_information>
"""

US_HOUSE_HTML = """
<table class="table"><caption id="state-alabama">Alabama</caption>
<thead><tr><th>District</th><th>Name</th><th>Party</th><th>Office Room</th><th>Phone</th><th>Committee Assignment</th></tr></thead>
<tbody><tr><td>1st</td><td><a href="https://elsewhere.house.gov">Elsewhere, Pat</a></td><td>R</td><td>1</td>
<td>(202) 225-0001</td><td>Rules</td></tr></tbody></table>
<table class="table"><caption id="state-florida">Florida</caption>
<thead><tr><th>District</th><th>Name</th><th>Party</th><th>Office Room</th><th>Phone</th><th>Committee Assignment</th></tr></thead>
<tbody>
<tr><td>1st</td><td><a href="https://hartley.house.gov">Hartley, James</a></td><td>R</td><td>2021 RHOB</td>
<td>(202) 225-0101</td><td>Armed Services</td></tr>
<tr><td>25th</td><td><a href="https://wassermanschultz.house.gov/">Wasserman Schultz, Debbie</a></td><td>D</td>
<td>270 CHOB</td><td>(202) 225-0125</td><td>Appropriations</td></tr>
<tr><td>6th</td><td>Vacancy</td><td></td><td></td><td></td><td></td></tr>
</tbody></table>
"""

SUPERVISOR_INDEX_HTML = """
<ul><li><a href="countyInfo.asp?county=ALA">Alachua</a></li>
<li><a href="countyInfo.asp?county=STJ">St. Johns</a></li>
<li><a href="/contact">Contact the Division</a></li></ul>
"""

SUPERVISOR_PAGE_HTML = """
<nav><a href="https://dos.fl.gov/elections/">Elections</a></nav>
<div id="content"><h2>Alachua County</h2>
<p>Linda Nguyen<br>Supervisor of Elections</p>
<p>515 North Main Street, Suite 300<br>Gainesville, FL 32601</p>
<p>Phone: 352-374-5252<br>Fax: 352-374-5264</p>
<p>Email: <a href="mailto:LNguyen@example.gov">lnguyen@example.gov</a></p>
<p>Web Address: <a href="https://www.votealachua.example.gov">https://www.votealachua.example.gov</a></p></div>
"""

COMMISSION_HTML = """
<table class="commission"><tbody>
<tr><td><a href="/commission/d1">Samuel Brooks</a></td><td>Mayor</td><td></td>
    <td><a href="tel:954-519-0100">954-519-0100</a></td><td><a href="mailto:sbrooks@example.gov">Email</a></td></tr>
<tr><td>Priya Raman</td><td>Commissioner</td><td>District 2</td><td>954-519-0102</td><td></td></tr>
<tr><td>Walter Finch</td><td>City Manager</td><td></td><td>954-519-0199</td><td></td></tr>
</tbody></table>
"""

COMMISSION_CONFIG = {
    "row_selector": "table.commission tbody tr",
    "fields": {
        "name": "td:nth-of-type(1)", "title": "td:nth-of-type(2)", "district": "td:nth-of-type(3)",
        "phone": "td:nth-of-type(4) a, td:nth-of-type(4)", "email": "a[href^='mailto:']",
        "website": "td:nth-of-type(1) a",
    },
    "title_must_contain": ["Mayor", "Commissioner"],
    "county": "Broward", "municipality": "West Park", "selection_method": "elected",
}


def _validated(raws):
    results = [validate_record(raw) for raw in raws]
    assert all(error is None for _, error in results), [e for _, e in results]
    return [record for record, _ in results]


def test_fl_senate_parser():
    raws = parse_fl_senate(FL_SENATE_HTML, "https://www.flsenate.gov/Senators")
    records = _validated(raws)
    assert [r.full_name for r in records] == ["Thomas Whitfield", "Ana M. Rivera"]  # vacant seat skipped
    first = records[0]
    assert (first.district, first.party, first.office_title) == ("1", "Republican", "State Senator")
    assert first.counties == ["Escambia", "Santa Rosa", "Okaloosa"]
    assert first.official_website == "https://www.flsenate.gov/Senators/S1"
    assert first.phone is None  # the roster has no phone numbers, so none are stored


def test_fl_house_parser():
    records = _validated(parse_fl_house(FL_HOUSE_HTML, "https://www.flhouse.gov/Representatives"))
    assert [(r.full_name, r.party, r.district) for r in records] == [
        ("Daniel Okafor", "Republican", "101"), ("Greta Lindqvist", "Democratic", "7"),
    ]
    assert "MemberId=4801" in records[0].official_website


def test_fl_house_parser_refuses_to_guess_when_cards_are_ambiguous():
    html = """<div>District: 5 <a href="?MemberId=1">A One</a> <a href="?MemberId=2">B Two</a></div>"""
    assert parse_fl_house(html, "https://www.flhouse.gov/Representatives") == []


def test_us_senate_parser_keeps_only_florida():
    records = _validated(parse_us_senate(US_SENATE_XML, "https://www.senate.gov/x.xml"))
    assert len(records) == 1
    senator = records[0]
    assert (senator.full_name, senator.party, senator.statewide) == ("Maria Castillo", "Republican", True)
    assert senator.phone == "(202) 224-0000"
    assert senator.email is None  # the feed holds a contact-form URL, which is not an email address
    assert senator.official_website == "https://www.castillo.senate.gov"


def test_us_house_parser_reads_only_the_florida_table():
    records = _validated(parse_us_house(US_HOUSE_HTML, "https://www.house.gov/representatives"))
    assert [(r.full_name, r.district, r.party) for r in records] == [
        ("James Hartley", "1", "Republican"), ("Debbie Wasserman Schultz", "25", "Democratic"),
    ]
    assert records[1].last_name == "Wasserman Schultz"
    assert records[0].phone == "(202) 225-0101"


def test_supervisor_index_and_page():
    index = parse_supervisor_index(SUPERVISOR_INDEX_HTML, "https://dos.elections.myflorida.com/supervisors/")
    assert index == [
        ("Alachua", "https://dos.elections.myflorida.com/supervisors/countyInfo.asp?county=ALA"),
        ("St. Johns", "https://dos.elections.myflorida.com/supervisors/countyInfo.asp?county=STJ"),
    ]
    raw = parse_supervisor_page(SUPERVISOR_PAGE_HTML, "Alachua", index[0][1])
    record = _validated([raw])[0]
    assert (record.full_name, record.office_title, record.county) == ("Linda Nguyen", "Supervisor of Elections", "Alachua")
    assert record.phone == "(352) 374-5252"
    assert record.email == "lnguyen@example.gov"
    assert record.official_website == "https://www.votealachua.example.gov"
    assert record.jurisdiction == "Alachua County"


def test_supervisor_page_without_a_recognisable_name_is_reported_not_guessed():
    raw = parse_supervisor_page("<div><h2>Baker County</h2><p>Office closed.</p></div>", "Baker", "https://x.gov/p")
    assert "_error" in raw and "name" not in raw


def test_generic_directory_parser():
    raws = parse_generic_directory(COMMISSION_HTML, "https://www.cityofwestpark.example.gov/commission",
                                   COMMISSION_CONFIG, "municipal")
    records = _validated(raws)
    assert [(r.full_name, r.office_title) for r in records] == [
        ("Samuel Brooks", "Mayor"), ("Priya Raman", "Commissioner"),  # appointed city manager filtered out
    ]
    mayor, commissioner = records
    assert mayor.phone == "(954) 519-0100"
    assert mayor.email == "sbrooks@example.gov"
    assert mayor.official_website == "https://www.cityofwestpark.example.gov/commission/d1"
    assert (mayor.municipality, mayor.county, mayor.government_level) == ("West Park", "Broward", "municipal")
    assert commissioner.district == "2" and commissioner.email is None


def test_generic_directory_requires_complete_config():
    with pytest.raises(SourceConfigError):
        parse_generic_directory("<html></html>", "https://x.gov", {"row_selector": "tr"}, "county")
    with pytest.raises(SourceConfigError):
        parse_generic_directory("<html></html>", "https://x.gov",
                                {"row_selector": "tr", "fields": {"name": "td"}, "county": "Leon"}, "municipal")


# -- HTTP client behaviour --------------------------------------------------
class FakeResponse:
    def __init__(self, status_code=200, text="", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}


class FakeSession:
    def __init__(self, pages, robots="User-agent: *\nDisallow: /private/\n"):
        self.pages = {k: list(v) if isinstance(v, list) else [v] for k, v in pages.items()}
        self.robots = robots
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, headers))
        if url.endswith("/robots.txt"):
            if isinstance(self.robots, Exception):
                raise self.robots
            return self.robots if isinstance(self.robots, FakeResponse) else FakeResponse(200, self.robots)
        queue = self.pages[url]
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        return item


def make_client(session, **kwargs):
    sleeps = []
    client = PoliteHttpClient("TestBot/1.0 (+https://example.org/bot)", delay_seconds=2.0, max_retries=2,
                              session=session, sleep=sleeps.append, clock=lambda: 0.0, **kwargs)
    return client, sleeps


def test_client_identifies_itself_and_waits_between_requests():
    session = FakeSession({"https://a.gov/1": FakeResponse(text="one"), "https://a.gov/2": FakeResponse(text="two")})
    client, sleeps = make_client(session)
    assert client.get("https://a.gov/1") == "one"
    assert client.get("https://a.gov/2") == "two"
    assert all(headers["User-Agent"].startswith("TestBot/1.0") for _, headers in session.calls)
    assert sleeps.count(2.0) == 2  # robots.txt -> page 1 -> page 2


def test_client_retries_temporary_errors_and_honours_retry_after():
    session = FakeSession({"https://a.gov/1": [
        FakeResponse(503, headers={"Retry-After": "7"}), requests.ConnectionError("reset"), FakeResponse(text="ok"),
    ]})
    client, sleeps = make_client(session)
    assert client.get("https://a.gov/1") == "ok"
    assert 7.0 in sleeps


def test_client_gives_up_after_max_retries():
    session = FakeSession({"https://a.gov/1": FakeResponse(500)})
    client, _ = make_client(session)
    with pytest.raises(FetchError, match="failed after 3 attempts"):
        client.get("https://a.gov/1")


def test_client_never_bypasses_access_restrictions():
    session = FakeSession({"https://a.gov/1": FakeResponse(403)})
    client, _ = make_client(session)
    with pytest.raises(FetchError, match="will not be bypassed"):
        client.get("https://a.gov/1")
    assert len([c for c in session.calls if c[0] == "https://a.gov/1"]) == 1  # no retry on 403


def test_client_obeys_robots_txt():
    session = FakeSession({"https://a.gov/private/x": FakeResponse(text="secret")})
    client, _ = make_client(session)
    with pytest.raises(RobotsDisallowed):
        client.get("https://a.gov/private/x")
    assert all(url.endswith("/robots.txt") for url, _ in session.calls)


def test_missing_robots_allows_but_unreachable_robots_blocks():
    allowed = FakeSession({"https://a.gov/1": FakeResponse(text="ok")}, robots=FakeResponse(404))
    assert make_client(allowed)[0].get("https://a.gov/1") == "ok"
    blocked = FakeSession({"https://a.gov/1": FakeResponse(text="ok")}, robots=FakeResponse(503))
    with pytest.raises(RobotsDisallowed):
        make_client(blocked)[0].get("https://a.gov/1")


def test_javascript_only_pages_are_reported_not_rendered():
    client, _ = make_client(FakeSession({}))
    scraper = BaseScraper("https://a.gov/list", {"requires_js": True}, client)
    with pytest.raises(FetchError, match="manual_officials.json"):
        scraper.fetch_and_parse("https://a.gov/list", lambda html: [])
