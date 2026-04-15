# MGR Advisory Lead Engine

Production-grade lead sourcing and referral partner discovery system for MGR Advisory.

A high-precision pipeline that identifies qualified direct prospects and referral partners for fractional CFO services, optimized for quality over volume.

## Quick Start

### 1. Install

```bash
pip install -r requirements.txt
```

Or with pip and pyproject.toml:
```bash
pip install -e .
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` and add your API keys:
- **`GMAPS_API_KEY`** (required for Google Maps discovery) — [Get one here](https://console.cloud.google.com/apis/credentials)
- **`SERPAPI_KEY`** (optional, for reliable search) — [Get one here](https://serpapi.com)

### 3. Launch the Dashboard

```bash
python -m app.cli.commands serve
```

Open **http://localhost:8000** in your browser.

### 4. Run Your First Search

From the dashboard:
1. Select a category (e.g., "SBA Lenders")
2. Select a geography (e.g., "Nassau County, NY")
3. Click **Run Search**
4. Review results when complete

Or from the terminal:
```bash
python -m app.cli.commands run-pipeline --category sba_lenders --geo "Nassau County, NY"
```

### 5. Export Results

From the Export Center page, or:
```bash
python -m app.cli.commands export --format excel
```

Exported files are saved to the `output/` directory.

### 6. Stop the App

Press `Ctrl+C` in the terminal running the server.

## Architecture

```
Seed Discovery → Classification → Enrichment → Scoring → Deduplication → Export
     ↓                ↓               ↓            ↓            ↓
 Google Maps      Hard filters    Website +     Category-    Merge by
 + Public web     Noise control   LinkedIn      specific     domain/name
                                  contacts      sub-models   /phone
```

### Pipeline Stages (Incremental)

1. **Seed Discovery** — Google Maps API search by category + geography
2. **First-Pass Classification** — Hard exclusion filters, noise control
3. **Enrichment** — Website parsing, contact extraction (ONLY promising records)
4. **Re-classification + Scoring** — Category-specific weighted scoring
5. **Deduplication** — Merge by domain, name, phone, LinkedIn URL
6. **Export** — Save to SQLite, optionally export CSV/Excel/JSON

### Precision-First Approach

- Default: **25 best results per category per geography**
- Top 25 are meaningfully stronger than results 26-100
- Low-confidence records go to review queue, never force-classified
- Every score includes machine-readable breakdown and rationale

## Project Structure

```
app/
├── config/           # YAML configuration files
│   ├── geographies.yaml    # Location tiers
│   ├── categories.yaml     # Category definitions + search queries
│   ├── scoring_weights.yaml # Scoring weights + thresholds
│   ├── keywords.yaml       # Title, industry, exclusion keywords
│   ├── personas.yaml       # Category-specific persona matrices
│   └── settings.py         # Configuration loader
├── models/           # Pydantic data models
├── collectors/       # Data collection modules
│   ├── google_maps.py      # Google Places API
│   ├── linkedin_public.py  # Public LinkedIn discovery
│   ├── website.py          # Website content extraction
│   ├── csv_import.py       # CSV import (Sales Nav, Apollo, etc.)
│   └── query_generator.py  # Search query generation
├── parsers/          # Content parsing
│   ├── contact_parser.py   # Team page contact extraction
│   └── website_parser.py   # Website signal extraction
├── classifiers/      # Classification + noise control
├── scorers/          # Category-specific scoring
├── enrichers/        # Data enrichment
├── dedupe/           # Deduplication engine
├── storage/          # SQLite persistence
├── exporters/        # CSV, Excel, JSON export
├── pipeline/         # Pipeline orchestrator
├── cli/              # CLI commands (Typer)
└── web/              # FastAPI dashboard
    ├── main.py             # Routes
    ├── templates/          # Jinja2 HTML templates
    └── static/             # CSS
data/
├── leads.db                # SQLite database (auto-created)
├── always_include_domains.csv  # Whitelist
├── always_exclude_domains.csv  # Blacklist
└── competitor_domains.csv      # Competitor domains
tests/                # Test suite
output/               # Export files
```

## CLI Commands

```bash
# Run full pipeline
python -m app.cli.commands run-pipeline -c sba_lenders -g "Nassau County, NY" -l 25

# Import CSV
python -m app.cli.commands import-csv leads.csv -t referral_partner -c sba_lenders

# Export
python -m app.cli.commands export -f excel
python -m app.cli.commands export -f csv --status accepted

# Review report
python -m app.cli.commands review-report

# List categories
python -m app.cli.commands list-categories

# List locations
python -m app.cli.commands list-locations

# Start web dashboard
python -m app.cli.commands serve
```

## Category Presets

### Referral Partners
- SBA Lenders
- Business Brokers
- Boutique Corporate Attorneys
- Boutique CPA Firms (low CFO overlap)
- Wealth Managers / RIAs
- Commercial Bankers (SMB focus)
- Valuation / Exit Planning Advisors

### Direct Prospects
- Construction & Skilled Trades
- Healthcare Practices
- Professional Services Firms
- Real Estate Operating Businesses
- Agencies & B2B Services
- Multi-Location Service Businesses

## Configuration

### Adding Geographies

Edit `app/config/geographies.yaml`:
```yaml
tier_1:
  locations:
    - name: "Miami, FL"
      state: "FL"
      county: "Miami-Dade County"
```

### Changing Scoring Weights

Edit `app/config/scoring_weights.yaml` to adjust point allocations.
Category-specific sub-model weights are in `app/config/personas.yaml`.

### Adding Categories

Edit `app/config/categories.yaml` and `app/config/personas.yaml`.

## Web Dashboard Pages

| Page | URL | Purpose |
|------|-----|---------|
| Dashboard | `/` | Run searches, use presets |
| Results | `/results` | Browse and filter leads |
| Lead Detail | `/lead/{id}` | Full lead profile + outreach guidance |
| Review Queue | `/review` | Triage borderline records |
| Export Center | `/export-center` | Download files |
| Import List | `/import` | Upload CSV files |
| Search History | `/history` | Past runs |
| Settings | `/settings` | View configuration |

## Data Sources

| Source | Method | API Key Required |
|--------|--------|-----------------|
| Google Maps | Official Places API | Yes (`GMAPS_API_KEY`) |
| LinkedIn | Public Google search discovery | No |
| Company websites | Direct HTTP with robots.txt | No |
| CSV imports | File upload | No |
| SerpAPI | Paid search API (optional) | Yes (`SERPAPI_KEY`) |

## Running Tests

```bash
pip install pytest
python -m pytest tests/ -v
```
