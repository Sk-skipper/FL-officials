from collector.normalize import normalize_email
from collector.scrapers.city_roster import _same_person, match_emails


def test_messy_mailto_links():
    assert normalize_email("mailto:email to:hweinberg@cityofaventura.com") == "hweinberg@cityofaventura.com"
    assert normalize_email("mailto:mail to:abloom@cityofaventura.com") == "abloom@cityofaventura.com"
    assert normalize_email("mailto:SGlassman@fortlauderdale.gov?subject=Hi") == "sglassman@fortlauderdale.gov"


def test_one_letter_surname_slip_is_one_person():
    assert _same_person("Howard S. Weiberg", "Howard S. Weinberg")
    assert not _same_person("John Smith", "Jane Smyth")
    assert not _same_person("Ann Lee", "Ann Lea")  # too short to call a typo


CARDS = """
<div><h3>Howard S. Weinberg</h3><p>Mayor<br><a href="mailto:email to:hweinberg@city.gov">hweinberg@city.gov</a></p></div>
<div><h3>Cindy Orlinsky</h3><p>Seat 2<br><a href="mailto:corlinsky@city.gov">corlinsky@city.gov</a></p></div>
<div><h3>Art Gonzalez</h3><p>Seat 3<br><a href="mailto:jgroth@city.gov">jgroth@city.gov</a></p></div>
<div><h3>Mary Davis</h3><p>Seat 4<br><a href="mailto:seat4@city.gov">seat4@city.gov</a></p></div>
<p>Contact the commission: <a href="mailto:commission@city.gov">commission@city.gov</a></p>
"""


def test_emails_go_to_their_own_block_and_must_name_the_member():
    members = [{"name": n} for n in ("Howard S. Weinberg", "Cindy Orlinsky", "Art Gonzalez", "Mary Davis")]
    match_emails(CARDS, members)
    assert [m.get("email") for m in members] == ["hweinberg@city.gov", "corlinsky@city.gov", None, "seat4@city.gov"]


def test_vacant_seats_are_counted():
    from collector.scrapers.city_roster import count_vacancies
    assert count_vacancies(["Vacant", "Seat 3 - Vacant", "District 2: Vacancy", "Jane Doe", "Mayor"]) == 3
    assert count_vacancies(["The vacant lot on Main Street will be a park"]) == 0
