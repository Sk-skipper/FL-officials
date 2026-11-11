"""Shared test helpers. The people in these tests are fictional."""


def make_raw(**overrides) -> dict:
    raw = {
        "name": "Rivera, Ana M.",
        "office_title": "State Senator",
        "government_level": "state",
        "selection_method": "elected",
        "party": "D",
        "district": "12",
        "jurisdiction": "Florida",
        "counties": ["Broward", "Palm Beach"],
        "phone": "(850) 487-5012",
        "official_website": "https://www.flsenate.gov/Senators/S12",
        "source_url": "https://www.flsenate.gov/Senators",
    }
    raw.update(overrides)
    return raw
