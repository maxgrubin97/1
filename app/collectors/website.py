"""
Website collector.

Fetches company websites for classification, contact extraction, and evidence.
Respects robots.txt. Only fetches key pages (home, about, team, services).
"""

import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.utils.http import fetch_url, rate_limit

logger = logging.getLogger(__name__)

# Pages most likely to contain useful information
KEY_PAGES = [
    "/",
    "/about",
    "/about-us",
    "/about-us/",
    "/team",
    "/our-team",
    "/people",
    "/attorneys",
    "/professionals",
    "/staff",
    "/services",
    "/practice-areas",
    "/what-we-do",
    "/contact",
    "/contact-us",
]


def _find_linked_pages(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Find internal links to about/team/services pages."""
    interesting_patterns = [
        r"about", r"team", r"people", r"staff", r"professionals",
        r"attorneys", r"partners", r"services", r"practice",
        r"what-we-do", r"our-work", r"leadership",
    ]
    found = set()
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        text = a.get_text(strip=True).lower()
        full_url = urljoin(base_url, href)
        if not full_url.startswith(base_url):
            continue
        for pattern in interesting_patterns:
            if re.search(pattern, href.lower()) or re.search(pattern, text):
                found.add(full_url)
                break
    return list(found)[:6]


def collect_website_data(
    url: str,
    delay_range: tuple[float, float] = (1.0, 2.0),
    max_pages: int = 4,
) -> dict:
    """
    Fetch key pages from a company website and extract text content.

    Returns:
        {
            "home_text": str,
            "about_text": str,
            "team_text": str,
            "services_text": str,
            "all_text": str,
            "page_titles": list[str],
            "meta_description": str,
            "emails_found": list[str],
            "phones_found": list[str],
            "pages_fetched": list[str],
            "team_page_html": str,
        }
    """
    result = {
        "home_text": "",
        "about_text": "",
        "team_text": "",
        "services_text": "",
        "all_text": "",
        "page_titles": [],
        "meta_description": "",
        "emails_found": [],
        "phones_found": [],
        "pages_fetched": [],
        "team_page_html": "",
    }

    if not url:
        return result

    if not url.startswith("http"):
        url = f"https://{url}"

    base_url = url.rstrip("/")

    # Fetch homepage
    resp = fetch_url(base_url)
    if not resp:
        return result

    soup = BeautifulSoup(resp.text, "lxml")
    body_text = soup.get_text(separator=" ", strip=True)
    result["home_text"] = body_text[:5000]
    result["all_text"] = body_text[:5000]

    # Meta description
    meta = soup.find("meta", attrs={"name": "description"})
    if meta:
        result["meta_description"] = meta.get("content", "")

    # Page title
    title_tag = soup.find("title")
    if title_tag:
        result["page_titles"].append(title_tag.get_text(strip=True))

    result["pages_fetched"].append(base_url)

    # Extract emails and phones from homepage
    result["emails_found"] = _extract_emails(body_text)
    result["phones_found"] = _extract_phones(body_text)

    # Find linked internal pages
    linked_pages = _find_linked_pages(soup, base_url)

    # Also try common paths
    for path in KEY_PAGES[1:]:
        candidate = f"{base_url}{path}"
        if candidate not in linked_pages:
            linked_pages.append(candidate)

    pages_fetched = 1
    for page_url in linked_pages:
        if pages_fetched >= max_pages:
            break

        rate_limit(*delay_range)
        resp = fetch_url(page_url)
        if not resp:
            continue

        page_soup = BeautifulSoup(resp.text, "lxml")
        page_text = page_soup.get_text(separator=" ", strip=True)[:5000]
        result["pages_fetched"].append(page_url)
        result["all_text"] += " " + page_text
        pages_fetched += 1

        path_lower = page_url.lower()
        if any(kw in path_lower for kw in ["about", "who-we-are"]):
            result["about_text"] = page_text
        elif any(kw in path_lower for kw in ["team", "people", "staff", "attorneys", "professionals", "leadership"]):
            result["team_text"] = page_text
            result["team_page_html"] = resp.text[:20000]
        elif any(kw in path_lower for kw in ["service", "practice", "what-we-do"]):
            result["services_text"] = page_text

        # Collect more emails/phones
        result["emails_found"].extend(_extract_emails(page_text))
        result["phones_found"].extend(_extract_phones(page_text))

    # Dedupe
    result["emails_found"] = list(set(result["emails_found"]))
    result["phones_found"] = list(set(result["phones_found"]))

    logger.info(f"  [Website] Fetched {pages_fetched} pages from {base_url}")
    return result


def _extract_emails(text: str) -> list[str]:
    """Extract email addresses from text."""
    pattern = r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
    emails = re.findall(pattern, text)
    # Filter out common noise
    noise = {"example.com", "domain.com", "email.com", "yoursite.com", "sentry.io"}
    return [e.lower() for e in emails if not any(n in e.lower() for n in noise)]


def _extract_phones(text: str) -> list[str]:
    """Extract US phone numbers from text."""
    pattern = r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"
    return re.findall(pattern, text)[:5]
