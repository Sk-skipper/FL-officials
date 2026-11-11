"""Unit tests: normalization, validation and deduplication."""
import pytest

from collector.dedupe import dedupe_batch, find_duplicate_candidates
from collector.geo import FLORIDA_COUNTIES, canonical_county, parse_county_list
from collector.normalize import (
    normalize_email,
    normalize_party,
    normalize_phone,
    normalize_url,
    parse_district,
    parse_name,
)
from collector.validate import validate_record
from tests.conftest import make_raw
from collector.normalize import make_record_id


def test_there_are_67_unique_counties():
    assert len(FLORIDA_COUNTIES) == 67
    assert len(set(FLORIDA_COUNTIES)) == 67


@pytest.mark.parametrize("raw,first,middle,last,full", [
    ("Rivera, Ana M.", "Ana", "M.", "Rivera", "Ana M. Rivera"),
    ("Ana M. Rivera", "Ana", "M.", "Rivera", "Ana M. Rivera"),
    ("Wasserman Schultz, Debbie", "Debbie", None, "Wasserman Schultz", "Debbie Wasserman Schultz"),
    ("Senator John Q. Public Jr.", "John", "Q.", "Public", "John Q. Public Jr."),
    ("Public, John, Jr.", "John", None, "Public", "John Public Jr."),
    ('Smith, Robert "Bob"', "Robert", None, "Smith", "Robert Smith"),
    ("Maria de la Cruz", "Maria", None, "de la Cruz", "Maria de la Cruz"),
    ("Hon.  Jane   Doe, Esq.", "Jane", None, "Doe", "Jane Doe"),
])
def test_parse_name(raw, first, middle, last, full):
    parts = parse_name(raw)
    assert (parts.first, parts.middle, parts.last, parts.full) == (first, middle, last, full)


def test_parse_name_rejects_garbage():
    assert parse_name("") is None
    assert parse_name("12345") is None


@pytest.mark.parametrize("raw,expected", [
    ("R", "Republican"), ("(D)", "Democratic"), ("Democrat", "Democratic"),
    ("NPA", "No Party Affiliation"), ("", None), (None, None),
])
def test_normalize_party(raw, expected):
    assert normalize_party(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("District 12", ("12", 12)), ("3rd", ("3", 3)), ("At Large", ("At-Large", None)),
    ("007", ("7", 7)), ("", (None, None)),
])
def test_parse_district(raw, expected):
    assert parse_district(raw) == expected


def test_phone_is_formatted_or_dropped():
    assert normalize_phone("850.487.5012") == "(850) 487-5012"
    assert normalize_phone("tel:+1-850-487-5012") == "(850) 487-5012"
    assert normalize_phone("call the office") is None
    assert normalize_phone("123-4567") is None


def test_email_and_url_are_validated_not_repaired():
    assert normalize_email("mailto:Jane.Doe@FLSenate.gov?subject=Hi") == "jane.doe@flsenate.gov"
    assert normalize_email("https://www.senate.gov/contact") is None
    assert normalize_url("https://www.flsenate.gov/Senators/S1") == "https://www.flsenate.gov/Senators/S1"
    assert normalize_url("javascript:void(0)") is None


def test_county_matching():
    assert canonical_county("saint johns county") == "St. Johns"
    assert canonical_county("Dade") == "Miami-Dade"
    assert canonical_county("Gotham") is None
    assert parse_county_list("Escambia, Santa Rosa and part of Okaloosa") == ["Escambia", "Santa Rosa", "Okaloosa"]


def test_valid_record_is_normalized():
    record, error = validate_record(make_raw())
    assert error is None
    assert record.full_name == "Ana M. Rivera"
    assert record.party == "Democratic"
    assert (record.district, record.district_number) == ("12", 12)
    assert record.counties == ["Broward", "Palm Beach"]


def test_invalid_contact_details_are_dropped_not_invented():
    record, _ = validate_record(make_raw(phone="n/a", email="see website", official_website="/Senators/S12"))
    assert record.phone is None
    assert record.email is None
    assert record.official_website is None


@pytest.mark.parametrize("overrides,fragment", [
    ({"name": "Vacant"}, "vacant"),
    ({"name": "Cher"}, "first and last name"),
    ({"name": ""}, "no name"),
    ({"office_title": ""}, "office_title"),
    ({"government_level": "galactic"}, "government_level"),
    ({"county": "Gotham"}, "not a Florida county"),
    ({"municipality": "West Park", "county": None}, "must name its county"),
])
def test_invalid_records_are_rejected_with_a_reason(overrides, fragment):
    record, error = validate_record(make_raw(**overrides))
    assert record is None
    assert fragment in error


def test_batch_dedupe_merges_same_person_same_seat():
    first, _ = validate_record(make_raw(phone=None))
    second, _ = validate_record(make_raw(name="Ana M. Rivera", counties=["Martin"]))
    other, _ = validate_record(make_raw(name="Whitfield, Thomas", district="3"))
    unique, dropped = dedupe_batch([first, second, other])
    assert dropped == 1
    assert len(unique) == 2
    assert unique[0].phone == "(850) 487-5012"  # gap filled from the duplicate row
    assert "Martin" in unique[0].counties


def _row(id_, first, last, office="State Senator", district="12", level="state"):
    return {"id": id_, "government_level": level, "first_name": first, "last_name": last,
            "office_title": office, "jurisdiction": "Florida", "district": district}


def test_duplicate_candidates_are_found():
    rows = [
        _row(1, "Robert", "Smith"),
        _row(2, "Rob", "Smith"),                           # nickname, same seat -> candidate
        _row(3, "Angela", "Smith"),                        # different person
        _row(4, "Robert", "Smith", level="county"),        # other level is never compared
        _row(5, "Robert", "Jones", district=None),
    ]
    assert [(a, b) for a, b, _ in find_duplicate_candidates(rows)] == [(1, 2)]


def test_same_name_in_unrelated_seats_is_not_flagged():
    rows = [_row(1, "Maria", "Garcia"), _row(2, "Maria", "Garcia", office="State Representative", district="99")]
    assert find_duplicate_candidates(rows) == []


def test_record_ids_are_stable_and_readable():
    record, _ = validate_record(make_raw())
    assert record.record_id == "state-senator-district-12-ana-rivera"
    assert make_record_id("Supervisor of Elections", "St. Johns County", None, "Zoë", "O'Brien") == \
        "supervisor-of-elections-st-johns-county-zoe-obrien"
