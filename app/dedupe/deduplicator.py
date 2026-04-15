"""
Deduplication engine.

Deduplicates by:
- normalized website domain
- normalized business name
- phone
- address
- LinkedIn URL

Merges evidence from duplicates into a single canonical record.
Preserves all source URLs.
"""

import logging

from app.models import LeadRecord
from app.utils.text import normalize_company_name, normalize_domain, normalize_phone, fuzzy_name_match

logger = logging.getLogger(__name__)


def deduplicate(leads: list[LeadRecord]) -> list[LeadRecord]:
    """
    Deduplicate a list of leads, merging evidence from duplicates.

    Priority: keeps the version with the higher score / more data.
    Returns the deduplicated list.
    """
    # Index by various keys
    by_domain: dict[str, LeadRecord] = {}
    by_name: dict[str, LeadRecord] = {}
    by_phone: dict[str, LeadRecord] = {}
    by_linkedin: dict[str, LeadRecord] = {}

    unique: list[LeadRecord] = []
    merged_count = 0

    for lead in leads:
        domain = normalize_domain(lead.company.website)
        name = normalize_company_name(lead.company.name)
        phone = normalize_phone(lead.company.phone) if lead.company.phone else ""
        li_url = lead.company.linkedin_company_url.rstrip("/").lower() if lead.company.linkedin_company_url else ""

        # Check for duplicates
        existing = None

        if domain and domain in by_domain:
            existing = by_domain[domain]
        elif name and name in by_name:
            existing = by_name[name]
        elif phone and len(phone) >= 10 and phone in by_phone:
            existing = by_phone[phone]
        elif li_url and li_url in by_linkedin:
            existing = by_linkedin[li_url]
        else:
            # Fuzzy name match as last resort
            for existing_name, existing_lead in by_name.items():
                if fuzzy_name_match(name, existing_name):
                    existing = existing_lead
                    break

        if existing:
            # Merge into the existing record
            _merge_leads(existing, lead)
            merged_count += 1
            logger.debug(f"  [Dedupe] Merged: {lead.company.name} -> {existing.company.name}")
        else:
            # New unique record
            if domain:
                by_domain[domain] = lead
            if name:
                by_name[name] = lead
            if phone:
                by_phone[phone] = lead
            if li_url:
                by_linkedin[li_url] = lead
            unique.append(lead)

    logger.info(f"[Dedupe] {len(leads)} input -> {len(unique)} unique ({merged_count} merged)")
    return unique


def _merge_leads(target: LeadRecord, source: LeadRecord):
    """Merge data from source into target, keeping the better data."""
    # Merge evidence
    existing_claims = {e.claim for e in target.evidence}
    for e in source.evidence:
        if e.claim not in existing_claims:
            target.evidence.append(e)

    # Merge source URLs
    for url in source.source_urls:
        if url not in target.source_urls:
            target.source_urls.append(url)

    # Merge contacts
    existing_names = {c.name.lower() for c in target.contacts if c.name}
    for c in source.contacts:
        if c.name and c.name.lower() not in existing_names:
            target.contacts.append(c)

    # Take primary contact from whichever has better priority
    if source.primary_contact and source.primary_contact.name:
        if not target.primary_contact or not target.primary_contact.name:
            target.primary_contact = source.primary_contact
        elif source.primary_contact.contact_priority < target.primary_contact.contact_priority:
            target.primary_contact = source.primary_contact

    # Fill in missing company fields
    c = target.company
    s = source.company
    if not c.website and s.website:
        c.website = s.website
        c.website_domain = s.website_domain
    if not c.phone and s.phone:
        c.phone = s.phone
    if not c.email and s.email:
        c.email = s.email
    if not c.address and s.address:
        c.address = s.address
    if not c.city and s.city:
        c.city = s.city
    if not c.state and s.state:
        c.state = s.state
    if not c.google_place_id and s.google_place_id:
        c.google_place_id = s.google_place_id
        c.google_maps_url = s.google_maps_url
        c.google_rating = s.google_rating
        c.google_review_count = s.google_review_count
    if not c.linkedin_company_url and s.linkedin_company_url:
        c.linkedin_company_url = s.linkedin_company_url
    if not c.primary_industry and s.primary_industry:
        c.primary_industry = s.primary_industry
    if not c.description and s.description:
        c.description = s.description
    if not c.employee_count_estimate and s.employee_count_estimate:
        c.employee_count_estimate = s.employee_count_estimate

    # Merge tags
    for tag in source.tags:
        if tag not in target.tags:
            target.tags.append(tag)

    # Take higher score
    if source.qualification_score > target.qualification_score:
        target.qualification_score = source.qualification_score
        target.score = source.score
        target.confidence_score = source.confidence_score
