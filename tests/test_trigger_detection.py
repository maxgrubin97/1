"""Tests for trigger detection in website parser."""

from app.parsers.website_parser import parse_website_signals


def _make_website_data(text: str) -> dict:
    """Helper to create website_data dict with text content."""
    return {
        "all_text": text,
        "home_text": text,
        "about_text": "",
        "services_text": "",
        "meta_description": "",
    }


def test_growth_triggers_detected():
    """Growth/expansion language should be detected."""
    data = _make_website_data(
        "We are expanding our operations and opening a new location in Queens. "
        "Our growing team now serves the entire tri-state area."
    )
    signals = parse_website_signals(data)
    triggers = signals.get("detected_triggers", [])

    assert len(triggers) > 0
    assert any("growth_expansion" in t for t in triggers)


def test_financing_triggers_detected():
    """Financing language should be detected."""
    data = _make_website_data(
        "We help clients secure SBA loan financing and establish a line of credit "
        "for their growing businesses."
    )
    signals = parse_website_signals(data)
    triggers = signals.get("detected_triggers", [])

    assert any("financing" in t for t in triggers)


def test_hiring_triggers_detected():
    """Hiring language should be detected."""
    data = _make_website_data(
        "We're hiring! Join our team and help us build the future. "
        "Check out our open positions on the careers page."
    )
    signals = parse_website_signals(data)
    triggers = signals.get("detected_triggers", [])

    assert any("hiring" in t for t in triggers)


def test_acquisition_triggers_detected():
    """Acquisition/sale language should be detected."""
    data = _make_website_data(
        "Our exit strategy consulting helps business owners prepare for "
        "succession planning and business transition."
    )
    signals = parse_website_signals(data)
    triggers = signals.get("detected_triggers", [])

    assert any("acquisition_sale" in t for t in triggers)


def test_no_triggers_on_plain_text():
    """Plain business text without trigger language should produce no triggers."""
    data = _make_website_data(
        "We are a local accounting firm providing tax preparation and bookkeeping services."
    )
    signals = parse_website_signals(data)
    triggers = signals.get("detected_triggers", [])

    assert len(triggers) == 0


def test_multiple_trigger_types():
    """Text with multiple trigger types should detect all of them."""
    data = _make_website_data(
        "We are expanding to a new location and seeking funding through an SBA loan. "
        "We're hiring for our new office. Our succession plan is in place."
    )
    signals = parse_website_signals(data)
    triggers = signals.get("detected_triggers", [])

    trigger_types = {t.split(":")[0] for t in triggers}
    assert "growth_expansion" in trigger_types
    assert "financing" in trigger_types
    assert "hiring" in trigger_types
    assert "acquisition_sale" in trigger_types
