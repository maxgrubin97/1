"""
Deduplication engine.

Operates at both firm and contact level:
1. One canonical firm record per real business.
2. Multiple ranked contacts may belong to a single firm.
3. Preserves all evidence from merged records.
4. Uses domain, phone, normalized name, address, and fuzzy similarity.
5. When merging, keeps the highest-confidence version of each field.
"""

import logging

from app.models import LeadRecord
from app.utils.text import normalize_company_name, normalize_domain, normalize_phone, fuzzy_name_match

logger = logging.getLogger(__name__)


def deduplicate(leads: list[LeadRecord]) -> list[LeadRecord]:
    """
    Deduplicate a list of leads, merging evidence and contacts from duplicates.

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
            _merge_leads(existing, lead)
            merged_count += 1
            logger.debug(f"  [Dedupe] Merged: {lead.company.name} -> {existing.company.name}")
        else:
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
    """
    Merge data from source into target.

    Keeps the highest-confidence version of each field.
    Preserves all contacts from both records (firm+contact level dedupe).
    Merges all evidence chains.
    """
    # --- Merge evidence (preserve all) ---
    existing_claims = {(e.claim, e.source_url) for e in target.evidence}
    for e in source.evidence:
        if (e.claim, e.source_url) not in existing_claims:
            target.evidence.append(e)

    # Merge source URLs
    for url in source.source_urls:
        if url not in target.source_urls:
            target.source_urls.append(url)

    # --- Contact-level deduplication ---
    # Preserve all unique contacts from both records
    existing_contacts = {}
    for c in target.contacts:
        key = c.name.lower().strip() if c.name else c.id
        existing_contacts[key] = c

    for c in source.contacts:
        key = c.name.lower().strip() if c.name else c.id
        if key in existing_contacts:
            # Same person — keep higher confidence version
            existing = existing_contacts[key]
            if c.contact_source_confidence > existing.contact_source_confidence:
                # Replace with higher confidence version
                idx = target.contacts.index(existing)
                target.contacts[idx] = c
                existing_contacts[key] = c
            else:
                # Keep existing but merge missing fields
                if not existing.email and c.email:
                    existing.email = c.email
                    existing.email_status = c.email_status
                if not existing.phone and c.phone:
                    existing.phone = c.phone
                if not existing.linkedin_url and c.linkedin_url:
                    existing.linkedin_url = c.linkedin_url
        else:
            # New person — add to contact list
            target.contacts.append(c)
            existing_contacts[key] = c

    # --- Primary contact: pick best across both records ---
    all_named_contacts = [c for c in target.contacts if c.name]
    if all_named_contacts:
        # Sort by: contact_source_confidence desc, then priority asc
        best = sorted(
            all_named_contacts,
            key=lambda c: (-c.contact_source_confidence, c.contact_priority),
        )[0]
        target.primary_contact = best

    # If source had a named primary contact and target didn't
    if source.primary_contact and source.primary_contact.name:
        if not target.primary_contact or not target.primary_contact.name:
            target.primary_contact = source.primary_contact

    # --- Company fields: keep highest-confidence version ---
    _merge_company_fields(target, source)

    # --- Merge tags ---
    for tag in source.tags:
        if tag not in target.tags:
            target.tags.append(tag)

    # --- Take higher score ---
    if source.qualification_score > target.qualification_score:
        target.qualification_score = source.qualification_score
        target.score = source.score
        target.confidence_score = source.confidence_score

    # --- Merge source hierarchy fields ---
    target.source_tier_best = min(target.source_tier_best, source.source_tier_best)
    target.source_count = max(target.source_count, source.source_count)
    if source.has_corroboration:
        target.has_corroboration = True
    if source.website_validated:
        target.website_validated = True
    if source.acceptance_gate_passed and not target.acceptance_gate_passed:
        target.acceptance_gate_passed = True
        target.acceptance_gate_explanation = source.acceptance_gate_explanation

    # Recalculate source summary from merged evidence
    target._update_source_summary()

    # --- Merge review evidence ---
    for item in source.review_evidence_for:
        if item not in target.review_evidence_for:
            target.review_evidence_for.append(item)
    for item in source.review_evidence_against:
        if item not in target.review_evidence_against:
            target.review_evidence_against.append(item)
    if source.review_suggested_next_step and not target.review_suggested_next_step:
        target.review_suggested_next_step = source.review_suggested_next_step


def _merge_company_fields(target: LeadRecord, source: LeadRecord):
    """Merge company fields, preferring higher-confidence versions."""
    t = target.company
    s = source.company

    # Website — prefer populated
    if not t.website and s.website:
        t.website = s.website
        t.website_domain = s.website_domain

    # Phone — prefer populated
    if not t.phone and s.phone:
        t.phone = s.phone

    # Email — prefer populated
    if not t.email and s.email:
        t.email = s.email

    # Address fields — prefer populated
    if not t.address and s.address:
        t.address = s.address
    if not t.city and s.city:
        t.city = s.city
    if not t.state and s.state:
        t.state = s.state
    if not t.zip_code and s.zip_code:
        t.zip_code = s.zip_code

    # Google Maps data — prefer populated
    if not t.google_place_id and s.google_place_id:
        t.google_place_id = s.google_place_id
        t.google_maps_url = s.google_maps_url
        t.google_rating = s.google_rating
        t.google_review_count = s.google_review_count
        t.google_categories = s.google_categories

    # LinkedIn
    if not t.linkedin_company_url and s.linkedin_company_url:
        t.linkedin_company_url = s.linkedin_company_url

    # Industry / description
    if not t.primary_industry and s.primary_industry:
        t.primary_industry = s.primary_industry
    if not t.description and s.description:
        t.description = s.description
    if not t.employee_count_estimate and s.employee_count_estimate:
        t.employee_count_estimate = s.employee_count_estimate
    if not t.revenue_estimate and s.revenue_estimate:
        t.revenue_estimate = s.revenue_estimate
    if s.is_founder_led and not t.is_founder_led:
        t.is_founder_led = True

    # Merge field provenance
    for field, prov in s.field_provenance.items():
        if field not in t.field_provenance:
            t.field_provenance[field] = prov
        elif prov.get("confidence", 0) > t.field_provenance[field].get("confidence", 0):
            t.field_provenance[field] = prov
