"""
LinkedIn public profile collector.

Discovers LinkedIn profiles through SerpAPI (paid, compliant) ONLY.
Does NOT log into LinkedIn, bypass authentication, or scrape private data.
Does NOT fall back to direct Google HTML scraping (brittle, non-compliant).

Compliance:
- Uses SerpAPI with site:linkedin.com/in/ queries
- Only captures data visible in search result snippets
- Respects rate limits with configurable delays
- Requires SERPAPI_KEY to be configured; disabled otherwise
"""

import logging
import re

from app.models.contact import Contact
from app.utils.http import serpapi_search, rate_limit
from app.utils.text import classify_title_seniority

logger = logging.getLogger(__name__)


def _parse_linkedin_title(title: str) -> dict:
    """Parse 'John Doe - CEO - Acme Corp | LinkedIn' format."""
    title = re.sub(r"\s*[|–-]\s*LinkedIn\s*$", "", title, flags=re.IGNORECASE).strip()
    parts = re.split(r"\s*–\s*|\s+-\s+", title, maxsplit=2)
    return {
        "name": parts[0].strip() if len(parts) >= 1 else "",
        "title": parts[1].strip() if len(parts) >= 2 else "",
        "company": parts[2].strip() if len(parts) >= 3 else "",
    }


def _parse_serpapi_results(results: list[dict]) -> list[Contact]:
    """Parse SerpAPI organic results."""
    contacts = []
    for r in results:
        link = r.get("link", "")
        if "linkedin.com/in/" not in link:
            continue

        title_text = r.get("title", "")
        parsed = _parse_linkedin_title(title_text)

        if not parsed["name"] or len(parsed["name"]) < 2:
            continue

        seniority, role_cat, priority = classify_title_seniority(parsed["title"])
        snippet = r.get("snippet", "")

        contact = Contact(
            name=parsed["name"],
            title=parsed["title"],
            linkedin_url=link,
            seniority_level=seniority,
            role_category=role_cat,
            contact_priority=priority,
            is_decision_maker=(priority <= 3),
            source="linkedin_public",
            person_description=parsed.get("company", ""),
            # Phase 1 trust fields
            email_status="unavailable",
            contact_source="linkedin_public",
            contact_source_confidence=0.4,
            extraction_method="search_snippet",
            source_snippet=snippet[:200] if snippet else "",
        )
        contacts.append(contact)

    return contacts


def is_available(serpapi_key: str = "") -> bool:
    """Check if LinkedIn discovery is available (requires SerpAPI key)."""
    return bool(serpapi_key)


def discover_contacts(
    query: str,
    serpapi_key: str = "",
    max_results: int = 10,
    delay_range: tuple[float, float] = (3.0, 6.0),
) -> list[Contact]:
    """
    Discover LinkedIn contacts via SerpAPI.

    Requires a valid SerpAPI key. Returns empty list if not configured.
    Direct Google HTML scraping has been removed (brittle, non-compliant).
    """
    if not serpapi_key:
        logger.debug("[LinkedIn] Skipped: no SERPAPI_KEY configured")
        return []

    results = serpapi_search(query, serpapi_key, num=max_results)
    contacts = _parse_serpapi_results(results) if results else []
    rate_limit(*delay_range)
    return contacts


def find_decision_maker_for_company(
    company_name: str,
    location: str,
    category_titles: list[str] | None = None,
    serpapi_key: str = "",
    delay_range: tuple[float, float] = (3.0, 6.0),
) -> Contact | None:
    """
    Search for the decision maker at a specific company via SerpAPI.

    Returns the highest-priority contact found, or None.
    Returns None immediately if SerpAPI key is not configured.
    """
    if not is_available(serpapi_key):
        logger.debug(f"[LinkedIn] Skipped for {company_name}: no SERPAPI_KEY")
        return None

    if not category_titles:
        category_titles = ["CEO", "founder", "owner", "president", "managing partner"]

    title_clause = " OR ".join(f'"{t}"' for t in category_titles[:5])
    query = f'site:linkedin.com/in/ "{company_name}" {title_clause} "{location}"'

    contacts = discover_contacts(query, serpapi_key, max_results=5, delay_range=delay_range)

    if not contacts:
        return None

    # Return the highest priority (lowest number) contact
    contacts.sort(key=lambda c: c.contact_priority)
    return contacts[0]
