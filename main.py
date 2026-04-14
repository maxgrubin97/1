#!/usr/bin/env python3
"""
MGR Advisory — Client Lead Scraper

Scrapes LinkedIn (public profiles) and Google Maps to find potential
Fractional CFO clients: small-to-mid businesses ($1M-$15M revenue)
with decision-maker contact info.

Usage:
    # Run both scrapers with default tri-state locations
    python main.py

    # LinkedIn only
    python main.py --source linkedin

    # Google Maps only
    python main.py --source maps

    # Custom locations (override defaults)
    python main.py --locations "Miami, FL" "Austin, TX" "Denver, CO"

    # Limit industries (Google Maps)
    python main.py --industries "law firm" "medical practice" "marketing agency"

    # Quick test with fewer queries
    python main.py --max-queries 3

    # Custom output file
    python main.py --output my_leads.csv
"""

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

import config
from scrapers.linkedin import scrape_linkedin
from scrapers.google_maps import scrape_google_maps
from enricher import enrich_leads
from exporter import export_to_csv

load_dotenv()


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="MGR Advisory — Client Lead Scraper for Fractional CFO prospects",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                                          # Full tri-state scrape
  python main.py --source linkedin                        # LinkedIn only
  python main.py --source maps                            # Google Maps only
  python main.py --locations "Miami, FL" "Austin, TX"     # Custom locations
  python main.py --industries "law firm" "dental practice" # Specific industries
  python main.py --max-queries 5 --verbose                # Quick test, verbose
        """,
    )

    parser.add_argument(
        "--source",
        choices=["both", "linkedin", "maps"],
        default="both",
        help="Which scraper(s) to run (default: both)",
    )

    parser.add_argument(
        "--locations",
        nargs="+",
        default=None,
        help='Target locations (default: tri-state area). Example: --locations "Miami, FL" "Austin, TX"',
    )

    parser.add_argument(
        "--industries",
        nargs="+",
        default=None,
        help='Google Maps industry search terms to use (default: all). Example: --industries "law firm" "medical practice"',
    )

    parser.add_argument(
        "--linkedin-queries",
        nargs="+",
        default=None,
        help="Custom LinkedIn search queries (overrides defaults)",
    )

    parser.add_argument(
        "--max-queries",
        type=int,
        default=None,
        help="Limit the number of search queries to run (useful for testing)",
    )

    parser.add_argument(
        "--output",
        default="",
        help="Output CSV filename (default: leads_YYYYMMDD_HHMMSS.csv)",
    )

    parser.add_argument(
        "--output-dir",
        default="output",
        help="Output directory (default: output/)",
    )

    parser.add_argument(
        "--skip-enrichment",
        action="store_true",
        help="Skip the enrichment step (faster but less data)",
    )

    parser.add_argument(
        "--skip-dm-lookup",
        action="store_true",
        help="Skip decision-maker lookup for Google Maps results",
    )

    parser.add_argument(
        "--delay-min",
        type=float,
        default=config.REQUEST_DELAY_MIN,
        help=f"Min seconds between requests (default: {config.REQUEST_DELAY_MIN})",
    )

    parser.add_argument(
        "--delay-max",
        type=float,
        default=config.REQUEST_DELAY_MAX,
        help=f"Max seconds between requests (default: {config.REQUEST_DELAY_MAX})",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )

    return parser.parse_args()


def main():
    args = parse_args()
    setup_logging(args.verbose)

    logger = logging.getLogger(__name__)

    # Resolve API keys
    gmaps_key = os.getenv("GMAPS_API_KEY", "")
    serpapi_key = os.getenv("SERPAPI_KEY", "")

    # Resolve locations
    locations = args.locations or config.DEFAULT_LOCATIONS

    delay_range = (args.delay_min, args.delay_max)

    logger.info("=" * 60)
    logger.info("MGR Advisory — Client Lead Scraper")
    logger.info("=" * 60)
    logger.info(f"Source:    {args.source}")
    logger.info(f"Locations: {len(locations)} areas")
    logger.info(f"Delay:     {delay_range[0]}-{delay_range[1]}s between requests")
    if serpapi_key:
        logger.info("SerpAPI:   enabled (reliable search)")
    else:
        logger.info("SerpAPI:   not set (using direct Google search)")
    logger.info("=" * 60)

    all_leads = []

    # ---- LinkedIn scraping ----
    if args.source in ("both", "linkedin"):
        linkedin_queries = args.linkedin_queries or config.LINKEDIN_QUERIES
        if args.max_queries:
            linkedin_queries = linkedin_queries[: args.max_queries]

        logger.info(f"\n--- LinkedIn Scraping ({len(linkedin_queries)} queries x {len(locations)} locations) ---")

        linkedin_leads = scrape_linkedin(
            queries=linkedin_queries,
            locations=locations,
            max_results_per_query=config.MAX_RESULTS_PER_QUERY,
            delay_range=delay_range,
            serpapi_key=serpapi_key,
        )
        logger.info(f"LinkedIn: {len(linkedin_leads)} leads found")
        all_leads.extend(linkedin_leads)

    # ---- Google Maps scraping ----
    if args.source in ("both", "maps"):
        if not gmaps_key:
            logger.warning(
                "GMAPS_API_KEY not set — skipping Google Maps scraping. "
                "Set it in your .env file to enable Maps search."
            )
        else:
            # Determine which industries to search
            if args.industries:
                maps_queries = args.industries
            else:
                maps_queries = [term for term, _label in config.TARGET_INDUSTRIES]

            if args.max_queries:
                maps_queries = maps_queries[: args.max_queries]

            logger.info(f"\n--- Google Maps Scraping ({len(maps_queries)} industries x {len(locations)} locations) ---")

            maps_leads = scrape_google_maps(
                queries=maps_queries,
                locations=locations,
                api_key=gmaps_key,
                max_per_query=config.MAX_GMAPS_PER_QUERY,
                find_decision_makers=not args.skip_dm_lookup,
                serpapi_key=serpapi_key,
                delay_range=delay_range,
            )
            logger.info(f"Google Maps: {len(maps_leads)} leads found")
            all_leads.extend(maps_leads)

    if not all_leads:
        logger.warning("No leads found. Check your API keys and try again.")
        sys.exit(1)

    # ---- Enrichment ----
    if not args.skip_enrichment:
        logger.info(f"\n--- Enriching {len(all_leads)} leads ---")
        all_leads = enrich_leads(
            leads=all_leads,
            serpapi_key=serpapi_key,
            delay_range=delay_range,
        )

    # ---- Export ----
    logger.info(f"\n--- Exporting {len(all_leads)} leads ---")
    filepath = export_to_csv(
        leads=all_leads,
        output_dir=args.output_dir,
        filename=args.output,
    )

    logger.info(f"\nDone! Leads saved to: {filepath}")
    logger.info(f"Total leads with decision-maker info: {len(all_leads)}")


if __name__ == "__main__":
    main()
