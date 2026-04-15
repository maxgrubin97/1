"""
Central configuration loader.

Reads YAML config files and environment variables into a single Settings object.
All pipeline components receive configuration through this module.
"""

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

CONFIG_DIR = Path(__file__).parent


def _load_yaml(filename: str) -> dict:
    path = CONFIG_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f) or {}


class Settings:
    """Immutable settings object built from YAML configs + env vars."""

    def __init__(self):
        self.geographies = _load_yaml("geographies.yaml")
        self.categories = _load_yaml("categories.yaml")
        self.scoring_weights = _load_yaml("scoring_weights.yaml")
        self.keywords = _load_yaml("keywords.yaml")

        # API keys
        self.gmaps_api_key: str = os.getenv("GMAPS_API_KEY", "")
        self.serpapi_key: str = os.getenv("SERPAPI_KEY", "")

        # Database
        self.database_path: str = os.getenv("DATABASE_PATH", "./data/leads.db")

        # Rate limiting
        self.delay_min: float = float(os.getenv("REQUEST_DELAY_MIN", "2.0"))
        self.delay_max: float = float(os.getenv("REQUEST_DELAY_MAX", "5.0"))

        # Logging
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")

        # Runtime mode: premium | hybrid | no_key (auto-detected if not set)
        explicit_mode = os.getenv("RUNTIME_MODE", "").lower()
        if explicit_mode in ("premium", "hybrid", "no_key"):
            self.runtime_mode: str = explicit_mode
        else:
            self.runtime_mode = self._detect_runtime_mode()

    def _detect_runtime_mode(self) -> str:
        """Auto-detect runtime mode from available API keys."""
        has_gmaps = bool(self.gmaps_api_key)
        has_serpapi = bool(self.serpapi_key)
        if has_gmaps and has_serpapi:
            return "premium"
        elif has_gmaps or has_serpapi:
            return "hybrid"
        else:
            return "no_key"

    def get_effective_thresholds(self) -> dict:
        """Return thresholds adjusted for runtime mode."""
        base = dict(self.get_thresholds())
        if self.runtime_mode == "no_key":
            base["auto_accept_min"] = max(base.get("auto_accept_min", 80), 85)
        return base

    # --- Geography helpers ---

    def get_locations(self, tiers: list[str] | None = None) -> list[dict]:
        """Return location dicts for the requested tiers."""
        if tiers is None:
            tiers = ["tier_1"]
        locations = []
        for tier_key in tiers:
            tier_data = self.geographies.get("tiers", {}).get(tier_key, {})
            locations.extend(tier_data.get("locations", []))
        return locations

    def get_location_names(self, tiers: list[str] | None = None) -> list[str]:
        """Return flat list of location name strings."""
        return [loc["name"] for loc in self.get_locations(tiers)]

    # --- Category helpers ---

    def get_category(self, category_key: str) -> dict:
        """Look up a category definition by key across referral_partners and direct_prospects."""
        for group in ("referral_partners", "direct_prospects"):
            cats = self.categories.get(group, {})
            if category_key in cats:
                return cats[category_key]
        raise KeyError(f"Unknown category: {category_key}")

    def get_all_category_keys(self) -> list[str]:
        """Return all category keys."""
        keys = []
        for group in ("referral_partners", "direct_prospects"):
            keys.extend(self.categories.get(group, {}).keys())
        return keys

    def get_referral_partner_keys(self) -> list[str]:
        return list(self.categories.get("referral_partners", {}).keys())

    def get_direct_prospect_keys(self) -> list[str]:
        return list(self.categories.get("direct_prospects", {}).keys())

    # --- Scoring helpers ---

    def get_scoring_weights(self, record_type: str) -> dict[str, int]:
        return self.scoring_weights.get(record_type, {})

    def get_thresholds(self) -> dict:
        return self.scoring_weights.get("thresholds", {})

    def get_noise_control(self) -> dict:
        return self.scoring_weights.get("noise_control", {})

    # --- Keyword helpers ---

    def get_high_priority_titles(self) -> list[str]:
        return self.keywords.get("titles", {}).get("high_priority", [])

    def get_exclude_titles(self) -> list[str]:
        return self.keywords.get("titles", {}).get("low_priority_exclude", [])

    def get_competitor_keywords(self) -> list[str]:
        return self.keywords.get("competitors", {}).get("direct_cfo_competitors", [])

    def get_exclusion_keywords(self, group: str) -> list[str]:
        return self.keywords.get("exclusions", {}).get(group, [])

    def get_buying_triggers(self) -> list[str]:
        return self.keywords.get("buying_triggers", [])

    def get_owner_led_signals(self) -> list[str]:
        return self.keywords.get("owner_led_signals", [])

    def get_complexity_signals(self) -> list[str]:
        return self.keywords.get("financial_complexity", [])


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached singleton Settings instance."""
    return Settings()
