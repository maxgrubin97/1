"""
CSV import collector.

First-class pipeline for importing lead lists from:
- LinkedIn Sales Navigator exports
- Apollo exports
- ZoomInfo exports
- Manual/custom CSV files

Maps columns to our data model and tags records for enrichment.
"""

import csv
import logging
from datetime import datetime
from pathlib import Path

from app.models import LeadRecord
from app.models.company import Company
from app.models.contact import Contact
from app.utils.text import normalize_company_name, normalize_domain

logger = logging.getLogger(__name__)

# Column mapping presets for common export formats
COLUMN_MAPS = {
    "linkedin_sales_navigator": {
        "First Name": "first_name",
        "Last Name": "last_name",
        "Title": "title",
        "Company": "company_name",
        "Company Name": "company_name",
        "Company Website": "website",
        "Industry": "industry",
        "City": "city",
        "State": "state",
        "Country": "country",
        "LinkedIn URL": "linkedin_url",
        "Company LinkedIn URL": "linkedin_company_url",
        "Employees": "employee_count",
        "Company Size": "employee_count",
    },
    "apollo": {
        "First Name": "first_name",
        "Last Name": "last_name",
        "Title": "title",
        "Company": "company_name",
        "Website": "website",
        "Industry": "industry",
        "City": "city",
        "State": "state",
        "Phone": "phone",
        "Email": "email",
        "LinkedIn Url": "linkedin_url",
        "Company Linkedin Url": "linkedin_company_url",
        "# Employees": "employee_count",
        "Annual Revenue": "revenue",
    },
    "generic": {
        "name": "full_name",
        "company": "company_name",
        "company_name": "company_name",
        "business_name": "company_name",
        "title": "title",
        "website": "website",
        "url": "website",
        "phone": "phone",
        "email": "email",
        "city": "city",
        "state": "state",
        "zip": "zip_code",
        "address": "address",
        "industry": "industry",
        "linkedin": "linkedin_url",
        "linkedin_url": "linkedin_url",
        "employees": "employee_count",
        "revenue": "revenue",
        "description": "description",
    },
}


def _detect_format(headers: list[str]) -> str:
    """Auto-detect CSV format from column headers."""
    header_set = set(h.strip() for h in headers)

    if "Company LinkedIn URL" in header_set or "Company Name" in header_set:
        return "linkedin_sales_navigator"
    if "Company Linkedin Url" in header_set or "# Employees" in header_set:
        return "apollo"
    return "generic"


def _map_row(row: dict, col_map: dict) -> dict:
    """Map CSV columns to normalized field names."""
    mapped = {}
    for csv_col, field_name in col_map.items():
        if csv_col in row and row[csv_col]:
            mapped[field_name] = row[csv_col].strip()
    return mapped


def import_csv(
    filepath: str,
    record_type: str = "referral_partner",
    category: str = "imported",
    format_hint: str = "auto",
    custom_column_map: dict | None = None,
) -> list[LeadRecord]:
    """
    Import leads from a CSV file.

    Args:
        filepath: Path to the CSV file.
        record_type: 'direct_prospect' or 'referral_partner'.
        category: Category to assign to imported records.
        format_hint: 'auto', 'linkedin_sales_navigator', 'apollo', or 'generic'.
        custom_column_map: Optional custom {csv_col: field_name} mapping.

    Returns:
        List of LeadRecord objects tagged for enrichment.
    """
    path = Path(filepath)
    if not path.exists():
        logger.error(f"File not found: {filepath}")
        return []

    leads = []

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []

        # Determine column mapping
        if custom_column_map:
            col_map = custom_column_map
            fmt = "custom"
        elif format_hint != "auto":
            col_map = COLUMN_MAPS.get(format_hint, COLUMN_MAPS["generic"])
            fmt = format_hint
        else:
            fmt = _detect_format(headers)
            col_map = COLUMN_MAPS.get(fmt, COLUMN_MAPS["generic"])

        logger.info(f"Importing {filepath} as format: {fmt}")
        logger.info(f"CSV columns: {headers}")

        for i, row in enumerate(reader):
            mapped = _map_row(row, col_map)
            if not mapped:
                continue

            # Build name
            name = mapped.get("full_name", "")
            if not name:
                first = mapped.get("first_name", "")
                last = mapped.get("last_name", "")
                name = f"{first} {last}".strip()

            company_name = mapped.get("company_name", "")
            if not company_name and not name:
                continue  # Skip empty rows

            website = mapped.get("website", "")

            company = Company(
                name=company_name,
                name_normalized=normalize_company_name(company_name),
                website=website,
                website_domain=normalize_domain(website),
                phone=mapped.get("phone", ""),
                email=mapped.get("email", ""),
                city=mapped.get("city", ""),
                state=mapped.get("state", ""),
                zip_code=mapped.get("zip_code", ""),
                address=mapped.get("address", ""),
                primary_industry=mapped.get("industry", ""),
                linkedin_company_url=mapped.get("linkedin_company_url", ""),
                employee_count_estimate=mapped.get("employee_count", ""),
                revenue_estimate=mapped.get("revenue", ""),
                description=mapped.get("description", ""),
                collected_at=datetime.utcnow(),
            )

            contact = None
            if name:
                contact = Contact(
                    company_id=company.id,
                    name=name,
                    title=mapped.get("title", ""),
                    email=mapped.get("email", ""),
                    phone=mapped.get("phone", ""),
                    linkedin_url=mapped.get("linkedin_url", ""),
                    source="csv_import",
                )

            lead = LeadRecord(
                record_type=record_type,
                company=company,
                category=category,
                pipeline_stage="seed",
                tags=["imported", fmt],
            )

            if contact:
                lead.set_primary_contact(contact)

            lead.add_evidence(
                claim=f"Imported from CSV ({fmt} format)",
                source_type="csv_import",
                snippet=f"Row {i + 1}: {company_name} / {name}",
                confidence=0.5,
            )

            leads.append(lead)

    logger.info(f"Imported {len(leads)} records from {filepath}")
    return leads
