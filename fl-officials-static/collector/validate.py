"""Validation of scraped rows before they are allowed near the database."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from collector.geo import canonical_county
from collector.normalize import (
    build_dedupe_key,
    make_record_id,
    clean_text,
    normalize_email,
    normalize_party,
    normalize_phone,
    normalize_url,
    parse_district,
    parse_name,
)

Level = Literal["federal", "state", "county", "municipal"]
SelectionMethod = Literal["elected", "appointed", "unknown"]


class ScrapedOfficial(BaseModel):
    model_config = ConfigDict(extra="ignore")

    full_name: str = Field(min_length=3, max_length=200)
    first_name: str = Field(min_length=1, max_length=80)
    middle_name: str | None = Field(default=None, max_length=80)
    last_name: str = Field(min_length=1, max_length=100)
    office_title: str = Field(min_length=2, max_length=150)
    government_level: Level
    selection_method: SelectionMethod = "unknown"
    party: str | None = None
    district: str | None = None
    district_number: int | None = None
    jurisdiction: str = Field(min_length=2, max_length=150)
    statewide: bool = False
    county: str | None = None
    counties: list[str] = []
    municipality: str | None = None
    phone: str | None = None
    email: str | None = None
    official_website: str | None = None
    source_url: str = Field(min_length=8, max_length=500)

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        data = dict(data)

        raw_name = clean_text(data.pop("name", None) or data.get("full_name"))
        if not raw_name:
            raise ValueError("record has no name")
        if "vacant" in raw_name.lower():
            raise ValueError("seat is listed as vacant")
        parts = parse_name(raw_name)
        if parts is None or not parts.first:
            raise ValueError(f"could not parse a first and last name from {raw_name!r}")
        data.update(full_name=parts.full, first_name=parts.first, middle_name=parts.middle, last_name=parts.last)

        data["office_title"] = clean_text(data.get("office_title"))
        data["jurisdiction"] = clean_text(data.get("jurisdiction"))
        data["party"] = normalize_party(data.get("party"))
        data["district"], data["district_number"] = parse_district(data.get("district"))
        # Unusable contact values are dropped, never "repaired".
        data["phone"] = normalize_phone(data.get("phone"))
        data["email"] = normalize_email(data.get("email"))
        data["official_website"] = normalize_url(data.get("official_website"))
        data["municipality"] = clean_text(data.get("municipality")) or None

        county_raw = clean_text(data.get("county"))
        if county_raw:
            county = canonical_county(county_raw)
            if county is None:
                raise ValueError(f"{county_raw!r} is not a Florida county")
            data["county"] = county
        else:
            data["county"] = None
        data["counties"] = [c for c in (canonical_county(n) for n in data.get("counties") or []) if c]

        if data["municipality"] and not data["county"]:
            raise ValueError("a municipal record must name its county")
        return data

    @property
    def record_id(self) -> str:
        return make_record_id(self.office_title, self.jurisdiction, self.district, self.first_name, self.last_name)

    @property
    def dedupe_key(self) -> str:
        return build_dedupe_key(
            self.government_level, self.office_title, self.jurisdiction, self.district,
            self.last_name, self.first_name,
        )


def validate_record(raw: dict) -> tuple[ScrapedOfficial | None, str | None]:
    """Return (record, None) or (None, human-readable reason)."""
    try:
        return ScrapedOfficial.model_validate(raw), None
    except ValidationError as exc:
        reasons = []
        for err in exc.errors():
            location = ".".join(str(p) for p in err["loc"])
            message = err["msg"].removeprefix("Value error, ")
            reasons.append(f"{location}: {message}" if location else message)
        return None, "; ".join(reasons)
