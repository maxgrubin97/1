"""
FastAPI web application — MGR Advisory Lead Engine Dashboard.

Lightweight internal operator tool. Server-rendered HTML with minimal JS.
"""

import json
import logging
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Form, UploadFile, File, Query
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config.settings import get_settings
from app.storage.database import Database
from app.pipeline.runner import PipelineRunner
from app.collectors.csv_import import import_csv as do_import_csv
from app.exporters.exporter import export_csv, export_excel, export_json

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

web_app = FastAPI(title="MGR Advisory Lead Engine")
web_app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Make runtime_mode available in all templates
templates.env.globals["runtime_mode"] = get_settings().runtime_mode

# Global state for active runs
_active_runs: dict[str, dict] = {}


def _get_db() -> Database:
    settings = get_settings()
    return Database(settings.database_path)


# Default presets
DEFAULT_PRESETS = [
    {"id": "p1", "name": "SBA Lenders - Nassau County", "config": {"category": "sba_lenders", "geo": "Nassau County, NY", "limit": 25, "record_type": "referral_partner"}},
    {"id": "p2", "name": "SBA Lenders - Suffolk County", "config": {"category": "sba_lenders", "geo": "Suffolk County, NY", "limit": 25, "record_type": "referral_partner"}},
    {"id": "p3", "name": "Business Brokers - Long Island", "config": {"category": "business_brokers", "geo": "Nassau County, NY,Suffolk County, NY", "limit": 25, "record_type": "referral_partner"}},
    {"id": "p4", "name": "Boutique Attorneys - Long Island", "config": {"category": "boutique_corporate_attorneys", "geo": "Nassau County, NY,Suffolk County, NY", "limit": 25, "record_type": "referral_partner"}},
    {"id": "p5", "name": "Boutique Attorneys - Manhattan", "config": {"category": "boutique_corporate_attorneys", "geo": "Manhattan, NY", "limit": 25, "record_type": "referral_partner"}},
    {"id": "p6", "name": "Wealth Managers - NYC Metro", "config": {"category": "wealth_managers", "geo": "Manhattan, NY,Brooklyn, NY,Queens, NY,Westchester, NY", "limit": 25, "record_type": "referral_partner"}},
    {"id": "p7", "name": "Boutique CPA Firms - Long Island", "config": {"category": "boutique_cpa_firms", "geo": "Nassau County, NY,Suffolk County, NY", "limit": 25, "record_type": "referral_partner"}},
    {"id": "p8", "name": "Construction - Suffolk County", "config": {"category": "construction_trades", "geo": "Suffolk County, NY", "limit": 25, "record_type": "direct_prospect"}},
    {"id": "p9", "name": "Construction - Nassau County", "config": {"category": "construction_trades", "geo": "Nassau County, NY", "limit": 25, "record_type": "direct_prospect"}},
    {"id": "p10", "name": "Healthcare Practices - Long Island", "config": {"category": "healthcare_practices", "geo": "Nassau County, NY,Suffolk County, NY", "limit": 25, "record_type": "direct_prospect"}},
    {"id": "p11", "name": "Professional Services - Manhattan", "config": {"category": "professional_services", "geo": "Manhattan, NY", "limit": 25, "record_type": "direct_prospect"}},
    {"id": "p12", "name": "Real Estate Ops - NYC Metro", "config": {"category": "real_estate_operations", "geo": "Manhattan, NY,Brooklyn, NY,Queens, NY", "limit": 25, "record_type": "direct_prospect"}},
]


# ========================================================================
# ROUTES
# ========================================================================

@web_app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Dashboard / Run Search page."""
    settings = get_settings()
    db = _get_db()

    categories_rp = [(k, settings.get_category(k).get("label", k)) for k in settings.get_referral_partner_keys()]
    categories_dp = [(k, settings.get_category(k).get("label", k)) for k in settings.get_direct_prospect_keys()]
    locations = settings.get_location_names(["tier_1", "tier_2"])
    recent_runs = db.get_search_runs(limit=10)

    # Load presets
    presets = db.get_presets()
    if not presets:
        for p in DEFAULT_PRESETS:
            db.save_preset(p["id"], p["name"], p["config"])
        presets = db.get_presets()

    db.close()
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "page": "dashboard",
        "categories_rp": categories_rp,
        "categories_dp": categories_dp,
        "locations": locations,
        "recent_runs": recent_runs,
        "presets": presets,
        "active_runs": _active_runs,
    })


@web_app.post("/run", response_class=HTMLResponse)
async def start_run(
    request: Request,
    category: str = Form(...),
    geo: str = Form(""),
    limit: int = Form(25),
    enrich: bool = Form(True),
):
    """Launch a pipeline run."""
    run_id = str(uuid.uuid4())
    _active_runs[run_id] = {
        "id": run_id,
        "category": category,
        "geo": geo,
        "limit": limit,
        "status": "running",
        "stage": "Starting...",
        "message": "",
        "stats": {},
        "log": [],
        "started_at": datetime.now().strftime("%H:%M:%S"),
    }

    def _progress(stage: str, message: str, **kwargs):
        if run_id in _active_runs:
            _active_runs[run_id]["stage"] = stage
            _active_runs[run_id]["message"] = message
            _active_runs[run_id]["log"].append(f"[{stage}] {message}")
            _active_runs[run_id]["stats"].update(kwargs)

    def _run_pipeline():
        try:
            settings = get_settings()
            locations = [g.strip() for g in geo.split(",")] if geo else settings.get_location_names(["tier_1"])
            runner = PipelineRunner(settings, progress_callback=_progress)
            stats = runner.run(
                category=category,
                locations=locations,
                limit=limit,
                enrich_contacts=enrich,
            )
            if run_id in _active_runs:
                _active_runs[run_id]["status"] = "completed"
                _active_runs[run_id]["stats"] = stats
        except Exception as e:
            logger.exception("Pipeline error")
            if run_id in _active_runs:
                _active_runs[run_id]["status"] = "error"
                _active_runs[run_id]["message"] = str(e)

    thread = threading.Thread(target=_run_pipeline, daemon=True)
    thread.start()

    return RedirectResponse(f"/progress/{run_id}", status_code=303)


@web_app.get("/progress/{run_id}", response_class=HTMLResponse)
async def progress_page(request: Request, run_id: str):
    """Live run progress page."""
    run = _active_runs.get(run_id, {"status": "not_found"})
    return templates.TemplateResponse("progress.html", {
        "request": request,
        "page": "progress",
        "run": run,
        "run_id": run_id,
    })


@web_app.get("/api/progress/{run_id}")
async def progress_api(run_id: str):
    """API endpoint for polling run progress."""
    run = _active_runs.get(run_id, {"status": "not_found"})
    return JSONResponse({
        "status": run.get("status"),
        "stage": run.get("stage"),
        "message": run.get("message"),
        "stats": run.get("stats", {}),
        "log": run.get("log", [])[-20:],
    })


@web_app.get("/results", response_class=HTMLResponse)
async def results_page(
    request: Request,
    status: str = Query("accepted"),
    category: str = Query(""),
    tier: str = Query(""),
    search: str = Query(""),
    sort: str = Query("qualification_score"),
    min_score: int = Query(0),
    run_id: str = Query(""),
    page_num: int = Query(1),
    contact_filter: str = Query(""),
):
    """Results Explorer page."""
    db = _get_db()
    per_page = 50
    offset = (page_num - 1) * per_page

    leads = db.query_leads(
        status=status or None,
        category=category or None,
        outreach_tier=tier or None,
        search=search or None,
        sort_by=sort,
        min_score=min_score,
        search_run_id=run_id or None,
        limit=per_page,
        offset=offset,
    )

    # Apply contact-level filters in-memory (not in DB query)
    if contact_filter:
        leads = _apply_contact_filter(leads, contact_filter)

    total = db.count_leads(status=status or None, category=category or None, search_run_id=run_id or None)
    settings = get_settings()
    all_categories = [(k, settings.get_category(k).get("label", k)) for k in settings.get_all_category_keys()]

    db.close()
    return templates.TemplateResponse("results.html", {
        "request": request,
        "page": "results",
        "leads": leads,
        "total": total,
        "current_status": status,
        "current_category": category,
        "current_tier": tier,
        "current_search": search,
        "current_sort": sort,
        "current_min_score": min_score,
        "current_run_id": run_id,
        "current_contact_filter": contact_filter,
        "page_num": page_num,
        "per_page": per_page,
        "all_categories": all_categories,
    })


@web_app.get("/lead/{lead_id}", response_class=HTMLResponse)
async def lead_detail(request: Request, lead_id: str):
    """Lead detail page."""
    db = _get_db()
    data = db.get_lead_with_ui_fields(lead_id)
    db.close()
    if not data:
        return HTMLResponse("<h1>Lead not found</h1>", status_code=404)

    return templates.TemplateResponse("lead_detail.html", {
        "request": request,
        "page": "results",
        "lead": data["lead"],
        "starred": data["starred"],
        "marked_for_outreach": data["marked_for_outreach"],
        "contacted": data["contacted"],
        "notes": data["notes"],
    })


@web_app.post("/lead/{lead_id}/action")
async def lead_action(
    lead_id: str,
    action: str = Form(...),
    notes: str = Form(""),
):
    """Handle lead actions: star, outreach, reject, accept, etc."""
    db = _get_db()

    if action == "star":
        db.update_lead_flags(lead_id, starred=True)
    elif action == "unstar":
        db.update_lead_flags(lead_id, starred=False)
    elif action == "outreach":
        db.update_lead_flags(lead_id, marked_for_outreach=True)
    elif action == "unoutreach":
        db.update_lead_flags(lead_id, marked_for_outreach=False)
    elif action == "accept":
        db.update_lead_status(lead_id, "accepted")
    elif action == "reject":
        db.update_lead_status(lead_id, "rejected")
    elif action == "review":
        db.update_lead_status(lead_id, "review_needed")
    elif action == "save_notes":
        db.update_lead_flags(lead_id, notes=notes)
    elif action == "contacted":
        db.update_lead_flags(lead_id, contacted=True)

    db.close()
    return RedirectResponse(f"/lead/{lead_id}", status_code=303)


@web_app.get("/review", response_class=HTMLResponse)
async def review_page(request: Request):
    """Review Queue page."""
    db = _get_db()
    leads = db.query_leads(status="review_needed", limit=200)
    stats = db.get_stats()
    db.close()

    # Categorize review items
    missing_contact = [l for l in leads if not l.has_decision_maker]
    conflicting = [l for l in leads if l.review_evidence_against]
    borderline = [l for l in leads if l.qualification_score > 40 and not l.review_evidence_against]

    return templates.TemplateResponse("review.html", {
        "request": request,
        "page": "review",
        "leads": leads,
        "stats": stats,
        "missing_contact": len(missing_contact),
        "conflicting": len(conflicting),
        "borderline": len(borderline),
    })


@web_app.get("/export-center", response_class=HTMLResponse)
async def export_center(request: Request):
    """Export Center page."""
    db = _get_db()
    stats = db.get_stats()
    runs = db.get_search_runs(limit=20)
    settings = get_settings()
    all_categories = [(k, settings.get_category(k).get("label", k)) for k in settings.get_all_category_keys()]
    db.close()

    return templates.TemplateResponse("export.html", {
        "request": request,
        "page": "export",
        "stats": stats,
        "runs": runs,
        "all_categories": all_categories,
    })


@web_app.post("/do-export")
async def do_export(
    format: str = Form("excel"),
    status: str = Form(""),
    category: str = Form(""),
    min_score: int = Form(0),
    tier: str = Form(""),
):
    """Generate and download an export file."""
    db = _get_db()
    leads = db.query_leads(
        status=status or None,
        category=category or None,
        outreach_tier=tier or None,
        min_score=min_score,
        limit=5000,
    )
    db.close()

    if not leads:
        return HTMLResponse("<h1>No leads match these filters</h1>")

    os.makedirs("output", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    if format == "csv":
        path = f"output/leads_{ts}.csv"
        export_csv(leads, path)
    elif format == "json":
        path = f"output/leads_{ts}.json"
        export_json(leads, path)
    else:
        path = f"output/leads_{ts}.xlsx"
        export_excel(leads, path)

    return FileResponse(path, filename=os.path.basename(path))


@web_app.get("/import", response_class=HTMLResponse)
async def import_page(request: Request):
    """Import List page."""
    return templates.TemplateResponse("import.html", {
        "request": request,
        "page": "import",
    })


@web_app.post("/do-import")
async def do_import(
    request: Request,
    file: UploadFile = File(...),
    record_type: str = Form("referral_partner"),
    category: str = Form("imported"),
    format_hint: str = Form("auto"),
):
    """Handle CSV file upload and import."""
    os.makedirs("data/imports", exist_ok=True)
    filepath = f"data/imports/{file.filename}"

    with open(filepath, "wb") as f:
        content = await file.read()
        f.write(content)

    leads = do_import_csv(filepath, record_type, category, format_hint)
    if leads:
        db = _get_db()
        db.upsert_leads(leads)
        db.close()

    return templates.TemplateResponse("import.html", {
        "request": request,
        "page": "import",
        "success": True,
        "count": len(leads),
        "filename": file.filename,
    })


@web_app.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):
    """Search History page."""
    db = _get_db()
    runs = db.get_search_runs(limit=50)
    db.close()

    return templates.TemplateResponse("history.html", {
        "request": request,
        "page": "history",
        "runs": runs,
    })


def _apply_contact_filter(leads: list, contact_filter: str) -> list:
    """Apply contact-level filters to a list of leads."""
    if contact_filter == "website_validated":
        return [l for l in leads if l.website_validated]
    elif contact_filter == "verified_contact":
        return [l for l in leads if l.primary_contact and l.primary_contact.email_status == "verified"]
    elif contact_filter == "has_guessed_email":
        return [l for l in leads if l.primary_contact and (l.primary_contact.email_guess or l.primary_contact.email_status == "guessed")]
    elif contact_filter == "generic_email":
        return [l for l in leads if l.primary_contact and l.primary_contact.email_status == "generic"]
    elif contact_filter == "high_referral_power":
        return [l for l in leads if l.referral_power_score >= 70]
    elif contact_filter == "high_buyer_intent":
        return [l for l in leads if l.buyer_intent_score >= 65]
    return leads


@web_app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings page."""
    settings = get_settings()
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "page": "settings",
        "scoring_weights": settings.scoring_weights,
        "thresholds": settings.get_thresholds(),
        "noise_control": settings.get_noise_control(),
        "locations_t1": settings.get_location_names(["tier_1"]),
        "locations_t2": settings.get_location_names(["tier_2"]),
    })
