"""Build data/elections/history.tsv: every state and local candidate outcome the Florida Division of Elections lists.

    python tools/election_history.py            # downloads anything not yet saved, then rebuilds the table

Source: the Division's public "Download Candidate List" form (dos.elections.myflorida.com/candidates/downloadcanlist.asp),
one tab-delimited file per election cycle and special election, 1996 onward, for state ("STA": Congress, the Legislature,
Cabinet, circuit and appellate judges, multi-county offices) and local ("LOC": county offices, school boards, county
judges, special districts) candidates. City elections are not in it.

Privacy: the files carry candidates' home addresses, phones, emails and voter ids. Raw files are kept only in
snapshots/elections/ (git-ignored) with a manifest of their SHA-256 hashes so re-runs are reproducible. The published
table keeps name, office, district, county, party and outcome, and replaces the voter id with a one-way hash, which
still links one person's records across elections but cannot be turned back into the id.

Outcome taxonomy (StatusCode): ELE elected, RET retained (judicial merit retention), UNO/UNP unopposed (elected without
a ballot line), DEF defeated, WIT withdrew, DNQ did not qualify, REM removed, DEC deceased, XTL transferred to a local
ballot. QUA qualified, HLD hold and ACT active appear on old elections (mostly 1996) whose outcome was never
recorded; they are kept as "not recorded", never counted as wins.
"""
import csv
import hashlib
import io
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from collector.scrapers.base import FetchError, PoliteHttpClient  # noqa: E402
from collector.scrapers.registry import user_agent  # noqa: E402

FORM = "https://dos.elections.myflorida.com/candidates/downloadcanlist.asp"
DOWNLOAD = "https://dos.elections.myflorida.com/candidates/extractCanList.asp"
RAW = ROOT / "snapshots" / "elections"
OUT = ROOT / "data" / "elections"
WON = {"ELE": "elected", "RET": "retained", "UNO": "unopposed", "UNP": "unopposed"}
COLUMNS = ["person", "election", "date", "kind", "level", "office_code", "office", "juris1", "juris2", "county",
           "status", "outcome", "party", "last", "first", "middle"]
SALT = "fl-officials:voter-id:v1"  # constant, so the hash is stable across runs; not a secret
PLACEHOLDER = "PLACEHOLDER"  # rows whose voter id is blank or all zeros (every row before 2012)


def person_key(voter_id: str) -> str:
    if not voter_id.strip().strip("0"):
        return "PLACEHOLDER"
    return hashlib.sha256(f"{SALT}:{voter_id.strip()}".encode()).hexdigest()[:16]


def elections(client: PoliteHttpClient) -> list[tuple[str, str]]:
    """(election id, label) for every general and special election on the form; presidential preference primaries skipped."""
    soup = BeautifulSoup(client.get(FORM), "lxml")
    out = []
    for opt in soup.select("select[name=elecID] option"):
        value, label = opt.get("value", ""), opt.get_text(" ", strip=True)
        if re.fullmatch(r"\d{8}-(GEN|S\d\d)", value) and int(value[:4]) <= 2026:
            out.append((value, label))
    return out


def outcome(code: str) -> str:
    return WON.get(code) or {"DEF": "defeated", "WIT": "withdrew", "DNQ": "did not qualify", "REM": "removed",
                             "DEC": "deceased", "XTL": "transferred",
                             # Old elections (mostly 1996) whose outcome the Division never recorded:
                             "QUA": "not recorded", "HLD": "not recorded", "ACT": "not recorded"}.get(code, code.lower() or "not recorded")


def main() -> None:
    client = PoliteHttpClient(user_agent(), 2, 120, 2)
    RAW.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    found = elections(client)
    print(f"{len(found)} elections on the form", file=sys.stderr)
    rows = []
    for election, label in found:
        for level in ("STA", "LOC"):
            path = RAW / f"{election}-{level}.tsv"
            current = election.startswith("2026")  # this cycle's outcomes are still being filled in
            if not path.exists() or current:
                try:
                    text = client.post(DOWNLOAD, {"elecID": election, "office": "All", "status": "All", "cantype": level,
                                                  "FormSubmit": "Download Candidate List"})
                except FetchError as exc:
                    print(f"  {election} {level}: {exc}", file=sys.stderr)
                    continue
                path.write_text(text, encoding="utf-8")
                manifest[path.name] = {"sha256": hashlib.sha256(text.encode()).hexdigest(), "label": label,
                                       "source": DOWNLOAD, "form": {"elecID": election, "cantype": level}}
            for r in csv.DictReader(io.StringIO(path.read_text(encoding="utf-8")), delimiter="\t"):
                if not (r.get("VoterID") or "").strip():
                    continue
                code = (r.get("StatusCode") or "").strip()
                rows.append({
                    "person": person_key(r["VoterID"]), "election": election, "date": f"{election[:4]}-{election[4:6]}-{election[6:8]}",
                    "kind": "general" if election.endswith("GEN") else "special", "level": level,
                    "office_code": (r.get("OfficeCode") or "").strip(), "office": (r.get("OfficeDesc") or "").strip(),
                    "juris1": (r.get("Juris1num") or "").strip(), "juris2": (r.get("Juris2num") or "").strip(),
                    "county": (r.get("County") or "").strip(), "status": code, "outcome": outcome(code),
                    "party": (r.get("PartyCode") or "").strip(), "last": (r.get("NameLast") or "").strip(),
                    "first": (r.get("NameFirst") or "").strip(), "middle": (r.get("NameMiddle") or "").strip()})
    # Voter ids appear from 2012 on; earlier rows carry a placeholder ("0"), shared by thousands of people. Those rows
    # get a name key instead (surname, first name, county, office), so they never link unrelated people; matching them
    # to a person is left to tools/derive_tenure.py, which does it only within the same county or seat.
    for r in rows:
        if r["person"] == PLACEHOLDER:
            r["person"] = "n" + hashlib.sha256(f"{SALT}:{r['last']}|{r['first']}|{r['county']}|{r['office']}".lower().encode()).hexdigest()[:15]
    # Some rows leave the county blank; take it from the same person's other rows for the same office.
    known: dict[tuple, str] = {}
    for r in rows:
        if r["county"] and not r["person"].startswith("n"):
            known.setdefault((r["person"], r["office"]), r["county"])
    for r in rows:
        if not r["county"]:
            r["county"] = known.get((r["person"], r["office"]), "")
    rows.sort(key=lambda r: (r["person"], r["date"], r["office"]))
    with (OUT / "history.tsv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, COLUMNS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    manifest_path.write_text(json.dumps(dict(sorted(manifest.items())), indent=1) + "\n")
    people = len({r["person"] for r in rows})
    print(f"Wrote {len(rows)} candidacies for {people} people to data/elections/history.tsv", file=sys.stderr)


if __name__ == "__main__":
    main()
