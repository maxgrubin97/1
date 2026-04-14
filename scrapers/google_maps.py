"""
Google Maps scraper using the Places API.

Finds businesses matching target criteria and enriches them
with decision-maker data from LinkedIn public profiles.
"""

import logging
import random
import re
import time
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from models import Lead, classify_role

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Google Places API helpers
# ---------------------------------------------------------------------------


def _places_text_search(query: str, api_key: str, page_token: str = "") -> dict:
    """Run a Places API Text Search."""
    params = {"query": query, "key": api_key}
    if page_token:
        params["pagetoken"] = page_token
    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/place/textsearch/json",
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.warning(f"Places text search failed: {e}")
        return {}


def _place_details(place_id: str, api_key: str) -> dict:
    """Fetch detailed info for a single place."""
    fields = "name,formatted_address,formatted_phone_number,website,rating,user_ratings_total,types,business_status,url"
    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/place/details/json",
            params={"place_id": place_id, "fields": fields, "key": api_key},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("result", {})
    except requests.RequestException as e:
        logger.warning(f"Place details failed for {place_id}: {e}")
        return {}


def _classify_industry(types: list[str], name: str) -> str:
    """Map Google place types to a human-readable industry."""
    type_map = {
        "lawyer": "Legal / Law Firm",
        "law": "Legal / Law Firm",
        "attorney": "Legal / Law Firm",
        "accounting": "Accounting / Finance",
        "finance": "Accounting / Finance",
        "insurance": "Insurance",
        "real_estate_agency": "Real Estate",
        "real estate": "Real Estate",
        "doctor": "Healthcare",
        "dentist": "Healthcare / Dental",
        "health": "Healthcare",
        "hospital": "Healthcare",
        "physiotherapist": "Healthcare",
        "veterinary": "Veterinary",
        "restaurant": "Hospitality / Restaurant",
        "construction": "Construction",
        "contractor": "Construction",
        "plumber": "Construction / Trades",
        "electrician": "Construction / Trades",
        "roofing": "Construction / Trades",
        "manufacturing": "Manufacturing",
        "store": "Retail",
        "car_dealer": "Automotive",
        "car_repair": "Automotive",
        "gym": "Fitness / Wellness",
        "spa": "Fitness / Wellness",
        "lodging": "Hospitality",
        "travel_agency": "Travel",
        "marketing": "Marketing / Advertising",
        "consulting": "Consulting",
        "staffing": "Staffing / Recruiting",
        "technology": "Technology",
        "software": "Technology / SaaS",
    }

    combined = " ".join(types).lower() + " " + name.lower()
    for keyword, industry in type_map.items():
        if keyword in combined:
            return industry
    return "Small Business"


# ---------------------------------------------------------------------------
# Decision-maker lookup for a company
# ---------------------------------------------------------------------------

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


def _find_decision_maker(
    company_name: str,
    location: str,
    serpapi_key: str = "",
    delay_range: tuple[float, float] = (2.0, 4.0),
) -> dict:
    """
    Search Google for the company's decision maker on LinkedIn.
    Returns dict with name, title, linkedin_url, role_type.
    """
    dm_titles = '"CEO" OR "founder" OR "owner" OR "president" OR "managing partner"'
    query = f'site:linkedin.com/in/ "{company_name}" {dm_titles} "{location}"'

    result = {"name": "", "title": "", "linkedin_url": "", "role_type": ""}

    # Try SerpAPI
    if serpapi_key:
        try:
            resp = requests.get(
                "https://serpapi.com/search",
                params={"q": query, "num": 5, "api_key": serpapi_key, "engine": "google"},
                timeout=15,
            )
            resp.raise_for_status()
            organic = resp.json().get("organic_results", [])
            for r in organic:
                link = r.get("link", "")
                if "linkedin.com/in/" not in link:
                    continue
                title_text = r.get("title", "")
                title_text = re.sub(r"\s*[|–-]\s*LinkedIn\s*$", "", title_text).strip()
                parts = re.split(r"\s*[–-]\s*", title_text, maxsplit=2)
                result["name"] = parts[0].strip() if parts else ""
                result["title"] = parts[1].strip() if len(parts) > 1 else ""
                result["linkedin_url"] = link
                result["role_type"] = classify_role(result["title"])
                break
            time.sleep(random.uniform(*delay_range))
            return result
        except Exception as e:
            logger.debug(f"SerpAPI DM lookup failed: {e}")

    # Fallback to direct Google search
    try:
        url = f"https://www.google.com/search?q={quote_plus(query)}&num=5&hl=en"
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for el in soup.select("div.g"):
            link_el = el.select_one("a[href]")
            if not link_el:
                continue
            href = link_el.get("href", "")
            if "linkedin.com/in/" not in href:
                continue
            title_el = el.select_one("h3")
            if not title_el:
                continue
            title_text = re.sub(r"\s*[|–-]\s*LinkedIn\s*$", "", title_el.get_text(strip=True)).strip()
            parts = re.split(r"\s*[–-]\s*", title_text, maxsplit=2)
            result["name"] = parts[0].strip() if parts else ""
            result["title"] = parts[1].strip() if len(parts) > 1 else ""
            result["linkedin_url"] = href.split("&sa=")[0].split("&ved=")[0]
            result["role_type"] = classify_role(result["title"])
            break
    except Exception as e:
        logger.debug(f"Google DM lookup failed: {e}")

    time.sleep(random.uniform(*delay_range))
    return result


# ---------------------------------------------------------------------------
# Main scraper
# ---------------------------------------------------------------------------


def scrape_google_maps(
    queries: list[str],
    locations: list[str],
    api_key: str,
    max_per_query: int = 20,
    find_decision_makers: bool = True,
    serpapi_key: str = "",
    delay_range: tuple[float, float] = (1.0, 3.0),
) -> list[Lead]:
    """
    Search Google Maps for businesses and optionally find their decision makers.

    Args:
        queries: Business type search terms (e.g. "marketing agency").
        locations: Locations to append to each query.
        api_key: Google Maps Places API key.
        max_per_query: Max businesses to process per query+location.
        find_decision_makers: Whether to do LinkedIn lookup per business.
        serpapi_key: Optional SerpAPI key for DM lookups.
        delay_range: Seconds to wait between API calls.

    Returns:
        List of Lead objects with business + decision-maker info.
    """
    if not api_key:
        logger.error("Google Maps API key is required. Set GMAPS_API_KEY in your .env file.")
        return []

    all_leads: list[Lead] = []
    seen_places: set[str] = set()
    total_combos = len(queries) * len(locations)
    current = 0

    for search_term in queries:
        for location in locations:
            current += 1
            full_query = f"{search_term} in {location}"
            logger.info(f"[{current}/{total_combos}] Maps search: {full_query}")

            data = _places_text_search(full_query, api_key)
            results = data.get("results", [])[:max_per_query]

            for place in results:
                place_id = place.get("place_id", "")
                if place_id in seen_places:
                    continue
                seen_places.add(place_id)

                # Skip permanently closed
                if place.get("business_status") == "CLOSED_PERMANENTLY":
                    continue

                # Get detailed info
                details = _place_details(place_id, api_key)
                if not details:
                    details = place  # Use basic info if details fail

                company_name = details.get("name", place.get("name", ""))
                address = details.get("formatted_address", place.get("formatted_address", ""))
                phone = details.get("formatted_phone_number", "")
                website = details.get("website", "")
                rating = str(details.get("rating", place.get("rating", "")))
                review_count = str(details.get("user_ratings_total", place.get("user_ratings_total", "")))
                types = place.get("types", [])

                industry = _classify_industry(types, company_name)

                lead = Lead(
                    company=company_name,
                    location=location,
                    gmaps_address=address,
                    phone=phone,
                    website=website,
                    gmaps_rating=rating,
                    gmaps_review_count=review_count,
                    industry=industry,
                    source="google_maps",
                )

                # Find the decision maker
                if find_decision_makers:
                    dm = _find_decision_maker(company_name, location, serpapi_key, delay_range)
                    if dm["name"]:
                        lead.name = dm["name"]
                        lead.title = dm["title"]
                        lead.linkedin_url = dm["linkedin_url"]
                        lead.role_type = dm["role_type"]
                        logger.info(
                            f"  [Maps] {company_name} -> DM: {dm['name']} ({dm['title']})"
                        )
                    else:
                        logger.info(f"  [Maps] {company_name} -> No DM found (will retry in enrichment)")

                all_leads.append(lead)
                time.sleep(random.uniform(*delay_range))

            logger.info(f"  -> {len(all_leads)} total leads")

    logger.info(f"Google Maps scraping complete: {len(all_leads)} leads")
    return all_leads
