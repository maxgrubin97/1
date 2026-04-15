"""Tests for acceptance gates and no-junk rules (Phase 2)."""

import pytest
from app.models import LeadRecord, Company, Contact, Evidence
from app.classifiers.classifier import classify_lead, _evaluate_acceptance_gate, _apply_no_junk_rules
from app.config.settings import Settings


@pytest.fixture
def settings():
    return Settings()


def test_maps_only_record_goes_to_review(settings):
    """A record with only Google Maps evidence should not be accepted."""
    lead = LeadRecord(
        record_type="referral_partner",
        category="sba_lenders",
        company=Company(name="Some Bank", city="NYC", state="NY"),
    )
    lead.add_evidence(
        claim="Found via Google Maps",
        source_type="google_maps",
        confidence=0.5,
        source_tier=3,
    )
    signals = {}
    lead = classify_lead(lead, signals, settings)
    assert lead.status != "accepted"


def test_website_validated_record_accepted(settings):
    """A website-validated record with category fit gets accepted."""
    lead = LeadRecord(
        record_type="referral_partner",
        category="sba_lenders",
        company=Company(name="Community Bank", website="https://communitybank.com", city="NYC", state="NY"),
    )
    lead.add_evidence(
        claim="Website content analyzed — category fit confirmed",
        source_type="website",
        source_url="https://communitybank.com",
        confidence=0.8,
        source_tier=1,
    )
    signals = {
        "has_website": True,
        "detected_services": ["SBA lending"],
        "serves_business_owners": True,
        "serves_smb": True,
        "website_text_length": 5000,
    }
    _evaluate_acceptance_gate(lead, signals)
    assert lead.acceptance_gate_passed is True
    assert lead.website_validated is True


def test_two_authoritative_sources_accepted(settings):
    """A record corroborated by 2+ Tier 1/2 sources gets accepted."""
    lead = LeadRecord(
        record_type="referral_partner",
        category="sba_lenders",
        company=Company(name="Metro Bank", website="https://metrobank.com", city="NYC", state="NY"),
    )
    lead.add_evidence(
        claim="Listed in SBA lender directory",
        source_type="authoritative_list",
        confidence=0.95,
        source_tier=1,
    )
    lead.add_evidence(
        claim="Website confirms SBA lending",
        source_type="website",
        confidence=0.8,
        source_tier=1,
    )
    signals = {"has_website": True, "detected_services": ["Commercial lending"]}
    _evaluate_acceptance_gate(lead, signals)
    assert lead.acceptance_gate_passed is True


def test_enterprise_mismatch_rejected():
    """Fortune 500 / enterprise companies should be rejected."""
    lead = LeadRecord(
        record_type="direct_prospect",
        category="construction_trades",
        company=Company(name="Mega Corp"),
    )
    signals = {"description": "Fortune 500 company with global operations"}
    result = _apply_no_junk_rules(lead, signals)
    assert result == "reject"
    assert "Enterprise mismatch" in lead.exclusion_reason


def test_solopreneur_rejected():
    """Solopreneurs should be rejected for direct prospects."""
    lead = LeadRecord(
        record_type="direct_prospect",
        category="construction_trades",
        company=Company(name="Joe's Handyman"),
    )
    signals = {"description": "solopreneur handyman service"}
    result = _apply_no_junk_rules(lead, signals)
    assert result == "reject"


def test_no_website_goes_to_review():
    """A record with no website should go to review."""
    lead = LeadRecord(
        record_type="referral_partner",
        category="sba_lenders",
        company=Company(name="Unknown Bank"),
    )
    result = _apply_no_junk_rules(lead, {})
    assert result == "review"
    assert any("No website" in r for r in lead.review_evidence_against)


def test_competitor_flagged_for_review():
    """A CPA firm marketing fractional CFO services should be flagged."""
    lead = LeadRecord(
        record_type="referral_partner",
        category="boutique_cpa_firms",
        company=Company(name="Tax & CFO Co"),
    )
    signals = {"description": "We offer fractional CFO and outsourced controller services"}
    result = _apply_no_junk_rules(lead, signals)
    assert result == "review"
    assert lead.competing_service_risk_score >= 80
