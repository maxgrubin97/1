"""
Lead enrichment module.

Only runs on leads that pass classification (accepted or review_needed).
Adds: website data, contacts, email patterns, company size estimates.

Staged approach:
1. Enrich ONLY high-quality leads (skip rejected)
2. Extract contacts ONLY for accepted/high-review records
"""

import logging
import re
from urllib.parse import urlparse

from app.models import LeadRecord
from app.models.contact import Contact
from app.collectors.website import collect_website_data
from app.collectors.linkedin_public import find_decision_maker_for_company
from app.parsers.contact_parser import extract_contacts_from_team_page, rank_contacts
from app.parsers.website_parser import parse_website_signals
from app.config.settings import Settings
from app.utils.text import normalize_domain

logger = logging.getLogger(__name__)


def enrich_lead(
    lead: LeadRecord,
    settings: Settings,
    fetch_website: bool = True,
    find_contacts: bool = True,
    delay_range: tuple[float, float] = (2.0, 4.0),
) -> tuple[LeadRecord, dict]:
    """
    Enrich a single lead with website data and contacts.

    Returns (lead, website_signals) tuple.
    website_signals is needed by the classifier and scorer.
    """
    website_signals = {}

    # Skip enrichment for rejected leads (staged approach)
    if lead.status == "rejected":
        return lead, website_signals

    # --- Website enrichment ---
    if fetch_website and lead.company.website:
        logger.info(f"  [Enrich] Fetching website: {lead.company.website}")
        website_data = collect_website_data(
            lead.company.website,
            delay_range=(1.0, 2.0),
            max_pages=4,
        )

        website_signals = parse_website_signals(
            website_data,
            competitor_keywords=settings.get_competitor_keywords(),
            buying_triggers=settings.get_buying_triggers(),
            owner_led_signals=settings.get_owner_led_signals(),
            complexity_signals=settings.get_complexity_signals(),
        )

        # Add website evidence
        if website_signals.get("has_website"):
            lead.add_evidence(
                claim="Website content analyzed",
                source_url=lead.company.website,
                source_type="website",
                snippet=website_data.get("meta_description", "")[:200],
                confidence=0.8,
            )

        # Update company info from website
        if website_signals.get("emails") and not lead.company.email:
            for email in website_signals["emails"]:
                if not any(g in email for g in ["info@", "admin@", "noreply@"]):
                    lead.company.email = email
                    break
            if not lead.company.email:
                lead.company.email = website_signals["emails"][0]

        if website_signals.get("phones") and not lead.company.phone:
            lead.company.phone = website_signals["phones"][0]

        # Extract contacts from team page
        if find_contacts and website_data.get("team_page_html"):
            team_contacts = extract_contacts_from_team_page(
                website_data["team_page_html"],
                source_url=lead.company.website,
            )
            if team_contacts:
                ranked = rank_contacts(team_contacts, lead.category)
                for c in ranked:
                    c.company_id = lead.company.id
                    lead.contacts.append(c)
                if not lead.primary_contact or not lead.primary_contact.name:
                    lead.set_primary_contact(ranked[0])
                    lead.add_evidence(
                        claim=f"Decision maker from team page: {ranked[0].name} ({ranked[0].title})",
                        source_url=lead.company.website,
                        source_type="website",
                        confidence=0.8,
                    )
                logger.info(f"  [Enrich] Found {len(ranked)} contacts from team page")

    # --- LinkedIn contact enrichment ---
    if find_contacts and not lead.has_decision_maker and lead.company.name:
        logger.info(f"  [Enrich] Searching for DM at {lead.company.name}")

        # Get category-specific priority titles
        try:
            cat_config = settings.get_category(lead.category)
            titles = cat_config.get("priority_titles", [])[:5]
        except KeyError:
            titles = ["founder", "owner", "CEO", "president", "managing partner"]

        contact = find_decision_maker_for_company(
            lead.company.name,
            lead.company.city or lead.company.state or "",
            category_titles=titles,
            serpapi_key=settings.serpapi_key,
            delay_range=delay_range,
        )
        if contact:
            contact.company_id = lead.company.id
            lead.set_primary_contact(contact)
            lead.add_evidence(
                claim=f"Decision maker via LinkedIn: {contact.name} ({contact.title})",
                source_url=contact.linkedin_url,
                source_type="linkedin_public",
                confidence=0.6,
            )
            logger.info(f"  [Enrich] Found DM: {contact.name} ({contact.title})")

    # --- Email pattern guessing ---
    if lead.has_decision_maker and lead.company.website and not lead.primary_contact.email:
        lead.primary_contact.email_guess = _guess_email(
            lead.primary_contact.name, lead.company.website
        )

    # --- Company size estimation ---
    if not lead.company.employee_count_estimate:
        lead.company.employee_count_estimate = _estimate_size(lead)

    lead.pipeline_stage = "enriched"
    return lead, website_signals


def _guess_email(name: str, website: str) -> str:
    """Generate likely email addresses based on name + domain."""
    if not name or not website:
        return ""

    parts = name.strip().split()
    if len(parts) < 2:
        return ""

    first = re.sub(r"[^a-z]", "", parts[0].lower())
    last = re.sub(r"[^a-z]", "", parts[-1].lower())
    if not first or not last:
        return ""

    domain = normalize_domain(website)
    if not domain:
        return ""

    patterns = [
        f"{first}@{domain}",
        f"{first}.{last}@{domain}",
        f"{first[0]}{last}@{domain}",
        f"{first}{last[0]}@{domain}",
    ]
    return " | ".join(patterns)


def _estimate_size(lead: LeadRecord) -> str:
    """Estimate company size from available signals."""
    reviews = lead.company.google_review_count or 0
    if reviews > 500:
        return "50-200 employees (est.)"
    if reviews > 200:
        return "20-50 employees (est.)"
    if reviews > 50:
        return "10-20 employees (est.)"
    if reviews > 10:
        return "5-10 employees (est.)"
    if reviews > 0:
        return "1-5 employees (est.)"
    return ""
