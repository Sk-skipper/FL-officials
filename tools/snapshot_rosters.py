"""Save every roster page (city_roster and civicplus_directory sources) so parsers can be tested offline.

    python tools/snapshot_rosters.py              # writes snapshots/rosters/<source key>.json (git-ignored)

Each file holds the source config and the fetched pages ([html, url] pairs), fetched exactly as the collector would
(same client, robots.txt, pacing, headless browser for "render" sources). tools/eval_rosters.py parses them.
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from collector.scrapers.base import FetchError, RobotsDisallowed  # noqa: E402
from collector.scrapers.registry import build_scraper  # noqa: E402

OUT = ROOT / "snapshots" / "rosters"


def save(source: dict) -> str:
    scraper = build_scraper(source["scraper"], source["url"], source.get("config"))
    cfg = source.get("config") or {}
    urls = [source["url"], *(cfg.get("extra_urls") or [])] if source["scraper"] == "city_roster" else [source["url"]]
    fetch = scraper.client.get_rendered if cfg.get("render") else scraper.client.get
    try:
        pages = [[fetch(u), u] for u in urls]
    except (FetchError, RobotsDisallowed) as exc:
        return f"FAIL {source['key']}: {str(exc)[:80]}"
    (OUT / f"{source['key']}.json").write_text(json.dumps({"source": source, "pages": pages}), encoding="utf-8")
    return f"ok {source['key']}"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sources = [s for s in json.loads((ROOT / "data/sources.json").read_text()) if s.get("scraper") in ("city_roster", "civicplus_directory")]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(save, sources))
    print(f"{sum(r.startswith('ok') for r in results)} of {len(sources)} saved")
    for r in results:
        if not r.startswith("ok"):
            print(r)


if __name__ == "__main__":
    main()
