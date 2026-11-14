"""Polite HTTP client and the scraper base class.

Rules the client enforces for every source:
  * identifies itself with a transparent User-Agent
  * obeys robots.txt (RFC 9309)
  * waits between requests to the same host
  * retries only temporary failures, honouring Retry-After
  * never tries to get around 401/403 responses, logins or bot checks
"""
import logging
import time
from collections.abc import Callable
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests

logger = logging.getLogger(__name__)

RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_RETRY_AFTER_SECONDS = 120


class FetchError(Exception):
    """A page could not be retrieved."""


class RobotsDisallowed(FetchError):
    """robots.txt does not allow this URL to be collected."""


class PoliteHttpClient:
    def __init__(
        self,
        user_agent: str,
        delay_seconds: float = 2.0,
        timeout_seconds: int = 30,
        max_retries: int = 3,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.user_agent = user_agent
        self.delay_seconds = delay_seconds
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.session = session or requests.Session()
        self._sleep = sleep
        self._clock = clock
        self._last_request: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser | None] = {}

    # -- robots.txt ---------------------------------------------------------
    def _robots_for(self, url: str) -> RobotFileParser | None:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin in self._robots:
            return self._robots[origin]
        parser: RobotFileParser | None = RobotFileParser()
        try:
            self._wait(parts.netloc)
            response = self.session.get(
                f"{origin}/robots.txt", headers=self._headers(), timeout=self.timeout_seconds
            )
            if response.status_code >= 500:
                # RFC 9309: an unreachable robots.txt means "assume disallowed".
                parser.parse(["User-agent: *", "Disallow: /"])
            elif response.status_code >= 400:
                parser = None  # no robots.txt -> no restrictions
            else:
                parser.parse(response.text.splitlines())
        except requests.RequestException as exc:
            logger.warning("robots.txt unreachable for %s (%s); treating as disallowed", origin, exc)
            parser.parse(["User-agent: *", "Disallow: /"])
        self._robots[origin] = parser
        return parser

    def check_allowed(self, url: str) -> None:
        parser = self._robots_for(url)
        if parser is not None and not parser.can_fetch(self.user_agent, url):
            raise RobotsDisallowed(f"robots.txt disallows collecting {url}")

    # -- requests -----------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        return {"User-Agent": self.user_agent, "Accept": "text/html,application/xhtml+xml,application/xml"}

    def _wait(self, host: str) -> None:
        last = self._last_request.get(host)
        if last is not None:
            remaining = self.delay_seconds - (self._clock() - last)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request[host] = self._clock()

    def get(self, url: str) -> str:
        """Fetch a page as text, or raise FetchError."""
        return self._fetch(url).text

    def get_bytes(self, url: str) -> bytes:
        """Fetch a file (a PDF, say) as bytes, or raise FetchError."""
        return self._fetch(url).content

    def _fetch(self, url: str) -> requests.Response:
        self.check_allowed(url)
        host = urlsplit(url).netloc
        last_error = "unknown error"
        for attempt in range(self.max_retries + 1):
            self._wait(host)
            try:
                response = self.session.get(url, headers=self._headers(), timeout=self.timeout_seconds)
            except requests.RequestException as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning("GET %s failed (%s), attempt %d", url, last_error, attempt + 1)
                self._sleep(min(2 ** attempt, 30))
                continue

            status = response.status_code
            if status in RETRY_STATUSES:
                last_error = f"HTTP {status}"
                retry_after = response.headers.get("Retry-After", "")
                wait = float(retry_after) if retry_after.isdigit() else min(2 ** (attempt + 1), 30)
                logger.warning("GET %s returned %s, attempt %d", url, status, attempt + 1)
                self._sleep(min(wait, MAX_RETRY_AFTER_SECONDS))
                continue
            if status in (401, 403):
                raise FetchError(f"HTTP {status} for {url}: access is restricted and will not be bypassed")
            if status >= 400:
                raise FetchError(f"HTTP {status} for {url}")
            return response
        raise FetchError(f"{url} failed after {self.max_retries + 1} attempts ({last_error})")


class BaseScraper:
    """One subclass per source. `collect()` returns plain dicts for validation.

    A dict may carry "_error" instead of a name; it is then reported as a row
    that could not be read, so a person can see what was skipped.
    """

    def __init__(self, source_url: str, config: dict | None, client: PoliteHttpClient):
        self.source_url = source_url
        self.config = config or {}
        self.client = client

    def collect(self) -> list[dict]:
        raise NotImplementedError

    def fetch_and_parse(self, url: str, parse: Callable[[str], list[dict]]) -> list[dict]:
        if self.config.get("requires_js"):
            raise FetchError(
                f"{url} only shows its content with JavaScript, which this static build does not run. "
                "Add these officials by hand in data/manual_officials.json instead."
            )
        return parse(self.client.get(url))
