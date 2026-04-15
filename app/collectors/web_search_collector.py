"""
Web search collector using DuckDuckGo HTML search.

No API key required. Uses DuckDuckGo's public HTML search to discover
candidate firms by category + geography. This is Tier 3 discovery only —
results must still pass website validation and acceptance gates.

If DuckDuckGo is unreliable or blocked, the collector fails gracefully
and the pipeline continues with curated lists only.
"""

import logging
import re
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from app.models import LeadRecord, Company
from app.utils.text import normalize_domain

logger = logging.getLogger(__name__)

_DDG_URL = "https://html.duckduckgo.com/html/"


def is_available() -> bool:
    """DuckDuckGo search is always nominally available (no key needed)."""
    return True


def search_businesses(
    query: str,
    max_results: int = 15,
    delay_range: tuple[float, float] = (2.0, 4.0),
) -> list[LeadRecord]:
    """
    Search DuckDuckGo for businesses matching a query.

    Returns LeadRecord stubs with company name + website for further enrichment.
    Fails gracefully on any error.
    """
    try:
        import requests
        from app.utils.http import rate_limit

        resp = requests.post(
            _DDG_URL,
            data={"q": query, "b": ""},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html",
            },
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


def discover_for_category(
    category: str,
    location: str,
    search_terms: list[str],
    max_results: int = 15,
    delay_range: tuple[float, float] = (3.0, 6.0),
) -> list[LeadRecord]:
    """
    Discover candidate businesses for a category + location.

    Builds search queries from category search terms and location,
    then parses results into LeadRecord stubs.
    """
    all_leads: list[LeadRecord] = []
    seen_domains: set[str] = set()

    for term in search_terms[:3]:  # Limit queries to avoid rate limits
        query = f"{term} {location}"
        results = search_businesses(query, max_results=max_results, delay_range=delay_range)

        for lead in results:
            domain = normalize_domain(lead.company.website)
            if domain and domain not in seen_domains:
                seen_domains.add(domain)
                lead.category = category
                all_leads.append(lead)

        if len(all_leads) >= max_results:
            break

    return all_leads[:max_results]


def _parse_ddg_results(html: str, max_results: int) -> list[LeadRecord]:
    """Parse DuckDuckGo HTML search results into LeadRecord stubs."""
    leads = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        results = soup.select("div.result, div.web-result")

        for result in results[:max_results * 2]:
            try:
                link_el = result.select_one("a.result__a, a.result__url, a[href]")
                if not link_el:
                    continue

                url = link_el.get("href", "")
                # DDG sometimes wraps URLs in redirects
                if "uddg=" in url:
                    url = url.split("uddg=")[1].split("&")[0]
                    from urllib.parse import unquote
                    url = unquote(url)

                if not url or not url.startswith("http"):
                    continue

                domain = normalize_domain(url)
                if not domain:
                    continue

                # Skip common non-business domains
                skip_domains = {
                    "wikipedia.org", "yelp.com", "facebook.com", "linkedin.com",
                    "twitter.com", "instagram.com", "youtube.com", "bbb.org",
                    "yellowpages.com", "mapquest.com", "indeed.com",
                }
                if any(sd in domain for sd in skip_domains):
                    continue

                title = link_el.get_text(strip=True)
                # Extract snippet
                snippet_el = result.select_one("a.result__snippet, div.result__snippet")
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""

                # Clean up company name from title
                name = _extract_company_name(title, domain)
                if not name or len(name) < 3:
                    continue

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
                leads.append(lead)

                if len(leads) >= max_results:
                    break

            except Exception:
                continue

    except Exception as e:
        logger.warning(f"[WebSearch] Failed to parse DDG results: {e}")

    return leads


def _extract_company_name(title: str, domain: str) -> str:
    """Extract a reasonable company name from a search result title."""
    # Remove common suffixes
    name = re.sub(r"\s*[-|–]\s*(Home|About|Welcome|Official).*$", "", title, flags=re.IGNORECASE)
    name = re.sub(r"\s*[-|–]\s*$", "", name).strip()
    if not name:
        # Fall back to domain
        name = domain.split(".")[0].replace("-", " ").title()
    return name[:100]
