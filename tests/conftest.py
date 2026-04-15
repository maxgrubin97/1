"""Shared test fixtures."""

import pytest
from app.config.settings import Settings
from app.models import LeadRecord
from app.models.company import Company
from app.models.contact import Contact


@pytest.fixture
def settings():
    return Settings()


@pytest.fixture
def sample_referral_lead():
    return LeadRecord(
        record_type="referral_partner",
        category="sba_lenders",
        company=Company(
            name="First National Bank",
            website="https://firstnational.com",
            website_domain="firstnational.com",
            phone="(516) 555-0100",
            city="Garden City",
            state="NY",
            zip_code="11530",
            google_rating=4.3,
            google_review_count=85,
            primary_industry="Financial Services",
        ),
        primary_contact=Contact(
            name="John Smith",
            title="VP SBA Lending",
            seniority_level="senior",
            role_category="specialist",
            contact_priority=3,
            is_decision_maker=True,
            source="linkedin_public",
        ),
    )


@pytest.fixture
def sample_prospect_lead():
    return LeadRecord(
        record_type="direct_prospect",
        category="construction_trades",
        company=Company(
            name="ABC Construction Corp",
            website="https://abcconstruction.com",
            website_domain="abcconstruction.com",
            phone="(631) 555-0200",
            city="Melville",
            state="NY",
            zip_code="11747",
            google_rating=4.7,
            google_review_count=120,
            primary_industry="Construction / Trades",
        ),
        primary_contact=Contact(
            name="Mike Johnson",
            title="Owner",
            seniority_level="executive",
            role_category="founder",
            contact_priority=1,
            is_decision_maker=True,
            source="website",
        ),
    )
