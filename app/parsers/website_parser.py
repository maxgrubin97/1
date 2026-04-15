"""
Website content parser.

Extracts structured signals from website text:
- What the firm does
- Whether it serves SMBs
- Whether it's boutique or large
- Practice areas / services
- Ownership signals
- Financial complexity signals
- Buying triggers
"""

import logging
import re

from app.utils.text import contains_any

logger = logging.getLogger(__name__)


def parse_website_signals(
    website_data: dict,
    competitor_keywords: list[str] | None = None,
    buying_triggers: list[str] | None = None,
    owner_led_signals: list[str] | None = None,
    complexity_signals: list[str] | None = None,
) -> dict:
    """
    Analyze website content and return structured signals.

    Args:
        website_data: Output from collectors.website.collect_website_data()
        competitor_keywords: Keywords that indicate a direct competitor
        buying_triggers: Keywords suggesting financial need
        owner_led_signals: Keywords suggesting owner-led business
        complexity_signals: Keywords suggesting financial complexity

    Returns:
        Dict of extracted signals with evidence snippets.
    """
    all_text = website_data.get("all_text", "")
    home_text = website_data.get("home_text", "")
    about_text = website_data.get("about_text", "")
    services_text = website_data.get("services_text", "")
    meta = website_data.get("meta_description", "")

    full_text = f"{all_text} {meta}"
    full_lower = full_text.lower()

    signals = {
        "has_website": bool(all_text),
        "website_quality": _assess_website_quality(website_data),

        # Services / practice areas
        "detected_services": [],
        "detected_practice_areas": [],

        # Size signals
        "size_signals": [],
        "is_boutique_likely": None,
        "is_large_likely": None,
        "employee_clues": [],

        # Market signals
        "serves_smb": None,
        "serves_enterprise": None,
        "serves_business_owners": None,
        "client_type_clues": [],

        # Ownership
        "owner_led_signals": [],
        "is_owner_led_likely": None,

        # Complexity / buying triggers
        "complexity_signals_found": [],
        "buying_triggers_found": [],
        "growth_signals": [],

        # Competition risk
        "competitor_signals": [],
        "is_competitor_likely": False,

        # Contact info
        "emails": website_data.get("emails_found", []),
        "phones": website_data.get("phones_found", []),
    }

    # Detect services
    service_patterns = {
        "SBA lending": ["sba", "small business loan", "sba 7", "sba 504"],
        "Commercial lending": ["commercial loan", "commercial lending", "business loan"],
        "M&A advisory": ["mergers", "acquisitions", "m&a", "sell your business", "buy a business"],
        "Business brokerage": ["business broker", "business for sale", "business intermediary"],
        "Corporate law": ["corporate law", "business law", "entity formation", "commercial contracts"],
        "Transaction law": ["transactional", "transaction attorney", "deal counsel"],
        "Tax advisory": ["tax planning", "tax advisory", "tax preparation", "tax compliance"],
        "Wealth management": ["wealth management", "financial planning", "investment advisory", "ria"],
        "Exit planning": ["exit planning", "succession planning", "business transition"],
        "Business valuation": ["business valuation", "company valuation", "fair market value"],
        "CFO services": ["cfo services", "fractional cfo", "outsourced cfo", "virtual cfo"],
        "Accounting": ["accounting", "bookkeeping", "financial statements", "audit"],
        "Insurance": ["insurance", "risk management", "liability coverage"],
    }
    for service, keywords in service_patterns.items():
        if any(kw in full_lower for kw in keywords):
            signals["detected_services"].append(service)

    # Boutique vs. large signals
    large_signals = [
        "global offices", "offices worldwide", "500+ attorney",
        "am law", "fortune 500", "10,000+ employees",
        "publicly traded", "nyse:", "nasdaq:",
    ]
    boutique_signals = [
        "boutique", "small firm", "personalized service",
        "family-owned", "locally owned", "independently owned",
        "hands-on", "personal attention", "close-knit",
    ]
    signals["size_signals"].extend(contains_any(full_text, large_signals))
    signals["is_large_likely"] = bool(signals["size_signals"])
    boutique_found = contains_any(full_text, boutique_signals)
    signals["is_boutique_likely"] = bool(boutique_found) or not signals["is_large_likely"]

    # Employee count clues
    emp_pattern = r"(\d{1,4})\+?\s*(?:employees|team members|professionals|attorneys|staff)"
    for match in re.finditer(emp_pattern, full_lower):
        signals["employee_clues"].append(match.group(0))

    # SMB / business owner signals
    smb_signals = [
        "small business", "business owners", "entrepreneurs",
        "privately held", "family business", "founder",
        "owner-operated", "growing businesses", "startups",
    ]
    enterprise_signals = [
        "enterprise", "fortune 500", "large corporation",
        "multinational", "institutional", "publicly traded",
    ]
    smb_found = contains_any(full_text, smb_signals)
    ent_found = contains_any(full_text, enterprise_signals)
    signals["serves_smb"] = bool(smb_found)
    signals["serves_enterprise"] = bool(ent_found)
    signals["serves_business_owners"] = bool(
        contains_any(full_text, ["business owner", "entrepreneur", "founder"])
    )
    signals["client_type_clues"] = smb_found + ent_found

    # Owner-led signals
    if owner_led_signals:
        found = contains_any(full_text, owner_led_signals)
        signals["owner_led_signals"] = found
        signals["is_owner_led_likely"] = len(found) >= 2

    # Complexity signals
    if complexity_signals:
        signals["complexity_signals_found"] = contains_any(full_text, complexity_signals)

    # Buying triggers
    if buying_triggers:
        signals["buying_triggers_found"] = contains_any(full_text, buying_triggers)

    # Growth signals
    growth_kw = ["growing", "expansion", "new location", "hiring", "scaling", "acquisition"]
    signals["growth_signals"] = contains_any(full_text, growth_kw)

    # Competition risk
    if competitor_keywords:
        signals["competitor_signals"] = contains_any(full_text, competitor_keywords)
        signals["is_competitor_likely"] = len(signals["competitor_signals"]) >= 2

    return signals


def _assess_website_quality(website_data: dict) -> str:
    """Rate website quality as high/medium/low."""
    text_len = len(website_data.get("all_text", ""))
    pages = len(website_data.get("pages_fetched", []))
    has_meta = bool(website_data.get("meta_description"))

    if text_len > 3000 and pages >= 3 and has_meta:
        return "high"
    if text_len > 500 and pages >= 1:
        return "medium"
    return "low"
