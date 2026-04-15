"""
SEC IAPD (Investment Adviser Public Disclosure) collector.

For wealth managers / RIAs. The SEC IAPD system provides data about
registered investment advisers including firm name, CRD number, address,
website, AUM, and number of accounts.

Status: STUBBED — The IAPD public search (adviserinfo.sec.gov) requires
JavaScript-rendered interaction and does not expose a clean REST API or
bulk data endpoint. Building a compliant collector would require either:
  1. A future SEC API (if released)
  2. IAPD bulk data files (if made publicly downloadable)
  3. A third-party data provider with IAPD data

This stub provides the interface so the pipeline can integrate it when
a compliant data source becomes available.

Source tier: 1 (authoritative — SEC regulatory data)
"""

import logging
from app.models import LeadRecord

logger = logging.getLogger(__name__)


def is_available() -> bool:
    """Check if IAPD collector is available. Currently always False (stubbed)."""
    return False


def collect_rias_by_location(
    state: str = "NY",
    city: str = "",
    max_results: int = 50,
) -> list[LeadRecord]:
    """
    Query IAPD for registered investment advisers by location.

    NOT YET IMPLEMENTED — requires compliant API access.
    Returns empty list.
    """
    logger.debug("[IAPD] Collector not available — stubbed pending compliant API access")
    return []


def validate_ria_registration(firm_name: str, state: str = "") -> dict | None:
    """
    Check if a firm is a registered investment adviser via IAPD.

    Would return: {crd_number, firm_name, address, website, aum, num_accounts}
    NOT YET IMPLEMENTED.
    """
    logger.debug(f"[IAPD] Cannot validate '{firm_name}' — stubbed")
    return None
