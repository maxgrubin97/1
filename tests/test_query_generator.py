"""Tests for query generation."""

from app.collectors.query_generator import generate_queries, generate_linkedin_queries
from app.config.settings import Settings


def test_generate_queries():
    s = Settings()
    queries = generate_queries("sba_lenders", ["Nassau County, NY"], s)
    assert len(queries) > 0
    assert all(q["category"] == "sba_lenders" for q in queries)
    assert all("Nassau County" in q["query"] for q in queries)


def test_generate_queries_multiple_locations():
    s = Settings()
    queries = generate_queries("sba_lenders", ["Nassau County, NY", "Manhattan, NY"], s)
    locations_found = {q["location"] for q in queries}
    assert "Nassau County, NY" in locations_found
    assert "Manhattan, NY" in locations_found


def test_generate_queries_with_limit():
    s = Settings()
    queries = generate_queries("sba_lenders", ["Nassau County, NY"], s, max_queries=3)
    assert len(queries) == 3


def test_linkedin_queries():
    s = Settings()
    queries = generate_linkedin_queries("sba_lenders", ["Nassau County, NY"], s)
    assert len(queries) > 0
    assert all("site:linkedin.com/in/" in q["query"] for q in queries)
