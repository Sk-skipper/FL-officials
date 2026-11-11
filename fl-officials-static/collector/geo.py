"""Florida's 67 counties and helpers for matching county names in scraped text."""
import re

FLORIDA_COUNTIES: list[str] = [
    "Alachua", "Baker", "Bay", "Bradford", "Brevard", "Broward", "Calhoun", "Charlotte", "Citrus",
    "Clay", "Collier", "Columbia", "DeSoto", "Dixie", "Duval", "Escambia", "Flagler", "Franklin",
    "Gadsden", "Gilchrist", "Glades", "Gulf", "Hamilton", "Hardee", "Hendry", "Hernando",
    "Highlands", "Hillsborough", "Holmes", "Indian River", "Jackson", "Jefferson", "Lafayette",
    "Lake", "Lee", "Leon", "Levy", "Liberty", "Madison", "Manatee", "Marion", "Martin",
    "Miami-Dade", "Monroe", "Nassau", "Okaloosa", "Okeechobee", "Orange", "Osceola", "Palm Beach",
    "Pasco", "Pinellas", "Polk", "Putnam", "St. Johns", "St. Lucie", "Santa Rosa", "Sarasota",
    "Seminole", "Sumter", "Suwannee", "Taylor", "Union", "Volusia", "Wakulla", "Walton",
    "Washington",
]


def _key(name: str) -> str:
    return re.sub(r"[^a-z]", "", name.lower())


_BY_KEY = {_key(c): c for c in FLORIDA_COUNTIES}
_ALIASES = {"saintjohns": "St. Johns", "saintlucie": "St. Lucie", "dade": "Miami-Dade"}

_PART_PREFIX = re.compile(r"^(?:parts?|portions?|a portion)\s+of\s+", re.I)
_SPLIT = re.compile(r",|;|/|&|\band\b", re.I)


def canonical_county(name: str | None) -> str | None:
    """Return the canonical county name, or None if it is not a Florida county."""
    if not name:
        return None
    cleaned = re.sub(r"\([^)]*\)", " ", name)
    cleaned = _PART_PREFIX.sub("", cleaned.strip())
    cleaned = re.sub(r"\bcount(?:y|ies)\b", " ", cleaned, flags=re.I)
    key = _key(cleaned)
    return _BY_KEY.get(key) or _ALIASES.get(key)


def parse_county_list(text: str | None) -> list[str]:
    """Split 'Escambia, Santa Rosa and part of Okaloosa' into canonical names."""
    if not text:
        return []
    found: list[str] = []
    for piece in _SPLIT.split(text):
        county = canonical_county(piece)
        if county and county not in found:
            found.append(county)
    return found
