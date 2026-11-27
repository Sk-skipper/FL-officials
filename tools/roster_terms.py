"""Read terms stated on city and special-district roster pages: "Term expires November 2028", "Current term:
2024-2028", "first elected in 2017", "Took office in January 2023".

    python tools/roster_terms.py        # reads snapshots/rosters/ (tools/snapshot_rosters.py), writes data/roster_terms.json

City elections are run by the cities, not the state, so the Division of Elections records used by
tools/derive_tenure.py don't have them; the cities' own pages are the source. Each official's statement is looked for
only in the lines between their name and the next official's name, and kept with the words it came from, so every
value can be checked against the page. A page that states nothing gives nothing; nothing is guessed.
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOTS = ROOT / "snapshots" / "rosters"
THIS_YEAR = 2026
MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
YEAR = r"((?:19|20)\d\d)"
ENDS = [
    re.compile(rf"(?i)term\s+(?:expires|ends|expiration)\s*(?:on|in)?\s*[:\-]?\s*({MONTH})?\s*(?:\d{{1,2}},?\s*)?{YEAR}"),
    re.compile(rf"(?i)term\s+(?:expires|ends)\s*[:\-]?\s*(\d{{1,2}})/(?:\d{{1,2}}/)?(\d{{2,4}})\b"),
    re.compile(rf"(?i)(?:current\s+)?term\s*(?:of office)?\s*[:\-]\s*(?:\w+\s+)?{YEAR}\s*(?:-|–|to|through)\s*(?:\w+\s+)?{YEAR}"),
    re.compile(r"(?i)(?:current\s+)?term\s*[:\-]\s*(\d{1,2})/(?:\d{1,2}/)?(\d{2,4})\s*(?:-|–|to|through)\s*(\d{1,2})/(?:\d{1,2}/)?(\d{2,4})"),
]
SINCE = re.compile(rf"(?i)\b(first\s+(?:elected|sworn\s+in|took\s+office|appointed)|serving\s+since|took\s+office|"
                   rf"has\s+served\s+since|(?<!re-)(?<!re)elected|sworn\s+in|appointed)\b[^.;]{{0,90}}?\b{YEAR}\b")
FIRST = re.compile(r"(?i)^(first|serving since|took office|has served since)")
NOT_ME = re.compile(r"(?i)city manager|city clerk|attorney|staff|police chief|director")


def fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def year4(y: str) -> int:
    n = int(y)
    return n + 2000 if n < 100 else n


def page_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
        tag.decompose()
    return [ln for ln in soup.get_text("\n", strip=True).split("\n") if ln.strip()]


def windows(lines: list[str], people: list[dict]) -> dict[str, list[str]]:
    """Each official's lines: from where their name appears to just before another official's name."""
    marks = []
    for i, ln in enumerate(lines):
        f = fold(ln)
        for p in people:
            last = fold(p["last_name"])
            if last and re.search(rf"\b{re.escape(last)}\b", f):
                marks.append((i, p["id"]))
    out: dict[str, list[str]] = {}
    for n, (i, pid) in enumerate(marks):
        end = next((j for j, other in marks[n + 1:] if other != pid), len(lines))
        out.setdefault(pid, []).extend(lines[i:min(end, i + 14)])
    return out


def term_end(text: str):
    for k, pat in enumerate(ENDS):
        m = pat.search(text)
        if not m:
            continue
        g = m.groups()
        if k == 0:
            month, year = (g[0] or "").lower()[:3] or None, int(g[1])
        elif k == 1:
            month, year = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"][int(g[0]) - 1] if 1 <= int(g[0]) <= 12 else None, year4(g[1])
        elif k == 2:
            month, year = None, int(g[1])
            return {"year": year, "month": month, "began": int(g[0]), "quote": m.group(0).strip()}
        else:
            months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
            month = months[int(g[2]) - 1] if 1 <= int(g[2]) <= 12 else None
            return {"year": year4(g[3]), "month": month, "began": year4(g[1]), "quote": m.group(0).strip()}
        return {"year": year, "month": month, "quote": m.group(0).strip()}
    return None


def since(text: str, title: str):
    """The earliest year they are said to have been elected, sworn in or appointed; a statement naming their current
    title (e.g. "elected mayor in 2022") is preferred, since an earlier "first elected to the commission" is a
    different office."""
    found = []
    for m in SINCE.finditer(text):
        y = int(m.group(2))
        if 1950 <= y <= THIS_YEAR and not re.search(r"(?i)\bagain\b|another term|second term|re-?elect", m.group(0)):
            found.append((y, m.group(0).strip(), m.group(1).lower()))
    if not found:
        return None
    t = fold(title)
    if "mayor" in t:
        named = [f for f in found if re.search(r"(?i)\bmayor\b", f[1]) and not re.search(r"(?i)vice|deputy", f[1])]
        if named:
            y, quote, verb = min(named)
            return {"year": y, "quote": quote, "office": "this office", "at_least": not FIRST.match(verb)}
    y, quote, verb = min(found)
    return {"year": y, "quote": quote, "office": "this office" if "mayor" not in t else "the council",
            "at_least": not FIRST.match(verb)}


def main() -> None:
    officials = json.loads((ROOT / "site/data/officials.json").read_text(encoding="utf-8"))["officials"]
    by_url: dict[str, list[dict]] = {}
    for r in officials:
        if r["government_level"] == "municipal" or r.get("special_district"):
            by_url.setdefault((r.get("source_url") or "").rstrip("/"), []).append(r)
    out, pages = {}, 0
    for f in sorted(SNAPSHOTS.glob("*.json")):
        snap = json.loads(f.read_text(encoding="utf-8"))
        urls = {snap["source"]["url"].rstrip("/"), *(u.rstrip("/") for _, u in snap["pages"])}
        people = [r for u in urls for r in by_url.get(u, [])]
        if not people:
            continue
        lines = [ln for html, _ in snap["pages"] for ln in page_lines(html)]
        for pid, win in windows(lines, people).items():
            text = " ".join(ln for ln in win if not NOT_ME.search(ln))
            r = next(p for p in people if p["id"] == pid)
            end, start = term_end(text), since(text, r["office_title"])
            if end and not THIS_YEAR - 1 <= end["year"] <= THIS_YEAR + 6:
                end = None  # a past or implausible end date: stale page
            if start and end and start["year"] > end["year"]:
                start = None
            if end and end.get("began") and not start:
                start = {"year": end["began"], "quote": end["quote"], "office": "current term", "at_least": True}
            if end or start:
                pages += 1
                out[pid] = {"name": r["full_name"], "source_url": r.get("source_url"),
                            **({"term_ends": {k: v for k, v in end.items() if k != "began"}} if end else {}),
                            **({"since": start} if start else {})}
    (ROOT / "data/roster_terms.json").write_text(json.dumps({"_how_to": "Generated by tools/roster_terms.py; see its docstring.",
                                                            **dict(sorted(out.items()))}, indent=1, ensure_ascii=False) + "\n",
                                                 encoding="utf-8")
    ends = sum("term_ends" in v for v in out.values())
    starts = sum("since" in v for v in out.values())
    print(f"{len(out)} officials with a stated term: {ends} term ends, {starts} start years", file=sys.stderr)


if __name__ == "__main__":
    main()
