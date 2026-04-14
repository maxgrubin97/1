"""
Lead enrichment module.

Adds missing data points to leads:
- Company website discovery
- Email address guessing
- Company size / revenue estimation
- Decision-maker identification for leads missing it
- Deduplication across sources
"""

import logging
import random
import re
import time
from urllib.parse import quote_plus, urlparse

import requests
from bs4 import BeautifulSoup

from models import Lead, classify_role

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

# ---------------------------------------------------------------------------
# Website discovery
# ---------------------------------------------------------------------------


def _find_company_website(company_name: str, location: str) -> str:
    """Try to find a company's website via Google search."""
    query = f'"{company_name}" {location} official website'
    try:
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept-Language": "en-US,en;q=0.9",
        }
        resp = requests.get(
            f"https://www.google.com/search?q={quote_plus(query)}&num=5&hl=en",
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        skip_domains = {
            "linkedin.com", "facebook.com", "twitter.com", "instagram.com",
            "yelp.com", "google.com", "youtube.com", "bbb.org",
            "glassdoor.com", "indeed.com", "crunchbase.com", "bloomberg.com",
            "wikipedia.org", "maps.google.com",
        }

        for a_tag in soup.select("a[href]"):
            href = a_tag.get("href", "")
            if href.startswith("/url?q="):
                href = href.split("/url?q=")[1].split("&")[0]
            parsed = urlparse(href)
            domain = parsed.hostname or ""
            if domain and not any(skip in domain for skip in skip_domains):
                if parsed.scheme in ("http", "https"):
                    return f"{parsed.scheme}://{domain}"
    except Exception as e:
        logger.debug(f"Website lookup failed for {company_name}: {e}")

    return ""


# ---------------------------------------------------------------------------
# Email guessing
# ---------------------------------------------------------------------------

COMMON_EMAIL_PATTERNS = [
    "{first}@{domain}",
    "{first}.{last}@{domain}",
    "{first}{last_initial}@{domain}",
    "{first_initial}{last}@{domain}",
]


def _guess_emails(name: str, website: str) -> str:
    """
    Generate likely email addresses based on name + company domain.
    Returns the most common patterns separated by ' | '.
    """
    if not name or not website:
        return ""

    parts = name.strip().split()
    if len(parts) < 2:
        return ""

    first = parts[0].lower()
    last = parts[-1].lower()

    # Clean special characters from names
    first = re.sub(r"[^a-z]", "", first)
    last = re.sub(r"[^a-z]", "", last)
    if not first or not last:
        return ""

    domain = urlparse(website).hostname or website
    domain = domain.replace("www.", "")

    guesses = []
    for pattern in COMMON_EMAIL_PATTERNS:
        email = pattern.format(
            first=first,
            last=last,
            first_initial=first[0],
            last_initial=last[0],
            domain=domain,
        )
        guesses.append(email)

    return " | ".join(guesses)


# ---------------------------------------------------------------------------
# Company size estimation
# ---------------------------------------------------------------------------

REVIEW_COUNT_TO_SIZE = [
    (500, "50-200 employees (est.)"),
    (200, "20-50 employees (est.)"),
    (50, "10-20 employees (est.)"),
    (10, "5-10 employees (est.)"),
    (0, "1-5 employees (est.)"),
]

REVIEW_COUNT_TO_REVENUE = [
    (500, "$5M-$15M (est.)"),
    (200, "$3M-$10M (est.)"),
    (50, "$1M-$5M (est.)"),
    (10, "$500K-$2M (est.)"),
    (0, "< $1M (est.)"),
]


def _estimate_company_size(lead: Lead) -> str:
    """Estimate company size from available signals."""
    if lead.company_size:
        return lead.company_size

    try:
        reviews = int(lead.gmaps_review_count) if lead.gmaps_review_count else 0
    except ValueError:
        reviews = 0

    for threshold, size in REVIEW_COUNT_TO_SIZE:
        if reviews >= threshold:
            return size
    return ""


def _estimate_revenue(lead: Lead) -> str:
    """Estimate revenue range from available signals."""
    if lead.revenue_estimate:
        return lead.revenue_estimate

    try:
        reviews = int(lead.gmaps_review_count) if lead.gmaps_review_count else 0
    except ValueError:
        reviews = 0

    for threshold, rev in REVIEW_COUNT_TO_REVENUE:
        if reviews >= threshold:
            return rev
    return ""


# ---------------------------------------------------------------------------
# Decision-maker retry for leads missing it
# ---------------------------------------------------------------------------


def _retry_decision_maker(
    lead: Lead,
    serpapi_key: str = "",
    delay_range: tuple[float, float] = (2.0, 4.0),
) -> None:
    """Attempt to find a decision maker for a lead that's missing one."""
    if lead.name and lead.title:
        return  # Already has DM info

    if not lead.company:
        return

    dm_titles = '"CEO" OR "founder" OR "owner" OR "president" OR "managing partner" OR "principal"'
    query = f'site:linkedin.com/in/ "{lead.company}" {dm_titles}'
    if lead.location:
        query += f' "{lead.location}"'

    try:
        if serpapi_key:
            resp = requests.get(
                "https://serpapi.com/search",
                params={"q": query, "num": 5, "api_key": serpapi_key, "engine": "google"},
                timeout=15,
            )
            resp.raise_for_status()
            organic = resp.json().get("organic_results", [])
            for r in organic:
                link = r.get("link", "")
                if "linkedin.com/in/" not in link:
                    continue
                title_text = r.get("title", "")
                title_text = re.sub(r"\s*[|–-]\s*LinkedIn\s*$", "", title_text).strip()
                parts = re.split(r"\s*[–-]\s*", title_text, maxsplit=2)
                lead.name = parts[0].strip() if parts else ""
                lead.title = parts[1].strip() if len(parts) > 1 else ""
                lead.linkedin_url = link
                lead.role_type = classify_role(lead.title)
                break
        else:
            headers = {
                "User-Agent": random.choice(USER_AGENTS),
                "Accept-Language": "en-US,en;q=0.9",
            }
            url = f"https://www.google.com/search?q={quote_plus(query)}&num=5&hl=en"
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            for el in soup.select("div.g"):
                link_el = el.select_one("a[href]")
                if not link_el:
                    continue
                href = link_el.get("href", "")
                if "linkedin.com/in/" not in href:
                    continue
                title_el = el.select_one("h3")
                if not title_el:
                    continue
                title_text = re.sub(
                    r"\s*[|–-]\s*LinkedIn\s*$", "", title_el.get_text(strip=True)
                ).strip()
                parts = re.split(r"\s*[–-]\s*", title_text, maxsplit=2)
                lead.name = parts[0].strip() if parts else ""
                lead.title = parts[1].strip() if len(parts) > 1 else ""
                lead.linkedin_url = href.split("&sa=")[0].split("&ved=")[0]
                lead.role_type = classify_role(lead.title)
                break
    except Exception as e:
        logger.debug(f"DM retry failed for {lead.company}: {e}")

    time.sleep(random.uniform(*delay_range))


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def _deduplicate(leads: list[Lead]) -> list[Lead]:
    """
    Remove duplicate leads, preferring the version with more data.
    Deduplicates by LinkedIn URL and by company name.
    """
    by_linkedin: dict[str, Lead] = {}
    by_company: dict[str, Lead] = {}
    unique: list[Lead] = []

    for lead in leads:
        linkedin_key = lead.linkedin_url.rstrip("/").lower() if lead.linkedin_url else ""
        company_key = lead.company.strip().lower() if lead.company else ""

        if linkedin_key and linkedin_key in by_linkedin:
            by_linkedin[linkedin_key].merge_from(lead)
            continue

        if company_key and company_key in by_company:
            by_company[company_key].merge_from(lead)
            if linkedin_key:
                by_linkedin[linkedin_key] = by_company[company_key]
            continue

        # New lead
        if linkedin_key:
            by_linkedin[linkedin_key] = lead
        if company_key:
            by_company[company_key] = lead
        unique.append(lead)

    return unique


# ---------------------------------------------------------------------------
# Main enrichment pipeline
# ---------------------------------------------------------------------------


def enrich_leads(
    leads: list[Lead],
    find_websites: bool = True,
    guess_emails: bool = True,
    estimate_size: bool = True,
    retry_decision_makers: bool = True,
    serpapi_key: str = "",
    delay_range: tuple[float, float] = (2.0, 4.0),
) -> list[Lead]:
    """
    Run the full enrichment pipeline on a list of leads.

    Steps:
      1. Deduplicate across sources
      2. Retry decision-maker lookup for leads missing one
      3. Find company websites
      4. Guess email addresses
      5. Estimate company size and revenue

    Returns:
        Enriched, deduplicated list of leads.
    """
    logger.info(f"Starting enrichment on {len(leads)} leads...")

    # Step 1: Deduplicate
    leads = _deduplicate(leads)
    logger.info(f"After dedup: {len(leads)} unique leads")

    for i, lead in enumerate(leads):
        logger.info(f"Enriching [{i + 1}/{len(leads)}]: {lead.company or lead.name}")

        # Step 2: Retry DM if missing
        if retry_decision_makers and not lead.name:
            _retry_decision_maker(lead, serpapi_key, delay_range)
            if lead.name:
                logger.info(f"  Found DM: {lead.name} ({lead.title})")

        # Step 3: Find website
        if find_websites and not lead.website and lead.company:
            lead.website = _find_company_website(lead.company, lead.location)
            if lead.website:
                logger.info(f"  Found website: {lead.website}")
            time.sleep(random.uniform(1.0, 2.0))

        # Step 4: Guess email
        if guess_emails:
            lead.email_guess = _guess_emails(lead.name, lead.website)

        # Step 5: Estimate size / revenue
        if estimate_size:
            lead.company_size = _estimate_company_size(lead)
            lead.revenue_estimate = _estimate_revenue(lead)

        # Ensure role_type is set
        if lead.title and not lead.role_type:
            lead.role_type = classify_role(lead.title)

    # Final filter: only keep leads with decision-maker info
    enriched = [lead for lead in leads if lead.name]
    skipped = len(leads) - len(enriched)
    if skipped:
        logger.warning(
            f"Dropped {skipped} leads with no decision-maker found. "
            f"Returning {len(enriched)} leads with DM info."
        )

    logger.info(f"Enrichment complete: {len(enriched)} leads with decision-maker data")
    return enriched
