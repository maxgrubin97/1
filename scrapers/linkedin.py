"""
LinkedIn public profile scraper via Google search.

Searches Google for public LinkedIn profiles matching target criteria.
No LinkedIn login required — zero risk of account restrictions.
"""

import logging
import random
import re
import time
from urllib.parse import quote_plus, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

from models import Lead, classify_role

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]


def _get_headers() -> dict:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }


def _parse_linkedin_title(title: str) -> dict:
    """
    Parse a LinkedIn search result title.
    Format: 'John Doe - CEO - Acme Corp | LinkedIn'
    """
    title = re.sub(r"\s*[|–-]\s*LinkedIn\s*$", "", title, flags=re.IGNORECASE).strip()
    parts = re.split(r"\s*[–-]\s*", title, maxsplit=2)

    result = {"name": "", "title": "", "company": ""}
    if len(parts) >= 1:
        result["name"] = parts[0].strip()
    if len(parts) >= 2:
        result["title"] = parts[1].strip()
    if len(parts) >= 3:
        result["company"] = parts[2].strip()
    return result


def _extract_linkedin_url(raw_url: str) -> str:
    """Extract the real LinkedIn URL from a Google redirect."""
    if "linkedin.com/in/" not in raw_url:
        return raw_url

    parsed = urlparse(raw_url)
    if parsed.hostname and "google" in parsed.hostname:
        qs = parse_qs(parsed.query)
        for key in ("q", "url"):
            if key in qs:
                return qs[key][0]

    # Strip tracking params
    clean = raw_url.split("&sa=")[0].split("&ved=")[0]
    return clean


def _extract_location(snippet: str) -> str:
    """Try to pull a location from a Google snippet."""
    patterns = [
        r"([\w\s]+Metropolitan Area)",
        r"([\w\s]+,\s*(?:NY|NJ|CT|New York|New Jersey|Connecticut))",
        r"([\w\s]+,\s*[A-Z]{2})\b",
        r"(Greater [\w\s]+ Area)",
    ]
    for pattern in patterns:
        match = re.search(pattern, snippet)
        if match:
            return match.group(1).strip()
    return ""


def _search_google(query: str, num: int = 20) -> requests.Response | None:
    """Execute a Google search and return the response."""
    url = f"https://www.google.com/search?q={quote_plus(query)}&num={num}&hl=en"
    try:
        resp = requests.get(url, headers=_get_headers(), timeout=15)
        resp.raise_for_status()
        return resp
    except requests.RequestException as e:
        logger.warning(f"Google search failed: {e}")
        return None


def _search_serpapi(query: str, num: int = 20, api_key: str = "") -> list[dict] | None:
    """Use SerpAPI for more reliable results (optional)."""
    if not api_key:
        return None
    try:
        resp = requests.get(
            "https://serpapi.com/search",
            params={"q": query, "num": num, "api_key": api_key, "engine": "google"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("organic_results", [])
    except Exception as e:
        logger.warning(f"SerpAPI request failed: {e}")
        return None


def _parse_google_html(html: str) -> list[Lead]:
    """Parse Google search result HTML for LinkedIn profiles."""
    leads = []
    soup = BeautifulSoup(html, "html.parser")

    for result in soup.select("div.g"):
        try:
            link_el = result.select_one("a[href]")
            if not link_el:
                continue
            raw_url = link_el.get("href", "")
            if "linkedin.com/in/" not in raw_url:
                continue

            linkedin_url = _extract_linkedin_url(raw_url)

            title_el = result.select_one("h3")
            title_text = title_el.get_text(strip=True) if title_el else ""
            parsed = _parse_linkedin_title(title_text)

            # Get snippet text
            snippet = ""
            for sel in ["div[data-sncf]", "div.VwiC3b", "span.aCOpRe", "div.IsZvec"]:
                snippet_el = result.select_one(sel)
                if snippet_el:
                    snippet = snippet_el.get_text(separator=" ", strip=True)
                    break

            location = _extract_location(snippet)
            job_title = parsed["title"]

            lead = Lead(
                name=parsed["name"],
                title=job_title,
                company=parsed["company"],
                location=location,
                linkedin_url=linkedin_url,
                role_type=classify_role(job_title),
                source="linkedin",
            )

            if lead.name and len(lead.name) > 1:
                leads.append(lead)
                logger.info(f"  [LinkedIn] {lead.name} | {lead.title} | {lead.company}")

        except Exception as e:
            logger.debug(f"Error parsing search result: {e}")
            continue

    return leads


def _parse_serpapi_results(results: list[dict]) -> list[Lead]:
    """Parse SerpAPI organic results for LinkedIn profiles."""
    leads = []
    for r in results:
        link = r.get("link", "")
        if "linkedin.com/in/" not in link:
            continue

        title_text = r.get("title", "")
        parsed = _parse_linkedin_title(title_text)
        snippet = r.get("snippet", "")
        location = _extract_location(snippet)
        job_title = parsed["title"]

        lead = Lead(
            name=parsed["name"],
            title=job_title,
            company=parsed["company"],
            location=location,
            linkedin_url=link,
            role_type=classify_role(job_title),
            source="linkedin",
        )

        if lead.name and len(lead.name) > 1:
            leads.append(lead)
            logger.info(f"  [LinkedIn] {lead.name} | {lead.title} | {lead.company}")

    return leads


def scrape_linkedin(
    queries: list[str],
    locations: list[str],
    max_results_per_query: int = 20,
    delay_range: tuple[float, float] = (3.0, 6.0),
    serpapi_key: str = "",
) -> list[Lead]:
    """
    Search for LinkedIn profiles across all query + location combinations.

    Args:
        queries: Search query templates (without location).
                 The term site:linkedin.com/in/ is prepended automatically.
        locations: Target locations to append to each query.
        max_results_per_query: Number of Google results per search.
        delay_range: (min, max) seconds to wait between requests.
        serpapi_key: Optional SerpAPI key for reliable results.

    Returns:
        Deduplicated list of Lead objects.
    """
    all_leads: list[Lead] = []
    seen_urls: set[str] = set()
    total_queries = len(queries) * len(locations)
    current = 0

    for query_template in queries:
        for location in locations:
            current += 1
            full_query = f'site:linkedin.com/in/ {query_template} "{location}"'
            logger.info(f"[{current}/{total_queries}] Searching: {full_query}")

            leads: list[Lead] = []

            # Try SerpAPI first if key is available
            serpapi_results = _search_serpapi(full_query, max_results_per_query, serpapi_key)
            if serpapi_results is not None:
                leads = _parse_serpapi_results(serpapi_results)
            else:
                # Fall back to direct Google search
                resp = _search_google(full_query, max_results_per_query)
                if resp:
                    leads = _parse_google_html(resp.text)

            # Deduplicate and add
            for lead in leads:
                url_key = lead.linkedin_url.rstrip("/").lower()
                if url_key not in seen_urls:
                    seen_urls.add(url_key)
                    if not lead.location:
                        lead.location = location
                    all_leads.append(lead)

            logger.info(f"  -> {len(leads)} results, {len(all_leads)} unique leads total")

            # Rate limiting
            delay = random.uniform(*delay_range)
            logger.debug(f"  Waiting {delay:.1f}s...")
            time.sleep(delay)

    logger.info(f"LinkedIn scraping complete: {len(all_leads)} unique leads")
    return all_leads
