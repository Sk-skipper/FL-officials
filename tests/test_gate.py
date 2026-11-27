from datetime import date

from collector.collect import SourceResult, needs_review
from collector.gate import classify


def test_county_failures_are_errors_and_city_failures_warnings():
    rows = [
        {"key": "soe_lee", "name": "Lee SOE", "level": "county", "status": "failed", "error": "HTTP 404", "failing_since": "2026-11-27"},
        {"key": "city_a", "name": "A City", "level": "municipal", "status": "failed", "error": "Expected about 5", "failing_since": "2026-11-20"},
        {"key": "city_b", "name": "B Town", "level": "municipal", "status": "failed", "error": "ReadTimeout", "failing_since": "2026-11-27"},
        {"key": "county_r", "name": "R County", "level": "county", "status": "failed",
         "error": "RobotsDisallowed: robots.txt disallows collecting x", "failing_since": "2026-11-01"},
        {"key": "ok", "name": "OK", "level": "state", "status": "success", "error": None, "failing_since": None},
    ]
    errors, warnings = classify(rows, date(2026, 11, 27))
    assert len(errors) == 1 and "Lee SOE" in errors[0] and "new today" in errors[0]
    assert [w.split(" (")[0] for w in warnings] == ["B Town", "A City", "R County"]  # newest first
    assert "failing 8 days, since 2026-11-20" in warnings[1]


def test_losing_several_people_is_held_for_review():
    r = SourceResult(key="k", name="n", removed=[{}, {}], added=[])
    assert needs_review(r, 7)
    turnover = SourceResult(key="k", name="n", removed=[{}], added=[{}])  # one seat changed hands
    assert not needs_review(turnover, 7)
    election = SourceResult(key="k", name="n", removed=[{}, {}], added=[{}, {}])  # two seats changed hands of five
    assert needs_review(election, 5)  # 40% of the list at once: a person checks it
