"""Tests for source hierarchy, evidence model, and lead source tracking (Phase 1+5)."""

from app.models import LeadRecord, Company, Evidence
from app.collectors.sba_lender_collector import validate_sba_lender, is_available as sba_available
from app.collectors.curated_list_collector import is_available as curated_available


def test_evidence_source_tier():
    """Evidence should carry source_tier."""
    e = Evidence(
        claim="SBA lender confirmed",
        source_type="authoritative_list",
        source_tier=1,
        extraction_method="curated_list",
    )
    assert e.source_tier == 1
    assert e.extraction_method == "curated_list"


def test_evidence_default_tier():
    """Default source_tier should be 3 (discovery)."""
    e = Evidence(claim="Found on Maps", source_type="google_maps")
    assert e.source_tier == 3


def test_lead_source_summary_update():
    """add_evidence should auto-update source_tier_best, source_count, has_corroboration."""
    lead = LeadRecord(company=Company(name="Test"))

    lead.add_evidence(
        claim="Maps discovery",
        source_type="google_maps",
        source_tier=3,
    )
    assert lead.source_tier_best == 3
    assert lead.source_count == 1

    lead.add_evidence(
        claim="Website validates",
        source_type="website",
        source_tier=1,
    )
    assert lead.source_tier_best == 1
    assert lead.source_count == 2
    # 2 source types → corroboration
    assert lead.has_corroboration is True


def test_lead_website_validated_default():
    """website_validated should default to False."""
    lead = LeadRecord(company=Company(name="Test"))
    assert lead.website_validated is False
    assert lead.acceptance_gate_passed is False
    assert lead.source_tier_best == 3


def test_company_field_provenance():
    """Company should support field_provenance tracking."""
    c = Company(name="Test Corp")
    c.field_provenance["phone"] = {
        "source_url": "https://test.com",
        "source_type": "website",
        "confidence": 0.9,
    }
    assert c.field_provenance["phone"]["confidence"] == 0.9


def test_sba_collector_graceful_when_no_list():
    """SBA collector should handle missing list file gracefully."""
    # The list file doesn't exist in the test environment
    result = validate_sba_lender("Nonexistent Bank")
    assert result is None


def test_curated_list_availability():
    """Curated list collector should report availability correctly."""
    # No CSVs in authoritative_lists by default
    # This just tests the function doesn't crash
    result = curated_available()
    assert isinstance(result, bool)
