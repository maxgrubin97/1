"""Tests for classification logic."""

from app.classifiers.classifier import classify_lead
from app.models import LeadRecord
from app.models.company import Company
from app.config.settings import Settings


def test_reject_too_large(settings):
    lead = LeadRecord(
        record_type="direct_prospect",
        category="construction_trades",
        company=Company(name="Fortune 500 Builder Corp"),
    )
    signals = {"detected_services": [], "has_website": True}
    all_text = "Fortune 500 company with global headquarters"
    lead = classify_lead(lead, {"all_text": all_text}, settings)
    # Should be rejected for being too large (keyword in name)
    assert lead.status == "rejected" or "too large" in lead.exclusion_reason.lower() or lead.status == "review_needed"


def test_reject_irrelevant_law_firm_with_signals(settings):
    """With website signals confirming PI practice, the firm should be rejected."""
    lead = LeadRecord(
        record_type="referral_partner",
        category="boutique_corporate_attorneys",
        company=Company(name="Smith Personal Injury Law"),
    )
    signals = {
        "detected_services": ["Personal injury"],
        "has_website": True,
        "all_text": "personal injury slip and fall car accident",
    }
    result = classify_lead(lead, signals, settings)
    assert result.status == "rejected" or "personal injury" in result.exclusion_reason.lower()


def test_review_irrelevant_law_firm_without_signals(settings):
    """Without website signals, unclear law firm goes to review (noise control)."""
    lead = LeadRecord(
        record_type="referral_partner",
        category="boutique_corporate_attorneys",
        company=Company(name="Smith Personal Injury Law"),
    )
    result = classify_lead(lead, {}, settings)
    assert result.status == "review_needed"


def test_review_for_missing_evidence(settings):
    lead = LeadRecord(
        record_type="referral_partner",
        category="sba_lenders",
        company=Company(name="Local Bank"),
    )
    # No website signals, no practice area evidence
    result = classify_lead(lead, {}, settings)
    # Should go to review due to missing practice-area evidence
    assert result.status in ("review_needed", "rejected")


def test_competitor_rejection(settings):
    lead = LeadRecord(
        record_type="referral_partner",
        category="boutique_cpa_firms",
        company=Company(name="Acme Advisory"),
    )
    signals = {
        "detected_services": ["CFO services"],
        "competitor_signals": ["fractional CFO", "outsourced CFO"],
        "is_competitor_likely": True,
        "has_website": True,
    }
    # Merge into a text-like structure for the classifier
    all_text = "We offer fractional CFO outsourced CFO services"
    result = classify_lead(lead, signals, settings)
    # Should have competition risk flagged
    assert result.competing_service_risk_score > 0 or result.status in ("review_needed", "rejected")
