"""Unified lead record combining company, contacts, scoring, and evidence."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.company import Company
from app.models.contact import Contact
from app.models.evidence import Evidence
from app.models.scoring import ScoreBreakdown


class LeadRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    record_type: str = ""               # direct_prospect or referral_partner
    status: str = "review_needed"       # accepted, review_needed, rejected

    # Core entities
    company: Company = Field(default_factory=Company)
    primary_contact: Optional[Contact] = None
    contacts: list[Contact] = Field(default_factory=list)

    # Classification
    category: str = ""                  # sba_lenders, construction_trades, etc.
    subcategory: str = ""
    tags: list[str] = Field(default_factory=list)

    # Evidence chain
    evidence: list[Evidence] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)

    # Scoring
    score: ScoreBreakdown = Field(default_factory=ScoreBreakdown)
    qualification_score: int = 0        # 0-100
    confidence_score: int = 0           # 0-100
    exclusion_reason: str = ""

    # Source hierarchy + acceptance (Phase 1)
    website_validated: bool = False             # True only if website fetched and category fit confirmed
    acceptance_gate_passed: bool = False        # True only if mandatory acceptance conditions met
    acceptance_gate_explanation: str = ""       # Why accepted, reviewed, or rejected
    source_tier_best: int = 3                  # Best (lowest) source tier among all evidence
    source_count: int = 0                      # Number of distinct sources supporting this record
    has_corroboration: bool = False             # True if 2+ independent sources confirm category fit

    # Metadata
    notes: str = ""
    last_verified_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    pipeline_stage: str = "seed"        # seed, classified, enriched, scored, final

    # --- Direct prospect specific ---
    financial_complexity_score: int = 0
    likely_need_signals: list[str] = Field(default_factory=list)
    estimated_fit_for_fractional_cfo: str = ""  # strong, moderate, weak, unclear
    likely_buying_triggers: list[str] = Field(default_factory=list)
    growth_transition_evidence: list[str] = Field(default_factory=list)
    complexity_flags: list[str] = Field(default_factory=list)

    # --- Referral partner specific ---
    referral_likelihood_score: int = 0
    client_overlap_score: int = 0
    seniority_score: int = 0
    network_leverage_score: int = 0
    boutique_fit_score: int = 0
    competing_service_risk_score: int = 0
    likely_referral_type: str = ""      # sba, legal, broker, wealth, cpa, consultant
    serves_founder_led: str = ""        # yes, no, probably, unclear
    serves_right_revenue_band: str = "" # yes, no, probably, unclear

    # --- Outreach intelligence (generated for accepted records) ---
    outreach_priority_tier: str = ""    # A, B, C
    primary_outreach_angle: str = ""
    likely_pain_point: str = ""
    likely_referral_reason: str = ""
    recommended_contact_order: list[str] = Field(default_factory=list)
    mutual_referral_fit: str = ""
    why_this_might_not_be_a_fit: list[str] = Field(default_factory=list)

    # --- Review queue fields ---
    review_evidence_for: list[str] = Field(default_factory=list)
    review_evidence_against: list[str] = Field(default_factory=list)
    review_suggested_next_step: str = ""

    def add_evidence(self, claim: str, source_url: str = "", source_type: str = "",
                     snippet: str = "", confidence: float = 0.5,
                     source_tier: int = 3, extraction_method: str = ""):
        self.evidence.append(Evidence(
            claim=claim,
            source_url=source_url,
            source_type=source_type,
            snippet=snippet,
            confidence=confidence,
            source_tier=source_tier,
            extraction_method=extraction_method,
        ))
        if source_url and source_url not in self.source_urls:
            self.source_urls.append(source_url)
        self._update_source_summary()

    def _update_source_summary(self):
        """Recalculate source_tier_best, source_count, and has_corroboration from evidence."""
        if not self.evidence:
            return
        self.source_tier_best = min(e.source_tier for e in self.evidence)
        distinct_sources = {e.source_type for e in self.evidence if e.source_type}
        self.source_count = len(distinct_sources)
        # Corroboration: 2+ independent source types confirm category-related claims
        category_sources = {e.source_type for e in self.evidence
                           if e.source_type and "category" in e.claim.lower() or "fit" in e.claim.lower()}
        self.has_corroboration = len(category_sources) >= 2 or self.source_count >= 2

    def set_primary_contact(self, contact: Contact):
        self.primary_contact = contact
        if contact not in self.contacts:
            self.contacts.append(contact)

    @property
    def has_decision_maker(self) -> bool:
        return self.primary_contact is not None and self.primary_contact.name != ""

    @property
    def has_website_evidence(self) -> bool:
        return any(e.source_type == "website" for e in self.evidence)

    @property
    def evidence_source_types(self) -> set[str]:
        return {e.source_type for e in self.evidence}
