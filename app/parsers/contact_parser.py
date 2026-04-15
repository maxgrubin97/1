"""
Contact extraction and ranking.

Extracts contacts from website team pages and ranks them by
seniority and relevance to the category.
"""

import logging
import re

from bs4 import BeautifulSoup

from app.models.contact import Contact
from app.utils.text import classify_title_seniority

logger = logging.getLogger(__name__)


def extract_contacts_from_team_page(html: str, source_url: str = "") -> list[Contact]:
    """
    Parse a team/people/attorneys page and extract contacts.

    Looks for patterns like:
    - Name + Title in structured elements (cards, list items)
    - Name patterns followed by role descriptions
    """
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    contacts = []
    seen_names = set()

    # Strategy 1: Look for structured team cards/items
    for selector in [
        "div.team-member", "div.person", "div.staff-member",
        "div.bio", "div.attorney", "div.partner",
        "li.team-member", "li.person",
        "article.team-member",
        "div[class*='team']", "div[class*='member']",
        "div[class*='person']", "div[class*='staff']",
    ]:
        items = soup.select(selector)
        if not items:
            continue
        for item in items:
            contact = _parse_team_card(item, source_url)
            if contact and contact.name not in seen_names:
                seen_names.add(contact.name)
                contacts.append(contact)

    # Strategy 2: Look for h2/h3 + paragraph patterns
    if not contacts:
        for heading_tag in ["h2", "h3", "h4"]:
            for heading in soup.find_all(heading_tag):
                name_text = heading.get_text(strip=True)
                if _looks_like_person_name(name_text) and name_text not in seen_names:
                    # Look for title in next sibling or parent
                    title = ""
                    next_el = heading.find_next_sibling()
                    if next_el:
                        title_text = next_el.get_text(strip=True)[:100]
                        if _looks_like_title(title_text):
                            title = title_text

                    if title:
                        seniority, role_cat, priority = classify_title_seniority(title)
                        contact = Contact(
                            name=name_text,
                            title=title,
                            seniority_level=seniority,
                            role_category=role_cat,
                            contact_priority=priority,
                            is_decision_maker=(priority <= 3),
                            source="website",
                        )
                        seen_names.add(name_text)
                        contacts.append(contact)

    # Sort by priority
    contacts.sort(key=lambda c: c.contact_priority)
    return contacts


def _parse_team_card(element, source_url: str) -> Contact | None:
    """Parse a team member card/div."""
    # Try to find name (usually in a heading or strong tag)
    name = ""
    for tag in ["h2", "h3", "h4", "h5", "strong", "b", "a"]:
        el = element.find(tag)
        if el and _looks_like_person_name(el.get_text(strip=True)):
            name = el.get_text(strip=True)
            break

    if not name:
        return None

    # Try to find title
    title = ""
    for tag in ["p", "span", "div", "em"]:
        els = element.find_all(tag)
        for el in els:
            text = el.get_text(strip=True)[:100]
            if _looks_like_title(text) and text != name:
                title = text
                break
        if title:
            break

    if not title:
        # Check class-based patterns
        for cls in ["title", "position", "role", "designation"]:
            el = element.find(attrs={"class": re.compile(cls, re.I)})
            if el:
                title = el.get_text(strip=True)[:100]
                break

    # Try to find email
    email = ""
    email_link = element.find("a", href=re.compile(r"mailto:"))
    if email_link:
        email = email_link.get("href", "").replace("mailto:", "").strip()

    # Try to find LinkedIn
    linkedin = ""
    li_link = element.find("a", href=re.compile(r"linkedin\.com"))
    if li_link:
        linkedin = li_link.get("href", "")

    seniority, role_cat, priority = classify_title_seniority(title)

    return Contact(
        name=name,
        title=title,
        email=email,
        linkedin_url=linkedin,
        seniority_level=seniority,
        role_category=role_cat,
        contact_priority=priority,
        is_decision_maker=(priority <= 3),
        source="website",
    )


def _looks_like_person_name(text: str) -> bool:
    """Heuristic: does this text look like a person's name?"""
    if not text or len(text) < 3 or len(text) > 60:
        return False
    # Should have 2-4 words, mostly capitalized
    words = text.split()
    if len(words) < 2 or len(words) > 5:
        return False
    # Check for common non-name patterns
    lower = text.lower()
    non_names = [
        "about us", "our team", "meet the", "contact us", "learn more",
        "read more", "view profile", "see all", "get in touch",
    ]
    if any(nn in lower for nn in non_names):
        return False
    # Most words should start with uppercase
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
    # Already sorted by priority from classify_title_seniority
    return sorted(contacts, key=lambda c: c.contact_priority)
