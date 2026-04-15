"""
Web search collector — free discovery source requiring no API keys.

Uses Google search (direct HTTP) as primary, with DuckDuckGo HTML search
as fallback if Google returns a CAPTCHA or blocks the request.

This is Tier 3 discovery only — results must still pass website validation
and acceptance gates. No lead may be accepted based solely on web search.

Source hierarchy:
- Primary: Google search (better local business results)
- Fallback: DuckDuckGo HTML search (more reliably accessible)
- If both fail: log and continue pipeline with curated lists only
"""

import logging
import random
import re
from urllib.parse import quote_plus, unquote

from bs4 import BeautifulSoup

from app.models import LeadRecord, Company
from app.utils.text import normalize_domain

logger = logging.getLogger(__name__)

_DDG_URL = "https://html.duckduckgo.com/html/"
_GOOGLE_URL = "https://www.google.com/search"

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

# Domains to skip in search results
_SKIP_DOMAINS = {
    "wikipedia.org", "yelp.com", "facebook.com", "linkedin.com",
    "twitter.com", "instagram.com", "youtube.com", "bbb.org",
    "yellowpages.com", "mapquest.com", "indeed.com", "glassdoor.com",
    "google.com", "bing.com", "duckduckgo.com", "amazon.com",
    "reddit.com", "pinterest.com", "tiktok.com",
}


def is_available() -> bool:
    """Web search is always nominally available (no key needed)."""
    return True


def discover_for_category(
    category: str,
    location: str,
    search_terms: list[str],
    max_results: int = 15,
    delay_range: tuple[float, float] = (3.0, 6.0),
) -> list[LeadRecord]:
    """
    Discover candidate businesses for a category + location.

    Tries Google search first, falls back to DuckDuckGo if blocked.
    """
    all_leads: list[LeadRecord] = []
    seen_domains: set[str] = set()

    for term in search_terms[:3]:
        query = f"{term} {location}"
        results = _search_with_fallback(query, max_results=max_results, delay_range=delay_range)

        for lead in results:
            domain = normalize_domain(lead.company.website)
            if domain and domain not in seen_domains:
                seen_domains.add(domain)
                lead.category = category
                all_leads.append(lead)

        if len(all_leads) >= max_results:
            break

    return all_leads[:max_results]


def _search_with_fallback(
    query: str,
    max_results: int = 15,
    delay_range: tuple[float, float] = (2.0, 4.0),
) -> list[LeadRecord]:
    """Try Google search first, fall back to DuckDuckGo."""
    # Try Google first
    results = _google_search(query, max_results, delay_range)
    if results:
        return results

    # Fall back to DuckDuckGo
    logger.info("[WebSearch] Google unavailable, falling back to DuckDuckGo")
    results = _ddg_search(query, max_results, delay_range)
    if results:
        return results

    logger.warning(f"[WebSearch] Both Google and DDG failed for: {query[:60]}")
    return []


def _google_search(
    query: str,
    max_results: int = 15,
    delay_range: tuple[float, float] = (2.0, 4.0),
) -> list[LeadRecord]:
    """Search Google via direct HTTP. Returns empty list on CAPTCHA/block."""
    try:
        import requests
        from app.utils.http import rate_limit

        ua = random.choice(_USER_AGENTS)
        resp = requests.get(
            _GOOGLE_URL,
            params={"q": query, "num": str(min(max_results + 5, 20))},
            headers={
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=10,
        )
        rate_limit(*delay_range)

        if resp.status_code != 200:
            logger.warning(f"[WebSearch] Google returned {resp.status_code}")
            return []

        # Detect CAPTCHA
        if "captcha" in resp.text.lower() or "unusual traffic" in resp.text.lower():
            logger.warning("[WebSearch] Google CAPTCHA detected")
            return []

        return _parse_google_results(resp.text, max_results)

    except Exception as e:
        logger.warning(f"[WebSearch] Google search failed: {e}")
        return []


def _ddg_search(
    query: str,
    max_results: int = 15,
    delay_range: tuple[float, float] = (2.0, 4.0),
) -> list[LeadRecord]:
    """Search DuckDuckGo via HTML form. Fallback when Google is blocked."""
    try:
        import requests
        from app.utils.http import rate_limit

        ua = random.choice(_USER_AGENTS)
        resp = requests.post(
            _DDG_URL,
            data={"q": query, "b": ""},
            headers={"User-Agent": ua, "Accept": "text/html"},
            timeout=10,
        )
        rate_limit(*delay_range)

        if resp.status_code != 200:
            logger.warning(f"[WebSearch] DuckDuckGo returned {resp.status_code}")
            return []

        return _parse_ddg_results(resp.text, max_results)

    except Exception as e:
        logger.warning(f"[WebSearch] DuckDuckGo search failed: {e}")
        return []


def _parse_google_results(html: str, max_results: int) -> list[LeadRecord]:
    """Parse Google search results HTML into LeadRecord stubs."""
    leads = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        for result in soup.select("div.g"):
            try:
                link_el = result.select_one("a[href]")
                if not link_el:
                    continue
                url = link_el.get("href", "")
                if not url.startswith("http"):
                    continue

                lead = _result_to_lead(
                    url=url,
                    title=link_el.get_text(strip=True),
                    snippet_el=result.select_one("div[data-sncf], div.VwiC3b, span.st"),
                )
                if lead:
                    leads.append(lead)
                if len(leads) >= max_results:
                    break
            except Exception:
                continue
    except Exception as e:
        logger.warning(f"[WebSearch] Failed to parse Google results: {e}")
    return leads


def _parse_ddg_results(html: str, max_results: int) -> list[LeadRecord]:
    """Parse DuckDuckGo HTML search results into LeadRecord stubs."""
    leads = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        for result in soup.select("div.result, div.web-result"):
            try:
                link_el = result.select_one("a.result__a, a.result__url, a[href]")
                if not link_el:
                    continue
                url = link_el.get("href", "")
                if "uddg=" in url:
                    url = unquote(url.split("uddg=")[1].split("&")[0])
                if not url.startswith("http"):
                    continue

                lead = _result_to_lead(
                    url=url,
                    title=link_el.get_text(strip=True),
                    snippet_el=result.select_one("a.result__snippet, div.result__snippet"),
                )
                if lead:
                    leads.append(lead)
                if len(leads) >= max_results:
                    break
            except Exception:
                continue
    except Exception as e:
        logger.warning(f"[WebSearch] Failed to parse DDG results: {e}")
    return leads


def _result_to_lead(url: str, title: str, snippet_el) -> LeadRecord | None:
    """Convert a single search result into a LeadRecord stub, or None."""
    domain = normalize_domain(url)
    if not domain:
        return None
    if any(sd in domain for sd in _SKIP_DOMAINS):
        return None

    snippet = snippet_el.get_text(strip=True) if snippet_el else ""
    name = _extract_company_name(title, domain)
    if not name or len(name) < 3:
        return None

    lead = LeadRecord(
        company=Company(
            name=name,
            website=url,
            website_domain=domain,
            description=snippet[:300],
        ),
    )
    lead.add_evidence(
        claim=f"Discovered via web search: {title[:100]}",
        source_type="web_search",
        source_url=url,
        snippet=snippet[:200],
        confidence=0.3,
        source_tier=3,
        extraction_method="search_result",
    )
    return lead


def _extract_company_name(title: str, domain: str) -> str:
    """Extract a reasonable company name from a search result title."""
    name = re.sub(r"\s*[-|–]\s*(Home|About|Welcome|Official).*$", "", title, flags=re.IGNORECASE)
    name = re.sub(r"\s*[-|–]\s*$", "", name).strip()
    if not name:
        name = domain.split(".")[0].replace("-", " ").title()
    return name[:100]
