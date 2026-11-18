"""A city or town's own "City Commission" / "Town Council" page: who holds each seat.

Florida's 411 municipalities use dozens of website builders, so writing CSS selectors for each one is
fragile. This scraper reads the page text instead and looks for the patterns every roster uses:

    Mayor Josh Levy                      (title, then name)
    Josh Levy, Mayor                     (name, then title)
    Josh Levy                            (name on one line,
    Mayor                                 title on the next)

Config for each source (data/sources.json):

    {
      "county": "Broward", "municipality": "Hollywood",
      "member_title": "Commissioner",   # what this city calls its members ("Councilmember" for councils)
      "seats": 7,                       # how many elected seats the body has, mayor included
      "selector": "main",               # optional: only read this part of the page
      "extra_urls": [],                 # optional: more pages, e.g. one per commissioner
      "exclude": ["Jane Doe"],          # optional: names the page shows that do not hold a seat
      "menu_links": true,               # optional: also read links anywhere on the page ("Mayor Jane Doe")
      "loose": true,                    # optional: a name followed by an email address counts as a member
      "title_map": {"Chair": "..."},    # optional: rename titles (a school board's "Chair" is still a board member)
      "render": true                    # optional: the page builds its list with JavaScript; load it in headless Chromium
    }

Safety: if the page yields fewer than `seats - 2` or more than `seats + 2` people, nothing is returned
and the source fails with a clear message, so the previous records stay published and a person checks it.
"""
import re
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from collector.normalize import clean_text
from collector.scrapers.base import BaseScraper, FetchError

TITLE = (r"(?:(?:School )?Board Member|(?<!Council )(?:Vice[- ])?President|(?:Board )?Supervisor(?! of Elections)|Vice[- ]Mayor|Deputy[- ]Mayor|Mayor[- ]Pro[- ]Tem(?:pore)?|Mayor|Council[- ]?(?:member|Member|man|woman|person)"
         r"|Commissioner|Council (?:Vice[- ])?President|(?:Vice[- ])?Chair(?:man|woman|person)?|Alderman|Village Trustee|Trustee)")
_PARTICLE = r"(?:de|del|de la|la|van|von|da|dos|St\.)"
_TOKEN = r"(?:(?:Mc|Mac|De|Di|Da|La|Le|Van|Von|O['’]|D['’])[A-Z][a-záéíóúñü]+|[A-ZÁÉÍÓÚÑ][a-záéíóúñü]+(?:['’][a-z]+)?(?:-[A-ZÁÉÍÓÚÑ]?[a-záéíóúñü]+)*|[A-Z]\.|[A-Z]{2,4}|\"[^\"]{2,20}\"|“[^”]{2,20}”|'[^']{2,20}'|\([A-Z][a-z]+\))"
NAME = rf"(?:(?:Dr|Hon|Rev)\.?\s+)?{_TOKEN}(?:\s+(?:{_PARTICLE}\s+)?{_TOKEN}){{1,4}}(?:,?\s+(?:Jr\.?|Sr\.?|III|II|IV|Esq\.?|Ph\.?D\.?|M\.?D\.?))?"
_SEAT_NO = r"(?:\d{1,2}|[A-H]|I{1,3}|IV|VI{0,2}|One|Two|Three|Four|Five|Six|Seven|Eight|Nine)"
SEAT = re.compile(rf"\b(?:(District|Seat|Group|Ward|Zone)\s*#?\s*({_SEAT_NO})\b|(At[- ]Large))", re.I)
SEATWORD = rf"(?:District|Seat|Group|Ward)\s*#?\s*{_SEAT_NO}"
_SEAT_NUMBER = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
                "i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7"}
_TITLE_FIRST = re.compile(rf"^(?:The\s+)?(?:Honorable\s+)?(?:(?:District|Seat|Group)\s*\w{{1,2}}\s+)?(?P<title>{TITLE})\b[\s,:\-–—]*(?P<name>{NAME})(?P<rest>(?:[\s,(\-–—|:].*)?)$")
_NAME_FIRST = re.compile(rf"^(?:The\s+)?(?:Honorable\s+)?(?P<name>{NAME})\s*(?:[,\-–—|:]\s*|\s+(?=Council|Vice|Mayor|Commissioner))(?P<seatfirst>{SEATWORD}\s+)?(?P<title>{TITLE})\b(?P<rest>.*)$")
_SEAT_TITLE = re.compile(rf"\(?{SEATWORD}\)?\s*[,\-–—|]\s*(?P<title>{TITLE})")
_TITLE_NAME = re.compile(rf"\b(?:{TITLE})\s+{NAME}")
_NAME_ONLY = re.compile(rf"^(?:The\s+)?(?:Honorable\s+)?(?P<name>{NAME})$")
_TITLE_ONLY = re.compile(rf"^(?:City |Town |Village )?(?P<title>{TITLE}|Council(?=,?\s*(?:Seat|District|Group)))\b(?P<rest>[^a-z]{{0,40}}|"
                         rf"\s*(?:[·•|/]|at[- ]large).{{0,40}}|[\s,\-–—]*(?:of|for)?\s*(?:District|Seat|Group|Ward|Zone|At[- ]Large).{{0,30}})$", re.I)
STAFF = re.compile(r"\b(manager|clerk|attorney|assistant|aide|liaison|secretary|former|emeritus|director|staff|candidate|"
                   r"executive|coordinator|police|fire|chief|department|committee|board of|appointed to|county)\b", re.I)
# With a real title on the line ("Commissioner Jane Doe, liaison to the county"), only these mean "not a member".
STAFF_TITLED = re.compile(r"\b(manager|clerk|attorney|assistant|aide|secretary|former|emeritus|interim|candidate)\b", re.I)
NOT_A_NAME = re.compile(
    r"\b(City|Town|Village|Commission|Council|Meeting|Meetings|Agenda|District|Seat|Office|Offices|Contact|Email|Phone|"
    r"Florida|Boulevard|Government|Department|Click|"
    r"Here|Message|Welcome|Biography|Members|Elected|Officials|Minutes|Calendar|Video|News|Proclamations|"
    r"Newsletter|Request|State|County|Board|Chambers|Search|Menu|About|Our|Your|The|And|Meet|Term|Expires|"
    r"Elections?|Mayors?|Commissioners?|Vice|Deputy|Council(?:member|man|woman)?s?|Members?|Pro|Tem|Chair|Report|"
    r"Address|Cell|Fax|Mobile|Tel|Phone|Agendas|Updates|Info|Information|Services|Resources|Documents|Directory|"
    r"Seal|Official|Photo|Photos|Edited|Website|Events|Newsletters?|Gallery|Training|Ethics|Certifications?|Policy|"
    r"Biography|Profile|Message|Annual|Economic|Empowerment|Initiative|Program|Programs|Who|Is|My|"
    r"International|Consortium|Development|Advocacy|Legislative|Click|Email|Headshot|Arrow|"
    r"Slideshow|Statement|Site|Map|Maps|Copyright|Notices|Together|Previous|Next|Portrait|"
    r"Committee|Strategic|Proclamations?|Citations|Zone|All|Districts)\b|\bWard (?:One|Two|Three|Four|Five|Six|I{1,3}|IV|V|\d)\b")
# Words that are also surnames (Mary Park, Grace Hall, John Beach): they reject a "name" only when every word of it is
# one of these or a hard word above ("City Hall", "Read More"), never a real person who happens to carry one.
AMBIGUOUS_WORDS = re.compile(r"(?i)^(?:Beach|Lakes|Park|Center|Hall|Read|More|View|Page|Great|Make|Close|Left|Right|Street|Road|Avenue|Mission|Trade|Watch|Home|Corner|Show|Find|Visit|Turns|Bio|Plan|Pillar|Again)$")
# Headline words a greedy name match can swallow ("Mayor Josh Levy Announces 2026 Budget").
HEADLINE_WORDS = re.compile(r"(?i)^(?:Announces?|Named|Sworn|Appointed|Presents?|Welcomes?|Hosts?|Celebrates?|Signs?|Votes?|"
                            r"Says|Joins|Receives?|Honou?red|Recognized|Proclaims?|Delivers?|Speaks?|Visits?|Attends?|Leads?|"
                            r"Launches|Releases|Thanks|Invites?|Shares|Message|Update|Updates|Statement|Corner|Newsletter)$")
CARD_NOT_A_NAME = re.compile(r"\b(District|Seat|Commission|Commissioners?|Council|Programs?|Office|City|Town|Village|Policy|"
                             r"Services|Department|Division|Recreation|Compliance|Resources|Works|Gardens|Biography|Events|"
                             r"Meetings?|Agendas?|Vacant|Vacancy|Information|Contact|Elections?|Members?)\b", re.I)
RANK_TITLES = {"President", "Vice President", "Mayor", "Vice Mayor", "Chair", "Vice Chair", "Council President", "Council Vice President", "Deputy Mayor"}
RANK = {"president": 0, "vice president": 1, "mayor": 0, "vice mayor": 1, "deputy mayor": 1, "mayor pro tem": 1, "council president": 0,
        "council vice president": 1, "chair": 0, "vice chair": 1}


@lru_cache(maxsize=16)
def _read_only_soup(html: str) -> BeautifulSoup:
    """One parse per page for the readers that only look (cards, photos); page_lines edits its own copy."""
    return BeautifulSoup(html, "lxml")


def _clean_name(raw: str, strict: bool = True) -> str | None:
    name = clean_text(re.sub(r"^(?:Dr|Hon|Rev)\.?\s+", "", raw))
    name = re.sub(r"['’]s\b.*$", "", name)  # "Jane Doe's Message" -> "Jane Doe"
    name = re.sub(r"\s*,\s*(Esq|Ph\.?D|M\.?D)\.?$", "", name)
    words = name.split()
    while words and HEADLINE_WORDS.match(words[-1]):  # "Josh Levy Announces" -> "Josh Levy"
        words.pop()
    half = len(words) // 2
    if len(words) >= 4 and len(words) % 2 == 0 and words[:half] == words[half:]:
        words = words[:half]  # "Eileen Higgins Eileen Higgins" (photo caption + heading on one line)
    name = " ".join(words)
    tokens = [t for t in re.split(r"\s+", name) if not re.fullmatch(r"[\"“'(].*[\"”')]", t)]
    if len(tokens) < 2 or len(tokens) > 6 or not re.match(r"[A-ZÁÉÍÓÚÑ]", name) or CARD_NOT_A_NAME.search(name) \
            or (strict and NOT_A_NAME.search(name)) \
            or all(AMBIGUOUS_WORDS.match(t) or NOT_A_NAME.fullmatch(t) for t in tokens if not re.fullmatch(r"[A-Z]\.?", t)):
        return None
    return name


def _smart_title(line: str) -> str:
    """An ALL-CAPS roster line in normal case: "MAYOR JOHN MCDONALD" -> "Mayor John McDonald"."""
    if not line.isupper() or len(re.findall(r"[A-Z]", line)) < 6:
        return line
    t = line.title()
    t = re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), t)
    t = re.sub(r"\bMac([a-z])(?=[a-z]{3})", lambda m: "Mac" + m.group(1).upper(), t)
    return re.sub(r"['’]S\b", "'s", t).replace(" Iii", " III").replace(" Ii", " II").replace(" Iv", " IV")


def _title(raw: str, member_title: str) -> str:
    t = clean_text(raw).lower().replace("-", " ")
    if t in ("president", "vice president"):
        return t.title()
    if "board member" in t or t in ("supervisor", "board supervisor"):
        return member_title
    if t.startswith("council") and ("president" in t):
        return "Council Vice President" if "vice" in t else "Council President"
    if t in ("vice mayor", "deputy mayor", "mayor"):
        return t.title()
    if t.startswith("mayor pro"):
        return "Vice Mayor"
    if "vice chair" in t:
        return "Vice Chair"
    if t.startswith("chair"):
        return "Chair"
    return member_title


def _seat(text: str) -> str | None:
    m = SEAT.search(text or "")
    if not m:
        return None
    if m.group(3):
        group = re.search(r"At[- ]Large,?\s*Group\s*(\d+)", text, re.I)
        return f"At-large Group {group.group(1)}" if group else "At-large"
    number = _SEAT_NUMBER.get(m.group(2).lower(), m.group(2).upper())
    return f"{m.group(1).title()} {number}"


def _link_heavy(tag) -> bool:
    text = len(tag.get_text(" ", strip=True))
    links = sum(len(a.get_text(" ", strip=True)) for a in tag.find_all("a"))
    return text == 0 or links / text > 0.5


def page_lines(html: str, selector: str | None = None, url: str | None = None, menu_links: bool = False) -> list[str]:
    """The page's visible text, one line per block, without menus and footers.

    Menus are recognised by being mostly links, not by their markup, because badly closed tags can make a
    <header> or a "menu" <div> contain the whole page. Menu links that sit under this page's own address and
    read like "Commissioner Jane Doe" are kept, since some cities only name members in the side menu.
    """
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    lines = []
    if url:
        base = urlsplit(url).path.rstrip("/").lower()
        for a in soup.select("a[href]"):
            path = urlsplit(urljoin(url, a["href"])).path.lower()
            text = clean_text(a.get_text(" "))
            if (menu_links or (base and path.startswith(base + "/"))) and (
                    _TITLE_FIRST.match(text) or _NAME_FIRST.match(text) or (menu_links and _SEAT_NAME.match(text))):
                lines.append(text)
    total = len((soup.body or soup).get_text(" ", strip=True)) or 1
    for tag in soup.select("nav, header, footer, aside, select, button, [class*='breadcrumb'], [id*='breadcrumb'], "
                           "[class*='menu'], [id*='menu'], [class*='footer'], [id*='footer'], [class*='navbar'], "
                           "[class*='sidebar'], [id*='sidebar'], [class*='skip']"):
        if tag.decomposed or (tag.name == "header" and tag.find_parent("article")):
            continue
        if len(tag.get_text(" ", strip=True)) < 0.5 * total and _link_heavy(tag):
            tag.decompose()
    root = soup.select_one(selector) if selector else None
    root = root or soup.body or soup
    for line in root.get_text("\n").splitlines():
        line = clean_text(line.replace("\u00a0", " ")).rstrip(",")
        if line.isupper() and 5 < len(line) < 60:
            line = re.sub(r"\b(Iv|Iii|Ii)\b", lambda m: m.group(0).upper(), line.title())  # "MAYOR JANE DOE"
        if line and len(line) < 140:
            lines.append(line)
    for img in root.select("img[alt]"):  # cards that name a member only in the photo's alt text
        alt = clean_text(img["alt"])
        if alt and _TITLE_FIRST.match(alt):
            lines.append(alt)
    return lines


_SEAT_NAME = re.compile(rf"^{SEATWORD}\s*[,:|\-–—]\s*(?:(?P<title>{TITLE})\s+)?(?P<name>{NAME})(?P<after>\s*,\s*[^,]{{1,30}}(?:,[^,]{{1,30}})*)?$")


_SEAT_LINE = re.compile(rf"\(?(?:{SEATWORD}|At[- ]Large(?:,?\s*Group\s*\d+)?)\)?", re.I)


def _same_person(a: str, b: str) -> bool:
    """"Josh Levy" / "Joshua Levy" / "Joshua A. Levy": same surname, and one first name begins the other."""
    def parts(n):
        t = [re.sub(r"[^a-z]", "", w) for w in n.lower().split() if w.strip(".,") not in ("jr", "sr", "ii", "iii", "iv")]
        return [w for w in t if w]
    pa, pb = parts(a), parts(b)
    if not pa or not pb or pa[-1] != pb[-1]:
        return False
    fa, fb = pa[0], pb[0]
    return fa.startswith(fb) or fb.startswith(fa) or SequenceMatcher(None, a.lower(), b.lower()).ratio() > 0.85


def find_members(lines: list[str], member_title: str, exclude: set[str] | None = None, loose: bool = False,
                 seat_lines: bool = False) -> list[dict]:
    """Every (name, title, seat) the lines describe, best title per person."""
    exclude = {e.lower() for e in exclude or ()}
    found: dict[str, dict] = {}

    def add(name_raw: str, title_raw: str, context: str, titled: bool = False):
        if (STAFF_TITLED if titled else STAFF).search(context):
            return
        name = _clean_name(name_raw)
        if not name or name.lower() in exclude:
            return
        title = _title(title_raw, member_title)
        tokens = [t for t in name.lower().replace(",", " ").split() if t.strip(".") not in ("jr", "sr", "ii", "iii", "iv")]
        key = re.sub(r"[^a-z]", "", "".join(tokens))  # full name: John Smith and Jane Smith stay two people
        seat = _seat(context)
        prev = found.get(key)
        if prev is None:
            found[key] = {"name": name, "title": title, "seat": seat, "first": title}
            return
        if RANK.get(title.lower(), 5) < RANK.get(prev["title"].lower(), 5):
            prev["title"] = title
        prev["seat"] = prev["seat"] or seat
        if len(name) > len(prev["name"]) and '"' not in prev["name"]:
            prev["name"] = name

    # Does this page put each title after the name ("Jane Doe" / "Mayor") or before it ("Mayor" / "Jane Doe")?
    names = [i for i, line in enumerate(lines) if _NAME_ONLY.match(line) and _clean_name(line)]
    follow = sum(1 for i in names if i + 1 < len(lines) and _TITLE_ONLY.match(lines[i + 1]))
    precede = sum(1 for i in names if i > 0 and _TITLE_ONLY.match(lines[i - 1]))
    titles_follow = follow >= precede
    lines = [_smart_title(line) for line in lines]
    for i, line in enumerate(lines):
        pairs = list(_TITLE_NAME.finditer(line))
        if len(pairs) > 1 and re.search(r"\band\b|;|&", line):  # "Commissioner Jane Doe (District 1) and Commissioner John Roe (District 2)"
            for part in re.split(r"\s+(?:and|&)\s+|;\s*", line):
                if pm := _TITLE_FIRST.match(part.strip()):
                    add(pm["name"], pm["title"], part, titled=True)
            continue
        m = _TITLE_FIRST.match(line) or _NAME_FIRST.match(line)
        if m:
            add(m["name"], m["title"], line, titled=True)
            continue
        if seat_lines and (sm := _SEAT_NAME.match(line)):
            # "District 1, Jane Doe" or "District 1: Jane Doe, M.Ed., Chair" (config "seat_name_lines")
            role = next((t for t in re.split(r"\s*,\s*", sm["after"] or "") if re.fullmatch(TITLE, t.strip())), None)
            add(sm["name"], sm["title"] or role or member_title, line, titled=bool(sm["title"] or role))
            continue
        n = _NAME_ONLY.match(line)
        if not n:
            continue
        is_seat = _SEAT_LINE.fullmatch(lines[i + 1]) if i + 1 < len(lines) else None
        order = (i + 1, i + 2, i - 1) if titles_follow else (i - 1, i + 1, i + 2)
        title_line = None if (titles_follow and is_seat) else next(
            (j for j in order if 0 <= j < len(lines) and _TITLE_ONLY.match(lines[j])), None)
        after = lines[i + 1] if i + 1 < len(lines) else ""
        if title_line is not None:
            t = _TITLE_ONLY.match(lines[title_line])
            seat_after = after if title_line != i + 1 else (lines[i + 2] if i + 2 < len(lines) else "")
            add(n["name"], t["title"], f"{seat_after} {lines[title_line]}" if SEAT.fullmatch(seat_after.strip("() ").replace("#", "")) else f"{lines[title_line]} {seat_after}")
        elif _SEAT_LINE.fullmatch(after):
            add(n["name"], member_title, after)  # "Jane Doe" / "Group 3": a member listed by seat
        elif st := _SEAT_TITLE.fullmatch(after):
            add(n["name"], st["title"], after, titled=True)  # "Jane Doe" / "District 1, Vice-Chair"
        elif loose and re.fullmatch(r"(?:mailto:)?[\w.+-]+@[\w.-]+", after):
            add(n["name"], member_title, line)  # "Jane Doe" / "jdoe@city.gov" (config "loose")

    members = []
    for m in found.values():
        twin = next((x for x in members if _same_person(x["name"], m["name"])), None)
        if twin is None:
            members.append(m)
        else:  # one person written two ways: keep the higher title, a seat, and the fuller name
            if RANK.get(m["title"].lower(), 5) < RANK.get(twin["title"].lower(), 5):
                twin["title"] = m["title"]
            twin["seat"] = twin["seat"] or m["seat"]
            if len(m["name"]) > len(twin["name"]) and '"' not in twin["name"]:
                twin["name"] = m["name"]
    # A leadership title held by two people means one mention was stale (a former mayor in a slideshow, say):
    # those people keep the title they were first listed with.
    for title in ("Mayor", "Vice Mayor", "Council President", "Chair"):
        holders = [m for m in members if m["title"] == title]
        if len(holders) > 1:
            for m in holders:
                if m["first"] != title:
                    m["title"] = m["first"]
    if section := heading_section(lines, member_title):
        for m in section:
            if not any(_same_person(m["name"], x["name"]) for x in members):
                members.append(m)
    return members


ROSTER_HEADING = re.compile(r"^(?:City |Town |Village )?(?:Commissioners|Council ?Members|Councilmembers|Members)$", re.I)


def heading_section(lines: list[str], member_title: str) -> list[dict]:
    """Names listed under a plain "City Commissioners" heading, each on its own line, with no title beside them."""
    out = []
    for i, line in enumerate(lines):
        if not ROSTER_HEADING.match(line):
            continue
        misses = 0
        for nxt in lines[i + 1:i + 16]:
            if _TITLE_ONLY.match(nxt) or re.match(r"(?i)^(contact|staff|meetings?|agendas?)$", nxt):
                break
            m = _NAME_ONLY.match(nxt)
            name = _clean_name(m["name"]) if m else None
            if name and not STAFF.search(nxt):
                out.append({"name": name, "title": member_title, "seat": None, "first": member_title})
                misses = 0
            elif not re.search(r"(?i)\d|term|email|@|phone|seat|district", nxt):
                misses += 1
                if misses >= 2:  # the list has ended
                    break
    return out


def _card_title(text: str) -> tuple[str | None, str]:
    """Split "Vice Mayor Jane Doe" into ("Vice Mayor", "Jane Doe")."""
    text = re.sub(r"^(?:(?!Vice|Deputy)[A-Z][a-z]+\s+){0,3}?(?=(?:Vice[- ]Mayor|Deputy[- ]Mayor|Mayor|Commissioner|Council))", "", text)
    m = re.match(rf"^(?P<title>{TITLE})\b[\s,:\-–—]*(?:/\s*(?:{TITLE})\s*)?(?P<rest>.+)$", text)
    if m:
        return m["title"], m["rest"]
    m = re.match(rf"^(?P<rest>.+?)\s*[,\-–—|]\s*(?P<title>{TITLE})\b.*$", text)
    return (m["title"], m["rest"]) if m else (None, text)


def find_cards(html: str, url: str, member_title: str) -> list[dict]:
    """Granicus OpenCities and similar platforms: one <article> card per member, name in .list-item-title."""
    soup = _read_only_soup(html)
    found = []
    for card in soup.select("article"):
        heading = card.select_one(".list-item-title")
        if heading is None:
            continue
        title, name = _card_title(clean_text(heading.get_text(" ")))
        context = clean_text(card.get_text(" "))
        link = card.select_one("a[href]")
        href = urljoin(url, link["href"]) if link else ""
        slug = urlsplit(href).path.rsplit("/", 1)[-1].replace("-", " ")
        if title is None:
            box = heading.find_parent("header") or heading.parent
            near = clean_text(box.get_text(" ").replace(heading.get_text(" "), " "))[:60]
            for candidate in (near, slug):
                m = re.match(rf"^(?:{TITLE})\b", candidate, re.I) or re.search(r"\b(Vice Mayor|Mayor)\b", candidate, re.I)
                if m:
                    title = m.group(0)
                    break
        name = re.sub(r"\s*[,\-–—]?\s*(?:District|Seat|Group)\s*\w+$", "", name)
        header = clean_text((heading.find_parent("header") or heading.parent).get_text(" "))[:120]
        if re.search(r"(?i)\b(former|past|emeritus|retired|in memoriam)\b", header):
            continue  # "Former Mayor Jane Doe": the leading word is cut from the title, so check the card's header
        if STAFF.search(f"{title or ''} {name}") or not _clean_name(name, strict=False):
            continue
        img = card.select_one("img[src]")
        email = card.select_one("a[href^='mailto:']")
        phone = card.select_one(".contact-phone .field-value")
        if any(f["name"] == _clean_name(name, strict=False) for f in found):
            continue  # the same card shown twice (a slider and a grid)
        found.append({
            "name": _clean_name(name, strict=False), "title": _title(title or member_title, member_title),
            "seat": _seat(f"{title or ''} {context[:200]} {slug}"),
            "photo_url": urljoin(url, img["src"]) if img else None,
            "email": email["href"] if email else None, "phone": clean_text(phone.get_text()) if phone else None,
            "official_website": href if href and href != url else None,
        })
    return found


BOARD_ROLES = [("vice[- ]?chair", "Vice Chair"), ("chair", "Chair"), ("secretary", "Secretary"), ("treasurer", "Treasurer")]
_HONORIFIC = re.compile(r"^(?:The Honorable|Senator|Representative|Judge|Dr\.|Hon\.)\s+")


def find_board(lines: list[str], role_pattern: str, member_title: str) -> list[dict]:
    """Boards list each member as a name line followed by a role line ("Jane Doe (Zone 3)" / "Chairperson")."""
    role_re = re.compile(role_pattern, re.I)
    out, seen = [], set()
    for i, line in enumerate(lines[:-1]):
        # The seat can be on the name line ("Jane Doe (Zone 3)") or alone just above it ("District 1").
        seat = _seat(line) or (_seat(lines[i - 1]) if i and _SEAT_LINE.fullmatch(lines[i - 1]) else None)
        bare = _HONORIFIC.sub("", re.sub(r"\s*\((?:Zone|District|Seat|Group)[^)]*\)\s*$", "", line))
        n = _NAME_ONLY.match(bare)
        role = lines[i + 1]
        if not n or not role_re.search(role):
            continue
        name = _clean_name(n["name"])
        if not name or name.lower() in seen or re.search(r"(?i)vacant", line):
            continue
        seen.add(name.lower())
        title = next((t for pat, t in BOARD_ROLES if re.match(pat, role, re.I)), member_title)
        out.append({"name": name, "title": title, "seat": seat, "first": title, "role": clean_text(role)[:80]})
    return out


def parse_city_roster(pages: list[tuple[str, str]], config: dict) -> list[dict]:
    member_title = config.get("member_title") or "Commissioner"
    exclude = {e.lower() for e in config.get("exclude") or []}
    if config.get("role_pattern"):
        lines = [line for html, url in pages for line in page_lines(html, config.get("selector"), url)]
        members = [m for m in find_board(lines, config["role_pattern"], member_title) if m["name"].lower() not in exclude]
    else:
        members = [m for html, url in pages for m in find_cards(html, url, member_title) if m["name"].lower() not in exclude]
    if members and len(members) < int(config.get("seats") or 5) - 2:
        # A stray card on a list-style page: read the lines too, and keep the cards' people plus any new ones.
        lines = [line for html, url in pages for line in page_lines(html, config.get("selector"), url, bool(config.get("menu_links")))]
        extra = find_members(lines, member_title, exclude, bool(config.get("loose")), bool(config.get("seat_name_lines")))
        members += [m for m in extra if not any(_same_person(m["name"], x["name"]) for x in members)]
    if not members:
        lines = []
        for html, url in pages:
            lines += page_lines(html, config.get("selector"), url, bool(config.get("menu_links")))
        members = find_members(lines, member_title, exclude, bool(config.get("loose")), bool(config.get("seat_name_lines")))
    # Excluded names match with or without a quoted nickname ("Robert \"Bob\" Campbell" = "Robert Campbell").
    plain = lambda n: " ".join(re.sub(r"[\"“”'‘’(][^\"“”'‘’)]*[\"“”'‘’)]", " ", n).split()).lower()  # noqa: E731
    members = [m for m in members if plain(m["name"]) not in exclude and m["name"].lower() not in exclude]
    for html, url in pages:
        match_photos(html, url, members)
    seats = int(config.get("seats") or 5)
    if not seats - 2 <= len(members) <= seats + 2:
        names = ", ".join(f"{m['name']} ({m['title']})" for m in members[:12])
        raise FetchError(f"Expected about {seats} seats on the page but found {len(members)}: {names or 'none'}. "
                         "The page may have changed; check it and update the config.")
    source_url = pages[0][1]
    municipality = config.get("municipality")
    level = config.get("government_level") or ("municipal" if municipality else "county")
    jurisdiction = config.get("jurisdiction") or municipality
    suffix = config.get("title_suffix") or ""
    records = []
    for m in members:
        seat = m["seat"]
        if m["title"] in ("Mayor", "Council President") and seat and not seat.startswith("At"):
            seat = None  # a citywide office; a district beside it on the page is someone else's
        district = seat.split()[-1] if seat and seat.split()[0] in ("District", "Seat", "Group", "Ward", "Zone") else None
        record = {
            "name": m["name"], "office_title": (config.get("title_map") or {}).get(m["title"], f"{m['title']}{suffix}"), "government_level": level,
            "jurisdiction": jurisdiction, "county": config["county"],
            "district": (district if district and district.isdigit() and seat.startswith("District") else (seat if district else None)),
            "seat_label": seat, "party": config.get("party", None if level == "county" and "School" not in (config.get("member_title") or "") else "Nonpartisan"),
            "selection_method": config.get("selection_method", "elected"), "source_url": source_url,
            "photo_url": m.get("photo_url"), "email": m.get("email"), "phone": m.get("phone"),
            "official_website": m.get("official_website"),
        }
        renamed = (config.get("title_map") or {}).get(m["title"])
        if renamed and renamed != m["title"] and m["title"] in RANK_TITLES:
            # A commission's "Mayor" or "Chair" is a member holding a rotating role: keep the role as the seat label.
            record["seat_label"] = f"{m['title']}{', ' + seat if seat else ''}"
        if municipality:
            record["municipality"] = municipality
        if config.get("special_district"):
            record["special_district"] = config["special_district"]
        records.append(record)
    return records


class CityRosterScraper(BaseScraper):
    def collect(self) -> list[dict]:
        urls = [self.source_url, *(self.config.get("extra_urls") or [])]
        fetch = self.client.get_rendered if self.config.get("render") else self.client.get
        pages = [(fetch(u), u) for u in urls]
        return parse_city_roster(pages, self.config)


# -- photos -----------------------------------------------------------------------------------------------------
_NOT_A_HEADSHOT = re.compile(r"(?i)logo|seal|banner|icon|header|footer|flag|map|button|arrow|social|facebook|twitter|"
                             r"instagram|youtube|linkedin|spacer|placeholder|default|blank|background|hero|sprite|flyer|poster|event|agenda|"
                             r"notice|news|announcement|workshop|meeting|calendar|signature|autograph|\bsig\b|building|courthouse|exterior|qr(?:[ _-]|%20)?code|coming(?:[ _-]|%20)*soon|webex|no[ _-]?image|\.svg(\?|$)")


def _img_src(img, url: str) -> str | None:
    for attr in ("data-src", "data-lazy-src", "data-original", "src"):
        value = (img.get(attr) or "").strip()
        if value and not value.startswith("data:"):
            return urljoin(url, value)
    srcset = (img.get("srcset") or img.get("data-srcset") or "").strip()
    return urljoin(url, srcset.split(",")[0].split()[0]) if srcset else None


def _fold(text: str) -> str:
    return re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower())


def match_photos(html: str, url: str, members: list[dict]) -> None:
    """Give each member without a photo the headshot that names them (alt text, title or file name) or that sits in the
    same small block of the page as their name. An image that would go to two people (a group photo) goes to nobody."""
    soup = _read_only_soup(html)
    images = []
    for img in soup.select("img"):
        src = _img_src(img, url)
        if not src or src.split("#")[0] == url or _NOT_A_HEADSHOT.search(f"{src} {img.get('alt', '')} {' '.join(img.get('class', []))}"):
            continue
        try:
            if int(img.get("width") or 999) < 48 or int(img.get("height") or 999) < 48:
                continue
        except ValueError:
            pass
        label = _fold(f"{img.get('alt', '')} {img.get('title', '')} {urlsplit(src).path.rsplit('/', 1)[-1]}")
        block, context = img, ""
        for _ in range(4):  # nearest ancestor with some text: the member's card or table row
            block = block.parent
            if block is None:
                break
            context = clean_text(block.get_text(" "))
            if len(context) > 3:
                break
        images.append((src, label, _fold(context[:300]), len(block.select("img")) if block else 99))
    chosen: dict[int, str] = {}
    for i, m in enumerate(members):
        if m.get("photo_url"):
            continue
        parts = [p for p in re.split(r"[\s.]+", m["name"]) if len(p) > 1]
        if len(parts) < 2:
            continue
        last, first = _fold(parts[-1] if not re.fullmatch(r"(?i)jr|sr|ii|iii|iv", parts[-1]) else parts[-2]), _fold(parts[0])
        hits = [src for src, label, context, n in images if last and (
            (last in label and (first in label or len(last) > 4)) or (n == 1 and last in context and first in context))]
        hits = list(dict.fromkeys(hits))
        if len(hits) == 1:
            chosen[i] = hits[0]
    counts: dict[str, int] = {}
    for src in chosen.values():
        counts[src] = counts.get(src, 0) + 1
    for i, src in chosen.items():
        if counts[src] == 1:
            # The site only shows https images; most city sites serve the same file over https.
            members[i]["photo_url"] = re.sub(r"^http://", "https://", src)
