"""Deduplication: exact merges inside a batch, likely duplicates across all records."""
from collections import defaultdict
from difflib import SequenceMatcher
from itertools import combinations

from collector.normalize import ascii_key
from collector.validate import ScrapedOfficial

_FILLABLE = ("party", "phone", "email", "official_website", "photo_url", "middle_name", "county", "municipality")

FIRST_NAME_THRESHOLD = 0.75
SCORE_THRESHOLD = 0.7


def dedupe_batch(records: list[ScrapedOfficial]) -> tuple[list[ScrapedOfficial], int]:
    """Collapse rows that describe the same person in the same seat.

    The first occurrence wins; later ones only fill fields the first left empty.
    Returns (unique records, number of rows dropped).
    """
    by_key: dict[str, ScrapedOfficial] = {}
    dropped = 0
    for record in records:
        key = record.dedupe_key
        kept = by_key.get(key)
        if kept is None:
            by_key[key] = record
            continue
        dropped += 1
        for field in _FILLABLE:
            if not getattr(kept, field) and getattr(record, field):
                setattr(kept, field, getattr(record, field))
        for county in record.counties:
            if county not in kept.counties:
                kept.counties.append(county)
    return list(by_key.values()), dropped


def _first_name_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a.startswith(b) or b.startswith(a):  # "Rob" vs "Robert"
        return 0.85
    return SequenceMatcher(None, a, b).ratio()


def find_duplicate_candidates(rows: list[dict]) -> list[tuple]:
    """Likely duplicates: same level and last name, similar first name, and the
    same office or place. Rows need id, government_level, first_name,
    last_name, office_title, jurisdiction, district.
    Returns (lower_id, higher_id, score) tuples."""
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        groups[(row["government_level"], ascii_key(row.get("last_name")))].append(row)

    candidates = []
    for group in groups.values():
        for a, b in combinations(group, 2):
            first_sim = _first_name_similarity(ascii_key(a.get("first_name")), ascii_key(b.get("first_name")))
            if first_sim < FIRST_NAME_THRESHOLD:
                continue
            same_office = ascii_key(a.get("office_title")) == ascii_key(b.get("office_title"))
            same_place = (ascii_key(a.get("jurisdiction")), ascii_key(a.get("district"))) == (
                ascii_key(b.get("jurisdiction")), ascii_key(b.get("district")))
            score = 0.6 * first_sim + (0.2 if same_office else 0) + (0.2 if same_place else 0)
            if score >= SCORE_THRESHOLD:
                low, high = sorted((a["id"], b["id"]))
                candidates.append((low, high, round(score, 3)))
    return sorted(candidates)
