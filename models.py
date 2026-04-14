"""Data models for scraped leads."""

from dataclasses import dataclass, asdict, field
from typing import Optional


@dataclass
class Lead:
    # Basic contact info
    name: str = ""
    title: str = ""
    company: str = ""
    location: str = ""
    linkedin_url: str = ""
    website: str = ""
    phone: str = ""
    email: str = ""

    # Company details
    company_size: str = ""
    industry: str = ""
    revenue_estimate: str = ""
    gmaps_rating: str = ""
    gmaps_review_count: str = ""
    gmaps_address: str = ""

    # Enrichment
    company_description: str = ""
    role_type: str = ""  # executive, finance-leader, operations-leader, etc.
    funding_stage: str = ""
    year_founded: str = ""
    email_guess: str = ""

    # Source tracking
    source: str = ""  # linkedin, google_maps

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def is_decision_maker(self) -> bool:
        dm_keywords = [
            "ceo", "cfo", "coo", "cto", "founder", "co-founder", "owner",
            "president", "partner", "principal", "managing director",
            "general manager", "director", "vp", "vice president",
            "head of finance", "head of operations",
        ]
        title_lower = self.title.lower()
        return any(kw in title_lower for kw in dm_keywords)

    def merge_from(self, other: "Lead"):
        """Merge non-empty fields from another lead into this one."""
        for f in self.__dataclass_fields__:
            other_val = getattr(other, f)
            self_val = getattr(self, f)
            if other_val and not self_val:
                setattr(self, f, other_val)


def classify_role(title: str) -> str:
    """Classify a job title into a role category."""
    t = title.lower()
    if any(kw in t for kw in ["ceo", "chief executive", "founder", "co-founder", "owner", "president"]):
        return "executive"
    if any(kw in t for kw in ["cfo", "chief financial", "finance director", "vp finance", "controller", "head of finance"]):
        return "finance-leader"
    if any(kw in t for kw in ["coo", "chief operating", "operations director", "vp operations", "head of operations"]):
        return "operations-leader"
    if any(kw in t for kw in ["cto", "chief technology", "vp engineering", "head of engineering"]):
        return "tech-leader"
    if any(kw in t for kw in ["director", "vp", "vice president", "head of", "managing director", "partner", "principal"]):
        return "senior-management"
    if any(kw in t for kw in ["manager", "lead"]):
        return "management"
    return "other"
