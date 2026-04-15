"""Tests for configuration loading."""

from app.config.settings import Settings


def test_settings_loads():
    s = Settings()
    assert s.geographies is not None
    assert s.categories is not None
    assert s.scoring_weights is not None
    assert s.keywords is not None


def test_categories_exist(settings):
    rp = settings.get_referral_partner_keys()
    dp = settings.get_direct_prospect_keys()
    assert "sba_lenders" in rp
    assert "business_brokers" in rp
    assert "boutique_corporate_attorneys" in rp
    assert "construction_trades" in dp
    assert "healthcare_practices" in dp


def test_category_lookup(settings):
    cat = settings.get_category("sba_lenders")
    assert cat["label"] == "SBA Lenders"
    assert cat["record_type"] == "referral_partner"
    assert len(cat["search_queries"]) > 0


def test_locations(settings):
    t1 = settings.get_location_names(["tier_1"])
    assert len(t1) >= 5
    assert "Nassau County, NY" in t1
    assert "Manhattan, NY" in t1


def test_scoring_weights(settings):
    dp_weights = settings.get_scoring_weights("direct_prospect")
    rp_weights = settings.get_scoring_weights("referral_partner")
    assert sum(dp_weights.values()) == 100
    assert sum(rp_weights.values()) == 100


def test_thresholds(settings):
    t = settings.get_thresholds()
    assert t["auto_accept_min"] == 80
    assert t["auto_reject_max"] == 30
    assert t["confidence_floor"] == 40


def test_keywords(settings):
    titles = settings.get_high_priority_titles()
    assert "Founder" in titles
    assert "Managing Partner" in titles

    competitors = settings.get_competitor_keywords()
    assert "fractional CFO" in competitors
