"""Company data model."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Company(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    name_normalized: str = ""
    website: str = ""
    website_domain: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    google_maps_url: str = ""
    google_place_id: str = ""
    linkedin_company_url: str = ""
    description: str = ""
    primary_industry: str = ""
    secondary_industry: str = ""
    employee_count_estimate: str = ""
    revenue_estimate: str = ""
    number_of_locations: int = 0
    google_rating: Optional[float] = None
    google_review_count: int = 0
    years_in_business_estimate: str = ""
    ownership_type: str = ""
    is_founder_led: Optional[bool] = None
    is_smb_likely: Optional[bool] = None
    business_status: str = "active"
    service_area: str = ""
    google_categories: list[str] = Field(default_factory=list)
    collected_at: Optional[datetime] = None
