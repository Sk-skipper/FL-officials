"""County Supervisors of Elections, from the Florida Division of Elections:
https://dos.elections.myflorida.com/supervisors/

The index page links to one page per county. A county page that cannot be
read with confidence becomes a failed record, never a guessed one.
"""
import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from collector.geo import canonical_county
from collector.normalize import clean_text, normalize_email, normalize_phone, normalize_url, parse_name
from collector.scrapers.base import BaseScraper, FetchError

logger = logging.getLogger(__name__)

_COUNTY_HREF = re.compile(r"countyInfo\.asp\?county=\w+", re.I)
_TITLE_LINE = re.compile(r"\bSupervisor of Elections\b", re.I)
# The live pages print the name and title on one line: "Joe Scott, Supervisor".
_NAME_COMMA_TITLE = re.compile(r"^(?P<name>[^,]+(?:,\s*(?:Jr|Sr|II|III|IV)\.?)?),\s*Supervisor(?: of Elections)?\.?$", re.I)
_PHOTO_ALT = re.compile(r"photo of the current supervisor", re.I)
_PHONE_LABEL = re.compile(r"^(?:Phone|Telephone|Office)\s*:?\s*(.+)$", re.I)
_EMAIL_IN_TEXT = re.compile(r"[\w.+'-]+@[\w-]+(?:\.[\w-]+)+")
_NOT_A_NAME = re.compile(
    r"\d|county|supervisor|elections|address|phone|fax|email|division|florida|\b(?:contact|your|meet|welcome|office)\b", re.I
)


_CF_EMAIL = re.compile(r"/cdn-cgi/l/email-protection#([0-9a-f]{4,})", re.I)


def decode_cf_email(encoded: str) -> str | None:
    """Cloudflare stores an address as hex bytes XORed with the first byte."""
    try:
        data = bytes.fromhex(encoded)
    except ValueError:
        return None
    if len(data) < 2:
        return None
    return "".join(chr(b ^ data[0]) for b in data[1:])


def parse_supervisor_index(html: str, base_url: str) -> list[tuple[str, str]]:
    """Return (county name, county page URL) pairs."""
    soup = BeautifulSoup(html, "lxml")
    seen: dict[str, str] = {}
    for link in soup.find_all("a", href=_COUNTY_HREF):
        county = canonical_county(link.get_text(" "))
        if county and county not in seen:
            seen[county] = urljoin(base_url, link["href"])
    return list(seen.items())


def _looks_like_name(line: str) -> bool:
    if _NOT_A_NAME.search(line) or not 2 <= len(line.split()) <= 6:
        return False
    parts = parse_name(line)
    return parts is not None and bool(parts.first)


def parse_supervisor_page(html: str, county: str, page_url: str) -> dict:
    """Read one county page. Expected shape: the supervisor's name on its own
    line next to a 'Supervisor of Elections' line, followed by labelled
    contact lines."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer", "title", "head"]):
        tag.decompose()
    lines = [clean_text(line) for line in soup.get_text("\n").split("\n")]
    lines = [line for line in lines if line]

    name = None
    for line in lines:
        match = _NAME_COMMA_TITLE.match(line)
        if match and _looks_like_name(match.group("name")):
            name = clean_text(match.group("name"))
            break
    for i, line in enumerate(lines):
        if name:
            break
        if not _TITLE_LINE.search(line):
            continue
        # "Jane Q. Public - Supervisor of Elections" on one line
        before = _TITLE_LINE.split(line)[0].strip(" ,-–:")
        if before and _looks_like_name(before):
            name = before
            break
        # name on the line above or below the title
        for j in (i - 1, i + 1):
            if 0 <= j < len(lines) and _looks_like_name(lines[j]):
                name = lines[j]
                break

    base = {"county": county, "source_url": page_url}
    if not name:
        return {**base, "_error": f"Could not identify the supervisor's name on the {county} County page"}

    phone = None
    for line in lines:
        match = _PHONE_LABEL.match(line)
        if match and (phone := normalize_phone(match.group(1))):
            break

    email = None
    mailto = soup.find("a", href=re.compile(r"^mailto:", re.I))
    if mailto:
        email = normalize_email(mailto["href"])
    if not email:
        # The live site hides addresses behind Cloudflare's email protection.
        for link in soup.find_all("a", href=_CF_EMAIL):
            if email := normalize_email(decode_cf_email(_CF_EMAIL.search(link["href"]).group(1))):
                break
        if not email:
            for tag in soup.find_all(attrs={"data-cfemail": True}):
                if email := normalize_email(decode_cf_email(tag["data-cfemail"])):
                    break
    if not email:
        for line in lines:
            if line.lower().startswith(("email", "e-mail")) and (m := _EMAIL_IN_TEXT.search(line)):
                email = normalize_email(m.group())
                break

    website = None
    for link in soup.find_all("a", href=re.compile(r"^https?://", re.I)):
        href = link["href"]
        if "myflorida.com" in href or "dos.fl.gov" in href or "state.fl.us" in href:
            continue
        # Only accept a link that is presented as the office's web address.
        label = clean_text(link.get_text(" ")).lower()
        context = clean_text(link.parent.get_text(" ")).lower() if link.parent else ""
        if not (label.startswith(("http", "www.")) or "web" in context):
            continue
        website = normalize_url(href)
        if website:
            break

    photo = None
    for img in soup.find_all("img", alt=_PHOTO_ALT):
        src = (img.get("src") or "").strip()
        if src and not src.startswith("data:"):
            photo = urljoin(page_url, src.split("?")[0])
            break

    return {
        **base,
        "name": name,
        "photo_url": photo,
        "office_title": "Supervisor of Elections",
        "government_level": "county",
        "selection_method": "elected",
        "jurisdiction": f"{county} County",
        "phone": phone,
        "email": email,
        "official_website": website,
    }


class FLSupervisorsScraper(BaseScraper):
    def collect(self) -> list[dict]:
        counties = parse_supervisor_index(self.client.get(self.source_url), self.source_url)
        records = []
        for county, url in counties:
            try:
                records.append(parse_supervisor_page(self.client.get(url), county, url))
            except FetchError as exc:
                logger.warning("Supervisor page for %s failed: %s", county, exc)
                records.append({"county": county, "source_url": url, "_error": str(exc)})
        return records
