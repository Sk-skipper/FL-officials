"""Download district boundaries for the "Find your representatives" map.

    pip install -r tools/requirements.txt
    python tools/build_boundaries.py            # writes site/assets/boundaries/*.json
    python tools/build_boundaries.py --counties # also rewrites the county lists in data/districts.json

Sources (all public government data):
  - U.S. Census Bureau TIGERweb: Florida counties, incorporated places, the 119th Congress's
    districts and the 2024 Florida Senate and House districts (the plans adopted in 2022, which
    members elected through November 2026 represent).
  - Broward County GIS, "Electoral District Boundaries": County Commission, School Board and city
    commission districts. Expired districts are skipped.
  - Broward County GIS, "DrainageDistricts": the water control, drainage and improvement districts
    (special districts). `key` matches data/special_districts.json.
  - Broward County GIS, "BCCity_Boundaries": Broward's 31 municipalities, used instead of the
    Census outlines inside Broward because the county's are the legal limits.
  - Miami-Dade County GIS, "Know Where To Vote": County Commission and School Board districts.
  - Miami-Dade County GIS, "Community Development District": the county's community development
    districts (special districts), with the ordinance that created each one.
  - City of Miami GIS, "Commissioner Districts": the City of Miami's five commission districts.

The county, school board, city district and special district layers are written as one file each for
both counties (county-commission, school-board, city-districts, special-districts); every feature
carries a `county`. Miami-Dade community development districts are also added to
data/special_districts.json (key "md-cdd-<name>"), replacing the previous generated entries.

Each output file is GeoJSON in longitude/latitude, simplified to about 10 m (Broward) or 50 m
(statewide) so the whole set loads quickly in a browser. Every feature carries a `district` (or
`name`) property that matches the `district` / `municipality` fields of the officials it belongs to.

Run it again after a redistricting. Commit the files it writes.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import requests
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "assets" / "boundaries"
TIGER = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb"
BROWARD = "https://services.arcgis.com/JMAJrTsHNLrSsWf5/ArcGIS/rest/services"
ELECTORAL = f"{BROWARD}/ElectionGeography_public_25135677cecf426483e4c6d93e58db0a/FeatureServer/2"
CITY_LIMITS = f"{BROWARD}/BCCity_Boundaries/FeatureServer/0"
DRAINAGE = f"{BROWARD}/DrainageDistricts/FeatureServer/0"
MD_VOTE = "https://gisweb.miamidade.gov/arcgis/rest/services/MD_KnowWhereToVote/MapServer"
MD_CDD = "https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/CommunityDevelopmentDistrict_gdb/FeatureServer/0"
MIAMI_CITY = "https://gis.miami.gov/gis/rest/services/Maps/CommissionerDistricts/MapServer/0"
HEADERS = {"User-Agent": "fl-officials-directory/1.0 (boundary builder)"}

STATEWIDE_OFFSET = 0.0005  # degrees, about 50 m
LOCAL_OFFSET = 0.0001      # about 10 m
COUNTY_OFFSET = 0.0001     # finer outlines, used only to work out which counties a district covers

SOURCES = {
    "census": {"name": "U.S. Census Bureau, TIGERweb", "url": "https://tigerweb.geo.census.gov/"},
    "broward": {"name": "Broward County GIS: Electoral District Boundaries", "url": "https://geohub-bcgis.opendata.arcgis.com/"},
    "local": {"name": "Broward County GIS, Miami-Dade County GIS and City of Miami GIS", "url": "https://gis-mdc.opendata.arcgis.com/"},
}


def query(layer_url: str, where: str, fields: str, offset: float) -> list[dict]:
    """All features of an ArcGIS layer as GeoJSON, following pagination."""
    features, start = [], 0
    while True:
        params = {
            "where": where, "outFields": fields, "outSR": 4326, "f": "geojson",
            "maxAllowableOffset": offset, "geometryPrecision": 5,
            "resultOffset": start, "resultRecordCount": 1000,
        }
        response = requests.get(f"{layer_url}/query", params=params, headers=HEADERS, timeout=180)
        response.raise_for_status()
        page = response.json()
        if "error" in page:
            raise RuntimeError(f"{layer_url}: {page['error']}")
        batch = [f for f in page.get("features", []) if f.get("geometry")]
        features += batch
        if not page.get("exceededTransferLimit") and len(page.get("features", [])) < 1000:
            return features
        start += len(page.get("features", []))


def tiger(layer: str, number: int, fields: str, offset: float = STATEWIDE_OFFSET) -> list[dict]:
    return query(f"{TIGER}/{layer}/MapServer/{number}", "STATE='12'", fields, offset)


def feature(geometry: dict, **props) -> dict:
    return {"type": "Feature", "properties": props, "geometry": geometry}


def collection(features: list[dict], source: str, note: str) -> dict:
    return {"type": "FeatureCollection", "source": SOURCES[source], "note": note, "features": features}


def district_number(text: str | None) -> str:
    return str(int(text)) if text and text.strip().isdigit() else (text or "").strip()


def _municipality(label: str) -> str:
    """'Davie CIty Commission District 1' -> 'Davie'."""
    name = re.split(r"\s+(?:City|Town)\s+(?:Commission|Council)\b", label, flags=re.I)[0].strip()
    return {"Lauderdale By The Sea": "Lauderdale-By-The-Sea"}.get(name, name)


def build_statewide() -> dict[str, dict]:
    out = {}
    cd = tiger("Legislative", 4, "BASENAME,CD119")
    out["fl-congress"] = collection(
        [feature(f["geometry"], district=district_number(f["properties"]["CD119"])) for f in cd], "census",
        "119th Congress districts (Florida's 2022 plan). Members elected in 2024 serve in them until January 2027.",
    )
    senate = tiger("Legislative", 5, "BASENAME,SLDU")
    out["fl-senate"] = collection(
        [feature(f["geometry"], district=district_number(f["properties"]["SLDU"])) for f in senate], "census",
        "Florida Senate districts (2022 plan).",
    )
    house = tiger("Legislative", 6, "BASENAME,SLDL")
    out["fl-house"] = collection(
        [feature(f["geometry"], district=district_number(f["properties"]["SLDL"])) for f in house], "census",
        "Florida House districts (2022 plan).",
    )
    counties = tiger("State_County", 1, "BASENAME,NAME")
    out["fl-counties"] = collection(
        [feature(f["geometry"], name=f["properties"]["BASENAME"]) for f in counties], "census", "Florida's 67 counties.",
    )
    places = tiger("Places_CouSub_ConCity_SubMCD", 4, "BASENAME,NAME,LSADC")
    out["fl-cities"] = collection(
        [feature(f["geometry"], name=f["properties"]["BASENAME"]) for f in places], "census",
        "Incorporated cities, towns and villages. Inside Broward County the county's own city limits are used instead.",
    )
    return out


def build_broward(statewide_cities: dict) -> dict[str, dict]:
    rows = query(ELECTORAL, "1=1", "electedoffice,district,districtid", LOCAL_OFFSET)
    commission, school, city = [], [], []
    for row in rows:
        p = row["properties"]
        office, label = (p.get("electedoffice") or ""), (p.get("district") or "")
        if "EXPIRED" in label.upper():
            continue
        number = district_number(p.get("districtid"))
        if office == "County Commissioner":
            commission.append(feature(row["geometry"], county="Broward", district=number))
        elif office == "School Board" and "At-Large" not in label:
            school.append(feature(row["geometry"], county="Broward", district=number))
        elif office in ("City Commission", "Town Council"):
            city.append(feature(row["geometry"], county="Broward", municipality=_municipality(label), district=number))

    limits = query(CITY_LIMITS, "1=1", "*", LOCAL_OFFSET)
    by_city: dict[str, list] = {}
    for row in limits:
        props = row["properties"]
        name = next((props[k] for k in ("CITYNAME", "CITY", "NAME", "MUNICIPALITY", "Municipality") if props.get(k)), None)
        if name and not re.search(r"unincorporated|bmsd|regional facility|tribal", name, re.I):
            by_city.setdefault(_city_name(name), []).append(shape(row["geometry"]))
    broward_cities = [
        feature(mapping(unary_union(parts)), name=name) for name, parts in sorted(by_city.items())
    ]
    # Replace the Census outlines of Broward cities with the county's legal limits.
    key = lambda n: re.sub(r"[^a-z]", "", n.lower())  # noqa: E731
    names = {key(f["properties"]["name"]) for f in broward_cities}
    statewide_cities["features"] = [
        f for f in statewide_cities["features"] if key(f["properties"]["name"]) not in names
    ] + broward_cities

    special = []
    for row in query(DRAINAGE, "1=1", "LABELNAME,DEPENDENT", LOCAL_OFFSET):
        label = " ".join((row["properties"].get("LABELNAME") or "").split("\r\n")[0].split())
        if label:
            special.append(feature(row["geometry"], county="Broward", key=label,
                                   status="dependent" if row["properties"].get("DEPENDENT") == "D" else "independent"))

    return {
        "broward-special": collection(special, "broward", "Water control, drainage and improvement districts (Broward County GIS)."),
        "broward-commission": collection(commission, "broward", "Broward County Commission districts (adopted 2022)."),
        "broward-school": collection(school, "broward", "Broward School Board districts 1–7. Seats 8 and 9 are countywide."),
        "broward-city-districts": collection(city, "broward", "City commission districts, for the cities that elect by district."),
    }


def cdd_key(name: str) -> str:
    return "md-cdd-" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def build_miamidade() -> tuple[dict[str, list], list[dict]]:
    commission = [feature(f["geometry"], county="Miami-Dade", district=district_number(str(f["properties"]["ID"])))
                  for f in query(f"{MD_VOTE}/4", "1=1", "ID", LOCAL_OFFSET)]
    school = [feature(f["geometry"], county="Miami-Dade", district=district_number(str(f["properties"]["ID"])))
              for f in query(f"{MD_VOTE}/8", "1=1", "ID", LOCAL_OFFSET)]
    city = [feature(f["geometry"], county="Miami-Dade", municipality="Miami", district=district_number(str(f["properties"]["COMDISTID"])))
            for f in query(MIAMI_CITY, "1=1", "COMDISTID", LOCAL_OFFSET)]
    special, entries, parts = [], [], {}
    for f in query(MD_CDD, "1=1", "NAME,ORD_NO,EXHBT_LINK", LOCAL_OFFSET):
        p = f["properties"]
        name = " ".join((p.get("NAME") or "").split())
        if name:
            parts.setdefault(name, []).append((shape(f["geometry"]), p))
    for name, items in sorted(parts.items()):
        key = cdd_key(name)
        special.append(feature(mapping(unary_union([g for g, _ in items])), county="Miami-Dade", key=key, status="independent"))
        p = items[0][1]
        sources = [{"name": "Miami-Dade County GIS: Community Development District", "url": "https://gis-mdc.opendata.arcgis.com/"}]
        if (p.get("EXHBT_LINK") or "").startswith("https://"):
            sources.append({"name": f"Miami-Dade ordinance {p.get('ORD_NO') or ''} creating the district".replace("  ", " "), "url": p["EXHBT_LINK"]})
        entries.append({
            "key": key, "name": f"{name} Community Development District", "type": "Community development district",
            "area": "mapped", "status": "independent", "county": "Miami-Dade",
            "board": "Board of supervisors, elected by landowners at first and later by residents (Chapter 190, Florida Statutes)",
            "note": "Name as recorded in Miami-Dade County GIS; board members are not listed yet.", "sources": sources,
        })
    return {"commission": commission, "school": school, "city": city, "special": special}, entries


def _city_name(raw: str) -> str:
    name = " ".join(w.capitalize() if w.isupper() or w.islower() else w for w in raw.strip().split())
    fixes = {"Lauderdale By The Sea": "Lauderdale-By-The-Sea", "Lauderdale-by-the-sea": "Lauderdale-By-The-Sea",
             "Southwest Ranches": "Southwest Ranches", "Sea Ranch Lakes": "Sea Ranch Lakes"}
    return fixes.get(name, name)


def counties_by_district(layer: dict, counties: list[dict]) -> dict[str, list[str]]:
    """Which counties each district covers: any overlap larger than 2 km² or 1% of the district.

    Census county outlines include bays and the sea, so a coastal district can touch a
    neighbouring county's water by a square kilometre or so; the 2 km² floor ignores those.
    """
    shapes = [(c["properties"]["name"], shape(c["geometry"]).buffer(0)) for c in counties]
    out = {}
    for f in layer["features"]:
        district = shape(f["geometry"]).buffer(0)
        found = []
        for name, county in shapes:
            if not district.intersects(county):
                continue
            area = district.intersection(county).area
            # One square degree is about 11,000 km² at Florida's latitude.
            if area * 11_000 > 2 or area > 0.01 * district.area:
                found.append(name)
        out[f["properties"]["district"]] = sorted(found)
    return dict(sorted(out.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 999))


def write(name: str, data: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.json"
    path.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"  {path.relative_to(ROOT)}: {len(data['features'])} shapes, {path.stat().st_size // 1024} KB")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--counties", action="store_true", help="rewrite the county lists in data/districts.json")
    args = parser.parse_args()

    print("Downloading statewide boundaries from the Census Bureau...")
    layers = build_statewide()
    print("Downloading Broward County districts...")
    broward = build_broward(layers["fl-cities"])
    print("Downloading Miami-Dade County districts...")
    dade, cdds = build_miamidade()
    combined = {
        "county-commission": ("broward-commission", "commission", "County Commission districts (Broward 2022 plan; Miami-Dade)."),
        "school-board": ("broward-school", "school", "School Board districts. Broward seats 8 and 9 are countywide."),
        "city-districts": ("broward-city-districts", "city", "City commission districts, for the cities that elect by district."),
        "special-districts": ("broward-special", "special", "Broward water control, drainage and improvement districts; "
                                                            "Miami-Dade community development districts."),
    }
    for name, (b, d, note) in combined.items():
        layers[name] = collection(broward[b]["features"] + dade[d], "local", note)
    for name, data in layers.items():
        write(name, data)
    for old in ("broward-commission", "broward-school", "broward-city-districts", "broward-special"):
        (OUT / f"{old}.json").unlink(missing_ok=True)
    path = ROOT / "data" / "special_districts.json"
    special = json.loads(path.read_text(encoding="utf-8"))
    special["districts"] = [d for d in special["districts"] if not d["key"].startswith("md-cdd-")] + cdds
    path.write_text(json.dumps(special, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  data/special_districts.json: {len(cdds)} Miami-Dade community development districts")

    if args.counties:
        print("Working out which counties each district covers...")
        fine = tiger("State_County", 1, "BASENAME", COUNTY_OFFSET)
        counties = [feature(f["geometry"], name=f["properties"]["BASENAME"]) for f in fine]
        path = ROOT / "data" / "districts.json"
        districts = json.loads(path.read_text(encoding="utf-8"))
        districts["State Representative"] = {
            "source": {"name": "U.S. Census Bureau, TIGERweb: 2024 Florida House districts", "url": SOURCES["census"]["url"]},
            "note": "Worked out from the district and county boundaries by tools/build_boundaries.py.",
            "districts": counties_by_district(layers["fl-house"], counties),
        }
        path.write_text(json.dumps(districts, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("  data/districts.json updated (State Representative)")
        # Check the method against lists published by official sources: the Florida Senate
        # roster (in collected.json) and the congressional district descriptions in statute.
        collected = json.loads((ROOT / "data" / "collected.json").read_text(encoding="utf-8"))
        official = {
            "Florida Senate": ("fl-senate", {r["district"]: r.get("counties") or [] for r in
                                            collected["sources"].get("fl_senate", {}).get("records", [])}),
            "U.S. House": ("fl-congress", districts["U.S. Representative"]["districts"]),
        }
        for label, (layer, published) in official.items():
            computed = counties_by_district(layers[layer], counties)
            diffs = [(d, set(published[d]) ^ set(computed.get(d, []))) for d in published if set(published[d]) != set(computed.get(d, []))]
            print(f"  check against {label}: {len(published) - len(diffs)} of {len(published)} districts agree"
                  + "".join(f"\n    District {d}: differs on {', '.join(sorted(c))}" for d, c in diffs))


if __name__ == "__main__":
    try:
        main()
    except (requests.RequestException, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
