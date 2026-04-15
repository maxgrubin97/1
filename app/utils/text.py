"""Text normalization and matching utilities."""

import re
from urllib.parse import urlparse


def normalize_company_name(name: str) -> str:
    """Normalize a company name for deduplication."""
    n = name.lower().strip()
    # Remove common suffixes
    for suffix in [
        ", llc", " llc", ", inc", " inc", ", ltd", " ltd", ", corp", " corp",
        ", llp", " llp", ", pllc", " pllc", ", pc", " pc", ", p.c.", " p.c.",
        ", pa", " p.a.", ", dba", " co.", ", co", " company",
        " & associates", " and associates", " associates",
        " group", " partners", " advisors", " advisory",
    ]:
        if n.endswith(suffix):
            n = n[: -len(suffix)]
    # Remove punctuation and extra whitespace
    n = re.sub(r"[^\w\s]", "", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def normalize_domain(url: str) -> str:
    """Extract and normalize domain from URL."""
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    domain = (parsed.hostname or "").lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def normalize_phone(phone: str) -> str:
    """Normalize phone number to digits only."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def extract_state_from_address(address: str) -> str:
    """Try to extract a US state abbreviation from an address."""
    states = {
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
        "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
        "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
        "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
        "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    }
    match = re.search(r"\b([A-Z]{2})\b", address)
    if match and match.group(1) in states:
        return match.group(1)
    return ""


def extract_zip_from_address(address: str) -> str:
    """Try to extract a ZIP code from an address."""
    match = re.search(r"\b(\d{5})(?:-\d{4})?\b", address)
    return match.group(1) if match else ""


def extract_city_from_address(address: str) -> str:
    """Try to extract city from a formatted address like '123 Main St, Melville, NY 11747'."""
    parts = [p.strip() for p in address.split(",")]
    if len(parts) >= 3:
        return parts[-2].strip().split()[0] if parts[-2].strip() else ""
    if len(parts) == 2:
        return parts[0].strip()
    return ""


def fuzzy_name_match(a: str, b: str) -> bool:
    """Check if two company names are fuzzy matches."""
    na = normalize_company_name(a)
    nb = normalize_company_name(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    # Check if one contains the other (for cases like "ABC" vs "ABC Electric")
    if len(na) > 3 and len(nb) > 3:
        if na in nb or nb in na:
            return True
    return False


def contains_any(text: str, keywords: list[str], case_sensitive: bool = False) -> list[str]:
    """Return which keywords are found in text."""
    if not case_sensitive:
        text = text.lower()
        return [kw for kw in keywords if kw.lower() in text]
    return [kw for kw in keywords if kw in text]


def classify_title_seniority(title: str) -> tuple[str, str, int]:
    """
    Classify a job title into (seniority_level, role_category, priority).

    Returns:
        seniority_level: executive, senior, mid, junior
        role_category: founder, partner, director, manager, associate, other
        priority: 1 (highest) to 99 (lowest)
    """
    t = title.lower()

    if any(kw in t for kw in ["founder", "co-founder", "owner", "principal", "proprietor"]):
        return "executive", "founder", 1
    if any(kw in t for kw in ["managing partner", "name partner"]):
        return "executive", "partner", 1
    if any(kw in t for kw in ["ceo", "chief executive", "president"]):
        return "executive", "founder", 1
    if any(kw in t for kw in ["coo", "chief operating", "cfo", "chief financial"]):
        return "executive", "c-suite", 2
    if any(kw in t for kw in ["partner", "of counsel"]):
        return "senior", "partner", 2
    if any(kw in t for kw in ["managing director", "general manager"]):
        return "senior", "director", 2
    if any(kw in t for kw in [
        "director", "vp", "vice president", "svp", "senior vice president",
        "evp", "executive vice president",
    ]):
        return "senior", "director", 3
    if any(kw in t for kw in [
        "sba lender", "relationship manager", "business development officer",
        "commercial loan officer", "senior advisor", "senior wealth advisor",
        "m&a advisor", "business broker", "business intermediary",
    ]):
        return "senior", "specialist", 3
    if any(kw in t for kw in ["manager", "lead", "senior associate", "senior"]):
        return "mid", "manager", 4
    if any(kw in t for kw in ["associate", "advisor", "financial advisor", "wealth advisor"]):
        return "mid", "associate", 5
    if any(kw in t for kw in [
        "analyst", "coordinator", "assistant", "intern", "paralegal",
        "clerk", "receptionist", "secretary",
    ]):
        return "junior", "support", 99

    return "mid", "other", 6
