"""Tests for deduplication."""

from app.dedupe.deduplicator import deduplicate
from app.models import LeadRecord
from app.models.company import Company


def test_dedupe_by_domain():
    leads = [
        LeadRecord(company=Company(name="Firm A", website="https://firma.com", website_domain="firma.com")),
        LeadRecord(company=Company(name="Firm A LLC", website="https://www.firma.com", website_domain="firma.com")),
    ]
    result = deduplicate(leads)
    assert len(result) == 1


def test_dedupe_by_name():
    leads = [
        LeadRecord(company=Company(name="Smith & Associates LLC")),
        LeadRecord(company=Company(name="Smith & Associates")),
    ]
    result = deduplicate(leads)
    assert len(result) == 1


def test_no_false_dedupe():
    leads = [
        LeadRecord(company=Company(name="Alpha Corp", website="https://alpha.com")),
        LeadRecord(company=Company(name="Beta Corp", website="https://beta.com")),
    ]
    result = deduplicate(leads)
    assert len(result) == 2


def test_evidence_merge():
    lead1 = LeadRecord(company=Company(name="Test Corp", website="https://test.com"))
    lead1.add_evidence("From Maps", source_type="google_maps")
    lead2 = LeadRecord(company=Company(name="Test Corp LLC", website="https://test.com"))
    lead2.add_evidence("From Website", source_type="website")

    result = deduplicate([lead1, lead2])
    assert len(result) == 1
    assert len(result[0].evidence) == 2
