"""Official portraits for Florida's members of Congress.

The Senate contact list names each senator's Bioguide ID. The House directory does not,
so House members are matched to the public-domain congress-legislators dataset by state and
district. Photos are served from the matching public-domain image set. If the dataset can't be
read, members simply have no photo; their other details are unaffected.
"""
import json
import logging

from collector.normalize import ascii_key, parse_district

logger = logging.getLogger(__name__)

LEGISLATORS_URL = "https://unitedstates.github.io/congress-legislators/legislators-current.json"
PHOTO_URL = "https://unitedstates.github.io/images/congress/450x550/{bioguide_id}.jpg"


def photo_url(bioguide_id: str | None) -> str | None:
    bioguide_id = (bioguide_id or "").strip()
    if len(bioguide_id) == 7 and bioguide_id.isalnum():
        return PHOTO_URL.format(bioguide_id=bioguide_id.upper())
    return None


def house_members(legislators: list[dict], state: str = "FL") -> dict[str, dict]:
    """Map district number -> {"bioguide_id", "last_name"} for a state's current House members."""
    found: dict[str, dict] = {}
    for person in legislators:
        term = (person.get("terms") or [{}])[-1]
        if term.get("type") != "rep" or term.get("state") != state:
            continue
        bioguide_id = (person.get("id") or {}).get("bioguide")
        if not bioguide_id or term.get("district") is None:
            continue
        found[str(term["district"])] = {"bioguide_id": bioguide_id, "last_name": (person.get("name") or {}).get("last", "")}
    return found


def add_house_photos(records: list[dict], legislators: list[dict]) -> int:
    """Attach a photo to each record whose district and surname both match. Returns how many matched."""
    members = house_members(legislators)
    matched = 0
    for record in records:
        # The House directory writes "1st", "25th"; the dataset uses plain numbers.
        member = members.get(parse_district(record.get("district"))[0] or "")
        if member is None:
            continue
        # A stale dataset must never put one person's face next to another's name.
        if member["last_name"] and ascii_key(member["last_name"]) not in ascii_key(record.get("name")):
            logger.warning("Skipped photo for district %s: name does not match the legislators dataset", record.get("district"))
            continue
        record["photo_url"] = photo_url(member["bioguide_id"])
        matched += record["photo_url"] is not None
    return matched


def add_senate_photos(records: list[dict], legislators: list[dict], state: str = "FL") -> int:
    """Fallback for senators whose Bioguide ID is missing from the Senate list: match by surname."""
    senators = {}
    for person in legislators:
        term = (person.get("terms") or [{}])[-1]
        bioguide_id = (person.get("id") or {}).get("bioguide")
        if term.get("type") == "sen" and term.get("state") == state and bioguide_id:
            senators[ascii_key((person.get("name") or {}).get("last"))] = bioguide_id
    matched = 0
    for record in records:
        if record.get("photo_url"):
            continue
        for last_name, bioguide_id in senators.items():
            if last_name and last_name in ascii_key(record.get("name")):
                record["photo_url"] = photo_url(bioguide_id)
                matched += record["photo_url"] is not None
                break
    return matched


def fetch_legislators(client) -> list[dict]:
    return json.loads(client.get(LEGISLATORS_URL))
