"""tools/find_photos.py: the rules that keep a wrong portrait off a profile."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import find_photos as fp  # noqa: E402

BIO = """<html><body><nav><img src="/logo.png"></nav><main><h1>Judge {name}</h1>
<img src="/uploads/portrait.jpg" width="300" height="400"><p>Biography...</p></main></body></html>"""


def test_surname_must_be_a_whole_word():
    assert fp.names_in("/judges/ann-lee", "lee")
    assert not fp.names_in("/fleet/colleagues", "lee")
    assert not fp.names_in("/brownsville-court", "brown")


def test_own_page_photo_needs_the_persons_name_on_the_page():
    assert fp.own_page_photo(BIO.format(name="Ann Lee"), "https://court.gov/judges/42", "Ann Lee") == "https://court.gov/uploads/portrait.jpg"
    assert fp.own_page_photo(BIO.format(name="Bo Ray"), "https://court.gov/judges/42", "Ann Lee") is None  # someone else's page


def test_own_page_photo_skips_small_images_and_deep_gallery_images():
    html = """<main><h1>Ann Lee</h1><img src="/a.jpg" width="40" height="40"><img src="/b.jpg" width="50" height="50">
    <img src="/c.jpg" width="60" height="60"><img src="/gallery/d.jpg" width="400" height="400"></main>"""
    assert fp.own_page_photo(html, "https://court.gov/x", "Ann Lee") is None


def test_circuit_names_written_as_words():
    assert fp.circuit_of({"jurisdiction": "Twentieth Judicial Circuit", "office_title": "Circuit Judge"}) == 20
    assert fp.circuit_of({"jurisdiction": "2nd Judicial Circuit", "office_title": "Circuit Judge"}) == 2
