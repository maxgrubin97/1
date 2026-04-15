"""Tests for scoring logic."""

from app.scorers.scorer import score_lead
from app.config.settings import Settings


def test_referral_partner_scoring(sample_referral_lead, settings):
    signals = {
        "has_website": True,
        "detected_services": ["SBA lending", "Commercial lending"],
        "serves_smb": True,
        "serves_business_owners": True,
        "is_boutique_likely": True,
        "is_large_likely": False,
        "serves_enterprise": False,
        "competitor_signals": [],
        "is_competitor_likely": False,
        "complexity_signals_found": [],
        "buying_triggers_found": [],
        "owner_led_signals": [],
        "is_owner_led_likely": False,
        "growth_signals": [],
        "employee_clues": [],
    }
    lead = score_lead(sample_referral_lead, signals, settings)
    assert lead.qualification_score > 0
    assert lead.confidence_score > 0
    assert lead.score.dimensions
    assert len(lead.score.reasons) > 0
    assert lead.outreach_priority_tier in ("A", "B", "C")


def test_direct_prospect_scoring(sample_prospect_lead, settings):
    signals = {
        "has_website": True,
        "detected_services": [],
        "serves_smb": False,
        "serves_business_owners": False,
        "is_boutique_likely": True,
        "is_large_likely": False,
        "serves_enterprise": False,
        "competitor_signals": [],
        "is_competitor_likely": False,
        "complexity_signals_found": ["job costing", "bonding", "multiple crews"],
        "buying_triggers_found": ["growing", "expansion"],
        "owner_led_signals": ["owner", "founded"],
        "is_owner_led_likely": True,
        "growth_signals": ["growing"],
        "employee_clues": ["45 employees"],
    }
    lead = score_lead(sample_prospect_lead, signals, settings)
    assert lead.qualification_score > 0
    assert lead.estimated_fit_for_fractional_cfo in ("strong", "moderate", "weak", "unclear")
    assert lead.financial_complexity_score > 0


def test_high_quality_scores_higher(settings):
    """A lead with strong signals should score higher than one without."""
    from app.models import LeadRecord
    from app.models.company import Company
    from app.models.contact import Contact

    strong = LeadRecord(
        record_type="direct_prospect",
        category="construction_trades",
        company=Company(name="Strong Corp", state="NY", google_review_count=150),
        primary_contact=Contact(name="Owner", title="Founder", contact_priority=1, is_decision_maker=True),
    )
    weak = LeadRecord(
        record_type="direct_prospect",
        category="construction_trades",
        company=Company(name="Weak Corp", state="OH", google_review_count=2),
    )

    strong_signals = {
        "has_website": True, "complexity_signals_found": ["job costing", "bonding"],
        "buying_triggers_found": ["growing"], "is_owner_led_likely": True,
        "growth_signals": ["expansion"], "employee_clues": ["30 employees"],
        "detected_services": [], "serves_smb": False, "serves_business_owners": False,
        "is_boutique_likely": True, "is_large_likely": False, "serves_enterprise": False,
        "competitor_signals": [], "is_competitor_likely": False, "owner_led_signals": ["owner"],
    }
    weak_signals = {
        "has_website": False, "complexity_signals_found": [],
        "buying_triggers_found": [], "is_owner_led_likely": False,
        "growth_signals": [], "employee_clues": [],
        "detected_services": [], "serves_smb": False, "serves_business_owners": False,
        "is_boutique_likely": None, "is_large_likely": None, "serves_enterprise": False,
        "competitor_signals": [], "is_competitor_likely": False, "owner_led_signals": [],
    }

    strong = score_lead(strong, strong_signals, settings)
    weak = score_lead(weak, weak_signals, settings)

    assert strong.qualification_score > weak.qualification_score
