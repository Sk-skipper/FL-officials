"""Normalization for names, parties, districts and contact details.

Every function returns None rather than guessing when the input is unusable,
so nothing invalid or invented reaches the database.
"""
import re
import unicodedata
from dataclasses import dataclass

try:  # phonenumbers is a hard requirement in production; the fallback keeps unit tests portable
    import phonenumbers
except ImportError:  # pragma: no cover
    phonenumbers = None

_WS = re.compile(r"\s+")
_NICKNAME = re.compile(r"[\"“”(][^\"“”)]*[\"“”)]")
_EMAIL = re.compile(r"^[a-z0-9._%+\-']+@[a-z0-9\-]+(\.[a-z0-9\-]+)+$")

_PREFIXES = {
    "senator", "sen", "representative", "rep", "congressman", "congresswoman", "hon", "honorable",
    "dr", "mr", "mrs", "ms", "commissioner", "mayor", "sheriff", "judge",
}
_SUFFIXES = {"jr": "Jr.", "sr": "Sr.", "ii": "II", "iii": "III", "iv": "IV"}
_CREDENTIALS = {"esq", "md", "phd", "cpa", "jd", "dds", "dvm", "rn", "pe", "cera", "mfcep", "cmc", "mmc"}
_PARTICLES = {"de", "del", "la", "van", "von", "der", "di", "da", "st", "st."}

_PARTIES = {
    "r": "Republican", "rep": "Republican", "republican": "Republican",
    "d": "Democratic", "dem": "Democratic", "democrat": "Democratic", "democratic": "Democratic",
    "npa": "No Party Affiliation", "no party affiliation": "No Party Affiliation",
    "i": "Independent", "ind": "Independent", "independent": "Independent",
    "nonpartisan": "Nonpartisan", "non-partisan": "Nonpartisan",
    "lpf": "Libertarian", "libertarian": "Libertarian",
    "green": "Green",
}


def clean_text(value: object) -> str:
    if value is None:
        return ""
    return _WS.sub(" ", str(value).replace("\xa0", " ")).strip()


@dataclass(frozen=True)
class NameParts:
    full: str
    first: str | None
    middle: str | None
    last: str
    suffix: str | None


def _strip_dot(token: str) -> str:
    return token.lower().replace(".", "")


def _pop_suffix(tokens: list[str]) -> str | None:
    if len(tokens) > 1 and _strip_dot(tokens[-1]) in _SUFFIXES:
        return _SUFFIXES[_strip_dot(tokens.pop())]
    return None


def _strip_prefixes(tokens: list[str]) -> list[str]:
    while len(tokens) > 1 and _strip_dot(tokens[0]) in _PREFIXES:
        tokens = tokens[1:]
    return tokens


def parse_name(raw: object) -> NameParts | None:
    """Parse 'Last, First M.' or 'First M. Last Jr.' into parts."""
    text = _NICKNAME.sub(" ", clean_text(raw))
    pieces = [p.strip() for p in text.split(",") if p.strip()]
    suffix: str | None = None
    core: list[str] = []
    for piece in pieces:
        key = _strip_dot(piece)
        if key in _SUFFIXES:
            suffix = _SUFFIXES[key]
        elif key in _CREDENTIALS:
            continue
        else:
            core.append(piece)
    if not core:
        return None

    if len(core) >= 2:  # "Last, First Middle"
        last_tokens = core[0].split()
        suffix = _pop_suffix(last_tokens) or suffix
        last = " ".join(last_tokens)
        given = _strip_prefixes(" ".join(core[1:]).split())
        suffix = _pop_suffix(given) or suffix
    else:  # "First Middle Last"
        tokens = _strip_prefixes(core[0].split())
        suffix = _pop_suffix(tokens) or suffix
        if not tokens:
            return None
        start = len(tokens) - 1
        while start > 1 and tokens[start - 1].lower() in _PARTICLES:
            start -= 1
        last = " ".join(tokens[start:])
        given = tokens[:start]

    if not last or not re.search(r"[A-Za-zÀ-ɏ]", last):
        return None
    first = given[0] if given else None
    middle = " ".join(given[1:]) or None
    full = " ".join(part for part in (first, middle, last, suffix) if part)
    return NameParts(full=full, first=first, middle=middle, last=last, suffix=suffix)


def normalize_party(raw: object) -> str | None:
    text = clean_text(raw).strip("()")
    if not text:
        return None
    return _PARTIES.get(text.lower(), text.title() if len(text) > 3 else None)


def parse_district(raw: object) -> tuple[str | None, int | None]:
    """'District 12' / '12th' -> ('12', 12); 'At Large' -> ('At-Large', None)."""
    text = clean_text(raw)
    if not text:
        return None, None
    if re.search(r"at[\s-]*large", text, re.I):
        return "At-Large", None
    match = re.search(r"\d+", text)
    if match:
        number = int(match.group())
        return str(number), number
    return text, None


def normalize_phone(raw: object) -> str | None:
    """Return a US number as '(850) 487-5000', or None if it is not valid."""
    text = clean_text(raw)
    if text.lower().startswith("tel:"):
        text = text[4:]
    if not text:
        return None
    if phonenumbers is not None:
        try:
            parsed = phonenumbers.parse(text, "US")
        except phonenumbers.NumberParseException:
            return None
        if not phonenumbers.is_valid_number(parsed):
            return None
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.NATIONAL)

    ext_match = re.search(r"(?:ext\.?|x)\s*(\d{1,6})\s*$", text, re.I)
    if ext_match:
        text = text[: ext_match.start()]
    digits = re.sub(r"\D", "", text)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10 or digits[0] in "01" or digits[3] in "01":
        return None
    formatted = f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return f"{formatted} ext. {ext_match.group(1)}" if ext_match else formatted


def normalize_email(raw: object) -> str | None:
    text = clean_text(raw).lower()
    if text.startswith("mailto:"):
        text = text[7:].split("?")[0]
    return text if _EMAIL.match(text) else None


def normalize_url(raw: object) -> str | None:
    text = clean_text(raw)
    if re.match(r"^https?://[^\s/]+\.[^\s]+$", text, re.I):
        return text
    return None


def ascii_key(value: str | None) -> str:
    if not value:
        return ""
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", folded.lower())


def build_dedupe_key(level: str, office_title: str, jurisdiction: str, district: str | None,
                     last_name: str, first_name: str | None) -> str:
    """Identity of a record: the same person in the same seat always maps to one key."""
    return "|".join([
        ascii_key(level), ascii_key(office_title), ascii_key(jurisdiction), ascii_key(district),
        ascii_key(last_name), ascii_key(first_name),
    ])


def slugify(value: str | None) -> str:
    if not value:
        return ""
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    folded = re.sub(r"['\u2019.]", "", folded.lower())  # "O'Brien" -> "obrien", "St." -> "st"
    return re.sub(r"[^a-z0-9]+", "-", folded).strip("-")


def make_record_id(office_title: str, jurisdiction: str, district: str | None,
                   first_name: str | None, last_name: str) -> str:
    """Readable id used in URLs and in data/corrections.json,
    e.g. "state-senator-district-12-ana-rivera"."""
    place = f"district-{district}" if district else jurisdiction
    return "-".join(p for p in (slugify(office_title), slugify(place), slugify(first_name), slugify(last_name)) if p)
