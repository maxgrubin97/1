"""Scoring data models."""

from pydantic import BaseModel, Field


class ScoreBreakdown(BaseModel):
    """Transparent, machine-readable scoring with rationale."""

    # Generic dimension scores (filled by the appropriate scorer)
    dimensions: dict[str, int] = Field(default_factory=dict)

    # Total qualification score (0-100)
    total: int = 0

    # Human-readable reasons why this scored well or poorly
    reasons: list[str] = Field(default_factory=list)

    # Human-readable reasons for any penalties applied
    penalties: list[str] = Field(default_factory=list)

    def to_summary(self) -> dict:
        return {
            "qualification_score": self.total,
            "score_breakdown": self.dimensions,
            "why_this_scored_well": self.reasons,
            "penalties_applied": self.penalties,
        }
