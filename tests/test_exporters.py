"""Tests for export functionality."""

import os
import json
import tempfile

from app.exporters.exporter import export_csv, export_json
from app.models import LeadRecord
from app.models.company import Company
from app.models.contact import Contact


def test_csv_export():
    leads = [
        LeadRecord(
            record_type="referral_partner",
            category="sba_lenders",
            status="accepted",
            company=Company(name="Test Bank", city="NYC", state="NY"),
            primary_contact=Contact(name="John Doe", title="VP SBA"),
            qualification_score=85,
        )
    ]
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        path = f.name

    try:
        export_csv(leads, path)
        assert os.path.exists(path)
        with open(path) as f:
            content = f.read()
        assert "Test Bank" in content
        assert "John Doe" in content
    finally:
        os.unlink(path)


def test_json_export():
    leads = [
        LeadRecord(
            record_type="direct_prospect",
            category="construction_trades",
            company=Company(name="Build Corp"),
            qualification_score=72,
        )
    ]
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name

    try:
        export_json(leads, path)
        assert os.path.exists(path)
        with open(path) as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["company"]["name"] == "Build Corp"
    finally:
        os.unlink(path)
