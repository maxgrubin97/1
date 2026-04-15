"""
SBA Lender collector.

Cross-references discovered banks against known active SBA lenders.
The SBA publishes lender activity data, but structured bulk downloads
vary in availability. This collector supports two modes:

1. Static curated list: A CSV of known active SBA lenders in the target
   market, maintained in data/authoritative_lists/sba_active_lenders.csv.
   This is the recommended starting approach.

2. SBA API (future): If/when SBA provides a structured API for lender
   lookup, this collector can be extended.

Source tier: 1 (authoritative — SBA regulatory/program data)

CSV format for sba_active_lenders.csv:
  lender_name,city,state,sba_program,website
  Example Bank,New York,NY,PLP,https://examplebank.com
"""

import csv
import logging
from pathlib import Path

from app.models import LeadRecord, Company, Evidence

logger = logging.getLogger(__name__)

_LENDER_LIST_PATH = Path(__file__).parent.parent.parent / "data" / "authoritative_lists" / "sba_active_lenders.csv"
_lender_cache: dict[str, dict] | None = None


def _load_lender_list() -> dict[str, dict]:
    """Load the curated SBA lender list. Returns dict keyed by normalized name."""
    global _lender_cache
    if _lender_cache is not None:
        return _lender_cache

    _lender_cache = {}
    if not _LENDER_LIST_PATH.exists():
        logger.debug(f"[SBA] No lender list at {_LENDER_LIST_PATH}")
        return _lender_cache

    try:
        with open(_LENDER_LIST_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get("lender_name", "").strip()
                if name:
                    key = name.lower().strip()
                    _lender_cache[key] = {
                        "lender_name": name,
                        "city": row.get("city", "").strip(),
                        "state": row.get("state", "").strip(),
                        "sba_program": row.get("sba_program", "").strip(),
                        "website": row.get("website", "").strip(),
                    }
        logger.info(f"[SBA] Loaded {len(_lender_cache)} lenders from curated list")
    except Exception as e:
        logger.warning(f"[SBA] Error loading lender list: {e}")

    return _lender_cache


def is_available() -> bool:
    """Check if SBA lender data is available."""
    lenders = _load_lender_list()
    return len(lenders) > 0


def validate_sba_lender(company_name: str) -> dict | None:
    """
    Check if a company name matches a known active SBA lender.

    Returns the lender record dict if found, None otherwise.
    Used for cross-referencing Google Maps-discovered banks.
    """
    lenders = _load_lender_list()
    if not lenders:
        return None

    name_lower = company_name.lower().strip()

    # Exact match
    if name_lower in lenders:
        return lenders[name_lower]

    # Substring match (bank names often vary)
    for key, data in lenders.items():
        if key in name_lower or name_lower in key:
            return data

    return None


def collect_sba_lenders(
    state: str = "NY",
    max_results: int = 50,
) -> list[LeadRecord]:
    """
    Return leads from the curated SBA lender list for a given state.

    Each returned lead is tagged as source_tier=1 (authoritative).
    """
    lenders = _load_lender_list()
    leads = []

    for data in lenders.values():
        if state and data.get("state", "").upper() != state.upper():
            continue
        if len(leads) >= max_results:
            break

        lead = LeadRecord(
            record_type="referral_partner",
            category="sba_lenders",
            company=Company(
                name=data["lender_name"],
                city=data.get("city", ""),
                state=data.get("state", ""),
                website=data.get("website", ""),
            ),
        )
        lead.add_evidence(
            claim=f"Active SBA lender ({data.get('sba_program', 'SBA')})",
            source_url="data/authoritative_lists/sba_active_lenders.csv",
            source_type="authoritative_list",
            snippet=f"{data['lender_name']} - {data.get('sba_program', '')} - {data.get('state', '')}",
            confidence=0.95,
            source_tier=1,
            extraction_method="curated_list",
        )
        leads.append(lead)

    logger.info(f"[SBA] Found {len(leads)} lenders in {state}")
    return leads
