import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import roster_terms  # noqa: E402
import wikipedia_terms  # noqa: E402
from derive_tenure import canon, one_surname, surname_tokens  # noqa: E402


def test_term_end_forms():
    assert roster_terms.term_end("Term expires November 2028")["year"] == 2028
    assert roster_terms.term_end("Term expires November 2028")["month"] == "nov"
    assert roster_terms.term_end("Current Term: 2024-2028")["year"] == 2028
    end = roster_terms.term_end("Current term: 8/11/25 - 6/30/29")
    assert (end["year"], end["began"]) == (2029, 2025)
    assert roster_terms.term_end("Term Expires: 6/2028")["year"] == 2028
    assert roster_terms.term_end("Commissioner since the town began") is None


def test_since_prefers_the_current_title_and_skips_reelections():
    text = "Harvey Ward was elected mayor of Gainesville in November of 2022 after being first elected to the City Commission in March 2017."
    assert roster_terms.since(text, "Mayor")["year"] == 2022
    assert roster_terms.since("He was re-elected in 2021 and 2023.", "Commissioner") is None
    s = roster_terms.since("John was first elected in 2015.", "Commissioner")
    assert (s["year"], s["at_least"]) == (2015, False)
    assert roster_terms.since("Elected again in November 2024.", "Commissioner") is None


def test_windows_split_between_officials():
    people = [{"id": "a", "last_name": "Smith"}, {"id": "b", "last_name": "Jones"}]
    lines = ["Mayor Ann Smith", "Term expires 2027", "Commissioner Bob Jones", "Term expires 2029"]
    w = roster_terms.windows(lines, people)
    assert roster_terms.term_end(" ".join(w["a"]))["year"] == 2027
    assert roster_terms.term_end(" ".join(w["b"]))["year"] == 2029


def test_infobox_current_office_only():
    text = """{{Infobox officeholder
| office = Attorney General of Florida
| governor = Ron DeSantis
| assumed_office = February 17, 2025
| appointer = [[Ron DeSantis]]
| office1 = Chief of Staff to the Governor
| term_start1 = 2023
| term_end1 = 2025
}}"""
    offices = wikipedia_terms.infobox_offices(text)
    assert len(offices) == 1
    assert offices[0]["year"] == 2025 and offices[0]["date"] == "2025-02-17" and offices[0]["appointer"] == "Ron DeSantis"
    assert wikipedia_terms.office_matches({"office_title": "Attorney General"}, offices[0])
    assert not wikipedia_terms.office_matches({"office_title": "Sheriff", "county": "Pasco"}, offices[0])


def test_infobox_district_must_match():
    entry = {"office": "Member of the Florida House of Representatives", "where": "38th district", "year": 2022}
    assert wikipedia_terms.office_matches({"office_title": "State Representative", "district": "38"}, entry)
    assert not wikipedia_terms.office_matches({"office_title": "State Representative", "district": "39"}, entry)
    assert wikipedia_terms.parse_date("{{start date and age|2019|1|8}}") == (2019, "2019-01-08")


def test_name_helpers():
    assert canon("Michael A.") == "michael"
    assert canon('Sherwood "Chip"') == "sherwood"
    assert canon("W. Greg") == canon("Gregory")
    assert one_surname([surname_tokens("Cabrera"), surname_tokens("Busatta Cabrera"), surname_tokens("Busatta")])
    assert one_surname([surname_tokens("Bauer Jr."), surname_tokens("Bauer Jr")])
    assert not one_surname([surname_tokens("Gardner"), surname_tokens("Barthle")])


def test_infobox_empty_term_end_does_not_swallow_next_line():
    text = "{{Infobox officeholder\n| office = 39th [[Florida Attorney General]]\n| term_start = February 17, 2025\n| term_end = \n| predecessor = [[Ashley Moody]]\n}}"
    offices = wikipedia_terms.infobox_offices(text)
    assert [o["date"] for o in offices] == ["2025-02-17"]
