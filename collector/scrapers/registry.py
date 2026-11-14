"""Maps the "scraper" value in data/sources.json to the class that collects it."""
import os

from collector.scrapers.base import BaseScraper, PoliteHttpClient
from collector.scrapers.broward_districts import BrowardDistrictsScraper
from collector.scrapers.broward_soe import BrowardSOEScraper
from collector.scrapers.city_roster import CityRosterScraper
from collector.scrapers.miamidade_soe import MiamiDadeSOEScraper
from collector.scrapers.fl_county_officers import ClerksScraper, FACScraper, SheriffsScraper
from collector.scrapers.fl_house import FLHouseScraper
from collector.scrapers.fl_senate import FLSenateScraper
from collector.scrapers.fl_supervisors import FLSupervisorsScraper
from collector.scrapers.generic_directory import CountyDirectoryScraper, MunicipalDirectoryScraper
from collector.scrapers.soe_officeholders import SOEOfficeHoldersScraper
from collector.scrapers.us_house import USHouseScraper
from collector.scrapers.us_senate import USSenateScraper

SCRAPERS: dict[str, type[BaseScraper]] = {
    "fl_senate": FLSenateScraper,
    "fl_house": FLHouseScraper,
    "fl_supervisors": FLSupervisorsScraper,
    "broward_districts": BrowardDistrictsScraper,
    "broward_soe": BrowardSOEScraper,
    "miamidade_soe": MiamiDadeSOEScraper,
    "city_roster": CityRosterScraper,
    "fl_sheriffs": SheriffsScraper,
    "fl_clerks": ClerksScraper,
    "fac_commissioners": FACScraper,
    "soe_officeholders": SOEOfficeHoldersScraper,
    "us_senate": USSenateScraper,
    "us_house": USHouseScraper,
    "county_directory": CountyDirectoryScraper,
    "municipal_directory": MunicipalDirectoryScraper,
}


def user_agent() -> str:
    """Identifies the collector honestly. In GitHub Actions the contact defaults
    to the repository's address, so site operators know where requests come from."""
    name = os.environ.get("SCRAPER_USER_AGENT") or "FloridaOfficialsDirectoryBot/1.0"
    contact = os.environ.get("SCRAPER_CONTACT", "").strip()
    if not contact and os.environ.get("GITHUB_REPOSITORY"):
        server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
        contact = f"{server}/{os.environ['GITHUB_REPOSITORY']}"
    return f"{name} (+{contact})" if contact else name


def build_scraper(scraper_key: str, source_url: str, config: dict | None) -> BaseScraper:
    try:
        scraper_cls = SCRAPERS[scraper_key]
    except KeyError:
        raise ValueError(f"Unknown scraper '{scraper_key}'. Choose one of: {', '.join(SCRAPERS)}") from None
    client = PoliteHttpClient(
        user_agent=user_agent(),
        delay_seconds=float(os.environ.get("SCRAPER_DELAY_SECONDS", "2")),
        timeout_seconds=int(os.environ.get("SCRAPER_TIMEOUT_SECONDS", "30")),
        max_retries=int(os.environ.get("SCRAPER_MAX_RETRIES", "3")),
    )
    return scraper_cls(source_url, config, client)
