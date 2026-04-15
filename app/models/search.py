"""Search run metadata model."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SearchRun(BaseModel):
    id: str = ""
    category: str = ""
    geography: str = ""
    query: str = ""
    source: str = ""                    # google_maps, linkedin_public, website, etc.
    results_found: int = 0
    results_accepted: int = 0
    results_rejected: int = 0
    results_review: int = 0
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    error: str = ""
