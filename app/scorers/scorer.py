"""
Unified scorer with category-specific sub-models.

Each category uses its own scoring weights from personas.yaml.
Also generates outreach intelligence for accepted records.

Quality definition enforced:
- Relevance
- Seniority
- Contactability
- Commercial need OR referral capacity
- Realistic probability of productive first conversation
"""

import logging
from pathlib import Path

import yaml

from app.models import LeadRecord
from app.models.scoring import ScoreBreakdown
from app.config.settings import Settings

logger = logging.getLogger(__name__)

# Load personas
_personas_path = Path(__file__).parent.parent / "config" / "personas.yaml"
_personas: dict = {}
if _personas_path.exists():
    with open(_personas_path) as f:
        _personas = yaml.safe_load(f) or {}


def score_lead(
    lead: LeadRecord,
    website_signals: dict,
    settings: Settings,
) -> LeadRecord:
    """
    Score a lead using category-specific sub-model weights.
    Also applies negative weights, generates outreach intelligence, and assigns tier.
    """
    if lead.status == "rejected":
        lead.pipeline_stage = "scored"
        return lead

    # Get category-specific sub-model
    persona = _get_persona(lead.category, lead.record_type)
    sub_model = persona.get("scoring_sub_model", {})

    if lead.record_type == "referral_partner":
        _score_referral_partner(lead, website_signals, settings, sub_model)
    else:
        _score_direct_prospect(lead, website_signals, settings, sub_model)

    # Apply negative weights after positive scoring
    _apply_negative_weights(lead, website_signals, settings)

    # Calculate confidence with explicit penalties
    lead.confidence_score = _calculate_confidence(lead, website_signals)

    # Apply thresholds
    thresholds = settings.get_thresholds()
    if lead.confidence_score < thresholds.get("confidence_floor", 40):
        lead.status = "review_needed"
        lead.review_evidence_against.append(f"Low confidence ({lead.confidence_score})")
        lead.review_suggested_next_step = "Verify with additional sources"
    elif lead.status != "review_needed":
        if lead.qualification_score >= thresholds.get("auto_accept_min", 80):
            lead.status = "accepted"
        elif lead.qualification_score <= thresholds.get("auto_reject_max", 30):
            lead.status = "rejected"
            lead.exclusion_reason = f"Score too low ({lead.qualification_score})"
        else:
            lead.status = "review_needed"

    # Generate outreach intelligence for accepted/review leads
    if lead.status in ("accepted", "review_needed"):
        _generate_outreach_intelligence(lead, persona)

    # Assign tier
    if lead.qualification_score >= 75:
        lead.outreach_priority_tier = "A"
    elif lead.qualification_score >= 50:
        lead.outreach_priority_tier = "B"
    else:
        lead.outreach_priority_tier = "C"

    lead.pipeline_stage = "scored"
    return lead


def _score_referral_partner(
    lead: LeadRecord,
    signals: dict,
    settings: Settings,
    sub_model: dict,
):
    """Score a referral partner using category-specific weights."""
    dimensions = {}
    reasons = []
    penalties = []

    # Geography fit
    max_geo = sub_model.get("geography_fit", 10)
    geo_score = max_geo  # Default: if it's in our search, geography fits
    if lead.company.state in ("NY", "NJ", "CT"):
        geo_score = max_geo
        reasons.append(f"Located in target market ({lead.company.state})")
    elif lead.company.state:
        geo_score = int(max_geo * 0.5)
    dimensions["geography_fit"] = geo_score

    # Category fit / practice area
    max_cat = sub_model.get("category_fit", sub_model.get("practice_area_fit", sub_model.get("sba_lending_focus", 15)))
    cat_score = 0
    if signals and signals.get("detected_services"):
        services = signals["detected_services"]
        # Check if detected services align with category
        cat_config = {}
        try:
            cat_config = settings.get_category(lead.category)
        except KeyError:
            pass
        cat_label = cat_config.get("label", lead.category)
        if any(s.lower() in cat_label.lower() for s in services):
            cat_score = max_cat
            reasons.append(f"Practice area directly aligns: {services[0]}")
        elif services:
            cat_score = int(max_cat * 0.6)
            reasons.append(f"Related services detected: {', '.join(services[:2])}")
    elif lead.has_website_evidence:
        cat_score = int(max_cat * 0.4)
    dimensions["category_fit"] = cat_score

    # Seniority
    max_sen = sub_model.get("seniority", sub_model.get("partner_seniority", 15))
    sen_score = 0
    if lead.primary_contact:
        priority = lead.primary_contact.contact_priority
        if priority <= 1:
            sen_score = max_sen
            reasons.append(f"Senior contact: {lead.primary_contact.title}")
        elif priority <= 3:
            sen_score = int(max_sen * 0.8)
            reasons.append(f"Mid-senior contact: {lead.primary_contact.title}")
        elif priority <= 5:
            sen_score = int(max_sen * 0.4)
        lead.seniority_score = sen_score
    dimensions["seniority"] = sen_score

    # Client overlap / SMB orientation
    max_overlap = sub_model.get("client_overlap", sub_model.get("smb_client_base",
                  sub_model.get("sell_side_smb_focus", sub_model.get("smb_tax_advisory_focus",
                  sub_model.get("entrepreneur_client_focus", 20)))))
    overlap_score = 0
    if signals:
        if signals.get("serves_business_owners"):
            overlap_score = max_overlap
            reasons.append("Serves business owners/entrepreneurs")
        elif signals.get("serves_smb"):
            overlap_score = int(max_overlap * 0.7)
            reasons.append("Serves small businesses")
        elif not signals.get("serves_enterprise"):
            overlap_score = int(max_overlap * 0.3)
    lead.client_overlap_score = overlap_score
    dimensions["client_overlap"] = overlap_score

    # Boutique fit
    max_bout = sub_model.get("boutique_fit", sub_model.get("boutique_size",
                sub_model.get("boutique_independent", 10)))
    bout_score = 0
    if signals:
        if signals.get("is_boutique_likely") and not signals.get("is_large_likely"):
            bout_score = max_bout
            reasons.append("Boutique/small firm")
        elif signals.get("is_large_likely"):
            bout_score = 0
            penalties.append("Appears to be a large firm")
        else:
            bout_score = int(max_bout * 0.5)
    lead.boutique_fit_score = bout_score
    dimensions["boutique_fit"] = bout_score

    # Referral likelihood
    max_ref = sub_model.get("referral_likelihood", sub_model.get("referral_orientation",
               sub_model.get("relationship_orientation", sub_model.get("relationship_model", 15))))
    ref_score = int(max_ref * 0.5)  # Moderate default
    if lead.primary_contact and lead.primary_contact.is_decision_maker:
        ref_score = int(max_ref * 0.8)
    if signals and signals.get("serves_business_owners"):
        ref_score = max_ref
        reasons.append("High referral potential — serves our target clients")
    lead.referral_likelihood_score = ref_score
    dimensions["referral_likelihood"] = ref_score

    # Competition risk (inverse)
    max_comp = sub_model.get("competition_risk_inverse", sub_model.get("non_competing_evidence", 5))
    comp_score = max_comp
    if lead.competing_service_risk_score > 50:
        comp_score = 0
        penalties.append(f"Competition risk: {lead.competing_service_risk_score}%")
    elif lead.competing_service_risk_score > 0:
        comp_score = int(max_comp * 0.3)
        penalties.append("Some competition overlap detected")
    dimensions["competition_risk_inv"] = comp_score

    # Data completeness
    max_data = sub_model.get("data_completeness", 5)
    completeness = _calculate_completeness(lead)
    data_score = int(max_data * completeness)
    dimensions["data_completeness"] = data_score

    # Total
    total = sum(dimensions.values())
    lead.qualification_score = min(100, total)
    lead.score = ScoreBreakdown(dimensions=dimensions, total=total, reasons=reasons, penalties=penalties)

    # Why it might not be a fit
    if not lead.has_decision_maker:
        lead.why_this_might_not_be_a_fit.append("No named decision-maker contact found")
    if lead.competing_service_risk_score > 0:
        lead.why_this_might_not_be_a_fit.append("Possible competing service overlap")
    if signals and signals.get("is_large_likely"):
        lead.why_this_might_not_be_a_fit.append("Firm may be too large for boutique referral relationship")
    if not lead.has_website_evidence:
        lead.why_this_might_not_be_a_fit.append("No website evidence to confirm practice area")


def _score_direct_prospect(
    lead: LeadRecord,
    signals: dict,
    settings: Settings,
    sub_model: dict,
):
    """Score a direct prospect using category-specific weights."""
    dimensions = {}
    reasons = []
    penalties = []

    # Geography fit
    max_geo = sub_model.get("geography_fit", 10)
    geo_score = max_geo if lead.company.state in ("NY", "NJ", "CT") else int(max_geo * 0.5)
    if geo_score == max_geo:
        reasons.append(f"Located in target market ({lead.company.city}, {lead.company.state})")
    dimensions["geography_fit"] = geo_score

    # Operational complexity
    max_complex = sub_model.get("operational_complexity", sub_model.get("multi_entity_complexity",
                   sub_model.get("multi_location_evidence", 25)))
    complex_score = 0
    if signals:
        complexity_count = len(signals.get("complexity_signals_found", []))
        if complexity_count >= 3:
            complex_score = max_complex
            reasons.append(f"High operational complexity: {', '.join(lead.complexity_flags[:3])}")
        elif complexity_count >= 1:
            complex_score = int(max_complex * 0.6)
            reasons.append(f"Some complexity signals: {', '.join(lead.complexity_flags[:2])}")
        elif lead.company.google_review_count > 50:
            complex_score = int(max_complex * 0.4)
            reasons.append("Significant business activity (reviews suggest scale)")
    lead.financial_complexity_score = complex_score
    dimensions["operational_complexity"] = complex_score

    # Likely revenue band
    max_rev = sub_model.get("likely_revenue_band", 20)
    rev_score = 0
    reviews = lead.company.google_review_count or 0
    if reviews > 200:
        rev_score = max_rev
        reasons.append("Likely $5M+ revenue (high review volume)")
        lead.company.revenue_estimate = "$5M-$15M (est.)"
    elif reviews > 50:
        rev_score = int(max_rev * 0.8)
        reasons.append("Likely $1M-$5M revenue (moderate review volume)")
        lead.company.revenue_estimate = "$1M-$5M (est.)"
    elif reviews > 10:
        rev_score = int(max_rev * 0.5)
        lead.company.revenue_estimate = "$500K-$2M (est.)"
    elif signals and signals.get("employee_clues"):
        rev_score = int(max_rev * 0.6)
    dimensions["likely_revenue_band"] = rev_score

    # Buying trigger evidence
    max_trigger = sub_model.get("buying_trigger_evidence", 15)
    trigger_score = 0
    if signals:
        triggers = signals.get("buying_triggers_found", [])
        if len(triggers) >= 3:
            trigger_score = max_trigger
            reasons.append(f"Multiple buying triggers: {', '.join(triggers[:3])}")
        elif len(triggers) >= 1:
            trigger_score = int(max_trigger * 0.6)
            reasons.append(f"Buying trigger: {triggers[0]}")
        growth = signals.get("growth_signals", [])
        if growth:
            trigger_score = max(trigger_score, int(max_trigger * 0.5))
            reasons.append(f"Growth signal: {growth[0]}")
    dimensions["buying_trigger_evidence"] = trigger_score

    # Owner-led likelihood
    max_owner = sub_model.get("owner_led_likelihood", 15)
    owner_score = 0
    if signals and signals.get("is_owner_led_likely"):
        owner_score = max_owner
        reasons.append("Likely owner-led business")
    elif lead.primary_contact and lead.primary_contact.role_category == "founder":
        owner_score = max_owner
        reasons.append(f"Owner/founder contact: {lead.primary_contact.name}")
    elif lead.company.is_founder_led:
        owner_score = int(max_owner * 0.8)
    dimensions["owner_led_likelihood"] = owner_score

    # Employee count fit
    max_emp = sub_model.get("employee_count_fit", sub_model.get("portfolio_size_signals", 10))
    emp_score = 0
    emp_est = lead.company.employee_count_estimate.lower() if lead.company.employee_count_estimate else ""
    if emp_est:
        try:
            num = int("".join(c for c in emp_est.split()[0] if c.isdigit()) or "0")
            if 10 <= num <= 200:
                emp_score = max_emp
                reasons.append(f"Ideal employee range: ~{num}")
            elif 5 <= num < 10:
                emp_score = int(max_emp * 0.6)
            elif num > 200:
                emp_score = int(max_emp * 0.3)
                penalties.append("May be too large")
        except (ValueError, IndexError):
            pass
    dimensions["employee_count_fit"] = emp_score

    # Data completeness
    max_data = sub_model.get("data_completeness", 5)
    completeness = _calculate_completeness(lead)
    data_score = int(max_data * completeness)
    dimensions["data_completeness"] = data_score

    # Total
    total = sum(dimensions.values())
    lead.qualification_score = min(100, total)
    lead.score = ScoreBreakdown(dimensions=dimensions, total=total, reasons=reasons, penalties=penalties)

    # Estimated fit
    if total >= 70:
        lead.estimated_fit_for_fractional_cfo = "strong"
    elif total >= 45:
        lead.estimated_fit_for_fractional_cfo = "moderate"
    elif total >= 25:
        lead.estimated_fit_for_fractional_cfo = "weak"
    else:
        lead.estimated_fit_for_fractional_cfo = "unclear"

    # Why might not fit
    if not lead.has_decision_maker:
        lead.why_this_might_not_be_a_fit.append("No owner/decision-maker contact found")
    if not lead.complexity_flags:
        lead.why_this_might_not_be_a_fit.append("No clear operational complexity signals")
    if reviews < 5 and not signals:
        lead.why_this_might_not_be_a_fit.append("Very limited data — may be too small or inactive")
    if signals and signals.get("is_large_likely"):
        lead.why_this_might_not_be_a_fit.append("May already have internal finance team")


def _generate_outreach_intelligence(lead: LeadRecord, persona: dict):
    """Generate outreach angle, pain point, and referral fit narrative."""
    outreach_angle = persona.get("outreach_angle", "").strip()
    lead.primary_outreach_angle = outreach_angle

    if lead.record_type == "referral_partner":
        lead.likely_pain_point = _infer_referral_pain(lead)
        lead.likely_referral_reason = _infer_referral_reason(lead)
        lead.mutual_referral_fit = _generate_mutual_fit(lead, outreach_angle)
    else:
        lead.likely_pain_point = _infer_prospect_pain(lead)
        lead.likely_referral_reason = ""
        lead.mutual_referral_fit = ""

    # Recommended contact order
    if lead.contacts:
        lead.recommended_contact_order = [
            f"{c.name} ({c.title})" for c in sorted(lead.contacts, key=lambda c: c.contact_priority)[:3]
        ]
    elif lead.primary_contact:
        lead.recommended_contact_order = [f"{lead.primary_contact.name} ({lead.primary_contact.title})"]


def _infer_referral_pain(lead: LeadRecord) -> str:
    category_pains = {
        "sba_lenders": "Borrowers with messy financials slow down loan processing and increase risk",
        "business_brokers": "Sellers with unclear financials reduce deal value and scare off buyers",
        "boutique_corporate_attorneys": "Clients in transactions often lack CFO-level financial diligence",
        "boutique_cpa_firms": "Business clients need strategic finance help that goes beyond tax compliance",
        "wealth_managers": "Entrepreneur clients need operational finance clarity before liquidity events",
        "commercial_bankers": "Borrowers without clean financials create risk and delay credit decisions",
        "valuation_exit_advisors": "Business owners often lack the financial documentation needed for accurate valuations",
    }
    return category_pains.get(lead.category, "Clients need better financial visibility and structure")


def _infer_referral_reason(lead: LeadRecord) -> str:
    category_reasons = {
        "sba_lenders": "I get borrowers lender-ready with clean financials, projections, and cash flow analysis",
        "business_brokers": "I help sellers present defensible financials that maximize deal value",
        "boutique_corporate_attorneys": "I provide CFO-level financial diligence that complements your legal work on deals",
        "boutique_cpa_firms": "I handle strategic CFO work (forecasting, KPIs, cash flow) while you keep the tax relationship",
        "wealth_managers": "I bring operational finance order to entrepreneur clients approaching transitions",
        "commercial_bankers": "I prepare borrowers with ongoing financial reporting that protects your credit position",
        "valuation_exit_advisors": "I get businesses financially ready for accurate valuation and successful transition",
    }
    return category_reasons.get(lead.category, "I provide fractional CFO services that complement your client relationships")


def _infer_prospect_pain(lead: LeadRecord) -> str:
    if lead.complexity_flags:
        return f"Likely struggling with: {', '.join(lead.complexity_flags[:3])}"
    if lead.likely_buying_triggers:
        return f"Facing: {', '.join(lead.likely_buying_triggers[:3])}"
    return "Likely needs better financial visibility, reporting, or cash flow management"


def _generate_mutual_fit(lead: LeadRecord, outreach_angle: str) -> str:
    """Generate 2-4 sentence mutual referral fit narrative."""
    company = lead.company.name
    contact = lead.primary_contact.name if lead.primary_contact else "the principal"
    category_label = lead.category.replace("_", " ").title()

    parts = [
        f"{company} appears to be a strong referral partner opportunity as a {category_label.lower()}.",
    ]
    if lead.serves_founder_led in ("yes", "probably"):
        parts.append("They likely serve founder-led businesses in our target market.")
    if lead.boutique_fit_score > 50:
        parts.append("Their boutique size suggests a relationship-driven approach to client service.")
    parts.append(f"A conversation with {contact} could explore mutual referral opportunities.")

    return " ".join(parts)


def _calculate_completeness(lead: LeadRecord) -> float:
    """Calculate data completeness as a 0-1 ratio."""
    fields_to_check = [
        bool(lead.company.name),
        bool(lead.company.website),
        bool(lead.company.phone or lead.company.email),
        bool(lead.company.address or lead.company.city),
        bool(lead.company.primary_industry),
        bool(lead.has_decision_maker),
        bool(lead.company.google_rating),
        len(lead.evidence) >= 2,
    ]
    return sum(fields_to_check) / len(fields_to_check)


def _apply_negative_weights(lead: LeadRecord, signals: dict, settings: Settings):
    """Apply negative scoring weights after positive dimension scoring."""
    penalties = lead.score.penalties
    neg_config = {}
    try:
        neg_all = settings.scoring_weights.get("negative_weights", {})
        neg_config = neg_all.get(lead.record_type, {})
    except Exception:
        pass

    total_penalty = 0

    # No website validation
    if not lead.website_validated:
        p = neg_config.get("no_website_validation", -10)
        total_penalty += p
        penalties.append(f"No website validation ({p})")

    # Generic contact only
    if lead.primary_contact and lead.primary_contact.email_status == "generic":
        has_named = lead.primary_contact.name and lead.primary_contact.email_status != "unavailable"
        if not has_named:
            p = neg_config.get("generic_contact_only", -5)
            total_penalty += p
            penalties.append(f"Generic contact only ({p})")

    # No named contact
    if not lead.has_decision_maker:
        p = neg_config.get("no_named_contact", -8)
        total_penalty += p
        penalties.append(f"No named contact ({p})")

    # Likely competitor
    if lead.competing_service_risk_score > 50:
        p = neg_config.get("likely_competitor", -15)
        total_penalty += p
        penalties.append(f"Likely competitor ({p})")

    # Generic directory only
    evidence_types = lead.evidence_source_types
    if evidence_types and evidence_types <= {"google_maps", "directory"}:
        p = neg_config.get("generic_directory_only", -10)
        total_penalty += p
        penalties.append(f"Only generic directory evidence ({p})")

    # Maps category only (no website-backed category fit)
    if not lead.website_validated and "google_maps" in evidence_types:
        if not any(e.source_type == "website" for e in lead.evidence):
            p = neg_config.get("maps_category_only", -8)
            total_penalty += p
            penalties.append(f"Category from Maps only ({p})")

    # Low complexity (direct prospect only)
    if lead.record_type == "direct_prospect":
        if signals and not signals.get("complexity_signals_found"):
            p = neg_config.get("low_complexity_business", -5)
            total_penalty += p
            penalties.append(f"No complexity signals ({p})")

    # Apply penalties to qualification score
    lead.qualification_score = max(0, lead.qualification_score + total_penalty)
    lead.score.total = lead.qualification_score


def _calculate_confidence(lead: LeadRecord, signals: dict) -> int:
    """
    Calculate confidence score (0-100) based on evidence quality.

    Uses explicit penalties for missing/weak evidence rather than
    purely additive scoring.
    """
    score = 50  # Start at midpoint

    # --- Positive factors ---

    # Source quality (best tier)
    if lead.source_tier_best == 1:
        score += 15
    elif lead.source_tier_best == 2:
        score += 10
    elif lead.source_tier_best == 3:
        score += 0

    # Corroboration
    if lead.has_corroboration:
        score += 10

    # Website validation
    if lead.website_validated:
        score += 10

    # Contact source quality
    if lead.primary_contact:
        cc = lead.primary_contact.contact_source_confidence
        if cc >= 0.7:
            score += 10  # Website team page structured
        elif cc >= 0.5:
            score += 5   # Website team card
        # LinkedIn snippet or lower → no bonus

    # Evidence volume
    if len(lead.evidence) >= 3:
        score += 5

    # --- Explicit penalties ---

    # No website validation
    if not lead.website_validated:
        score -= 20

    # Category inferred only from Maps or search snippet
    evidence_types = lead.evidence_source_types
    if evidence_types and evidence_types <= {"google_maps", "directory", "linkedin_public"}:
        if not any(e.source_type == "website" for e in lead.evidence):
            score -= 15

    # No named contact
    if not lead.has_decision_maker:
        score -= 10

    # Only guessed email, no verified or generic
    if lead.primary_contact:
        if (lead.primary_contact.email_status == "guessed"
                and not lead.primary_contact.email):
            score -= 5

    # Conflicting category data across sources
    if signals and signals.get("competitor_signals") and signals.get("detected_services"):
        score -= 10

    # Low-content website
    if signals and signals.get("has_website"):
        text_len = signals.get("website_text_length", 0)
        if 0 < text_len < 500:
            score -= 10

    # Only generic directory evidence
    if evidence_types and evidence_types <= {"directory"}:
        score -= 15

    # Likely competitor signals
    if lead.competing_service_risk_score > 50:
        score -= 10

    return max(0, min(100, score))


def _get_persona(category: str, record_type: str) -> dict:
    group = "referral_partners" if record_type == "referral_partner" else "direct_prospects"
    return _personas.get(group, {}).get(category, {})
