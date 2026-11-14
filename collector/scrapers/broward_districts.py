"""Broward County GIS, "Electoral District Boundaries": who holds each district seat in the county.

The layer lists, for every district polygon, the elected official and a link to their page. It is
used for district seats only: the County Commission, the School Board and city commission districts.
Mayors are skipped unless the source config lists the city in "mayor_cities". When checked in November
2026, the layer named a former mayor for about a quarter of Broward's cities (mayors in many cities rotate
yearly), while every district seat matched the city's own page. "mayor_cities" holds only cities whose
own website cannot be collected (it blocks automated requests) and whose GIS mayor matched the city's
page when checked; cities whose own site works are collected from it instead (city_roster sources).

Rows marked EXPIRED (old district plans) and "TO BE DETERMINED" seats are skipped.
"""
import json
import re
from urllib.parse import urlencode

from collector.normalize import clean_text
from collector.scrapers.base import BaseScraper, FetchError

FIELDS = "electedoffice,district,districtid,repname1,repimageurl1,districturl1,email1,phone1"
COUNCIL_TOWNS = {"Davie", "Southwest Ranches"}  # their "commissioners" are council members
CITY_NAMES = {"Lauderdale By The Sea": "Lauderdale-By-The-Sea"}
_SUFFIX = re.compile(r",\s*(jr|sr)\.?$", re.I)
_CREDENTIAL = re.compile(r",\s*esq\.?$", re.I)


def _name(raw: str) -> str:
    name = clean_text(raw)
    name = _CREDENTIAL.sub("", name)
    name = _SUFFIX.sub(lambda m: f" {m.group(1).capitalize()}.", name)
    return re.sub(r"\s*\(([^)]+)\)\s*", r' "\1" ', name).strip()


def _municipality(label: str) -> str:
    name = re.split(r"\s+(?:City|Town)\s+(?:Commission|Council)\b", label, flags=re.I)[0].strip()
    return CITY_NAMES.get(name, name)


def _https(url: str | None) -> str | None:
    return url if url and url.startswith("https://") else None


def parse_broward_districts(payload: str, source_url: str, mayor_cities: set[str] | frozenset = frozenset()) -> list[dict]:
    data = json.loads(payload)
    if "error" in data:
        raise FetchError(f"Broward County GIS returned an error: {data['error'].get('message')}")
    records = []
    for feature in data.get("features", []):
        row = feature.get("attributes") or {}
        office, label = row.get("electedoffice") or "", clean_text(row.get("district"))
        name = _name(row.get("repname1") or "")
        district = clean_text(row.get("districtid")).lstrip("0") or None
        if office == "Mayor" and _municipality(label) in mayor_cities and name and not re.search(r"vacant", name, re.I):
            municipality = _municipality(label)
            records.append({"name": name, "office_title": "Mayor", "selection_method": "elected", "source_url": source_url,
                            "photo_url": _https(row.get("repimageurl1")), "official_website": row.get("districturl1"),
                            "email": row.get("email1"), "phone": row.get("phone1"), "county": "Broward",
                            "government_level": "municipal", "municipality": municipality, "jurisdiction": municipality,
                            "party": "Nonpartisan"})
            continue
        if "EXPIRED" in label.upper() or not name or re.search(r"to be determined|vacant", name, re.I) or not district:
            continue
        base = {
            "name": name, "selection_method": "elected", "source_url": source_url,
            "photo_url": _https(row.get("repimageurl1")), "official_website": row.get("districturl1"),
            "email": row.get("email1"), "phone": row.get("phone1"), "county": "Broward",
        }
        if office == "County Commissioner":
            records.append({**base, "office_title": "County Commissioner", "government_level": "county",
                            "district": district, "jurisdiction": "Broward County", "party": row.get("party1")})
        elif office == "School Board":
            countywide = "at-large" in label.lower()
            records.append({**base, "office_title": "School Board Member", "government_level": "county",
                            "district": district, "jurisdiction": "Broward County Public Schools",
                            "seat_label": f"District {district}{' (countywide)' if countywide else ''}", "party": "Nonpartisan"})
        elif office in ("City Commission", "Town Council"):
            municipality = _municipality(label)
            records.append({**base, "office_title": "Councilmember" if municipality in COUNCIL_TOWNS else "Commissioner",
                            "government_level": "municipal", "municipality": municipality, "jurisdiction": municipality,
                            "district": district if district.isdigit() else f"District {district}",
                            "seat_label": f"District {district}", "party": "Nonpartisan"})
    return records


class BrowardDistrictsScraper(BaseScraper):
    def collect(self) -> list[dict]:
        query = urlencode({"where": "1=1", "outFields": FIELDS, "returnGeometry": "false", "f": "json"})
        url = f"{self.source_url.rstrip('/')}/query?{query}"
        return parse_broward_districts(self.client.get(url), self.source_url, set(self.config.get("mayor_cities") or []))
