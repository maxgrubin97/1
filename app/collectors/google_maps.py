"""
Google Maps collector.

Uses the official Google Places API for discovery and legitimacy signals.
Respects API terms of service and rate limits.
"""

import logging
from datetime import datetime

from app.models import LeadRecord, Evidence
from app.models.company import Company
from app.utils.http import google_places_search, google_place_details, rate_limit
from app.utils.text import (
    normalize_company_name, normalize_domain,
    extract_state_from_address, extract_zip_from_address,
)

logger = logging.getLogger(__name__)


def _classify_industry_from_types(types: list[str], name: str) -> str:
    """Map Google place types to industry label."""
    combined = " ".join(types).lower() + " " + name.lower()
    mapping = [
        (["lawyer", "attorney", "law"], "Legal"),
        (["accounting", "accountant", "cpa", "tax"], "Accounting / Finance"),
        (["doctor", "medical", "health", "hospital", "clinic"], "Healthcare"),
        (["dentist", "dental"], "Healthcare / Dental"),
        (["veterinary", "vet"], "Veterinary"),
        (["real_estate", "property"], "Real Estate"),
        (["construction", "contractor", "plumb", "hvac", "electric", "roof"], "Construction / Trades"),
        (["insurance"], "Insurance"),
        (["finance", "bank", "lending", "credit"], "Financial Services"),
        (["restaurant", "food", "catering"], "Hospitality"),
        (["gym", "fitness", "spa", "wellness"], "Fitness / Wellness"),
        (["consulting", "consultant", "advisory"], "Consulting"),
        (["marketing", "advertising", "agency", "creative", "design", "pr"], "Marketing / Agency"),
        (["staffing", "recruit", "employment"], "Staffing / Recruiting"),
        (["manufacturing", "factory", "industrial"], "Manufacturing"),
        (["logistics", "shipping", "freight", "warehouse"], "Logistics"),
        (["cleaning", "janitorial", "maid"], "Facility Services"),
        (["landscap", "lawn", "garden"], "Landscaping"),
        (["security", "guard"], "Security"),
        (["auto", "car", "vehicle"], "Automotive"),
        (["engineer"], "Engineering"),
        (["architect"], "Architecture"),
    ]
    for keywords, industry in mapping:
        if any(kw in combined for kw in keywords):
            return industry
    return "Small Business"


def collect_from_google_maps(
    query: str,
    api_key: str,
    category: str = "",
    location: str = "",
    delay_range: tuple[float, float] = (1.0, 3.0),
    max_results: int = 20,
) -> list[LeadRecord]:
    """
    Search Google Maps and return LeadRecords with basic company info.

    This is Stage 1 (seed discovery). Records are created with pipeline_stage='seed'.
    """
    if not api_key:
        logger.warning("No GMAPS_API_KEY set — skipping Google Maps collection")
        return []

    logger.info(f"[Maps] Searching: {query}")
    data = google_places_search(query, api_key)
    results = data.get("results", [])[:max_results]

    leads = []
    for place in results:
        place_id = place.get("place_id", "")
        if not place_id:
            continue

        # Skip permanently closed
        if place.get("business_status") == "CLOSED_PERMANENTLY":
            continue

        # Get details
        details = google_place_details(place_id, api_key)
        if not details:
            details = place

        name = details.get("name", place.get("name", ""))
        address = details.get("formatted_address", place.get("formatted_address", ""))
        phone = details.get("formatted_phone_number", "")
        website = details.get("website", "")
        rating = details.get("rating", place.get("rating"))
        review_count = details.get("user_ratings_total", place.get("user_ratings_total", 0))
        types = place.get("types", [])
        maps_url = details.get("url", "")

        industry = _classify_industry_from_types(types, name)

        company = Company(
            name=name,
            name_normalized=normalize_company_name(name),
            website=website,
            website_domain=normalize_domain(website),
            phone=phone,
            address=address,
            city=location.split(",")[0].strip() if location else "",
            state=extract_state_from_address(address),
            zip_code=extract_zip_from_address(address),
            google_maps_url=maps_url,
            google_place_id=place_id,
            google_rating=rating,
            google_review_count=review_count or 0,
            primary_industry=industry,
            google_categories=types,
            collected_at=datetime.utcnow(),
        )

        lead = LeadRecord(
            company=company,
            category=category,
            pipeline_stage="seed",
            source_urls=[maps_url] if maps_url else [],
        )

        lead.add_evidence(
            claim=f"Found on Google Maps as '{name}'",
            source_url=maps_url,
            source_type="google_maps",
            snippet=f"Rating: {rating}, Reviews: {review_count}, Types: {', '.join(types[:3])}",
            confidence=0.7,
        )

        leads.append(lead)
        logger.info(f"  [Maps] {name} | {industry} | {rating}* ({review_count} reviews)")
        rate_limit(*delay_range)

    logger.info(f"  [Maps] Collected {len(leads)} records")
    return leads
