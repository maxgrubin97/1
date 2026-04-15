"""
Lead enrichment module.

Only runs on leads that pass classification (accepted or review_needed).
Adds: website data, contacts, email patterns, company size estimates.

Staged approach:
1. Enrich ONLY high-quality leads (skip rejected)
2. Extract contacts ONLY for accepted/high-review records
3. LinkedIn is auxiliary only — runs only if website team page found no contacts
4. All contacts get email_status and contact_source fields populated
"""

import logging
import re
from urllib.parse import urlparse

from app.models import LeadRecord
from app.models.contact import Contact
from app.collectors.website import collect_website_data
from app.collectors.linkedin_public import find_decision_maker_for_company, is_available as linkedin_available
from app.parsers.contact_parser import extract_contacts_from_team_page, rank_contacts
from app.parsers.website_parser import parse_website_signals
from app.config.settings import Settings
from app.utils.text import normalize_domain

logger = logging.getLogger(__name__)

# Generic email prefixes
_GENERIC_PREFIXES = {"info", "contact", "admin", "support", "noreply", "hello",
                     "office", "team", "sales", "help", "inquiries", "general"}


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

        # Determine if website validates category fit
        has_category_fit = bool(
            website_signals.get("detected_services")
            or website_signals.get("complexity_signals_found")
            or website_signals.get("serves_business_owners")
            or website_signals.get("serves_smb")
        )

        if website_signals.get("has_website"):
            lead.add_evidence(
                claim="Website content analyzed" + (" — category fit confirmed" if has_category_fit else ""),
                source_url=lead.company.website,
                source_type="website",
                snippet=website_data.get("meta_description", "")[:200],
                confidence=0.8 if has_category_fit else 0.5,
                source_tier=1,
                extraction_method="website_crawl",
            )
            # Only set website_validated if we got actual category fit signals
            if has_category_fit:
                lead.website_validated = True

            # Track provenance for key fields from website
            _update_provenance_from_website(lead, website_signals, lead.company.website)

        # Update company info from website with email_status tracking
        if website_signals.get("emails") and not lead.company.email:
            for email in website_signals["emails"]:
                status = _classify_email_status(email)
                if status == "verified":
                    lead.company.email = email
                    break
            if not lead.company.email and website_signals["emails"]:
                lead.company.email = website_signals["emails"][0]

        if website_signals.get("phones") and not lead.company.phone:
            lead.company.phone = website_signals["phones"][0]

        # Extract contacts from team page
        website_contacts_found = False
        if find_contacts and website_data.get("team_page_html"):
            team_contacts = extract_contacts_from_team_page(
                website_data["team_page_html"],
                source_url=lead.company.website,
            )
            if team_contacts:
                website_contacts_found = True
                ranked = rank_contacts(team_contacts, lead.category)
                for c in ranked:
                    c.company_id = lead.company.id
                    lead.contacts.append(c)
                if not lead.primary_contact or not lead.primary_contact.name:
                    lead.set_primary_contact(ranked[0])
                    lead.add_evidence(
                        claim=f"Decision maker from team page: {ranked[0].name} ({ranked[0].title})",
                        source_url=ranked[0].source_page_url or lead.company.website,
                        source_type="website",
                        confidence=ranked[0].contact_source_confidence,
                        source_tier=1,
                        extraction_method=ranked[0].extraction_method,
                    )
                logger.info(f"  [Enrich] Found {len(ranked)} contacts from team page")

    # --- LinkedIn contact enrichment (auxiliary only) ---
    # Only runs if: (1) website team page found zero contacts, (2) SerpAPI is configured
    if (find_contacts
            and not lead.has_decision_maker
            and lead.company.name
            and linkedin_available(settings.serpapi_key)):
        logger.info(f"  [Enrich] Searching LinkedIn for DM at {lead.company.name}")

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
            # LinkedIn contacts must never override website-extracted contacts
            if not lead.primary_contact or not lead.primary_contact.name:
                lead.set_primary_contact(contact)
            else:
                lead.contacts.append(contact)
            lead.add_evidence(
                claim=f"Decision maker via LinkedIn: {contact.name} ({contact.title})",
                source_url=contact.linkedin_url,
                source_type="linkedin_public",
                confidence=0.4,
                source_tier=3,
                extraction_method="search_snippet",
            )
            logger.info(f"  [Enrich] Found DM via LinkedIn: {contact.name} ({contact.title})")

    # --- Set email_status on primary contact if it has a real email ---
    if lead.primary_contact and lead.primary_contact.email:
        if lead.primary_contact.email_status == "unavailable":
            lead.primary_contact.email_status = _classify_email_status(
                lead.primary_contact.email
            )

    # --- Propagate detected triggers from website signals ---
    if website_signals.get("detected_triggers"):
        lead.detected_triggers = website_signals["detected_triggers"]

    # --- Company size estimation ---
    if not lead.company.employee_count_estimate:
        lead.company.employee_count_estimate = _estimate_size(lead, website_signals)

    lead.pipeline_stage = "enriched"
    return lead, website_signals


def _classify_email_status(email: str) -> str:
    """Classify email as verified, generic, or unavailable."""
    if not email:
        return "unavailable"
    prefix = email.split("@")[0].lower() if "@" in email else ""
    if prefix in _GENERIC_PREFIXES:
        return "generic"
    return "verified"


def _update_provenance_from_website(lead: LeadRecord, signals: dict, website_url: str):
    """Track provenance for company fields sourced from website."""
    prov = lead.company.field_provenance

    if signals.get("description") and not prov.get("description"):
        prov["description"] = {
            "source_url": website_url,
            "source_type": "website",
            "confidence": 0.9,
            "snippet": str(signals["description"])[:200],
        }

    if signals.get("phones") and not prov.get("phone"):
        prov["phone"] = {
            "source_url": website_url,
            "source_type": "website",
            "confidence": 0.8,
        }

    if signals.get("detected_services") and not prov.get("primary_industry"):
        prov["primary_industry"] = {
            "source_url": website_url,
            "source_type": "website",
            "confidence": 0.8,
            "snippet": ", ".join(signals["detected_services"][:3]),
        }

    lead.company.field_provenance = prov


def _estimate_size(lead: LeadRecord, signals: dict = None) -> str:
    """
    Estimate company size from available signals.

    Prefers website-derived signals over Google review count.
    Review count is a weak supporting signal only.
    """
    # Prefer team page data if available
    team_size = len(lead.contacts) if lead.contacts else 0
    if team_size >= 10:
        return f"{team_size}+ employees (from team page)"
    if team_size >= 5:
        return f"{team_size}-{team_size * 2} employees (est. from team page)"

    # Website signals (location count, service lines)
    if signals:
        locations = signals.get("location_count", 0)
        if locations and locations > 3:
            return "20-50 employees (est. from multiple locations)"
        if locations and locations > 1:
            return "10-20 employees (est. from multiple locations)"

    # Google reviews as weak fallback only
    reviews = lead.company.google_review_count or 0
    if reviews > 500:
        return "50-200 employees (weak est. from reviews)"
    if reviews > 200:
        return "20-50 employees (weak est. from reviews)"
    if reviews > 50:
        return "10-20 employees (weak est. from reviews)"
    if reviews > 10:
        return "5-10 employees (weak est. from reviews)"
    if reviews > 0:
        return "1-5 employees (weak est. from reviews)"

    if team_size >= 2:
        return f"{team_size}+ employees (from team page)"

    return ""
