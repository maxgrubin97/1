"""Tests for review queue routing (Phase 6)."""

from app.models import LeadRecord, Company, Contact
from app.pipeline.runner import _populate_review_metadata


def test_strong_firm_no_contact_to_review():
    """A strong firm with no contact should go to review, not rejected."""
    lead = LeadRecord(
        record_type="referral_partner",
        category="sba_lenders",
        status="review_needed",
        company=Company(name="Good Bank", website="https://goodbank.com"),
        website_validated=True,
        qualification_score=65,
    )
    lead.add_evidence(claim="Website validates", source_type="website", source_tier=1)

    _populate_review_metadata(lead)

    assert "No named contact found" in lead.review_evidence_against
    assert "Website validates category fit" in lead.review_evidence_for
    assert lead.review_suggested_next_step != ""


def test_conflicting_category_to_review():
    """A firm with conflicting category signals should go to review."""
    lead = LeadRecord(
        record_type="referral_partner",
        category="boutique_cpa_firms",
        status="review_needed",
        company=Company(name="CPA & CFO Firm"),
        competing_service_risk_score=60,
        qualification_score=50,
    )

    _populate_review_metadata(lead)

    assert any("competitor" in r.lower() for r in lead.review_evidence_against)


def test_review_metadata_actionable_next_step():
    """Review items should have actionable next steps."""
    # No website case
    lead = LeadRecord(
        record_type="referral_partner",
        category="sba_lenders",
        status="review_needed",
        company=Company(name="Mystery Bank"),
    )
    _populate_review_metadata(lead)
    assert "website" in lead.review_suggested_next_step.lower()


def test_review_metadata_has_evidence_for():
    """Review items should list positive evidence too."""
    lead = LeadRecord(
        record_type="direct_prospect",
        category="construction_trades",
        status="review_needed",
        company=Company(name="Builder Corp", website="https://builder.com"),
        website_validated=True,
        has_corroboration=True,
        qualification_score=55,
        primary_contact=Contact(name="Bob", title="Owner"),
    )
    _populate_review_metadata(lead)

    assert "Website validates category fit" in lead.review_evidence_for
    assert "Named decision-maker contact found" in lead.review_evidence_for
    assert "Multiple sources corroborate identity" in lead.review_evidence_for


def test_guessed_email_noted_in_review():
    """A record with only a guessed email should note this in review."""
    lead = LeadRecord(
        record_type="referral_partner",
        category="sba_lenders",
        status="review_needed",
        company=Company(name="Some Bank"),
        primary_contact=Contact(
            name="John",
            title="VP",
            email_status="guessed",
            email_guess="john@somebank.com",
        ),
    )
    _populate_review_metadata(lead)

    assert any("guessed" in r.lower() for r in lead.review_evidence_against)
