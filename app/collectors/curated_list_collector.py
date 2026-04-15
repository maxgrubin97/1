"""
Curated list collector.

Ingests manually curated CSV files from data/authoritative_lists/ as
Tier 2 sources for cross-referencing and validation.

Supported CSV formats (column headers):
  - company_name (required)
  - category (e.g., "boutique_corporate_attorneys", "business_brokers")
  - city, state
  - website
  - source_name (e.g., "IBBA Member Directory", "NYSSCPA Member List")
  - certification (e.g., "CBI", "ASA", "CPA")
  - notes

Usage:
  Place CSV files in data/authoritative_lists/ with descriptive names:
    - ibba_certified_brokers_ny.csv
    - nysscpa_members_metro.csv
    - nysba_corporate_attorneys.csv

Source tier: 2 (high-quality — curated from authoritative directories)
"""

import csv
import logging
from pathlib import Path

from app.models import LeadRecord, Company
from app.utils.text import normalize_domain

logger = logging.getLogger(__name__)

_LISTS_DIR = Path(__file__).parent.parent.parent / "data" / "authoritative_lists"


def is_available() -> bool:
    """Check if any curated list CSVs exist."""
    if not _LISTS_DIR.exists():
        return False
    return any(_LISTS_DIR.glob("*.csv"))


def list_available_files() -> list[str]:
    """Return names of available curated list CSV files."""
    if not _LISTS_DIR.exists():
        return []
    return [f.name for f in _LISTS_DIR.glob("*.csv")]


def collect_from_curated_list(
    filename: str,
    category: str = "",
    state_filter: str = "",
    max_results: int = 200,
) -> list[LeadRecord]:
    """
    Load leads from a specific curated CSV file.

    Args:
        filename: Name of CSV file in data/authoritative_lists/
        category: Override category for all records (if not in CSV)
        state_filter: Filter to specific state
        max_results: Maximum records to return

    Returns:
        List of LeadRecord objects tagged as Tier 2 sources.
    """
    filepath = _LISTS_DIR / filename
    if not filepath.exists():
        logger.warning(f"[Curated] File not found: {filepath}")
        return []

    leads = []
    try:
        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if len(leads) >= max_results:
                    break

                name = row.get("company_name", "").strip()
                if not name:
                    continue

                row_state = row.get("state", "").strip()
                if state_filter and row_state.upper() != state_filter.upper():
                    continue

                row_category = row.get("category", "").strip() or category
                website = row.get("website", "").strip()
                source_name = row.get("source_name", filename).strip()
                certification = row.get("certification", "").strip()

                lead = LeadRecord(
                    record_type="referral_partner",
                    category=row_category,
                    company=Company(
                        name=name,
                        city=row.get("city", "").strip(),
                        state=row_state,
                        website=website,
                        website_domain=normalize_domain(website) if website else "",
                    ),
                )

                snippet = f"{name}"
                if certification:
                    snippet += f" ({certification})"
                if row.get("notes"):
                    snippet += f" — {row['notes']}"

                lead.add_evidence(
                    claim=f"Listed in {source_name}" + (f" ({certification})" if certification else ""),
                    source_url=f"data/authoritative_lists/{filename}",
                    source_type="authoritative_list",
                    snippet=snippet[:200],
                    confidence=0.85,
                    source_tier=2,
                    extraction_method="curated_list",
                )
                leads.append(lead)

    except Exception as e:
        logger.warning(f"[Curated] Error reading {filepath}: {e}")

    logger.info(f"[Curated] Loaded {len(leads)} records from {filename}")
    return leads


def collect_all_curated_lists(
    category: str = "",
    state_filter: str = "",
    max_per_file: int = 100,
) -> list[LeadRecord]:
    """Load leads from all curated CSV files in the directory."""
    all_leads = []
    for filepath in sorted(_LISTS_DIR.glob("*.csv")):
        # Skip the SBA lender list (handled by sba_lender_collector)
        if "sba_active_lenders" in filepath.name:
            continue
        leads = collect_from_curated_list(
            filepath.name,
            category=category,
            state_filter=state_filter,
            max_results=max_per_file,
        )
        all_leads.extend(leads)
    return all_leads
