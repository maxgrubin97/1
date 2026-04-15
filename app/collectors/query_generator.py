"""
Search query generator.

Produces precise search strings by combining category definitions,
geography, and modifier dictionaries. All queries are geography-aware.
"""

import logging
from app.config.settings import Settings

logger = logging.getLogger(__name__)


def generate_queries(
    category_key: str,
    locations: list[str],
    settings: Settings,
    max_queries: int | None = None,
) -> list[dict]:
    """
    Generate search queries for a given category across locations.

    Returns:
        List of dicts: {"query": str, "category": str, "location": str, "source": str}
    """
    cat = settings.get_category(category_key)
    search_queries = cat.get("search_queries", [])
    modifiers = cat.get("modifiers", [])

    results = []

    for base_query in search_queries:
        for location in locations:
            # Base query + location
            q = f"{base_query} {location}"
            results.append({
                "query": q,
                "category": category_key,
                "location": location,
                "source": "google_maps",
            })

            # With modifiers (only first 2 to avoid explosion)
            for mod in modifiers[:2]:
                q_mod = f"{base_query} {mod} {location}"
                results.append({
                    "query": q_mod,
                    "category": category_key,
                    "location": location,
                    "source": "web_search",
                })

    if max_queries:
        results = results[:max_queries]

    logger.info(f"Generated {len(results)} queries for {category_key} x {len(locations)} locations")
    return results


def generate_linkedin_queries(
    category_key: str,
    locations: list[str],
    settings: Settings,
    max_queries: int | None = None,
) -> list[dict]:
    """
    Generate LinkedIn discovery queries (via Google site:linkedin.com).

    Uses category-specific priority titles to find decision makers.
    """
    cat = settings.get_category(category_key)
    priority_titles = cat.get("priority_titles", [])
    label = cat.get("label", category_key)

    results = []

    # Build title groups (batch 3 titles per query to reduce volume)
    title_groups = []
    for i in range(0, len(priority_titles), 3):
        group = priority_titles[i:i + 3]
        title_or = " OR ".join(f'"{t}"' for t in group)
        title_groups.append(title_or)

    for title_group in title_groups:
        for location in locations:
            q = f'site:linkedin.com/in/ {title_group} "{location}"'
            results.append({
                "query": q,
                "category": category_key,
                "location": location,
                "source": "linkedin_public",
            })

    if max_queries:
        results = results[:max_queries]

    logger.info(f"Generated {len(results)} LinkedIn queries for {category_key}")
    return results
