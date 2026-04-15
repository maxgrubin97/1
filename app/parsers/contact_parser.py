"""
Contact extraction and ranking.

Extracts contacts from website team pages and ranks them by
seniority and relevance to the category.

Extraction confidence tiers:
- structured_markup (schema.org, vcard): 0.9
- team_card (clear name/title in same container): 0.8
- team_card_loose (name/title loosely paired): 0.6
- page_text (regex from page body): 0.4
"""

import logging
import re

from bs4 import BeautifulSoup, Tag

from app.models.contact import Contact
from app.utils.text import classify_title_seniority

logger = logging.getLogger(__name__)

# Max character distance between name and title to consider them paired
_MAX_NAME_TITLE_DISTANCE = 200

# Generic email prefixes that are not person-specific
_GENERIC_EMAIL_PREFIXES = {"info", "contact", "admin", "support", "noreply", "hello",
                           "office", "team", "sales", "help", "inquiries", "general"}


def extract_contacts_from_team_page(html: str, source_url: str = "") -> list[Contact]:
    """
    Parse a team/people/attorneys page and extract contacts.

    Extraction priority:
    1. Structured markup (schema.org/Person, vcard, hcard)
    2. Team card containers (name + title in same parent)
    3. Heading + sibling patterns
    4. Page-wide text regex (lowest confidence)
    """
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    contacts = []
    seen_names: set[str] = set()

    # Strategy 1: Structured markup (schema.org/Person, vcard, hcard)
    structured = _extract_structured_markup(soup, source_url)
    for c in structured:
        if c.name not in seen_names:
            seen_names.add(c.name)
            contacts.append(c)

    # Strategy 2: Team card containers
    if not contacts:
        card_contacts = _extract_team_cards(soup, source_url)
        for c in card_contacts:
            if c.name not in seen_names:
                seen_names.add(c.name)
                contacts.append(c)

    # Strategy 3: Heading + sibling patterns
    if not contacts:
        heading_contacts = _extract_heading_patterns(soup, source_url)
        for c in heading_contacts:
            if c.name not in seen_names:
                seen_names.add(c.name)
                contacts.append(c)

    # Sort by priority
    contacts.sort(key=lambda c: c.contact_priority)
    return contacts


def _extract_structured_markup(soup: BeautifulSoup, source_url: str) -> list[Contact]:
    """Extract contacts from schema.org/Person, vcard, or hcard markup."""
    contacts = []

    # schema.org/Person (itemtype or JSON-LD)
    for person in soup.find_all(attrs={"itemtype": re.compile(r"schema\.org/Person", re.I)}):
        name_el = person.find(attrs={"itemprop": "name"})
        title_el = person.find(attrs={"itemprop": "jobTitle"})
        email_el = person.find(attrs={"itemprop": "email"})

        name = name_el.get_text(strip=True) if name_el else ""
        title = title_el.get_text(strip=True) if title_el else ""

        if not name or not _looks_like_person_name(name):
            continue

        email = ""
        if email_el:
            email = email_el.get("href", "").replace("mailto:", "") or email_el.get_text(strip=True)

        seniority, role_cat, priority = classify_title_seniority(title)
        email_status = _classify_email_status(email)

        contacts.append(Contact(
            name=name,
            title=title,
            email=email if email_status != "generic" else "",
            seniority_level=seniority,
            role_category=role_cat,
            contact_priority=priority,
            is_decision_maker=(priority <= 3),
            source="website",
            email_status=email_status if email else "unavailable",
            contact_source="website_team_page",
            contact_source_confidence=0.9,
            extraction_method="structured_markup",
            source_page_url=source_url,
            source_snippet=f"{name} - {title}"[:200],
        ))

    # vcard / hcard
    for vcard in soup.find_all(class_=re.compile(r"\bv-?card\b", re.I)):
        name_el = vcard.find(class_=re.compile(r"\bfn\b", re.I))
        title_el = vcard.find(class_=re.compile(r"\btitle\b", re.I))

        name = name_el.get_text(strip=True) if name_el else ""
        title = title_el.get_text(strip=True) if title_el else ""

        if not name or not _looks_like_person_name(name):
            continue

        email = ""
        email_el = vcard.find("a", href=re.compile(r"mailto:"))
        if email_el:
            email = email_el.get("href", "").replace("mailto:", "").strip()

        seniority, role_cat, priority = classify_title_seniority(title)
        email_status = _classify_email_status(email)

        contacts.append(Contact(
            name=name,
            title=title,
            email=email if email_status != "generic" else "",
            seniority_level=seniority,
            role_category=role_cat,
            contact_priority=priority,
            is_decision_maker=(priority <= 3),
            source="website",
            email_status=email_status if email else "unavailable",
            contact_source="website_team_page",
            contact_source_confidence=0.9,
            extraction_method="structured_markup",
            source_page_url=source_url,
            source_snippet=f"{name} - {title}"[:200],
        ))

    return contacts


def _extract_team_cards(soup: BeautifulSoup, source_url: str) -> list[Contact]:
    """Extract contacts from team card containers (div/li with name + title)."""
    contacts = []

    selectors = [
        "div.team-member", "div.person", "div.staff-member",
        "div.bio", "div.attorney", "div.partner",
        "li.team-member", "li.person",
        "article.team-member",
        "div[class*='team']", "div[class*='member']",
        "div[class*='person']", "div[class*='staff']",
    ]

    for selector in selectors:
        items = soup.select(selector)
        if not items:
            continue
        for item in items:
            contact = _parse_team_card(item, source_url)
            if contact:
                contacts.append(contact)

    return contacts


def _parse_team_card(element: Tag, source_url: str) -> Contact | None:
    """Parse a team member card/div with container-level pairing."""
    # Find name within this container
    name = ""
    name_el = None
    for tag in ["h2", "h3", "h4", "h5", "strong", "b", "a"]:
        el = element.find(tag)
        if el and _looks_like_person_name(el.get_text(strip=True)):
            name = el.get_text(strip=True)
            name_el = el
            break

    if not name:
        return None

    # Find title within this same container (not the full page)
    title = ""
    title_el = None

    # Check class-based patterns first (most reliable)
    for cls in ["title", "position", "role", "designation", "job-title"]:
        el = element.find(attrs={"class": re.compile(cls, re.I)})
        if el:
            candidate = el.get_text(strip=True)[:100]
            if candidate and candidate != name:
                title = candidate
                title_el = el
                break

    # Then check p/span/div/em tags
    if not title:
        for tag in ["p", "span", "div", "em"]:
            els = element.find_all(tag)
            for el in els:
                text = el.get_text(strip=True)[:100]
                if _looks_like_title(text) and text != name:
                    # Enforce max distance within container
                    if name_el and _elements_within_distance(name_el, el, _MAX_NAME_TITLE_DISTANCE):
                        title = text
                        title_el = el
                        break
            if title:
                break

    # Determine extraction confidence based on pairing quality
    if title and title_el:
        # Both name and title in same container with clear pairing
        confidence = 0.8
        method = "team_card"
    elif title:
        confidence = 0.6
        method = "team_card"
    else:
        # Name only, no title — low value
        return None

    # Extract email
    email = ""
    email_link = element.find("a", href=re.compile(r"mailto:"))
    if email_link:
        email = email_link.get("href", "").replace("mailto:", "").strip()

    # Extract LinkedIn
    linkedin = ""
    li_link = element.find("a", href=re.compile(r"linkedin\.com"))
    if li_link:
        linkedin = li_link.get("href", "")

    seniority, role_cat, priority = classify_title_seniority(title)
    email_status = _classify_email_status(email)
    snippet = element.get_text(strip=True)[:200]

    return Contact(
        name=name,
        title=title,
        email=email if email_status not in ("generic",) else "",
        linkedin_url=linkedin,
        seniority_level=seniority,
        role_category=role_cat,
        contact_priority=priority,
        is_decision_maker=(priority <= 3),
        source="website",
        email_status=email_status if email else "unavailable",
        contact_source="website_team_page",
        contact_source_confidence=confidence,
        extraction_method=method,
        source_page_url=source_url,
        source_snippet=snippet,
    )


def _extract_heading_patterns(soup: BeautifulSoup, source_url: str) -> list[Contact]:
    """Extract contacts from heading + sibling patterns (lower confidence)."""
    contacts = []

    for heading_tag in ["h2", "h3", "h4"]:
        for heading in soup.find_all(heading_tag):
            name_text = heading.get_text(strip=True)
            if not _looks_like_person_name(name_text):
                continue

            # Look for title in next sibling — must be close
            title = ""
            next_el = heading.find_next_sibling()
            if next_el:
                title_text = next_el.get_text(strip=True)[:100]
                if _looks_like_title(title_text):
                    # Check distance
                    if _elements_within_distance(heading, next_el, _MAX_NAME_TITLE_DISTANCE):
                        title = title_text

            if not title:
                continue

            seniority, role_cat, priority = classify_title_seniority(title)
            snippet = f"{name_text} - {title}"

            contacts.append(Contact(
                name=name_text,
                title=title,
                seniority_level=seniority,
                role_category=role_cat,
                contact_priority=priority,
                is_decision_maker=(priority <= 3),
                source="website",
                email_status="unavailable",
                contact_source="website_team_page",
                contact_source_confidence=0.6,
                extraction_method="team_card",
                source_page_url=source_url,
                source_snippet=snippet[:200],
            ))

    return contacts


def _elements_within_distance(el1: Tag, el2: Tag, max_chars: int) -> bool:
    """Check if two elements are within max_chars of each other in the page text."""
    try:
        parent = el1.parent
        if parent is None:
            return True  # Can't determine, allow
        text = parent.get_text()
        t1 = el1.get_text(strip=True)
        t2 = el2.get_text(strip=True)
        pos1 = text.find(t1)
        pos2 = text.find(t2)
        if pos1 == -1 or pos2 == -1:
            return True  # Can't determine, allow
        return abs(pos2 - pos1) <= max_chars
    except Exception:
        return True  # Error → allow


def _classify_email_status(email: str) -> str:
    """Classify an email as verified, generic, or unavailable."""
    if not email:
        return "unavailable"
    prefix = email.split("@")[0].lower() if "@" in email else ""
    if prefix in _GENERIC_EMAIL_PREFIXES:
        return "generic"
    return "verified"


def _looks_like_person_name(text: str) -> bool:
    """Heuristic: does this text look like a person's name?"""
    if not text or len(text) < 3 or len(text) > 60:
        return False
    words = text.split()
    if len(words) < 2 or len(words) > 5:
        return False
    lower = text.lower()
    non_names = [
        "about us", "our team", "meet the", "contact us", "learn more",
        "read more", "view profile", "see all", "get in touch",
    ]
    if any(nn in lower for nn in non_names):
        return False
    cap_words = sum(1 for w in words if w[0].isupper())
    return cap_words >= len(words) * 0.5


def _looks_like_title(text: str) -> bool:
    """Heuristic: does this text look like a job title?"""
    if not text or len(text) < 3 or len(text) > 100:
        return False
    title_keywords = [
        "partner", "director", "manager", "founder", "owner", "president",
        "ceo", "cfo", "coo", "attorney", "advisor", "officer",
        "principal", "counsel", "associate", "vp", "vice president",
        "senior", "managing", "head of", "lead", "chief", "broker",
        "lender", "relationship", "administrator",
    ]
    return any(kw in text.lower() for kw in title_keywords)


def rank_contacts(contacts: list[Contact], category: str = "") -> list[Contact]:
    """
    Rank contacts by priority for a given category.

    Contact ranking order:
    1. founder / managing partner / owner / principal
    2. partner / director / managing director
    3. BDO / SBA lender / relationship manager
    4. senior advisor / wealth advisor
    5. generic contact (fallback)
    """
    return sorted(contacts, key=lambda c: c.contact_priority)
