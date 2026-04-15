"""Tests for contact trust levels and email status (Phase 3)."""

import pytest
from app.models.contact import Contact
from app.parsers.contact_parser import (
    extract_contacts_from_team_page,
    _classify_email_status,
)


def test_guessed_email_status():
    """Guessed emails must get email_status = 'guessed'."""
    contact = Contact(
        name="Jane Doe",
        title="Partner",
        email_guess="jane@example.com | jane.doe@example.com",
        email_status="guessed",
    )
    assert contact.email_status == "guessed"


def test_generic_email_status():
    """info@/contact@ emails must get email_status = 'generic'."""
    assert _classify_email_status("info@example.com") == "generic"
    assert _classify_email_status("contact@example.com") == "generic"
    assert _classify_email_status("admin@example.com") == "generic"
    assert _classify_email_status("noreply@example.com") == "generic"
    assert _classify_email_status("hello@example.com") == "generic"


def test_verified_email_status():
    """Person-specific emails get email_status = 'verified'."""
    assert _classify_email_status("john.doe@example.com") == "verified"
    assert _classify_email_status("jsmith@example.com") == "verified"


def test_unavailable_email_status():
    """Empty email returns 'unavailable'."""
    assert _classify_email_status("") == "unavailable"


def test_team_page_extraction_confidence():
    """Team page extracted contacts should have higher confidence than LinkedIn."""
    html = """
    <div class="team-member">
        <h3>John Smith</h3>
        <p class="title">Managing Partner</p>
        <a href="mailto:jsmith@firm.com">Email</a>
    </div>
    <div class="team-member">
        <h3>Jane Doe</h3>
        <p class="title">Senior Associate</p>
    </div>
    """
    contacts = extract_contacts_from_team_page(html, source_url="https://firm.com/team")

    assert len(contacts) >= 1
    for c in contacts:
        assert c.contact_source_confidence >= 0.6
        assert c.contact_source == "website_team_page"
        assert c.source_page_url == "https://firm.com/team"


def test_linkedin_contact_lower_confidence():
    """LinkedIn-derived contacts should have confidence <= 0.4."""
    contact = Contact(
        name="Bob Builder",
        title="CEO",
        source="linkedin_public",
        contact_source="linkedin_public",
        contact_source_confidence=0.4,
        extraction_method="search_snippet",
    )
    assert contact.contact_source_confidence <= 0.4


def test_structured_markup_highest_confidence():
    """schema.org/Person markup should get confidence >= 0.9."""
    html = """
    <div itemscope itemtype="https://schema.org/Person">
        <span itemprop="name">Sarah Connor</span>
        <span itemprop="jobTitle">Founding Partner</span>
        <a itemprop="email" href="mailto:sarah@firm.com">sarah@firm.com</a>
    </div>
    """
    contacts = extract_contacts_from_team_page(html, source_url="https://firm.com/about")
    assert len(contacts) >= 1
    assert contacts[0].contact_source_confidence >= 0.9
    assert contacts[0].extraction_method == "structured_markup"
    assert contacts[0].email == "sarah@firm.com"
    assert contacts[0].email_status == "verified"
