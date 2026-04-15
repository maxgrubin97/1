"""Contact data model."""

import uuid
from typing import Optional

from pydantic import BaseModel, Field


class Contact(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company_id: str = ""
    name: str = ""
    title: str = ""
    email: str = ""
    email_guess: str = ""
    phone: str = ""
    linkedin_url: str = ""
    seniority_level: str = ""       # executive, senior, mid, junior
    role_category: str = ""         # founder, partner, director, manager, etc.
    is_decision_maker: bool = False
    contact_priority: int = 99      # 1 = highest priority
    source: str = ""                # google_maps, linkedin, website, csv_import
    person_description: str = ""

    # --- Source trust fields (Phase 1) ---
    email_status: str = "unavailable"       # verified | generic | guessed | unavailable
    contact_source: str = ""                # website_team_page | website_about | linkedin_public | csv_import | google_maps
    contact_source_confidence: float = 0.0  # 0.0-1.0
    extraction_method: str = ""             # structured_markup | team_card | page_text | search_snippet | manual
    source_page_url: str = ""               # exact URL where this contact was found
    source_snippet: str = ""                # text snippet that evidences this contact
