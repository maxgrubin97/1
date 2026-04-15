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
