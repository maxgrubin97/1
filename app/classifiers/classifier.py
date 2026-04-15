"""
Unified classifier.

Applies category-specific classification logic, hard exclusion filters,
and noise control rules. Determines record_type, status, and exclusion reasons.

Noise control rules (strictly enforced):
- Never accept with only directory evidence unless authoritative
- Never accept referral partner without practice-area evidence
- Never accept prospect without complexity signals
- CPA offering CFO services → high competition risk
- Law firm not clearly business-focused → reject
- Wealth advisor focused on retirees → reject
- Unclear size/market → review_needed
"""

import logging
from typing import Optional

import yaml
from pathlib import Path

from app.models import LeadRecord
from app.config.settings import Settings
from app.utils.text import contains_any

logger = logging.getLogger(__name__)

# Load personas config once
_personas_path = Path(__file__).parent.parent / "config" / "personas.yaml"
_personas: dict = {}
if _personas_path.exists():
    with open(_personas_path) as f:
        _personas = yaml.safe_load(f) or {}


def classify_lead(
    lead: LeadRecord,
    website_signals: dict,
    settings: Settings,
) -> LeadRecord:
    """
    Classify a lead record: determine type, apply exclusion filters,
    and set initial status.

    This is the main classification entry point called during the pipeline.
    """
    category = lead.category
    noise_control = settings.get_noise_control()

    # Determine record type from category config
    try:
        cat_config = settings.get_category(category)
        lead.record_type = cat_config.get("record_type", lead.record_type)
    except KeyError:
        pass

    # Apply hard exclusion filters first
    exclusion = _check_hard_exclusions(lead, website_signals, settings)
    if exclusion:
        lead.status = "rejected"
        lead.exclusion_reason = exclusion
        lead.pipeline_stage = "classified"
        logger.info(f"  [Classify] REJECTED: {lead.company.name} — {exclusion}")
        return lead

    # Apply noise control rules
    noise_result = _apply_noise_control(lead, website_signals, noise_control)
    if noise_result == "reject":
        lead.status = "rejected"
        lead.pipeline_stage = "classified"
        return lead
    elif noise_result == "review":
        lead.status = "review_needed"

    # Apply category-specific classification
    _apply_category_classification(lead, website_signals, settings)

    # Set pipeline stage
    lead.pipeline_stage = "classified"

    return lead


def _check_hard_exclusions(
    lead: LeadRecord,
    signals: dict,
    settings: Settings,
) -> str:
    """Check hard exclusion filters. Returns exclusion reason or empty string."""
    name_lower = lead.company.name.lower()
    all_text_lower = ""
    if signals:
        all_text_lower = " ".join(str(v) for v in signals.values()).lower()

    # --- Too large ---
    too_large = settings.get_exclusion_keywords("too_large_signals")
    found = contains_any(name_lower + " " + all_text_lower, too_large)
    if found:
        lead.exclusion_reason = f"Too large: {', '.join(found[:3])}"
        return lead.exclusion_reason

    # --- Too small (only for direct prospects) ---
    if lead.record_type == "direct_prospect":
        too_small = settings.get_exclusion_keywords("too_small_signals")
        found = contains_any(all_text_lower, too_small)
        if found:
            lead.exclusion_reason = f"Too small: {', '.join(found[:3])}"
            return lead.exclusion_reason

    # --- Irrelevant industry ---
    irrelevant = settings.get_exclusion_keywords("irrelevant_industries")
    found = contains_any(name_lower + " " + all_text_lower, irrelevant)
    if found:
        lead.exclusion_reason = f"Irrelevant industry: {', '.join(found[:3])}"
        return lead.exclusion_reason

    # --- Category-specific exclusions ---
    persona = _get_persona(lead.category, lead.record_type)
    if persona:
        excl_keywords = persona.get("exclusion_keywords", [])
        disqualifying = persona.get("disqualifying_traits", [])

        found_excl = contains_any(all_text_lower, excl_keywords)
        found_disq = contains_any(all_text_lower, disqualifying)

        if found_excl:
            lead.exclusion_reason = f"Category exclusion: {', '.join(found_excl[:3])}"
            return lead.exclusion_reason
        if found_disq:
            lead.exclusion_reason = f"Disqualifying trait: {', '.join(found_disq[:3])}"
            return lead.exclusion_reason

    # --- Competitor check ---
    competitor_kw = settings.get_competitor_keywords()
    if lead.record_type == "referral_partner":
        found = contains_any(all_text_lower, competitor_kw)
        if len(found) >= 2:
            lead.exclusion_reason = f"Likely competitor: {', '.join(found[:3])}"
            lead.competing_service_risk_score = 100
            return lead.exclusion_reason

    # --- Irrelevant law practice ---
    if lead.category in ("boutique_corporate_attorneys",):
        irrelevant_law = settings.get_exclusion_keywords("irrelevant_law_practice")
        detected_services = signals.get("detected_services", []) if signals else []
        detected_lower = " ".join(detected_services).lower()
        all_check = all_text_lower + " " + detected_lower

        found = contains_any(all_check, irrelevant_law)
        # Only exclude if irrelevant practice AND no business practice evidence
        biz_law = ["corporate", "business law", "m&a", "transactional", "commercial", "entity"]
        has_biz = contains_any(all_check, biz_law)
        if found and not has_biz:
            lead.exclusion_reason = f"Irrelevant legal practice: {', '.join(found[:3])}"
            return lead.exclusion_reason

    return ""


def _apply_noise_control(
    lead: LeadRecord,
    signals: dict,
    noise_control: dict,
) -> str:
    """
    Apply noise control rules. Returns 'accept', 'review', or 'reject'.
    """
    evidence_types = lead.evidence_source_types

    # Rule: Never accept with only directory evidence
    if noise_control.get("require_non_directory_evidence"):
        auth_dirs = set(noise_control.get("authoritative_directories", []))
        if evidence_types == {"directory"}:
            has_auth = any(
                any(ad in e.source_url for ad in auth_dirs)
                for e in lead.evidence
            )
            if not has_auth:
                lead.add_evidence(
                    claim="Only directory evidence (non-authoritative)",
                    source_type="noise_control",
                    confidence=0.2,
                )
                lead.review_evidence_against.append("Only directory evidence found")
                lead.review_suggested_next_step = "Check company website for legitimacy"
                return "review"

    # Rule: Referral partners need practice-area evidence
    if lead.record_type == "referral_partner":
        if noise_control.get("require_practice_area_evidence_for_referral"):
            if not signals or not signals.get("detected_services"):
                if not lead.has_website_evidence:
                    lead.review_evidence_against.append("No practice-area evidence found")
                    lead.review_suggested_next_step = "Visit website to confirm practice area alignment"
                    return "review"

    # Rule: Direct prospects need more than geography + category
    if lead.record_type == "direct_prospect":
        if noise_control.get("require_additional_signal_for_prospect"):
            has_signal = bool(
                (signals and signals.get("complexity_signals_found"))
                or (signals and signals.get("buying_triggers_found"))
                or lead.company.google_review_count > 10
                or (signals and signals.get("employee_clues"))
            )
            if not has_signal:
                lead.review_evidence_against.append("No complexity or buying trigger signals")
                lead.review_suggested_next_step = "Check website for signs of operational complexity"
                return "review"

    # Rule: Unclear size → review
    if noise_control.get("unclear_size_to_review"):
        if signals and signals.get("is_large_likely") is None and signals.get("is_boutique_likely") is None:
            if not lead.company.employee_count_estimate and not lead.company.google_review_count:
                lead.review_evidence_against.append("Unable to determine firm size")
                lead.review_suggested_next_step = "Check website or LinkedIn for employee count"
                return "review"

    # Rule: Broad law firm → review (not reject)
    if noise_control.get("broad_law_firm_to_review"):
        if lead.category in ("boutique_corporate_attorneys",):
            if signals and not signals.get("detected_services"):
                lead.review_evidence_against.append("Law firm practice areas unclear")
                lead.review_suggested_next_step = "Check practice areas page"
                return "review"

    # Rule: CPA with CFO services → high competition risk
    if lead.category in ("boutique_cpa_firms",):
        comp_kw = noise_control.get("cpa_cfo_competition_keywords", [])
        if signals:
            all_text = " ".join(str(v) for v in signals.values()).lower()
            found = contains_any(all_text, comp_kw)
            if found:
                lead.competing_service_risk_score = 80
                lead.review_evidence_against.append(f"CPA offers competing services: {', '.join(found[:3])}")
                lead.review_suggested_next_step = "Verify if CFO services are a major offering or minor add-on"
                return "review"

    # Rule: Wealth advisor focused on retirees → reject
    if lead.category in ("wealth_managers",):
        retiree_kw = noise_control.get("wealth_retiree_reject_keywords", [])
        if signals:
            all_text = " ".join(str(v) for v in signals.values()).lower()
            found = contains_any(all_text, retiree_kw)
            if found and not contains_any(all_text, ["business owner", "entrepreneur"]):
                lead.exclusion_reason = f"Wealth advisor focused on retirees: {', '.join(found[:2])}"
                return "reject"

    return "accept"


def _apply_category_classification(
    lead: LeadRecord,
    signals: dict,
    settings: Settings,
):
    """Apply category-specific classification to enrich the lead."""
    if not signals:
        return

    # Set industry from signals
    if signals.get("detected_services") and not lead.company.primary_industry:
        lead.company.primary_industry = signals["detected_services"][0]

    # Owner-led assessment
    if signals.get("is_owner_led_likely"):
        lead.company.is_founder_led = True
        lead.add_evidence("Likely owner-led business", source_type="website", confidence=0.6)

    # Complexity flags for direct prospects
    if lead.record_type == "direct_prospect":
        lead.complexity_flags = signals.get("complexity_signals_found", [])
        lead.likely_buying_triggers = signals.get("buying_triggers_found", [])
        lead.growth_transition_evidence = signals.get("growth_signals", [])

        if signals.get("employee_clues"):
            lead.company.employee_count_estimate = signals["employee_clues"][0]

    # Referral partner classification
    if lead.record_type == "referral_partner":
        lead.serves_founder_led = (
            "yes" if signals.get("serves_business_owners") else
            "probably" if signals.get("serves_smb") else
            "unclear"
        )
        lead.serves_right_revenue_band = (
            "probably" if signals.get("serves_smb") and not signals.get("serves_enterprise") else
            "unclear"
        )

        # Competition risk
        if signals.get("competitor_signals"):
            lead.competing_service_risk_score = min(100, len(signals["competitor_signals"]) * 30)

        # Boutique fit
        if signals.get("is_boutique_likely") and not signals.get("is_large_likely"):
            lead.boutique_fit_score = 80
        elif signals.get("is_large_likely"):
            lead.boutique_fit_score = 20

    # Contact info from website
    if signals.get("emails") and not lead.company.email:
        # Prefer non-generic emails
        for email in signals["emails"]:
            if not any(g in email for g in ["info@", "admin@", "support@", "noreply@"]):
                lead.company.email = email
                break
        if not lead.company.email and signals["emails"]:
            lead.company.email = signals["emails"][0]

    if signals.get("phones") and not lead.company.phone:
        lead.company.phone = signals["phones"][0]


def _get_persona(category: str, record_type: str) -> dict:
    """Get the persona config for a category."""
    group = "referral_partners" if record_type == "referral_partner" else "direct_prospects"
    return _personas.get(group, {}).get(category, {})
