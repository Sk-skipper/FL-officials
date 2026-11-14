"""Miami-Dade County Supervisor of Elections: "Elected Officials Information" and "Judicial Directory" (PDFs).

Used for what no other source covers in Miami-Dade: the County Mayor and Commission, the School Board, the
State Attorney and Public Defender, the constitutional officers, the South Dade Soil and Water Conservation
District, the Community Councils, the Third District Court of Appeal, and the circuit and county judges.
Congress, the Legislature, the state executives, the Supreme Court and the Supervisor of Elections are
skipped because other sources already cover them.

Each row of the officials PDF has a "Contact" link; it is matched to its row by position on the page.
"""
import io
import re

from pypdf import PdfReader

from collector.normalize import clean_text
from collector.scrapers.base import BaseScraper

CIRCUIT = "11th Judicial Circuit (Miami-Dade County)"
COUNTY = "Miami-Dade County"
THIRD_DCA_COUNTIES = ["Miami-Dade", "Monroe"]
_TAIL = re.compile(
    r"\s+(?P<term>\d+\s+[Yy]ears|Appointed|N/A|-\s*-)\s.*?(?P<ballot>20\d\d|TBD|-+)\s+(?P<ends>[\d/]+|TBD|-+)\s*(Contact|_+)?\s*$")


def _link(url: str | None) -> str | None:
    """Keep a usable link: drop placeholders ("http://Vacant") and links rewritten by a browser-isolation proxy."""
    if not url or not url.startswith("http") or "fireglass" in url or "." not in url.split("//", 1)[-1].split("/")[0]:
        return None
    return re.sub(r"\?doing_wp_cron=[\d.]+$", "", url)


def _name(raw: str) -> str:
    return clean_text(raw).rstrip(",")


def pdf_lines(data: bytes) -> list[tuple[str, str | None]]:
    """Each text line of the PDF with its row's "Contact" link, if any.

    The office labels are placed on the page next to their link, so links are matched to labels by
    position, then to the full text lines (which pypdf joins correctly) by their label.
    """
    out = []
    for page in PdfReader(io.BytesIO(data)).pages:
        frags: list[tuple[float, float, str]] = []

        def visit(text, cm, tm, *_):
            if text.strip():
                frags.append((round(tm[5] * cm[3] + cm[5], 0), tm[4] * cm[0] + cm[4], text))
        text = page.extract_text(visitor_text=visit)
        links = []
        for annot in page.get("/Annots") or []:
            a = annot.get_object()
            uri = (a.get("/A") or {}).get("/URI")
            if uri:
                y0, y1 = float(a["/Rect"][1]), float(a["/Rect"][3])
                links.append(((y0 + y1) / 2, str(uri)))
        rows: dict[float, list] = {}
        for y, x, frag in frags:
            key = next((k for k in rows if abs(k - y) <= 2), y)
            rows.setdefault(key, []).append((x, frag))
        by_label = {}
        for y, parts in rows.items():
            label = clean_text(" ".join(t for _, t in sorted(parts))).rstrip(":")
            near = [(abs(ly - y), uri) for ly, uri in links if abs(ly - y) <= 6]
            if label and near and len(label) < 90:
                by_label[label] = min(near)[1]
        for line in (clean_text(t) for t in text.splitlines()):
            label = max((k for k in by_label if line.startswith(k)), key=len, default=None)
            out.append((line, by_label[label] if label else None))
    return out


def _bio(ballot: str, ends: str, month: str = "November") -> dict | None:
    bio = {}
    if re.fullmatch(r"20\d\d", ballot):
        bio["next_election"] = f"{month} {ballot}"
    if re.fullmatch(r"\d{1,2}/\d{1,2}/20\d\d", ends):
        bio["term_ends"] = ends
    return bio or None


def _office(label: str) -> dict | None:
    if label.startswith("State Attorney") or label.startswith("Public Defender"):
        return {"office_title": label, "government_level": "county", "jurisdiction": CIRCUIT, "county": "Miami-Dade"}
    if label.startswith("Clerk of the Circuit Court"):
        return {"office_title": "Clerk of the Circuit Court", "government_level": "county", "jurisdiction": COUNTY,
                "county": "Miami-Dade"}
    if label in ("Sheriff", "Property Appraiser", "Tax Collector"):
        return {"office_title": label, "government_level": "county", "jurisdiction": COUNTY, "county": "Miami-Dade"}
    if label == "Mayor":
        return {"office_title": "County Mayor", "government_level": "county", "jurisdiction": COUNTY,
                "county": "Miami-Dade", "party": "Nonpartisan"}
    if m := re.match(r"Board of County Commissioners District (\d+)", label):
        return {"office_title": "County Commissioner", "government_level": "county", "jurisdiction": COUNTY,
                "district": str(int(m.group(1))), "county": "Miami-Dade", "party": "Nonpartisan"}
    if m := re.match(r"School Board Members District (\d+)", label):
        return {"office_title": "School Board Member", "government_level": "county",
                "jurisdiction": "Miami-Dade County Public Schools", "district": str(int(m.group(1))),
                "seat_label": f"District {int(m.group(1))}", "county": "Miami-Dade", "party": "Nonpartisan"}
    if m := re.match(r"South Dade Soil & Water Conservation District Group (\d+)", label):
        return {"office_title": "Supervisor, South Dade Soil and Water Conservation District", "government_level": "county",
                "jurisdiction": "South Dade Soil and Water Conservation District", "district": str(int(m.group(1))),
                "seat_label": f"Group {int(m.group(1))}", "county": "Miami-Dade", "party": "Nonpartisan",
                "special_district": "south-dade-swcd"}
    if m := re.match(r"Community Council Area/Subarea (\d+)/\(?(.+?)\)?$", label):
        area, seat = str(int(m.group(1))), m.group(2)
        appointee = "Appointee" in seat
        return {"office_title": "Community Council Member", "government_level": "county",
                "jurisdiction": f"Miami-Dade Community Council {area}", "county": "Miami-Dade", "party": "Nonpartisan",
                "district": None if appointee else seat,
                "seat_label": "Appointed by the County Commissioner" if appointee else
                ("At-large" if seat == "At-Large" else f"Subarea {seat}"),
                "selection_method": "appointed" if appointee else "elected"}
    return None


SKIP_SECTIONS = ("President", "Vice President", "U.S.", "Governor", "Lt. Governor", "Secretary of State",
                 "Attorney General", "Chief Financial Officer", "Commissioner of Education",
                 "Commissioner of Agriculture", "State Senator", "State House", "Supervisor of Elections")


def parse_md_officials(lines: list[tuple[str, str | None]], source_url: str) -> list[dict]:
    records = []
    for line, link in lines:
        if line.startswith(SKIP_SECTIONS):
            continue
        tail = _TAIL.search(line)
        if not tail:
            continue
        head = line[:tail.start()]
        label, _, name = head.rpartition(": ") if ": " in head else (None, None, None)
        if label is None:  # "Sheriff Rosanna ..." has no colon: the office is a known prefix
            label = next((p for p in ("Clerk of the Circuit Court and Comptroller", "Sheriff", "Property Appraiser",
                                      "Tax Collector", "State Attorney", "Public Defender", "Mayor") if head.startswith(p + " ")), None)
            name = head[len(label):] if label else None
        if not label:
            continue
        office = _office(label.strip())
        if office is None:
            records.append({"name": name or label, "source_url": source_url,
                            "_error": f"Unrecognised office '{label}'; add it to collector/scrapers/miamidade_soe.py"})
            continue
        name = _name(name or "")
        if not name or re.match(r"(?i)vacant\b", name):
            continue
        records.append({"name": name, "selection_method": "appointed" if tail["term"] == "Appointed" else "elected",
                        **office, "official_website": _link(link),
                        "source_url": source_url, "bio": _bio(tail["ballot"], tail["ends"])})
    return records


_JUDGE = re.compile(r"^[\d/]*?(?P<year>20\d\d)(?P<name>\D.*?)(?P<group>\d{1,2})?$")


def parse_md_judges(text: str, source_url: str) -> list[dict]:
    records, section = [], None
    for raw in text.splitlines():
        line = clean_text(raw)
        if line.startswith("Justice of the Supreme Court"):
            section = None  # the Supreme Court comes from the Broward source, which lists contact details
        elif line.startswith("Third District Court of Appeal"):
            section = "dca"
        elif line.startswith("Circuit Judge"):
            section = "circuit"
        elif line.startswith("County Judge"):
            section = "county"
        if not section or not re.match(r"^\d", line):
            continue
        m = _JUDGE.match(line)
        if not m or "," not in m["name"]:
            continue
        last, _, first = m["name"].partition(",")
        if re.match(r"(?i)vacant", last.strip()):
            continue
        name = f"{clean_text(first)} {clean_text(last)}"
        base = {"name": name, "party": "Nonpartisan", "source_url": source_url}
        if section == "dca":
            records.append({**base, "office_title": "Judge, Third District Court of Appeal", "government_level": "state",
                            "jurisdiction": "Third District Court of Appeal", "counties": THIRD_DCA_COUNTIES,
                            "selection_method": "appointed", "bio": _bio(m["year"], "")})
            continue
        if not m["group"]:
            records.append({**base, "_error": f"No group number in '{line}'"})
            continue
        group = str(int(m["group"]))
        office = ({"office_title": "Circuit Judge", "jurisdiction": CIRCUIT} if section == "circuit"
                  else {"office_title": "County Court Judge", "jurisdiction": "Miami-Dade County Court"})
        records.append({**base, **office, "government_level": "county", "county": "Miami-Dade", "district": group,
                        "seat_label": f"Group {group}", "selection_method": "elected", "bio": _bio(m["year"], "", "August")})
    return records


class MiamiDadeSOEScraper(BaseScraper):
    def collect(self) -> list[dict]:
        records = parse_md_officials(pdf_lines(self.client.get_bytes(self.source_url)), self.source_url)
        judges_url = self.config.get("judges_url")
        if judges_url:
            reader = PdfReader(io.BytesIO(self.client.get_bytes(judges_url)))
            records += parse_md_judges("\n".join(p.extract_text() for p in reader.pages), judges_url)
        return records
