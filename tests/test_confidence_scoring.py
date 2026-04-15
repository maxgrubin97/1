"""Tests for confidence scoring penalties and negative weights (Phase 4)."""

import pytest
from app.models import LeadRecord, Company, Contact
from app.scorers.scorer import _calculate_confidence, _apply_negative_weights
from app.config.settings import Settings


@pytest.fixture
def settings():
    return Settings()


def test_no_website_validation_penalty():
    """Missing website validation should reduce confidence by ~20 points."""
    lead_with = LeadRecord(
        record_type="referral_partner",
        category="sba_lenders",
        company=Company(name="Good Bank", website="https://good.com"),
        website_validated=True,
    )
    lead_with.add_evidence(claim="Website fit", source_type="website", source_tier=1)

    lead_without = LeadRecord(
        record_type="referral_partner",
        category="sba_lenders",
        company=Company(name="Unknown Bank"),
        website_validated=False,
    )
    lead_without.add_evidence(claim="Maps found", source_type="google_maps", source_tier=3)

    signals_with = {"has_website": True, "website_text_length": 5000}
    signals_without = {}

    conf_with = _calculate_confidence(lead_with, signals_with)
    conf_without = _calculate_confidence(lead_without, signals_without)

    assert conf_with > conf_without
    # The gap should be significant (website validation bonus + no-validation penalty)
    assert conf_with - conf_without >= 15


def test_conflicting_sources_penalty():
    """Conflicting source claims should reduce confidence."""
    lead = LeadRecord(
        record_type="referral_partner",
        category="sba_lenders",
        company=Company(name="Ambiguous Firm"),
    )
    lead.add_evidence(claim="Category fit", source_type="website", source_tier=1)

    # Signals with competitor overlap
    signals_conflict = {
        "has_website": True,
        "detected_services": ["CFO services"],
        "competitor_signals": ["fractional CFO", "outsourced CFO"],
        "website_text_length": 3000,
    }
    signals_clean = {
        "has_website": True,
        "detected_services": ["SBA lending"],
        "competitor_signals": [],
        "website_text_length": 3000,
    }

    conf_conflict = _calculate_confidence(lead, signals_conflict)
    conf_clean = _calculate_confidence(lead, signals_clean)

    assert conf_clean > conf_conflict


def test_negative_weights_reduce_score(settings):
    """Negative weights should reduce qualification score."""
    lead = LeadRecord(
        record_type="direct_prospect",
        category="construction_trades",
        company=Company(name="Test Corp"),
        qualification_score=60,
        website_validated=False,
    )
    lead.score.penalties = []

    _apply_negative_weights(lead, {}, settings)

    # Score should be reduced due to no website validation + no named contact
    assert lead.qualification_score < 60
    assert len(lead.score.penalties) > 0


def test_corroboration_boosts_confidence():
    """Corroborated records should have higher confidence."""
    lead = LeadRecord(
        record_type="referral_partner",
        category="sba_lenders",
        company=Company(name="Verified Bank", website="https://verified.com"),
        website_validated=True,
        has_corroboration=True,
        source_tier_best=1,
    )
    lead.add_evidence(claim="SBA list", source_type="authoritative_list", source_tier=1)
    lead.add_evidence(claim="Website", source_type="website", source_tier=1)

    signals = {"has_website": True, "website_text_length": 5000}
    confidence = _calculate_confidence(lead, signals)

    # Well-corroborated record should have high confidence
    assert confidence >= 60


def test_low_content_website_penalty():
    """Very low website text content should reduce confidence."""
    lead = LeadRecord(
        record_type="referral_partner",
        category="sba_lenders",
        company=Company(name="Thin Site Bank"),
    )
    lead.add_evidence(claim="Found", source_type="website", source_tier=1)

    signals_thin = {"has_website": True, "website_text_length": 100}
    signals_rich = {"has_website": True, "website_text_length": 5000}

    conf_thin = _calculate_confidence(lead, signals_thin)
    conf_rich = _calculate_confidence(lead, signals_rich)

    assert conf_rich > conf_thin
