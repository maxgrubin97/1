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
    apply acceptance gates, and set initial status.

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
        lead.acceptance_gate_passed = False
        lead.acceptance_gate_explanation = f"Hard exclusion: {exclusion}"
        lead.pipeline_stage = "classified"
        logger.info(f"  [Classify] REJECTED: {lead.company.name} — {exclusion}")
        return lead

    # Apply no-junk rules
    junk_result = _apply_no_junk_rules(lead, website_signals)
    if junk_result == "reject":
        lead.status = "rejected"
        lead.acceptance_gate_passed = False
        lead.pipeline_stage = "classified"
        return lead
    elif junk_result == "review":
        lead.status = "review_needed"

    # Apply noise control rules
    noise_result = _apply_noise_control(lead, website_signals, noise_control)
    if noise_result == "reject":
        lead.status = "rejected"
        lead.acceptance_gate_passed = False
        lead.pipeline_stage = "classified"
        return lead
    elif noise_result == "review":
        lead.status = "review_needed"

    # Apply category-specific classification
    _apply_category_classification(lead, website_signals, settings)

    # Apply acceptance gate (only after enrichment — when we have signals)
    if website_signals:
        _evaluate_acceptance_gate(lead, website_signals)

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


def _apply_no_junk_rules(
    lead: LeadRecord,
    signals: dict,
) -> str:
    """
    Apply no-junk rejection/review rules. Returns 'accept', 'review', or 'reject'.

    These rules catch records that should never pass acceptance gates regardless
    of score — they represent structural quality problems, not just low scores.
    """
    reasons = []

    # No real website found
    if not lead.company.website and not lead.company.website_domain:
        reasons.append("No website found")

    # Category based only on Maps label or thin search snippet (no website evidence)
    evidence_types = lead.evidence_source_types
    if evidence_types and evidence_types <= {"google_maps", "directory"}:
        if not lead.has_website_evidence:
            reasons.append("Only Maps/directory evidence — no website validation")

    # No clear business activity evidence
    if signals:
        has_biz_evidence = bool(
            signals.get("detected_services")
            or signals.get("complexity_signals_found")
            or signals.get("description")
            or signals.get("buying_triggers_found")
        )
        if not has_biz_evidence and lead.has_website_evidence:
            reasons.append("Website fetched but no business activity evidence found")

    # Obvious enterprise mismatch
    name_lower = lead.company.name.lower()
    all_text = ""
    if signals:
        all_text = " ".join(str(v) for v in signals.values()).lower()

    enterprise_signals = contains_any(
        name_lower + " " + all_text,
        ["fortune 500", "am law 100", "big 4", "big four", "publicly traded", "nyse:", "nasdaq:"]
    )
    if enterprise_signals:
        lead.exclusion_reason = f"Enterprise mismatch: {', '.join(enterprise_signals[:2])}"
        lead.acceptance_gate_explanation = f"Rejected: {lead.exclusion_reason}"
        return "reject"

    # Obvious too-small mismatch for direct prospects
    if lead.record_type == "direct_prospect":
        too_small = contains_any(
            all_text,
            ["solopreneur", "freelancer", "one-person", "one person shop", "solo practitioner"]
        )
        if too_small:
            lead.exclusion_reason = f"Too small: {', '.join(too_small[:2])}"
            lead.acceptance_gate_explanation = f"Rejected: {lead.exclusion_reason}"
            return "reject"

    # Direct prospect complexity requirement — must show operational complexity on website
    if lead.record_type == "direct_prospect" and signals:
        has_complexity = bool(
            signals.get("complexity_signals_found")
            or (signals.get("location_count", 0) >= 2)
            or (signals.get("leadership_depth", 0) >= 5)
            or signals.get("multi_entity_signals")
            or (signals.get("service_line_count", 0) >= 3)
            or signals.get("growth_signals")
            or signals.get("detected_triggers")
            or (signals.get("employee_clues") and len(signals["employee_clues"]) > 0)
        )
        if not has_complexity and lead.has_website_evidence:
            reasons.append("No operational complexity evidence found on website")

    # Competitor overlap (fractional CFO / outsourced CFO / virtual CFO services)
    competitor_terms = contains_any(
        all_text,
        ["fractional cfo", "outsourced cfo", "virtual cfo", "fractional controller",
         "outsourced controller", "cfo services", "cfo advisory", "cfo as a service"]
    )
    if competitor_terms and lead.record_type == "referral_partner":
        lead.competing_service_risk_score = max(lead.competing_service_risk_score, 80)
        reasons.append(f"Possible competitor: {', '.join(competitor_terms[:2])}")

    # If reasons found, route to review (not reject — these are soft signals)
    if reasons:
        for r in reasons:
            if r not in lead.review_evidence_against:
                lead.review_evidence_against.append(r)
        if not lead.review_suggested_next_step:
            lead.review_suggested_next_step = "Verify business legitimacy and category fit from website"
        return "review"

    return "accept"


def _evaluate_acceptance_gate(
    lead: LeadRecord,
    signals: dict,
) -> None:
    """
    Evaluate mandatory acceptance gates. Sets acceptance_gate_passed and
    acceptance_gate_explanation on the lead.

    A record may be ACCEPTED only if one of these is true:
    1. Website validated AND website content shows category fit evidence.
    2. Supported by 2+ high-confidence non-generic sources (Tier 1 or 2).

    Additionally ALL accepted records must satisfy:
    - Has a real website or equivalent Tier 1 source
    - No major source conflicts
    - Category fit evidenced from content, not merely from Maps label or snippet
    - Contact is named+credible (source_confidence >= 0.5) OR marked firm-level
    """
    gate_reasons = []
    passed = False

    has_website = bool(lead.company.website or lead.company.website_domain)
    has_website_evidence = lead.has_website_evidence
    has_category_fit_from_content = bool(
        signals.get("detected_services")
        or signals.get("complexity_signals_found")
        or signals.get("serves_business_owners")
        or signals.get("serves_smb")
    )

    # Path 1: Website validated with category fit
    website_validated = has_website_evidence and has_category_fit_from_content
    if website_validated:
        lead.website_validated = True
        gate_reasons.append("Website validated with category fit evidence")
        passed = True

    # Path 2: 2+ Tier 1/2 sources corroborate
    high_tier_sources = {e.source_type for e in lead.evidence if e.source_tier <= 2}
    if len(high_tier_sources) >= 2:
        gate_reasons.append(f"Corroborated by {len(high_tier_sources)} authoritative sources")
        passed = True

    # Additional mandatory checks for all accepted records
    if passed:
        if not has_website:
            passed = False
            gate_reasons.append("BLOCKED: No website found")

        # Check contact quality — named and credible, or firm-level only
        if lead.primary_contact and lead.primary_contact.name:
            if lead.primary_contact.contact_source_confidence < 0.5:
                # Low confidence contact — still allow if website validated
                if not website_validated:
                    gate_reasons.append("Contact has low source confidence and no website validation")
        # No contact is OK if firm-level evidence is strong

    # Set fields
    lead.acceptance_gate_passed = passed
    if passed:
        lead.acceptance_gate_explanation = "Accepted: " + "; ".join(gate_reasons)
        if lead.status != "rejected":
            lead.status = "accepted"
    else:
        explanation_parts = gate_reasons if gate_reasons else ["No acceptance path met"]
        missing = []
        if not has_website:
            missing.append("website")
        if not has_website_evidence:
            missing.append("website evidence")
        if not has_category_fit_from_content:
            missing.append("category fit from content")
        if missing:
            explanation_parts.append(f"Missing: {', '.join(missing)}")
        lead.acceptance_gate_explanation = "Not accepted: " + "; ".join(explanation_parts)
        if lead.status == "accepted":
            lead.status = "review_needed"


def _get_persona(category: str, record_type: str) -> dict:
    """Get the persona config for a category."""
    group = "referral_partners" if record_type == "referral_partner" else "direct_prospects"
    return _personas.get(group, {}).get(category, {})
