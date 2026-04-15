"""
HTTP utilities with rate limiting, retries, and compliance features.

Respects robots.txt, uses honest user agents, and enforces delays.
"""

import logging
import random
import time
from functools import lru_cache
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser

import requests

logger = logging.getLogger(__name__)

# Honest user agent — no spoofing
USER_AGENT = "MGRAdvisory-LeadEngine/1.0 (business research; contact@mgradvisory.com)"

# Browser-like agent for Google search (Google blocks non-browser agents)
SEARCH_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "DNT": "1",
}

SEARCH_HEADERS = {
    "User-Agent": SEARCH_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
}


@lru_cache(maxsize=200)
def _check_robots(base_url: str, path: str) -> bool:
    """Check robots.txt before fetching. Returns True if allowed."""
    try:
        rp = RobotFileParser()
        rp.set_url(urljoin(base_url, "/robots.txt"))
        rp.read()
        return rp.can_fetch(USER_AGENT, urljoin(base_url, path))
    except Exception:
        # If we can't read robots.txt, err on the side of caution for
        # non-search pages, but allow it (common for small business sites)
        return True


def fetch_url(
    url: str,
    respect_robots: bool = True,
    timeout: int = 15,
    max_retries: int = 2,
) -> requests.Response | None:
    """
    Fetch a URL with compliance checks.

    Returns None if blocked by robots.txt or on failure.
    """
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    if respect_robots and not _check_robots(base, parsed.path):
        logger.info(f"Blocked by robots.txt: {url}")
        return None

    for attempt in range(max_retries + 1):
        try:
            resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
            if resp.status_code == 429:
                wait = 2 ** (attempt + 2)
                logger.warning(f"Rate limited on {url}, waiting {wait}s")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            if attempt < max_retries:
                time.sleep(2 ** attempt)
            else:
                logger.warning(f"Failed to fetch {url}: {e}")
    return None


def google_search(
    query: str,
    num: int = 20,
) -> requests.Response | None:
    """Execute a Google web search. Returns raw response."""
    from urllib.parse import quote_plus

    url = f"https://www.google.com/search?q={quote_plus(query)}&num={num}&hl=en"
    try:
        resp = requests.get(url, headers=SEARCH_HEADERS, timeout=15)
        resp.raise_for_status()
        return resp
    except requests.RequestException as e:
        logger.warning(f"Google search failed: {e}")
        return None


def serpapi_search(
    query: str,
    api_key: str,
    num: int = 20,
    engine: str = "google",
) -> list[dict]:
    """Search via SerpAPI (compliant paid API). Returns organic results."""
    if not api_key:
        return []
    try:
        resp = requests.get(
            "https://serpapi.com/search",
            params={"q": query, "num": num, "api_key": api_key, "engine": engine},
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json().get("organic_results", [])
    except Exception as e:
        logger.warning(f"SerpAPI search failed: {e}")
        return []


def google_places_search(
    query: str,
    api_key: str,
) -> dict:
    """Google Places API text search."""
    if not api_key:
        return {}
    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/place/textsearch/json",
            params={"query": query, "key": api_key},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.warning(f"Places search failed: {e}")
        return {}


def google_place_details(
    place_id: str,
    api_key: str,
) -> dict:
    """Google Places API detail lookup."""
    if not api_key:
        return {}
    fields = (
        "name,formatted_address,formatted_phone_number,website,"
        "rating,user_ratings_total,types,business_status,url,"
        "opening_hours,reviews"
    )
    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/place/details/json",
            params={"place_id": place_id, "fields": fields, "key": api_key},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("result", {})
    except requests.RequestException as e:
        logger.warning(f"Place details failed: {e}")
        return {}


def rate_limit(delay_min: float = 2.0, delay_max: float = 5.0):
    """Sleep a random interval between requests."""
    delay = random.uniform(delay_min, delay_max)
    time.sleep(delay)
