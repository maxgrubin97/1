"""Tests for no-junk ruleset — records that should be rejected or reviewed (Phase 2+4)."""

import pytest
from app.models import LeadRecord, Company, Contact
from app.classifiers.classifier import classify_lead, _apply_no_junk_rules
from app.config.settings import Settings


@pytest.fixture
def settings():
    return Settings()


def test_no_website_no_evidence_rejected(settings):
    """A record with no website, no evidence beyond Maps, and no email should be rejected or reviewed."""
    lead = LeadRecord(
        record_type="direct_prospect",
        category="construction_trades",
        company=Company(name="Unknown Builder"),
        primary_contact=Contact(
            name="Someone",
            title="Owner",
            email_status="unavailable",
        ),
    )
    lead.add_evidence(claim="Found on Maps", source_type="google_maps", source_tier=3)

    lead = classify_lead(lead, {}, settings)
    # Should NOT be accepted
    assert lead.status != "accepted"


def test_personal_injury_law_firm_rejected(settings):
    """A personal injury law firm should be rejected from attorney referral partner category."""
    lead = LeadRecord(
        record_type="referral_partner",
        category="boutique_corporate_attorneys",
        company=Company(name="Smith Injury Law"),
    )
    signals = {
        "detected_services": ["personal injury"],
        "description": "personal injury attorney specializing in car accidents",
    }
    lead = classify_lead(lead, signals, settings)
    assert lead.status == "rejected"


def test_retirement_only_wealth_advisor_rejected(settings):
    """A retirement-only wealth advisor should be rejected."""
    lead = LeadRecord(
        record_type="referral_partner",
        category="wealth_managers",
        company=Company(name="Sunset Retirement Planners"),
    )
    signals = {
        "description": "Retirement planning only. Serving retirees with Social Security optimization and Medicare planning.",
    }
    lead = classify_lead(lead, signals, settings)
    assert lead.status == "rejected"


def test_cpa_outsourced_cfo_flagged(settings):
    """A CPA firm marketing outsourced CFO services should be flagged as competitor."""
    lead = LeadRecord(
        record_type="referral_partner",
        category="boutique_cpa_firms",
        company=Company(name="Tax Plus CFO"),
    )
    signals = {
        "description": "Full-service CPA firm offering outsourced CFO and virtual CFO services to small businesses",
        "detected_services": ["CFO services", "Tax advisory"],
    }
    lead = classify_lead(lead, signals, settings)
    # Should be review or rejected, not accepted
    assert lead.status in ("review_needed", "rejected")


def test_too_large_company_rejected(settings):
    """Fortune 500 / Big 4 / Am Law 100 should be rejected."""
    lead = LeadRecord(
        record_type="referral_partner",
        category="boutique_cpa_firms",
        company=Company(name="Deloitte LLP"),
    )
    signals = {"description": "One of the Big 4 accounting firms"}
    lead = classify_lead(lead, signals, settings)
    assert lead.status == "rejected"


def test_too_small_prospect_rejected(settings):
    """Freelancers and solopreneurs should be rejected for direct prospects."""
    lead = LeadRecord(
        record_type="direct_prospect",
        category="professional_services",
        company=Company(name="Freelance Web Design"),
    )
    signals = {"description": "freelancer providing web design services"}
    result = _apply_no_junk_rules(lead, signals)
    # Should be review (no website) or reject (solopreneur)
    assert result in ("review", "reject")
