"""
LinkedIn public profile collector.

Discovers LinkedIn profiles through public Google search results ONLY.
Does NOT log into LinkedIn, bypass authentication, or scrape private data.

Compliance:
- Uses Google search with site:linkedin.com/in/ prefix
- Only captures data visible in Google search result snippets
- Respects rate limits with configurable delays
- Falls back to SerpAPI (paid, compliant) if configured
"""

import logging
import re

from bs4 import BeautifulSoup

from app.models.contact import Contact
from app.utils.http import google_search, serpapi_search, rate_limit
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


def _extract_linkedin_url(raw: str) -> str:
    """Clean up a LinkedIn URL from Google results."""
    if "linkedin.com/in/" not in raw:
        return raw
    # Strip Google tracking params
    clean = raw.split("&sa=")[0].split("&ved=")[0]
    # Handle /url?q= redirects
    if "/url?q=" in clean:
        clean = clean.split("/url?q=")[1].split("&")[0]
    return clean


def _parse_google_html(html: str) -> list[Contact]:
    """Parse Google search results HTML for LinkedIn profiles."""
    contacts = []
    soup = BeautifulSoup(html, "html.parser")

    for result in soup.select("div.g"):
        try:
            link_el = result.select_one("a[href]")
            if not link_el:
                continue
            url = link_el.get("href", "")
            if "linkedin.com/in/" not in url:
                continue

            linkedin_url = _extract_linkedin_url(url)

            title_el = result.select_one("h3")
            title_text = title_el.get_text(strip=True) if title_el else ""
            parsed = _parse_linkedin_title(title_text)

            if not parsed["name"] or len(parsed["name"]) < 2:
                continue

            seniority, role_cat, priority = classify_title_seniority(parsed["title"])

            contact = Contact(
                name=parsed["name"],
                title=parsed["title"],
                linkedin_url=linkedin_url,
                seniority_level=seniority,
                role_category=role_cat,
                contact_priority=priority,
                is_decision_maker=(priority <= 3),
                source="linkedin_public",
                person_description=parsed.get("company", ""),
            )
            contacts.append(contact)
            logger.debug(f"  [LinkedIn] {contact.name} | {contact.title}")

        except Exception as e:
            logger.debug(f"Parse error: {e}")
            continue

    return contacts


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
        )
        contacts.append(contact)

    return contacts


def discover_contacts(
    query: str,
    serpapi_key: str = "",
    max_results: int = 10,
    delay_range: tuple[float, float] = (3.0, 6.0),
) -> list[Contact]:
    """
    Discover LinkedIn contacts via public Google search.

    Args:
        query: Full search query (should include site:linkedin.com/in/).
        serpapi_key: Optional SerpAPI key for reliable results.
        max_results: Max results to request.
        delay_range: Rate limiting delay range.

    Returns:
        List of Contact objects found.
    """
    contacts = []

    # Try SerpAPI first (more reliable, paid)
    if serpapi_key:
        results = serpapi_search(query, serpapi_key, num=max_results)
        if results:
            contacts = _parse_serpapi_results(results)
            rate_limit(*delay_range)
            return contacts

    # Fallback to direct Google search
    resp = google_search(query, num=max_results)
    if resp:
        contacts = _parse_google_html(resp.text)

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
    Search for the decision maker at a specific company.

    Uses a targeted LinkedIn search via Google.
    Returns the highest-priority contact found, or None.
    """
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
