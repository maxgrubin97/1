"""Tests for firm+contact level deduplication (Phase 6)."""

from app.models import LeadRecord, Company, Contact
from app.dedupe.deduplicator import deduplicate


def test_merge_preserves_contacts_from_both():
    """When merging two records for the same firm, contacts from both should be preserved."""
    lead1 = LeadRecord(
        company=Company(name="Acme Corp", website="https://acme.com", website_domain="acme.com"),
        primary_contact=Contact(name="Alice", title="CEO", contact_source_confidence=0.8),
    )
    lead1.contacts = [lead1.primary_contact]

    lead2 = LeadRecord(
        company=Company(name="Acme Corp LLC", website="https://acme.com", website_domain="acme.com"),
        primary_contact=Contact(name="Bob", title="CFO", contact_source_confidence=0.6),
    )
    lead2.contacts = [lead2.primary_contact]

    result = deduplicate([lead1, lead2])
    assert len(result) == 1

    merged = result[0]
    contact_names = {c.name for c in merged.contacts}
    assert "Alice" in contact_names
    assert "Bob" in contact_names


def test_merge_evidence_chains():
    """Evidence from both records should be merged."""
    lead1 = LeadRecord(
        company=Company(name="Test Corp", website="https://test.com", website_domain="test.com"),
    )
    lead1.add_evidence(claim="Found on Maps", source_type="google_maps", source_tier=3)

    lead2 = LeadRecord(
        company=Company(name="Test Corp LLC", website="https://test.com", website_domain="test.com"),
    )
    lead2.add_evidence(claim="SBA lender confirmed", source_type="authoritative_list", source_tier=1)

    result = deduplicate([lead1, lead2])
    assert len(result) == 1

    merged = result[0]
    assert len(merged.evidence) == 2
    assert merged.source_tier_best == 1


def test_merge_keeps_higher_confidence_contact():
    """When same person appears in both records, keep higher confidence version."""
    lead1 = LeadRecord(
        company=Company(name="Firm X", website="https://firmx.com", website_domain="firmx.com"),
    )
    lead1.contacts = [Contact(name="John", title="Partner", contact_source_confidence=0.4)]

    lead2 = LeadRecord(
        company=Company(name="Firm X", website="https://firmx.com", website_domain="firmx.com"),
    )
    lead2.contacts = [Contact(name="John", title="Managing Partner", contact_source_confidence=0.8)]

    result = deduplicate([lead1, lead2])
    merged = result[0]

    # Should keep the 0.8 confidence version
    johns = [c for c in merged.contacts if c.name == "John"]
    assert len(johns) == 1
    assert johns[0].contact_source_confidence == 0.8
    assert johns[0].title == "Managing Partner"


def test_merge_source_hierarchy_fields():
    """Source hierarchy fields should be merged correctly."""
    lead1 = LeadRecord(
        company=Company(name="Bank A", website="https://banka.com", website_domain="banka.com"),
        source_tier_best=3,
        website_validated=False,
    )
    lead2 = LeadRecord(
        company=Company(name="Bank A", website="https://banka.com", website_domain="banka.com"),
        source_tier_best=1,
        website_validated=True,
        has_corroboration=True,
    )

    result = deduplicate([lead1, lead2])
    merged = result[0]

    assert merged.source_tier_best == 1
    assert merged.website_validated is True
    assert merged.has_corroboration is True
