"""Parse the saved roster pages offline and report who each source yields, and how long parsing took.

    python tools/eval_rosters.py > before.json     # run, change the parser, run again, then:
    python tools/eval_rosters.py --compare before.json after.json
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from collector.scrapers.base import FetchError  # noqa: E402
from collector.scrapers.city_roster import parse_city_roster  # noqa: E402
from collector.scrapers.civicplus_directory import parse_directory  # noqa: E402

SNAP = ROOT / "snapshots" / "rosters"


def evaluate() -> dict:
    out = {}
    for path in sorted(SNAP.glob("*.json")):
        snap = json.loads(path.read_text(encoding="utf-8"))
        src, pages = snap["source"], [tuple(p) for p in snap["pages"]]
        start = time.perf_counter()
        try:
            if src["scraper"] == "civicplus_directory":
                rows = parse_directory(pages[0][0], pages[0][1], src.get("config") or {})
            else:
                rows = parse_city_roster(pages, src.get("config") or {})
            people = sorted(f"{r['name']} | {r['office_title']}" for r in rows)
            error = None
        except FetchError as exc:
            people, error = [], str(exc)[:160]
        out[src["key"]] = {"seconds": round(time.perf_counter() - start, 4), "people": people, "error": error,
                           "photos": sum(1 for r in (rows if not error else []) if r.get("photo_url")),
                           "seats": (src.get("config") or {}).get("seats")}
    return out


def compare(before: dict, after: dict) -> None:
    t0 = sum(v["seconds"] for v in before.values()); t1 = sum(v["seconds"] for v in after.values())
    ok0 = sum(1 for v in before.values() if not v["error"]); ok1 = sum(1 for v in after.values() if not v["error"])
    p0 = sum(len(v["people"]) for v in before.values()); p1 = sum(len(v["people"]) for v in after.values())
    print(f"sources passing: {ok0} -> {ok1}   people: {p0} -> {p1}   parse time: {t0:.1f}s -> {t1:.1f}s")
    for key in sorted(after):
        b, a = before.get(key, {"people": [], "error": None}), after[key]
        gained, lost = sorted(set(a["people"]) - set(b["people"])), sorted(set(b["people"]) - set(a["people"]))
        if gained or lost or bool(a["error"]) != bool(b["error"]):
            print(f"\n{key}  (seats {a.get('seats')})" + (f"  NOW FAILS: {a['error']}" if a["error"] and not b["error"] else "")
                  + (f"  NOW PASSES (was: {b['error']})" if b["error"] and not a["error"] else ""))
            for p in gained:
                print(f"   + {p}")
            for p in lost:
                print(f"   - {p}")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--compare"]:
        compare(json.loads(Path(sys.argv[2]).read_text()), json.loads(Path(sys.argv[3]).read_text()))
    else:
        print(json.dumps(evaluate(), indent=1))
