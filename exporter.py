"""CSV export for leads."""

import csv
import logging
import os
from datetime import datetime

from models import Lead

logger = logging.getLogger(__name__)

CSV_COLUMNS = [
    ("name", "Decision Maker Name"),
    ("title", "Title"),
    ("role_type", "Role Category"),
    ("company", "Company"),
    ("industry", "Industry"),
    ("location", "Location"),
    ("linkedin_url", "LinkedIn URL"),
    ("website", "Company Website"),
    ("phone", "Phone"),
    ("email", "Email"),
    ("email_guess", "Email (Guessed)"),
    ("company_size", "Company Size (Est.)"),
    ("revenue_estimate", "Revenue (Est.)"),
    ("gmaps_rating", "Google Rating"),
    ("gmaps_review_count", "Google Reviews"),
    ("gmaps_address", "Address"),
    ("company_description", "Company Description"),
    ("funding_stage", "Funding Stage"),
    ("year_founded", "Year Founded"),
    ("source", "Source"),
]


def export_to_csv(
    leads: list[Lead],
    output_dir: str = "output",
    filename: str = "",
) -> str:
    """
    Export leads to a CSV file.

    Args:
        leads: List of Lead objects to export.
        output_dir: Directory to write the file to.
        filename: Custom filename. Defaults to leads_YYYYMMDD_HHMMSS.csv.

    Returns:
        The full path to the written CSV file.
    """
    os.makedirs(output_dir, exist_ok=True)

    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"leads_{timestamp}.csv"

    filepath = os.path.join(output_dir, filename)

    headers = [col[1] for col in CSV_COLUMNS]
    field_keys = [col[0] for col in CSV_COLUMNS]

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)

        for lead in leads:
            lead_dict = lead.to_dict()
            row = [lead_dict.get(key, "") for key in field_keys]
            writer.writerow(row)

    logger.info(f"Exported {len(leads)} leads to {filepath}")

    # Print summary stats
    sources = {}
    industries = {}
    roles = {}
    for lead in leads:
        sources[lead.source] = sources.get(lead.source, 0) + 1
        if lead.industry:
            industries[lead.industry] = industries.get(lead.industry, 0) + 1
        if lead.role_type:
            roles[lead.role_type] = roles.get(lead.role_type, 0) + 1

    logger.info("--- Export Summary ---")
    logger.info(f"Total leads: {len(leads)}")
    logger.info(f"By source: {sources}")
    logger.info(f"Decision makers: {sum(1 for l in leads if l.is_decision_maker)}")
    if industries:
        top_industries = sorted(industries.items(), key=lambda x: x[1], reverse=True)[:5]
        logger.info(f"Top industries: {dict(top_industries)}")

    return filepath
