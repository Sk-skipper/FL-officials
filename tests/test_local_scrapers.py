"""Tests for the county elections-office, city roster and board scrapers. No network access.

The people in these fixtures are fictional; the markup and text mirror each source's layout.
"""
import pytest

from collector.publish import build
from collector.scrapers.base import FetchError
from collector.scrapers.broward_districts import parse_broward_districts
from collector.scrapers.broward_soe import parse_broward_soe
from collector.scrapers.city_roster import find_cards, find_members, page_lines, parse_city_roster
from collector.scrapers.miamidade_soe import parse_md_judges, parse_md_officials
from collector.validate import validate_record
from datetime import datetime, timezone
import json

SOE_URL = "https://browardvotes.gov/candidates/elected-officials"


def _row(office, holder, party="", status=(), contact=(), district="Broward County", link="https://example.gov/p"):
    party_html = f'<span class="Value Party"> ({party})</span>' if party else ""
    return f"""<tr class="ResultRow">
      <td class="OfficeName"><strong class="tablesaw-cell-label">Office Name</strong><span class="Value">{office}</span></td>
      <td class="OfficeHolder"><strong class="tablesaw-cell-label">Office Holder</strong><a href="{link}"><span class="Value Holder">{holder}</span></a>{party_html}</td>
      <td class="HolderStatus">{''.join(f'<p><span class="Value">{s}</span></p>' for s in status)}</td>
      <td class="ContactInformation">{''.join(f'<span class="Value">{c}</span><br>' for c in contact)}</td>
      <td class="District"><span class="Value">{district}</span></td></tr>"""


def test_broward_soe_maps_offices_and_skips_those_with_their_own_source():
    html = "<table>" + "".join([
        _row("Governor", "Pat Governor", "REP", ["Term Length: 4 years", "Next Election: 11/2026"], ["Phone: (850) 555-0100", "pat@example.gov"]),
        _row("17th Judicial Circuit Judge Group 12", "Jordan Q.Sample", status=["Next Election: 08//2030"]),
        _row("4th District Court of Appeal Chief Judge", "Casey Appeal", status=["Appointed"]),
        _row("Sheriff", "Robin Lawman", "DEM", contact=["Phone: (954) 555-0101", "Fax: (954) 555-0199"]),
        _row("State Senate", "Skip Me", "DEM"),
        _row("County Court Judge Group 3", "Vacant"),
        _row("Mosquito Control Board", "New Office"),
    ]) + "</table>"
    records = parse_broward_soe(html, SOE_URL)
    by_title = {r.get("office_title", "unknown"): r for r in records}
    gov = by_title["Governor"]
    assert gov["party"] == "REP" and gov["statewide"] and gov["phone"] == "(850) 555-0100"
    assert gov["bio"] == {"next_election": "November 2026"}
    judge = by_title["Circuit Judge"]
    assert judge["name"] == "Jordan Q. Sample" and judge["seat_label"] == "Group 12" and judge["bio"] == {"next_election": "August 2030"}
    assert by_title["Chief Judge, Fourth District Court of Appeal"]["selection_method"] == "appointed"
    assert by_title["Sheriff"]["phone"] == "(954) 555-0101"
    assert not any(r.get("name") == "Skip Me" for r in records)
    assert any("_error" in r and "Mosquito" in r["_error"] for r in records)
    for raw in records:
        if "_error" not in raw:
            assert validate_record(raw)[0] is not None


def test_miamidade_officials_pdf_lines():
    lines = [
        ("Governor Pat Governor 4 years 2026 01/05/2027 Contact", "https://example.gov/gov"),
        ("Sheriff Robin Lawman 4 years 2028 01/02/2029 Contact", "https://example.gov/sheriff"),
        ("Board of County Commissioners District 05: Dana Sample Appointed 2026 ------------ Contact", "http://example.gov/d5"),
        ("School Board Members District 01: Vacant - - - - 2026 11/21/2028 ____", "http://Vacant"),
        ("Community Council Area/Subarea 07/71-A: Lee Example 4 years 2026 11/17/2026 Contact", None),
        ("Community Council Area/Subarea 07/(Comm. Appointee): Kim Example N/A ---- ---------- Contact", None),
    ]
    records = parse_md_officials(lines, "https://www.miamidade.gov/elections/library/reports/elected-officials.pdf")
    assert [r["office_title"] for r in records] == ["Sheriff", "County Commissioner", "Community Council Member", "Community Council Member"]
    sheriff, commissioner, council, appointee = records
    assert sheriff["bio"] == {"next_election": "November 2028", "term_ends": "01/02/2029"} and sheriff["county"] == "Miami-Dade"
    assert commissioner["district"] == "5" and commissioner["selection_method"] == "appointed"
    assert council["jurisdiction"] == "Miami-Dade Community Council 7" and council["seat_label"] == "Subarea 71-A"
    assert appointee["selection_method"] == "appointed" and appointee["district"] is None


def test_miamidade_judges_pdf_text():
    text = "\n".join([
        "Third District Court of Appeal", "1/2/20292028Sample, Avery J.",
        "Circuit Judge, 11th Judicial Circuit", "Group No.", "1/7/20312030Example, Jordan08", "1/2/20292028Vacant07",
        "County Judge", "1/720312030De La Test, Morgan12",
    ])
    records = parse_md_judges(text, "https://www.miamidade.gov/elections/library/reports/judges.pdf")
    assert [(r["office_title"], r["name"], r.get("district")) for r in records] == [
        ("Judge, Third District Court of Appeal", "Avery J. Sample", None),
        ("Circuit Judge", "Jordan Example", "8"),
        ("County Court Judge", "Morgan De La Test", "12"),
    ]
    assert records[1]["bio"] == {"next_election": "August 2030"}


ROSTER_LINES = [
    "City Commission", "Mayor Jane Q. Doe", "Vice Mayor Richard DeNapoli", "Commissioner Don D'Arminio, District 2",
    "Sam Example", "Commissioner - Group 4", "Alex Sample", "(Seat #5)", "City Manager Pat Staff", "Who Is My Commissioner",
]


def test_city_roster_reads_common_roster_layouts():
    members = {m["name"]: m for m in find_members(ROSTER_LINES, "Commissioner")}
    assert set(members) == {"Jane Q. Doe", "Richard DeNapoli", "Don D'Arminio", "Sam Example", "Alex Sample"}
    assert members["Jane Q. Doe"]["title"] == "Mayor" and members["Richard DeNapoli"]["title"] == "Vice Mayor"
    assert members["Don D'Arminio"]["seat"] == "District 2" and members["Sam Example"]["seat"] == "Group 4"
    assert members["Alex Sample"]["seat"] == "Seat 5"


def test_city_roster_keeps_one_mayor_when_a_stale_mention_appears():
    lines = ["Jane Doe", "Mayor", "Lee Roe", "Commissioner", "Mayor Lee Roe"]
    members = {m["name"]: m["title"] for m in find_members(lines, "Commissioner")}
    assert members == {"Jane Doe": "Mayor", "Lee Roe": "Commissioner"}


def test_city_roster_reads_opencities_cards():
    html = """<main><article><header><a href="https://city.example.gov/Commission/Vice-Mayor-Jane-Doe"><h2 class="list-item-title">
      Example Vice Mayor Jane Doe</h2></a></header><img src="/files/jane.jpg"><li class="contact-phone"><span class="field-value">954-555-0100</span></li>
      <a href="mailto:jdoe@example.gov">jdoe@example.gov</a></article>
      <article><a href="https://city.example.gov/Commission/Seat-2"><h2 class="list-item-title">Sam Example</h2></a></article>
      <article><a href="https://city.example.gov/Programs"><h2 class="list-item-title">Commission Programs</h2></a></article></main>"""
    cards = find_cards(html, "https://city.example.gov/Commission", "Councilmember")
    assert [(c["name"], c["title"], c["seat"]) for c in cards] == [("Jane Doe", "Vice Mayor", None), ("Sam Example", "Councilmember", "Seat 2")]
    assert cards[0]["photo_url"] == "https://city.example.gov/files/jane.jpg" and cards[0]["phone"] == "954-555-0100"


def test_city_roster_refuses_a_page_with_the_wrong_number_of_seats():
    html = "<main><p>Mayor Jane Doe</p></main>"
    with pytest.raises(FetchError, match="Expected about 5 seats"):
        parse_city_roster([(html, "https://city.example.gov/commission")],
                          {"county": "Broward", "municipality": "Example", "seats": 5})


def test_city_roster_menus_are_dropped_by_link_density():
    html = """<body><nav><a href="/a">Home</a><a href="/b">Mayor Not Here</a></nav>
      <div class="has-menu"><p>Mayor Jane Doe</p><p>Commissioner Sam Example</p><p>Some long paragraph of text about the city.</p></div></body>"""
    lines = page_lines(html)
    assert "Mayor Jane Doe" in lines and "Mayor Not Here" not in lines


def test_board_mode_reads_name_and_role_lines_for_a_special_district():
    html = """<main><p>Jane Doe (Zone 3)</p><p>Chairperson – Nov 2024 – Oct 2028</p><p>Sam Example (Zone 5)</p><p>Commissioner – 2026</p>
      <p>Search Button</p><p>Commissioner</p></main>"""
    records = parse_city_roster([(html, "https://district.example.gov/board")], {
        "county": "Broward", "jurisdiction": "Example Drainage District", "special_district": "example", "member_title": "Commissioner",
        "title_suffix": ", Example Drainage District", "seats": 2, "role_pattern": "^(chair|commissioner)"})
    assert [(r["name"], r["office_title"], r["seat_label"], r["special_district"], r["government_level"]) for r in records] == [
        ("Jane Doe", "Chair, Example Drainage District", "Zone 3", "example", "county"),
        ("Sam Example", "Commissioner, Example Drainage District", "Zone 5", "example", "county"),
    ]


def test_broward_gis_mayors_only_for_listed_cities():
    payload = json.dumps({"features": [
        {"attributes": {"electedoffice": "Mayor", "district": "Davie", "repname1": "Morgan Mayor"}},
        {"attributes": {"electedoffice": "Mayor", "district": "Weston", "repname1": "Stale Mayor"}},
    ]})
    records = parse_broward_districts(payload, "https://gis.example.gov/layer", {"Davie"})
    assert [(r["name"], r["office_title"], r["municipality"]) for r in records] == [("Morgan Mayor", "Mayor", "Davie")]


def _record(rid, title, district, first, last, source="city", **extra):
    return {"id": rid, "full_name": f"{first} {last}", "first_name": first, "last_name": last, "office_title": title,
            "government_level": "municipal", "jurisdiction": "Example", "municipality": "Example", "county": "Broward",
            "district": district, "source_url": "https://example.gov", **extra}


def test_publish_merges_a_member_listed_by_the_city_and_the_county_gis():
    collected = {"sources": {
        "city": {"name": "City", "url": "https://city.example.gov", "level": "municipal", "status": "success",
                 "records": [_record("vice-mayor-example-jane-doe", "Vice Mayor", None, "Jane", "Doe", photo_url="https://city.example.gov/j.jpg")]},
        "gis": {"name": "GIS", "url": "https://gis.example.gov", "level": "county", "status": "success",
                "records": [_record("commissioner-district-4-jane-doe", "Commissioner", "4", "Jane", "Doe", email="jdoe@example.gov")]},
    }}
    profiles = {"commissioner-district-4-jane-doe": {"phone": "954-555-0100"}}
    officials, _, _, warnings = build(collected, {"officials": []}, {}, {}, datetime(2026, 11, 13, tzinfo=timezone.utc), {}, profiles=profiles)
    people = officials["officials"]
    assert len(people) == 1
    jane = people[0]
    assert (jane["office_title"], jane["district"], jane["email"], jane["photo_url"]) == (
        "Vice Mayor", "4", "jdoe@example.gov", "https://city.example.gov/j.jpg")
    assert jane["phone"] == "(954) 555-0100"  # profile keyed by the merged-away id still applies
    assert not warnings


from collector.scrapers.fl_county_officers import hold_back_stale_counties, parse_clerks, parse_fac, parse_sheriffs


def test_statewide_sheriffs_and_clerks_skip_counties_with_their_own_source():
    sheriffs = """<a href="https://flsheriffs.org/staff/a/" class="card:post »staff"><img src="https://flsheriffs.org/a.jpg">
      <h2 class="card:post::heading">Sheriff Dr. Pat Example</h2><div class="card:post::role">Alachua</div></a>
      <a href="https://flsheriffs.org/staff/b/" class="card:post »staff"><h2 class="card:post::heading">Sheriff Lee Sample</h2>
      <div class="card:post::role">Broward</div></a>"""
    records = parse_sheriffs(sheriffs, "https://flsheriffs.org/sheriffs/", {"Broward"})
    assert [(r["name"], r["county"], r["photo_url"]) for r in records] == [("Pat Example", "Alachua", "https://flsheriffs.org/a.jpg")]
    clerks = """<p><a href="https://bakerclerk.example">Baker County Clerk of Court - STACIE Q. MCEXAMPLE, ESQ.</a></p>
      <p><a href="https://x.example">St. Johns County Clerk of Court & Comptroller - JANE DOE</a></p>"""
    names = [(r["name"], r["county"]) for r in parse_clerks(clerks, "https://flccoc.org/about-us/clerks/", set())]
    assert names == [("Stacie Q. McExample", "Baker"), ("Jane Doe", "St. Johns")]


def _fac_box(name, position, county):
    return f"""<div class="dirResultsBox"><div class="dirEntryName">{name}</div><div class="dirEntryPosition">{position}</div>
      <div class="dirEntryAddress">{county}<br>1 Main St</div><span class="dirPhone">(850) 555-0100</span></div>"""


def test_fac_commissioners_are_held_back_when_a_county_lists_too_many():
    html = "".join(_fac_box(f"Member{i}, Pat", "Commissioner", "Leon County") for i in range(5))
    html += "".join(_fac_box(f"Member{i}, Lee", "Commissioner", "Palm Beach County") for i in range(9))
    html += _fac_box("Mayor, Mo", "Mayor", "Palm Beach County") + _fac_box("Clerk, Cy", "Staff Assistant", "Leon County")
    html += '<a href="/directory-results/?group=1&cpage=2">2</a>'
    records, pages = parse_fac(html, "https://www.fl-counties.com/directory-results/?group=1", set())
    assert pages == ["https://www.fl-counties.com/directory-results/?group=1&cpage=2"]
    kept = hold_back_stale_counties(records, {5, 7})
    assert sum(1 for r in kept if r.get("county") == "Leon") == 5
    held = [r for r in kept if "_error" in r]
    assert len(held) == 1 and "Palm Beach County" in held[0]["_error"] and "9 commissioners" in held[0]["_error"]


from collector.scrapers.soe_officeholders import parse_officeholders


def test_soe_officeholders_reads_names_with_party_and_the_office_above():
    html = """<main><h3>Sheriff</h3><p>Pat Example (Republican)</p><p>Website</p>
      <h3>Property Appraiser</h3><p>Lee Sample</p><p>(DEM)</p>
      <h3>County Commission</h3><p>District 3</p><p>Jane Doe (R)</p>
      <p>School Board District 2: Sam Roe (NOP)</p>
      <h3>State Senator</h3><p>Skip Me (R)</p><h3>Superintendent of Schools</h3><p>Kim Teach (Rep)</p></main>"""
    records = parse_officeholders(html, "https://vote.example.gov/officials", "Leon")
    got = [(r["name"], r["office_title"], r.get("district"), r["party"]) for r in records]
    assert got == [
        ("Pat Example", "Sheriff", None, "Republican"),
        ("Lee Sample", "Property Appraiser", None, "Democratic"),
        ("Jane Doe", "County Commissioner", "3", "Republican"),
        ("Sam Roe", "School Board Member", "2", "Nonpartisan"),
        ("Kim Teach", "Superintendent of Schools", None, "Republican"),
    ]
    assert all(validate_record(r)[0] is not None for r in records)


def test_soe_officeholders_fails_on_a_page_it_cannot_read():
    with pytest.raises(FetchError, match="Only 0 county officials"):
        parse_officeholders("<main><p>Loading...</p></main>", "https://vote.example.gov/officials", "Leon")


def test_publish_keeps_one_holder_of_a_single_seat_office_preferring_the_county_source():
    def rec(rid, first, last, source):
        return {"id": rid, "full_name": f"{first} {last}", "first_name": first, "last_name": last, "office_title": "Sheriff",
                "government_level": "county", "jurisdiction": "Franklin County", "county": "Franklin",
                "source_url": "https://example.gov", "photo_url": "https://example.gov/p.jpg" if source == "assoc" else None}
    collected = {"sources": {
        "assoc": {"name": "Florida Sheriffs Association", "url": "https://a.example", "level": "county", "status": "success",
                  "records": [rec("sheriff-a", "A.J.", "Smith", "assoc")]},
        "soe": {"name": "Franklin County Supervisor of Elections", "url": "https://s.example", "level": "county", "status": "success",
                "records": [rec("sheriff-b", "Tony", "Smith", "soe")]},
    }}
    officials, *_ = build(collected, {"officials": []}, {}, {}, datetime(2026, 11, 13, tzinfo=timezone.utc), {})
    people = officials["officials"]
    assert [(p["full_name"], p["source_name"], p["photo_url"]) for p in people] == [
        ("Tony Smith", "Franklin County Supervisor of Elections", "https://example.gov/p.jpg")]
