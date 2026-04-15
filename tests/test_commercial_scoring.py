"""Tests for referral power and buyer intent scoring."""

import pytest
from app.models import LeadRecord, Company, Contact
from app.scorers.scorer import _calculate_referral_power, _calculate_buyer_intent


def test_senior_sba_lender_high_referral_power():
    """A senior SBA lender should have high referral power score."""
    lead = LeadRecord(
        record_type="referral_partner",
        category="sba_lenders",
        company=Company(name="Community Bank"),
        primary_contact=Contact(
            name="John VP",
            title="VP SBA Lending",
            contact_priority=3,
            is_decision_maker=True,
        ),
        serves_founder_led="yes",
        boutique_fit_score=70,
    )
    score = _calculate_referral_power(lead, {"serves_smb": True})
    # High exposure (30) + seniority (15) + founder-led (25) + boutique (15) = 85
    assert score >= 70


def test_junior_associate_low_referral_power():
    """A junior associate should have lower referral power score."""
    lead = LeadRecord(
        record_type="referral_partner",
        category="boutique_corporate_attorneys",
        company=Company(name="Law Firm"),
        primary_contact=Contact(
            name="New Associate",
            title="Associate",
            contact_priority=5,
        ),
        serves_founder_led="unclear",
        boutique_fit_score=20,
    )
    score = _calculate_referral_power(lead, {})
    assert score < 50


def test_referral_power_penalizes_competitors():
    """Competitors should get penalized on referral power."""
    lead = LeadRecord(
        record_type="referral_partner",
        category="boutique_cpa_firms",
        company=Company(name="CFO Shop"),
        primary_contact=Contact(name="Boss", title="Founder", contact_priority=1),
        serves_founder_led="yes",
        competing_service_risk_score=80,
        boutique_fit_score=60,
    )
    score = _calculate_referral_power(lead, {"serves_smb": True})
    # Should be reduced by competitor penalty
    lead_no_comp = LeadRecord(
        record_type="referral_partner",
        category="boutique_cpa_firms",
        company=Company(name="Tax Only"),
        primary_contact=Contact(name="Boss", title="Founder", contact_priority=1),
        serves_founder_led="yes",
        competing_service_risk_score=0,
        boutique_fit_score=60,
    )
    score_no_comp = _calculate_referral_power(lead_no_comp, {"serves_smb": True})
    assert score_no_comp > score


def test_multi_location_contractor_high_buyer_intent():
    """A multi-location contractor with complexity should have high buyer intent."""
    lead = LeadRecord(
        record_type="direct_prospect",
        category="construction_trades",
        company=Company(
            name="Big Builder Corp",
            is_founder_led=True,
            google_review_count=150,
        ),
        primary_contact=Contact(name="Owner", title="Founder", role_category="founder", contact_priority=1),
        complexity_flags=["job costing", "bonding", "multiple crews", "commercial projects"],
        detected_triggers=["growth_expansion: expanding", "financing: business loan"],
    )
    lead.contacts = [lead.primary_contact, Contact(name="A"), Contact(name="B"), Contact(name="C")]

    score = _calculate_buyer_intent(lead, {"location_count": 3})
    assert score >= 65


def test_single_location_solo_shop_low_buyer_intent():
    """A single-location solo shop should have low buyer intent."""
    lead = LeadRecord(
        record_type="direct_prospect",
        category="construction_trades",
        company=Company(name="Joe's Repair", google_review_count=5),
        complexity_flags=[],
        detected_triggers=[],
    )
    score = _calculate_buyer_intent(lead, {"location_count": 0})
    assert score < 30


def test_triggers_boost_buyer_intent():
    """Detected triggers should boost buyer intent score."""
    base_lead = LeadRecord(
        record_type="direct_prospect",
        category="construction_trades",
        company=Company(name="Grow Corp", is_founder_led=True),
        primary_contact=Contact(name="Owner", title="Founder", role_category="founder", contact_priority=1),
        complexity_flags=["job costing"],
        detected_triggers=[],
    )
    score_no_triggers = _calculate_buyer_intent(base_lead, {})

    lead_with = LeadRecord(
        record_type="direct_prospect",
        category="construction_trades",
        company=Company(name="Grow Corp", is_founder_led=True),
        primary_contact=Contact(name="Owner", title="Founder", role_category="founder", contact_priority=1),
        complexity_flags=["job costing"],
        detected_triggers=["growth_expansion: expanding", "financing: sba loan"],
    )
    score_with_triggers = _calculate_buyer_intent(lead_with, {})

    assert score_with_triggers > score_no_triggers
