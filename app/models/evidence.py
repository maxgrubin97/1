"""Evidence data model for auditability."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    claim: str
    source_url: str = ""
    source_type: str = ""           # website, google_maps, linkedin, directory, csv_import
    snippet: str = ""
    confidence: float = 0.0         # 0.0 to 1.0
    collected_at: datetime = Field(default_factory=datetime.utcnow)

    # --- Source hierarchy fields (Phase 1) ---
    source_tier: int = 3            # 1=authoritative, 2=high-quality, 3=discovery
    extraction_method: str = ""     # how the claim was extracted
