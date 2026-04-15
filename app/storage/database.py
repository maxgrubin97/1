"""
SQLite persistence layer.

Stores leads, search runs, and review state. Uses JSON columns for
complex nested data (evidence, contacts, scores) to keep the schema simple
while still allowing SQL queries on key fields.
"""

import csv
import json
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.models import LeadRecord, SearchRun

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id TEXT PRIMARY KEY,
    record_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'review_needed',
    category TEXT,
    subcategory TEXT,
    company_name TEXT,
    company_name_normalized TEXT,
    company_domain TEXT,
    company_phone TEXT,
    company_address TEXT,
    city TEXT,
    state TEXT,
    zip_code TEXT,
    google_place_id TEXT,
    linkedin_company_url TEXT,
    primary_contact_name TEXT,
    primary_contact_title TEXT,
    primary_contact_linkedin TEXT,
    qualification_score INTEGER DEFAULT 0,
    confidence_score INTEGER DEFAULT 0,
    outreach_priority_tier TEXT DEFAULT '',
    pipeline_stage TEXT DEFAULT 'seed',
    exclusion_reason TEXT DEFAULT '',
    starred INTEGER DEFAULT 0,
    marked_for_outreach INTEGER DEFAULT 0,
    contacted INTEGER DEFAULT 0,
    notes TEXT DEFAULT '',
    data_json TEXT,
    created_at TEXT,
    updated_at TEXT,
    search_run_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_category ON leads(category);
CREATE INDEX IF NOT EXISTS idx_leads_score ON leads(qualification_score);
CREATE INDEX IF NOT EXISTS idx_leads_domain ON leads(company_domain);
CREATE INDEX IF NOT EXISTS idx_leads_name ON leads(company_name_normalized);
CREATE INDEX IF NOT EXISTS idx_leads_tier ON leads(outreach_priority_tier);
CREATE INDEX IF NOT EXISTS idx_leads_run ON leads(search_run_id);

CREATE TABLE IF NOT EXISTS search_runs (
    id TEXT PRIMARY KEY,
    category TEXT,
    geography TEXT,
    query TEXT,
    source TEXT,
    results_found INTEGER DEFAULT 0,
    results_accepted INTEGER DEFAULT 0,
    results_rejected INTEGER DEFAULT 0,
    results_review INTEGER DEFAULT 0,
    started_at TEXT,
    completed_at TEXT,
    error TEXT DEFAULT '',
    status TEXT DEFAULT 'running',
    config_json TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS presets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    config_json TEXT NOT NULL,
    created_at TEXT
);
"""


class Database:
    def __init__(self, db_path: str = "./data/leads.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self):
        self.conn.close()

    # --- Leads ---

    def upsert_lead(self, lead: LeadRecord, search_run_id: str = ""):
        now = datetime.utcnow().isoformat()
        from app.utils.text import normalize_company_name, normalize_domain

        data_json = lead.model_dump_json()
        domain = normalize_domain(lead.company.website)
        name_norm = normalize_company_name(lead.company.name)

        self.conn.execute(
            """INSERT OR REPLACE INTO leads
            (id, record_type, status, category, subcategory,
             company_name, company_name_normalized, company_domain,
             company_phone, company_address, city, state, zip_code,
             google_place_id, linkedin_company_url,
             primary_contact_name, primary_contact_title, primary_contact_linkedin,
             qualification_score, confidence_score, outreach_priority_tier,
             pipeline_stage, exclusion_reason, notes, data_json,
             created_at, updated_at, search_run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                lead.id, lead.record_type, lead.status,
                lead.category, lead.subcategory,
                lead.company.name, name_norm, domain,
                lead.company.phone, lead.company.address,
                lead.company.city, lead.company.state, lead.company.zip_code,
                lead.company.google_place_id, lead.company.linkedin_company_url,
                lead.primary_contact.name if lead.primary_contact else "",
                lead.primary_contact.title if lead.primary_contact else "",
                lead.primary_contact.linkedin_url if lead.primary_contact else "",
                lead.qualification_score, lead.confidence_score,
                lead.outreach_priority_tier, lead.pipeline_stage,
                lead.exclusion_reason, lead.notes, data_json,
                lead.created_at.isoformat(), now, search_run_id,
            ),
        )
        self.conn.commit()

    def upsert_leads(self, leads: list[LeadRecord], search_run_id: str = ""):
        for lead in leads:
            self.upsert_lead(lead, search_run_id)

    def get_lead(self, lead_id: str) -> Optional[LeadRecord]:
        row = self.conn.execute(
            "SELECT data_json FROM leads WHERE id = ?", (lead_id,)
        ).fetchone()
        if row:
            return LeadRecord.model_validate_json(row["data_json"])
        return None

    def get_lead_with_ui_fields(self, lead_id: str) -> Optional[dict]:
        """Get lead with both parsed model and UI state fields (starred, etc.)."""
        row = self.conn.execute(
            "SELECT * FROM leads WHERE id = ?", (lead_id,)
        ).fetchone()
        if not row:
            return None
        lead = LeadRecord.model_validate_json(row["data_json"])
        return {
            "lead": lead,
            "starred": bool(row["starred"]),
            "marked_for_outreach": bool(row["marked_for_outreach"]),
            "contacted": bool(row["contacted"]),
            "notes": row["notes"],
        }

    def query_leads(
        self,
        status: str | None = None,
        category: str | None = None,
        state: str | None = None,
        min_score: int = 0,
        outreach_tier: str | None = None,
        search: str | None = None,
        starred_only: bool = False,
        outreach_only: bool = False,
        sort_by: str = "qualification_score",
        sort_dir: str = "DESC",
        limit: int = 200,
        offset: int = 0,
        search_run_id: str | None = None,
    ) -> list[LeadRecord]:
        conditions = []
        params: list = []

        if status:
            conditions.append("status = ?")
            params.append(status)
        if category:
            conditions.append("category = ?")
            params.append(category)
        if state:
            conditions.append("state = ?")
            params.append(state)
        if min_score > 0:
            conditions.append("qualification_score >= ?")
            params.append(min_score)
        if outreach_tier:
            conditions.append("outreach_priority_tier = ?")
            params.append(outreach_tier)
        if search:
            conditions.append("(company_name LIKE ? OR primary_contact_name LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])
        if starred_only:
            conditions.append("starred = 1")
        if outreach_only:
            conditions.append("marked_for_outreach = 1")
        if search_run_id:
            conditions.append("search_run_id = ?")
            params.append(search_run_id)

        where = " AND ".join(conditions) if conditions else "1=1"

        allowed_sorts = {
            "qualification_score", "confidence_score", "company_name",
            "created_at", "outreach_priority_tier",
        }
        if sort_by not in allowed_sorts:
            sort_by = "qualification_score"
        if sort_dir not in ("ASC", "DESC"):
            sort_dir = "DESC"

        rows = self.conn.execute(
            f"SELECT data_json FROM leads WHERE {where} ORDER BY {sort_by} {sort_dir} LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        return [LeadRecord.model_validate_json(r["data_json"]) for r in rows]

    def count_leads(self, status: str | None = None, category: str | None = None, search_run_id: str | None = None) -> int:
        conditions = []
        params: list = []
        if status:
            conditions.append("status = ?")
            params.append(status)
        if category:
            conditions.append("category = ?")
            params.append(category)
        if search_run_id:
            conditions.append("search_run_id = ?")
            params.append(search_run_id)
        where = " AND ".join(conditions) if conditions else "1=1"
        row = self.conn.execute(f"SELECT COUNT(*) as cnt FROM leads WHERE {where}", params).fetchone()
        return row["cnt"]

    def update_lead_status(self, lead_id: str, status: str):
        lead = self.get_lead(lead_id)
        if lead:
            lead.status = status
            self.upsert_lead(lead)

    def update_lead_flags(self, lead_id: str, starred: bool | None = None,
                          marked_for_outreach: bool | None = None,
                          contacted: bool | None = None, notes: str | None = None):
        updates = []
        params: list = []
        if starred is not None:
            updates.append("starred = ?")
            params.append(int(starred))
        if marked_for_outreach is not None:
            updates.append("marked_for_outreach = ?")
            params.append(int(marked_for_outreach))
        if contacted is not None:
            updates.append("contacted = ?")
            params.append(int(contacted))
        if notes is not None:
            updates.append("notes = ?")
            params.append(notes)
        if updates:
            updates.append("updated_at = ?")
            params.append(datetime.utcnow().isoformat())
            params.append(lead_id)
            self.conn.execute(
                f"UPDATE leads SET {', '.join(updates)} WHERE id = ?", params
            )
            self.conn.commit()

    def check_domain_exists(self, domain: str) -> bool:
        if not domain:
            return False
        row = self.conn.execute(
            "SELECT 1 FROM leads WHERE company_domain = ? LIMIT 1", (domain,)
        ).fetchone()
        return row is not None

    def check_name_exists(self, name_normalized: str) -> bool:
        if not name_normalized:
            return False
        row = self.conn.execute(
            "SELECT 1 FROM leads WHERE company_name_normalized = ? LIMIT 1", (name_normalized,)
        ).fetchone()
        return row is not None

    # --- Search Runs ---

    def save_search_run(self, run: SearchRun):
        self.conn.execute(
            """INSERT OR REPLACE INTO search_runs
            (id, category, geography, query, source,
             results_found, results_accepted, results_rejected, results_review,
             started_at, completed_at, error, status, config_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run.id, run.category, run.geography, run.query, run.source,
                run.results_found, run.results_accepted, run.results_rejected,
                run.results_review,
                run.started_at.isoformat() if run.started_at else None,
                run.completed_at.isoformat() if run.completed_at else None,
                run.error, "completed" if run.completed_at else "running", "{}",
            ),
        )
        self.conn.commit()

    def get_search_runs(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM search_runs ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_search_run(self, run_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM search_runs WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    def update_search_run(self, run_id: str, **kwargs):
        updates = []
        params: list = []
        for key, val in kwargs.items():
            updates.append(f"{key} = ?")
            params.append(val)
        if updates:
            params.append(run_id)
            self.conn.execute(
                f"UPDATE search_runs SET {', '.join(updates)} WHERE id = ?", params
            )
            self.conn.commit()

    # --- Presets ---

    def save_preset(self, preset_id: str, name: str, config: dict):
        self.conn.execute(
            "INSERT OR REPLACE INTO presets (id, name, config_json, created_at) VALUES (?, ?, ?, ?)",
            (preset_id, name, json.dumps(config), datetime.utcnow().isoformat()),
        )
        self.conn.commit()

    def get_presets(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM presets ORDER BY name").fetchall()
        return [{"id": r["id"], "name": r["name"], "config": json.loads(r["config_json"])} for r in rows]

    def delete_preset(self, preset_id: str):
        self.conn.execute("DELETE FROM presets WHERE id = ?", (preset_id,))
        self.conn.commit()

    # --- Whitelist / Blacklist ---

    def load_domain_list(self, filepath: str) -> set[str]:
        """Load a CSV list of domains (for whitelist/blacklist)."""
        domains = set()
        if not os.path.exists(filepath):
            return domains
        with open(filepath, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                d = row.get("domain", "").strip().lower()
                if d and not d.startswith("#"):
                    domains.add(d)
        return domains

    # --- Stats ---

    def get_stats(self, search_run_id: str | None = None) -> dict:
        cond = f"WHERE search_run_id = '{search_run_id}'" if search_run_id else ""
        stats = {}
        for status in ("accepted", "review_needed", "rejected"):
            row = self.conn.execute(
                f"SELECT COUNT(*) as cnt FROM leads {cond} {'AND' if cond else 'WHERE'} status = ?",
                (status,),
            ).fetchone()
            stats[status] = row["cnt"]
        stats["total"] = sum(stats.values())
        row = self.conn.execute(
            f"SELECT COUNT(*) as cnt FROM leads {cond} {'AND' if cond else 'WHERE'} starred = 1"
        ).fetchone()
        stats["starred"] = row["cnt"]
        row = self.conn.execute(
            f"SELECT COUNT(*) as cnt FROM leads {cond} {'AND' if cond else 'WHERE'} marked_for_outreach = 1"
        ).fetchone()
        stats["outreach"] = row["cnt"]
        return stats
