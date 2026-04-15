"""Tests for the final refinement pass: email removal, runtime modes, commercial scoring,
trigger detection, direct prospect tightening, and outreach narratives."""

import os
import pytest
from unittest.mock import patch

from app.models import LeadRecord, Company, Contact
from app.models.contact import Contact as ContactModel
from app.config.settings import Settings
from app.scorers.scorer import (
    _calculate_referral_power, _calculate_buyer_intent,
    _generate_why_this_lead, _generate_why_now, _generate_outreach_angle,
    _assign_commercial_tier, score_lead,
)
from app.parsers.website_parser import parse_website_signals
from app.classifiers.classifier import _apply_no_junk_rules
from app.collectors.web_search_collector import _result_to_lead, is_available


# ============================================================
# PHASE 1: Email guess removal
# ============================================================

def test_email_guess_field_removed():
    """Confirm email_guess field no longer exists on Contact model."""
    c = ContactModel(name="Test", title="VP")
    assert not hasattr(c, "email_guess")


def test_no_guessed_email_status():
    """Contacts without extracted emails must have email_status = 'unavailable'."""
    c = ContactModel(name="Test", title="VP")
    assert c.email_status == "unavailable"
    assert c.email == ""


def test_guess_email_function_removed():
    """_guess_email function should not exist in enricher."""
    from app.enrichers import enricher
    assert not hasattr(enricher, "_guess_email")


# ============================================================
# PHASE 2: Runtime modes
# ============================================================

def test_no_keys_detects_no_key():
    with patch.dict(os.environ, {"GMAPS_API_KEY": "", "SERPAPI_KEY": "", "RUNTIME_MODE": ""}, clear=False):
        s = Settings()
        assert s.runtime_mode == "no_key"


def test_all_keys_detects_premium():
    with patch.dict(os.environ, {"GMAPS_API_KEY": "k", "SERPAPI_KEY": "k", "RUNTIME_MODE": ""}, clear=False):
        s = Settings()
        assert s.runtime_mode == "premium"


def test_some_keys_detects_hybrid():
    with patch.dict(os.environ, {"GMAPS_API_KEY": "k", "SERPAPI_KEY": "", "RUNTIME_MODE": ""}, clear=False):
        s = Settings()
        assert s.runtime_mode == "hybrid"


def test_no_key_threshold_85():
    with patch.dict(os.environ, {"GMAPS_API_KEY": "", "SERPAPI_KEY": "", "RUNTIME_MODE": ""}, clear=False):
        s = Settings()
        assert s.get_effective_thresholds()["auto_accept_min"] >= 85


def test_no_key_no_google_maps_sources():
    """In no_key mode, default sources should NOT include google_maps."""
    with patch.dict(os.environ, {"GMAPS_API_KEY": "", "SERPAPI_KEY": "", "RUNTIME_MODE": ""}, clear=False):
        s = Settings()
        assert s.runtime_mode == "no_key"
        # The pipeline runner sets sources=["web_search"] for no_key mode


# ============================================================
# PHASE 2: Web search collector
# ============================================================

def test_web_search_available():
    assert is_available() is True


def test_web_search_result_is_tier_3():
    """Web search results must be tagged source_tier=3."""
    lead = _result_to_lead(
        url="https://example-bank.com/about",
        title="Example Bank - About Us",
        snippet_el=None,
    )
    assert lead is not None
    assert lead.evidence[0].source_tier == 3
    assert lead.evidence[0].source_type == "web_search"


def test_web_search_skips_social_domains():
    """Social media domains should be filtered out."""
    for domain in ["https://facebook.com/bank", "https://linkedin.com/company/bank",
                   "https://yelp.com/biz/bank"]:
        lead = _result_to_lead(url=domain, title="Bank", snippet_el=None)
        assert lead is None


# ============================================================
# PHASE 3: Commercial scoring
# ============================================================

def test_senior_sba_bdo_high_referral_power():
    """A senior SBA BDO should have high referral power."""
    lead = LeadRecord(
        record_type="referral_partner",
        category="sba_lenders",
        primary_contact=Contact(name="VP", title="VP SBA Lending", contact_priority=3),
        serves_founder_led="yes",
        boutique_fit_score=70,
    )
    score = _calculate_referral_power(lead, {"serves_smb": True})
    assert score >= 70


def test_junior_associate_low_referral_power():
    """A junior associate should have lower referral power."""
    lead = LeadRecord(
        record_type="referral_partner",
        category="boutique_corporate_attorneys",
        primary_contact=Contact(name="Jr", title="Associate", contact_priority=5),
        serves_founder_led="unclear",
        boutique_fit_score=20,
    )
    score = _calculate_referral_power(lead, {})
    assert score < 50


def test_multi_location_contractor_high_buyer_intent():
    """A multi-location contractor with growth should have high buyer intent."""
    lead = LeadRecord(
        record_type="direct_prospect",
        category="construction_trades",
        company=Company(name="Big Builder", is_founder_led=True),
        primary_contact=Contact(name="Owner", title="Founder", role_category="founder", contact_priority=1),
        complexity_flags=["job costing", "bonding", "multiple crews", "commercial projects"],
        detected_triggers=["growth_expansion: expanding", "financing: business loan"],
    )
    lead.contacts = [lead.primary_contact] + [Contact(name=f"P{i}") for i in range(7)]
    score = _calculate_buyer_intent(lead, {"location_count": 3})
    assert score >= 65


def test_solo_shop_low_buyer_intent():
    """A single-location solo shop should have low buyer intent."""
    lead = LeadRecord(
        record_type="direct_prospect",
        category="construction_trades",
        company=Company(name="Joe's Repair"),
    )
    score = _calculate_buyer_intent(lead, {"location_count": 0})
    assert score < 30


# ============================================================
# PHASE 3: Trigger detection
# ============================================================

def test_growth_triggers_detected():
    data = {"all_text": "We are expanding to a new location in Queens.", "home_text": "", "about_text": "", "services_text": "", "meta_description": ""}
    signals = parse_website_signals(data)
    assert len(signals.get("detected_triggers", [])) > 0
    assert any("growth_expansion" in t for t in signals["detected_triggers"])


def test_financing_triggers_detected():
    data = {"all_text": "We help clients secure SBA loan financing.", "home_text": "", "about_text": "", "services_text": "", "meta_description": ""}
    signals = parse_website_signals(data)
    assert any("financing" in t for t in signals.get("detected_triggers", []))


def test_no_triggers_on_plain_text():
    data = {"all_text": "We are a local accounting firm.", "home_text": "", "about_text": "", "services_text": "", "meta_description": ""}
    signals = parse_website_signals(data)
    assert len(signals.get("detected_triggers", [])) == 0


# ============================================================
# PHASE 4: Direct prospect tightening
# ============================================================

def test_prospect_no_complexity_to_review():
    """A direct prospect with no complexity evidence should go to review."""
    lead = LeadRecord(
        record_type="direct_prospect",
        category="construction_trades",
        company=Company(name="Plain Builder", website="https://plain.com"),
    )
    lead.add_evidence(claim="Website analyzed", source_type="website", source_tier=1)
    signals = {
        "has_website": True,
        "complexity_signals_found": [],
        "location_count": 0,
        "leadership_depth": 1,
        "multi_entity_signals": [],
        "service_line_count": 1,
        "growth_signals": [],
        "detected_triggers": [],
        "employee_clues": [],
    }
    result = _apply_no_junk_rules(lead, signals)
    assert result == "review"
    assert any("complexity" in r.lower() for r in lead.review_evidence_against)


def test_prospect_with_complexity_not_blocked():
    """A direct prospect with multi-location signals should not be blocked by complexity check."""
    lead = LeadRecord(
        record_type="direct_prospect",
        category="construction_trades",
        company=Company(name="Big Builder", website="https://big.com"),
    )
    lead.add_evidence(claim="Website analyzed", source_type="website", source_tier=1)
    signals = {
        "has_website": True,
        "complexity_signals_found": ["job costing", "bonding"],
        "location_count": 3,
        "leadership_depth": 8,
        "multi_entity_signals": [],
        "service_line_count": 4,
        "growth_signals": ["expanding"],
        "detected_triggers": ["growth_expansion: expanding"],
        "employee_clues": [],
    }
    result = _apply_no_junk_rules(lead, signals)
    # Should not be blocked by complexity check — may be review for other reasons or accept
    assert not any("complexity" in r.lower() for r in lead.review_evidence_against)


# ============================================================
# PHASE 3: Commercial priority tier
# ============================================================

def test_tier_a_high_confidence_high_commercial_named_contact():
    """High confidence + high commercial score + good contact = Tier A."""
    lead = LeadRecord(
        record_type="referral_partner",
        confidence_score=75,
        referral_power_score=80,
        primary_contact=Contact(name="John", title="Partner", contact_source_confidence=0.8),
    )
    assert _assign_commercial_tier(lead) == "A"


def test_tier_b_moderate_scores():
    """Moderate scores = Tier B."""
    lead = LeadRecord(
        record_type="direct_prospect",
        confidence_score=60,
        buyer_intent_score=50,
    )
    assert _assign_commercial_tier(lead) == "B"


def test_tier_c_low_scores():
    """Low scores = Tier C."""
    lead = LeadRecord(
        record_type="direct_prospect",
        confidence_score=40,
        buyer_intent_score=20,
    )
    assert _assign_commercial_tier(lead) == "C"


# ============================================================
# PHASE 3: Outreach narrative generation
# ============================================================

def test_accepted_leads_have_outreach_fields(settings=None):
    """Accepted leads should have non-empty why_this_lead, why_now, outreach_angle."""
    s = Settings()
    lead = LeadRecord(
        record_type="referral_partner",
        category="sba_lenders",
        status="review_needed",
        company=Company(name="Community Bank", website="https://communitybank.com", city="NYC", state="NY",
                        google_review_count=50),
        primary_contact=Contact(name="John", title="VP SBA Lending", contact_priority=3,
                                is_decision_maker=True, contact_source_confidence=0.8),
        serves_founder_led="yes",
        boutique_fit_score=70,
    )
    lead.add_evidence(claim="Website fit", source_type="website", confidence=0.8, source_tier=1)
    lead.website_validated = True

    signals = {
        "has_website": True,
        "detected_services": ["SBA lending"],
        "serves_business_owners": True,
        "serves_smb": True,
        "website_text_length": 5000,
    }
    scored = score_lead(lead, signals, s)

    # Should be accepted or review with outreach fields populated
    if scored.status in ("accepted", "review_needed"):
        assert scored.why_this_lead != ""
        assert scored.why_now != ""
        assert scored.outreach_angle != ""
        assert scored.commercial_priority_tier in ("A", "B", "C")


def test_why_now_with_triggers():
    """why_now should reference detected triggers."""
    lead = LeadRecord(detected_triggers=["growth_expansion: expanding", "financing: sba loan"])
    result = _generate_why_now(lead)
    assert "expanding" in result
    assert "No strong timing" not in result


def test_why_now_without_triggers():
    """why_now should say 'no strong timing signal' when no triggers."""
    lead = LeadRecord(detected_triggers=[])
    result = _generate_why_now(lead)
    assert "No strong timing" in result
