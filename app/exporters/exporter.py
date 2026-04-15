"""
Multi-format exporter: CSV, Excel, JSON.

Excel exports include:
- Separate tabs for accepted, review, rejected
- Frozen header row
- Clickable links
- Human-readable column names
"""

import csv
import json
import logging
import os
from datetime import datetime

from app.models import LeadRecord

logger = logging.getLogger(__name__)

# Column mapping: (field_path, display_name)
COLUMNS = [
    ("record_type", "Record Type"),
    ("status", "Status"),
    ("outreach_priority_tier", "Outreach Tier"),
    ("category", "Category"),
    ("company.name", "Business Name"),
    ("primary_contact_name", "Contact Name"),
    ("primary_contact_title", "Contact Title"),
    ("primary_contact_email_verified", "Contact Email (Verified)"),
    ("primary_contact_email_guessed", "Contact Email (Guessed)"),
    ("primary_contact_email_status", "Email Status"),
    ("primary_contact_source_confidence", "Contact Confidence"),
    ("company.city", "City"),
    ("company.state", "State"),
    ("company.zip_code", "ZIP"),
    ("company.address", "Full Address"),
    ("company.website", "Website"),
    ("company.phone", "Phone"),
    ("company.email", "Email"),
    ("primary_contact_linkedin", "LinkedIn (Contact)"),
    ("company.linkedin_company_url", "LinkedIn (Company)"),
    ("company.google_maps_url", "Google Maps"),
    ("qualification_score", "Score"),
    ("confidence_score", "Confidence"),
    ("website_validated", "Website Validated"),
    ("acceptance_gate_passed", "Gate Passed"),
    ("source_tier_best", "Best Source Tier"),
    ("source_count", "Source Count"),
    ("has_corroboration", "Corroborated"),
    ("company.primary_industry", "Industry"),
    ("company.employee_count_estimate", "Employees (Est.)"),
    ("company.revenue_estimate", "Revenue (Est.)"),
    ("company.google_rating", "Google Rating"),
    ("company.google_review_count", "Google Reviews"),
    ("primary_outreach_angle", "Outreach Angle"),
    ("likely_pain_point", "Likely Pain Point"),
    ("likely_referral_reason", "Referral Reason"),
    ("mutual_referral_fit", "Mutual Fit"),
    ("score_reasons", "Why It Fits"),
    ("why_not_fit", "Why It Might Not Fit"),
    ("source_summary", "Source Summary"),
    ("estimated_fit_for_fractional_cfo", "CFO Fit"),
    ("competing_service_risk_score", "Competition Risk"),
    ("acceptance_gate_explanation", "Gate Explanation"),
    ("exclusion_reason", "Exclusion Reason"),
    ("notes", "Notes"),
    ("source_urls_str", "Source URLs"),
]


def _extract_row(lead: LeadRecord) -> dict:
    """Extract a flat dict from a LeadRecord for export."""
    row = {}
    pc = lead.primary_contact  # shorthand

    for field_path, display_name in COLUMNS:
        if field_path == "primary_contact_name":
            row[display_name] = pc.name if pc else ""
        elif field_path == "primary_contact_title":
            row[display_name] = pc.title if pc else ""
        elif field_path == "primary_contact_linkedin":
            row[display_name] = pc.linkedin_url if pc else ""
        elif field_path == "primary_contact_email_verified":
            # Only show email if verified status
            if pc and pc.email and pc.email_status == "verified":
                row[display_name] = pc.email
            else:
                row[display_name] = ""
        elif field_path == "primary_contact_email_guessed":
            # Show guessed emails separately
            if pc and pc.email_guess:
                row[display_name] = pc.email_guess
            elif pc and pc.email and pc.email_status in ("guessed", "generic"):
                row[display_name] = pc.email
            else:
                row[display_name] = ""
        elif field_path == "primary_contact_email_status":
            row[display_name] = pc.email_status if pc else "unavailable"
        elif field_path == "primary_contact_source_confidence":
            row[display_name] = f"{pc.contact_source_confidence:.1f}" if pc else ""
        elif field_path == "score_reasons":
            row[display_name] = " | ".join(lead.score.reasons[:5])
        elif field_path == "why_not_fit":
            row[display_name] = " | ".join(lead.why_this_might_not_be_a_fit[:3])
        elif field_path == "source_urls_str":
            row[display_name] = " | ".join(lead.source_urls[:5])
        elif field_path == "source_summary":
            # Which sources contributed and best tier
            source_types = sorted(lead.evidence_source_types)
            tier_label = {1: "Authoritative", 2: "High-Quality", 3: "Discovery"}.get(lead.source_tier_best, "Unknown")
            row[display_name] = f"Tier {lead.source_tier_best} ({tier_label}) | {', '.join(source_types)}"
        elif "." in field_path:
            obj_name, attr = field_path.split(".", 1)
            obj = getattr(lead, obj_name, None)
            row[display_name] = getattr(obj, attr, "") if obj else ""
        else:
            row[display_name] = getattr(lead, field_path, "")
    return row


def export_csv(leads: list[LeadRecord], filepath: str) -> str:
    """Export leads to CSV."""
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    headers = [col[1] for col in COLUMNS]

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for lead in leads:
            writer.writerow(_extract_row(lead))

    logger.info(f"Exported {len(leads)} leads to {filepath}")
    return filepath


def export_json(leads: list[LeadRecord], filepath: str) -> str:
    """Export leads to JSON with full data."""
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

    data = []
    for lead in leads:
        record = lead.model_dump()
        record["score_summary"] = lead.score.to_summary()
        data.append(record)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)

    logger.info(f"Exported {len(leads)} leads to {filepath}")
    return filepath


def export_excel(
    leads: list[LeadRecord],
    filepath: str,
    include_rejected: bool = True,
) -> str:
    """
    Export leads to a polished Excel file with multiple tabs.

    Tabs: Accepted, Needs Review, Rejected (optional), Starred, Summary
    """
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        logger.warning("openpyxl not installed — falling back to CSV export")
        return export_csv(leads, filepath.replace(".xlsx", ".csv"))

    wb = Workbook()

    # Styles
    header_font = Font(bold=True, size=11)
    header_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    link_font = Font(color="0563C1", underline="single")
    green_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
    amber_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
    thin_border = Border(
        bottom=Side(style="thin", color="D9D9D9"),
    )

    headers = [col[1] for col in COLUMNS]

    def _write_sheet(ws, records, name):
        ws.title = name

        # Headers
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", wrap_text=True)

        # Freeze header row
        ws.freeze_panes = "A2"

        # Data rows
        for row_idx, lead in enumerate(records, 2):
            row_data = _extract_row(lead)
            for col_idx, header in enumerate(headers, 1):
                value = row_data.get(header, "")
                cell = ws.cell(row=row_idx, column=col_idx, value=str(value) if value is not None else "")
                cell.border = thin_border

                # Make URLs clickable
                str_val = str(value)
                if str_val.startswith("http"):
                    cell.font = link_font
                    cell.hyperlink = str_val

            # Row coloring
            if lead.outreach_priority_tier == "A":
                for col_idx in range(1, len(headers) + 1):
                    ws.cell(row=row_idx, column=col_idx).fill = green_fill
            elif lead.status == "review_needed":
                for col_idx in range(1, len(headers) + 1):
                    ws.cell(row=row_idx, column=col_idx).fill = amber_fill

        # Auto-width columns (approximate)
        for col_idx in range(1, len(headers) + 1):
            col_letter = get_column_letter(col_idx)
            max_len = max(
                len(str(ws.cell(row=r, column=col_idx).value or ""))
                for r in range(1, min(ws.max_row + 1, 50))
            )
            ws.column_dimensions[col_letter].width = min(50, max(12, max_len + 2))

    # Create tabs
    accepted = [l for l in leads if l.status == "accepted"]
    review = [l for l in leads if l.status == "review_needed"]
    rejected = [l for l in leads if l.status == "rejected"]

    # Accepted tab (default sheet)
    _write_sheet(wb.active, accepted, "Accepted")

    # Review tab
    ws_review = wb.create_sheet()
    _write_sheet(ws_review, review, "Needs Review")

    # Rejected tab (optional)
    if include_rejected and rejected:
        ws_rejected = wb.create_sheet()
        _write_sheet(ws_rejected, rejected, "Rejected")

    # Summary tab
    ws_summary = wb.create_sheet("Summary")
    summary_data = [
        ("Metric", "Value"),
        ("Total Records", len(leads)),
        ("Accepted", len(accepted)),
        ("Needs Review", len(review)),
        ("Rejected", len(rejected)),
        ("A-Tier", sum(1 for l in leads if l.outreach_priority_tier == "A")),
        ("B-Tier", sum(1 for l in leads if l.outreach_priority_tier == "B")),
        ("C-Tier", sum(1 for l in leads if l.outreach_priority_tier == "C")),
        ("With Named Contact", sum(1 for l in leads if l.has_decision_maker)),
        ("With Website", sum(1 for l in leads if l.company.website)),
        ("Export Date", datetime.now().strftime("%Y-%m-%d %H:%M")),
    ]
    for row_idx, (label, value) in enumerate(summary_data, 1):
        ws_summary.cell(row=row_idx, column=1, value=label).font = Font(bold=True)
        ws_summary.cell(row=row_idx, column=2, value=value)

    wb.save(filepath)
    logger.info(f"Exported {len(leads)} leads to {filepath}")
    return filepath
