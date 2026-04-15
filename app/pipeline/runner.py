"""
Pipeline runner — orchestrates the staged collection strategy.

Stages:
1. SEED DISCOVERY — Google Maps + public search queries
2. FIRST-PASS CLASSIFICATION — light filtering, hard exclusions
3. ENRICHMENT — website + contacts (ONLY for promising records)
4. SCORING — category-specific scoring with outreach intelligence
5. DEDUPLICATION — merge duplicates
6. FINAL FILTER — apply thresholds, assign tiers
7. EXPORT — save to database and optionally export files

Precision-first: default 25 per category per geography.
"""

import logging
import uuid
from datetime import datetime
from typing import Callable, Optional

from app.config.settings import Settings, get_settings
from app.models import LeadRecord, SearchRun
from app.collectors.google_maps import collect_from_google_maps
from app.collectors.query_generator import generate_queries
from app.classifiers.classifier import classify_lead
from app.enrichers.enricher import enrich_lead
from app.scorers.scorer import score_lead
from app.dedupe.deduplicator import deduplicate
from app.storage.database import Database
from app.utils.text import normalize_domain

logger = logging.getLogger(__name__)


class PipelineRunner:
    """Orchestrates the full lead sourcing pipeline."""

    def __init__(
        self,
        settings: Settings | None = None,
        db: Database | None = None,
        progress_callback: Callable | None = None,
    ):
        self.settings = settings or get_settings()
        self.db = db or Database(self.settings.database_path)
        self.progress_callback = progress_callback

        # Load whitelist/blacklist
        self.whitelist = self.db.load_domain_list("data/always_include_domains.csv")
        self.blacklist = self.db.load_domain_list("data/always_exclude_domains.csv")
        self.competitors = self.db.load_domain_list("data/competitor_domains.csv")

    def _emit(self, stage: str, message: str, **kwargs):
        """Emit a progress event."""
        logger.info(f"[{stage}] {message}")
        if self.progress_callback:
            self.progress_callback(stage=stage, message=message, **kwargs)

    def run(
        self,
        category: str,
        locations: list[str] | None = None,
        limit: int = 25,
        sources: list[str] | None = None,
        enrich_contacts: bool = True,
        strict_mode: bool = False,
    ) -> dict:
        """
        Run the full pipeline for a category + geography.

        Args:
            category: Category key (e.g., 'sba_lenders', 'construction_trades')
            locations: Location names to search. Defaults to Tier 1.
            limit: Max records to return per category per geography.
            sources: Which sources to use ('google_maps', 'web_search').
            enrich_contacts: Whether to do contact enrichment.
            strict_mode: If True, only return accepted records.

        Returns:
            Dict with run stats and lead IDs.
        """
        if sources is None:
            sources = ["google_maps"]

        if locations is None:
            locations = self.settings.get_location_names(["tier_1"])

        # Create search run
        run_id = str(uuid.uuid4())
        run = SearchRun(
            id=run_id,
            category=category,
            geography=", ".join(locations[:3]) + ("..." if len(locations) > 3 else ""),
            source=", ".join(sources),
            started_at=datetime.utcnow(),
        )

        self._emit("start", f"Starting pipeline: {category} in {len(locations)} locations (limit {limit})")

        stats = {
            "run_id": run_id,
            "category": category,
            "discovered": 0,
            "classified": 0,
            "enriched": 0,
            "accepted": 0,
            "review": 0,
            "rejected": 0,
            "duplicates_merged": 0,
            "lead_ids": [],
        }

        all_leads: list[LeadRecord] = []

        # ============================================================
        # STAGE 1: SEED DISCOVERY
        # ============================================================
        self._emit("discovering", "Discovering candidate businesses...")

        if "google_maps" in sources and self.settings.gmaps_api_key:
            queries = generate_queries(
                category, locations, self.settings,
                max_queries=limit * 2,
            )

            for q in queries:
                if len(all_leads) >= limit * 3:
                    break  # Enough seeds
                leads = collect_from_google_maps(
                    query=q["query"],
                    api_key=self.settings.gmaps_api_key,
                    category=category,
                    location=q["location"],
                    delay_range=(self.settings.delay_min, self.settings.delay_max),
                    max_results=20,
                )
                all_leads.extend(leads)
                self._emit("discovering", f"Found {len(leads)} from Maps: {q['query'][:60]}",
                           discovered=len(all_leads))

        stats["discovered"] = len(all_leads)
        self._emit("discovering", f"Discovery complete: {len(all_leads)} candidates")

        if not all_leads:
            self._emit("complete", "No candidates found. Check API keys and try again.")
            run.error = "No candidates discovered"
            run.completed_at = datetime.utcnow()
            self.db.save_search_run(run)
            return stats

        # ============================================================
        # STAGE 2: BLACKLIST / WHITELIST CHECK
        # ============================================================
        filtered_leads = []
        for lead in all_leads:
            domain = normalize_domain(lead.company.website)

            if domain in self.blacklist or domain in self.competitors:
                lead.status = "rejected"
                lead.exclusion_reason = "Domain blacklisted or competitor"
                stats["rejected"] += 1
                continue

            if domain in self.whitelist:
                lead.tags.append("whitelisted")

            # Skip if already in database
            if domain and self.db.check_domain_exists(domain):
                stats["duplicates_merged"] += 1
                continue

            filtered_leads.append(lead)

        all_leads = filtered_leads
        self._emit("filtering", f"After whitelist/blacklist: {len(all_leads)} candidates")

        # ============================================================
        # STAGE 3: FIRST-PASS CLASSIFICATION (light, no website fetch)
        # ============================================================
        self._emit("classifying", "Running first-pass classification...")

        classified = []
        for lead in all_leads:
            lead = classify_lead(lead, {}, self.settings)  # Empty signals (no website yet)
            if lead.status == "rejected":
                stats["rejected"] += 1
                self._emit("classifying", f"Rejected: {lead.company.name} — {lead.exclusion_reason}")
            else:
                classified.append(lead)

        stats["classified"] = len(classified)
        self._emit("classifying", f"After first-pass: {len(classified)} promising, {stats['rejected']} rejected")

        # ============================================================
        # STAGE 4: ENRICHMENT (only promising records)
        # ============================================================
        self._emit("enriching", f"Enriching {len(classified)} promising records...")

        enriched_data: list[tuple[LeadRecord, dict]] = []
        for i, lead in enumerate(classified):
            self._emit("enriching", f"[{i+1}/{len(classified)}] {lead.company.name}",
                       enriched=i+1)
            lead, signals = enrich_lead(
                lead, self.settings,
                fetch_website=True,
                find_contacts=enrich_contacts,
                delay_range=(self.settings.delay_min, self.settings.delay_max),
            )
            enriched_data.append((lead, signals))

        stats["enriched"] = len(enriched_data)

        # ============================================================
        # STAGE 5: RE-CLASSIFY + SCORE (with website signals now)
        # ============================================================
        self._emit("scoring", "Scoring and classifying with full data...")

        scored_leads = []
        for lead, signals in enriched_data:
            lead = classify_lead(lead, signals, self.settings)
            if lead.status != "rejected":
                lead = score_lead(lead, signals, self.settings)
            scored_leads.append(lead)

        # ============================================================
        # STAGE 6: DEDUPLICATION
        # ============================================================
        self._emit("deduplicating", "Merging duplicates...")
        pre_dedupe = len(scored_leads)
        scored_leads = deduplicate(scored_leads)
        stats["duplicates_merged"] += pre_dedupe - len(scored_leads)

        # ============================================================
        # STAGE 7: FINAL SORT + LIMIT
        # ============================================================
        # Sort by score descending
        scored_leads.sort(key=lambda l: l.qualification_score, reverse=True)

        # Count stats
        for lead in scored_leads:
            if lead.status == "accepted":
                stats["accepted"] += 1
            elif lead.status == "review_needed":
                stats["review"] += 1
            elif lead.status == "rejected":
                stats["rejected"] += 1

        # Apply limit (top N per category per geography)
        if strict_mode:
            scored_leads = [l for l in scored_leads if l.status == "accepted"]
        final_leads = scored_leads[:limit]

        self._emit("saving", f"Saving {len(final_leads)} leads to database...")

        # ============================================================
        # STAGE 8: SAVE TO DATABASE
        # ============================================================
        for lead in final_leads:
            lead.pipeline_stage = "final"
            self.db.upsert_lead(lead, search_run_id=run_id)
            stats["lead_ids"].append(lead.id)

        # Also save rejected for audit trail
        for lead in scored_leads[len(final_leads):]:
            if lead.status == "rejected":
                self.db.upsert_lead(lead, search_run_id=run_id)

        # Update search run
        run.results_found = stats["discovered"]
        run.results_accepted = stats["accepted"]
        run.results_rejected = stats["rejected"]
        run.results_review = stats["review"]
        run.completed_at = datetime.utcnow()
        self.db.save_search_run(run)

        self._emit("complete",
                    f"Pipeline complete: {stats['accepted']} accepted, "
                    f"{stats['review']} review, {stats['rejected']} rejected",
                    stats=stats)

        return stats
