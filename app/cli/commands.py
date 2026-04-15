"""
CLI commands for the MGR Advisory Lead Engine.

Usage:
    python -m app.cli.commands run-pipeline --category sba_lenders --geo "Nassau County, NY"
    python -m app.cli.commands import-csv leads.csv --type referral_partner
    python -m app.cli.commands export --format excel
    python -m app.cli.commands review-report
    python -m app.cli.commands serve
"""

import logging
import sys
from datetime import datetime

import typer
from rich.console import Console
from rich.table import Table

from app.config.settings import get_settings
from app.pipeline.runner import PipelineRunner
from app.storage.database import Database
from app.collectors.csv_import import import_csv
from app.exporters.exporter import export_csv, export_excel, export_json

app = typer.Typer(
    name="mgr",
    help="MGR Advisory Lead Engine — Fractional CFO prospecting and referral sourcing",
    no_args_is_help=True,
)
console = Console()


def _setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


@app.command("run-pipeline")
def run_pipeline(
    category: str = typer.Option(..., "--category", "-c", help="Category key (e.g., sba_lenders, construction_trades)"),
    geo: str = typer.Option("", "--geo", "-g", help="Geography filter (e.g., 'Nassau County, NY'). Comma-separated for multiple."),
    limit: int = typer.Option(25, "--limit", "-l", help="Max results per category per geography"),
    source: str = typer.Option("google_maps", "--source", "-s", help="Data source(s): google_maps, web_search, both"),
    strict: bool = typer.Option(False, "--strict", help="Only return accepted records"),
    no_enrich: bool = typer.Option(False, "--no-enrich", help="Skip contact enrichment"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
):
    """Run the full lead sourcing pipeline for a category and geography."""
    _setup_logging(verbose)
    settings = get_settings()

    # Parse locations
    locations = None
    if geo:
        locations = [g.strip() for g in geo.split(",")]
    else:
        locations = settings.get_location_names(["tier_1"])

    # Parse sources
    sources = []
    if source in ("both", "all"):
        sources = ["google_maps", "web_search"]
    else:
        sources = [s.strip() for s in source.split(",")]

    console.print(f"\n[bold]MGR Advisory Lead Engine[/bold]")
    console.print(f"Category: [cyan]{category}[/cyan]")
    console.print(f"Locations: [cyan]{', '.join(locations[:5])}{'...' if len(locations) > 5 else ''}[/cyan]")
    console.print(f"Limit: [cyan]{limit}[/cyan]")
    console.print(f"Sources: [cyan]{', '.join(sources)}[/cyan]")
    console.print()

    runner = PipelineRunner(settings)
    stats = runner.run(
        category=category,
        locations=locations,
        limit=limit,
        sources=sources,
        enrich_contacts=not no_enrich,
        strict_mode=strict,
    )

    # Print results
    console.print(f"\n[bold green]Pipeline Complete[/bold green]")
    table = Table(title="Results Summary")
    table.add_column("Metric", style="bold")
    table.add_column("Count", justify="right")
    table.add_row("Discovered", str(stats["discovered"]))
    table.add_row("Accepted", f"[green]{stats['accepted']}[/green]")
    table.add_row("Needs Review", f"[yellow]{stats['review']}[/yellow]")
    table.add_row("Rejected", f"[red]{stats['rejected']}[/red]")
    table.add_row("Duplicates Merged", str(stats["duplicates_merged"]))
    console.print(table)
    console.print(f"\nRun ID: {stats['run_id']}")
    console.print(f"View results: python -m app.cli.commands export --run-id {stats['run_id']}")


@app.command("import-csv")
def import_csv_cmd(
    filepath: str = typer.Argument(..., help="Path to CSV file"),
    record_type: str = typer.Option("referral_partner", "--type", "-t", help="Record type: referral_partner or direct_prospect"),
    category: str = typer.Option("imported", "--category", "-c", help="Category to assign"),
    format_hint: str = typer.Option("auto", "--format", "-f", help="Format: auto, linkedin_sales_navigator, apollo, generic"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Import a CSV file (LinkedIn, Apollo, or manual list)."""
    _setup_logging(verbose)
    settings = get_settings()

    leads = import_csv(filepath, record_type, category, format_hint)
    if not leads:
        console.print("[red]No records imported.[/red]")
        return

    db = Database(settings.database_path)
    db.upsert_leads(leads)
    console.print(f"[green]Imported {len(leads)} records from {filepath}[/green]")


@app.command("export")
def export_cmd(
    format: str = typer.Option("excel", "--format", "-f", help="Export format: csv, excel, json"),
    status: str = typer.Option("", "--status", "-s", help="Filter by status: accepted, review_needed, rejected"),
    category: str = typer.Option("", "--category", "-c", help="Filter by category"),
    run_id: str = typer.Option("", "--run-id", help="Filter by search run ID"),
    output: str = typer.Option("", "--output", "-o", help="Output file path"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Export leads to CSV, Excel, or JSON."""
    _setup_logging(verbose)
    settings = get_settings()
    db = Database(settings.database_path)

    leads = db.query_leads(
        status=status or None,
        category=category or None,
        search_run_id=run_id or None,
        limit=5000,
    )

    if not leads:
        console.print("[yellow]No leads found matching filters.[/yellow]")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = "output"

    if format == "csv":
        path = output or f"{out_dir}/leads_{timestamp}.csv"
        export_csv(leads, path)
    elif format == "json":
        path = output or f"{out_dir}/leads_{timestamp}.json"
        export_json(leads, path)
    else:
        path = output or f"{out_dir}/leads_{timestamp}.xlsx"
        export_excel(leads, path)

    console.print(f"[green]Exported {len(leads)} leads to {path}[/green]")


@app.command("review-report")
def review_report(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Show a summary of records needing review."""
    _setup_logging(verbose)
    settings = get_settings()
    db = Database(settings.database_path)

    stats = db.get_stats()
    console.print(f"\n[bold]Lead Database Summary[/bold]")

    table = Table()
    table.add_column("Status", style="bold")
    table.add_column("Count", justify="right")
    table.add_row("Accepted", f"[green]{stats.get('accepted', 0)}[/green]")
    table.add_row("Needs Review", f"[yellow]{stats.get('review_needed', 0)}[/yellow]")
    table.add_row("Rejected", f"[red]{stats.get('rejected', 0)}[/red]")
    table.add_row("Starred", str(stats.get("starred", 0)))
    table.add_row("Marked for Outreach", str(stats.get("outreach", 0)))
    table.add_row("Total", f"[bold]{stats.get('total', 0)}[/bold]")
    console.print(table)

    # Show review items
    review_leads = db.query_leads(status="review_needed", limit=20)
    if review_leads:
        console.print(f"\n[bold yellow]Top Review Items ({len(review_leads)}):[/bold yellow]")
        for lead in review_leads[:10]:
            reasons = ", ".join(lead.review_evidence_against[:2]) or "Needs manual review"
            next_step = lead.review_suggested_next_step or "Check website"
            console.print(f"  • {lead.company.name} ({lead.category}) — {reasons}")
            console.print(f"    → Next step: {next_step}")


@app.command("serve")
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind to"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload for development"),
):
    """Start the web dashboard."""
    console.print(f"\n[bold]MGR Advisory Lead Engine — Dashboard[/bold]")
    console.print(f"Starting at http://{host}:{port}")
    console.print(f"Press Ctrl+C to stop\n")

    import uvicorn
    uvicorn.run(
        "app.web.main:web_app",
        host=host,
        port=port,
        reload=reload,
    )


@app.command("list-categories")
def list_categories():
    """List all available categories."""
    settings = get_settings()
    console.print("\n[bold]Referral Partner Categories:[/bold]")
    for key in settings.get_referral_partner_keys():
        cat = settings.get_category(key)
        console.print(f"  • {key}: {cat.get('label', key)}")

    console.print("\n[bold]Direct Prospect Categories:[/bold]")
    for key in settings.get_direct_prospect_keys():
        cat = settings.get_category(key)
        console.print(f"  • {key}: {cat.get('label', key)}")


@app.command("list-locations")
def list_locations():
    """List all configured geographies."""
    settings = get_settings()
    for tier in ["tier_1", "tier_2", "tier_3"]:
        locs = settings.get_locations([tier])
        if locs:
            label = settings.geographies.get("tiers", {}).get(tier, {}).get("label", tier)
            console.print(f"\n[bold]{label} ({tier}):[/bold]")
            for loc in locs:
                aliases = ", ".join(loc.get("aliases", [])[:3])
                alias_str = f" (also: {aliases})" if aliases else ""
                console.print(f"  • {loc['name']}{alias_str}")


if __name__ == "__main__":
    app()
