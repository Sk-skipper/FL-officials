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
    rows.append({"key": "soe_x", "name": "X SOE", "level": "county", "status": "failed",
                 "error": "FetchError: HTTP 403 for https://x: access is restricted", "failing_since": "2026-11-27"})
    errors, warnings = classify(rows, date(2026, 11, 27))
    assert len(errors) == 1 and "Lee SOE" in errors[0] and "new today" in errors[0]
    assert [w.split(" (")[0] for w in warnings] == ["B Town", "X SOE", "A City", "R County"]  # newest first
    assert "failing 8 days, since 2026-11-20" in warnings[2]


def test_only_a_shrinking_list_is_held_for_review():
    p = lambda n, t="Commissioner": {"full_name": n, "office_title": t}  # noqa: E731
    shrink = SourceResult(key="k", name="n", removed=[p("A"), p("B")], added=[])
    assert needs_review(shrink, 7)
    election = SourceResult(key="k", name="n", removed=[p("A"), p("B"), p("C")], added=[p("D"), p("E"), p("F")])
    assert not needs_review(election, 5)  # three seats changed hands: news, published
    rotation = SourceResult(key="k", name="n", removed=[p("Ruzzano"), p("Caggiano", "Vice Mayor"), p("Arserio", "Mayor")],
                            added=[p("Ruzzano", "Vice Mayor"), p("Caggiano", "Mayor"), p("Schwartz")])
    assert not needs_review(rotation, 5)  # titles rotated, one new member
    gone = SourceResult(key="k", name="n", removed=[p("A"), p("B"), p("C")], added=[p("D")])
    assert needs_review(gone, 5)  # net two fewer people
