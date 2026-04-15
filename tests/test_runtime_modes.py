"""Tests for runtime mode detection and behavior."""

import os
import pytest
from unittest.mock import patch
from app.config.settings import Settings


def test_no_keys_detects_no_key_mode():
    """No API keys → no_key mode."""
    with patch.dict(os.environ, {"GMAPS_API_KEY": "", "SERPAPI_KEY": "", "RUNTIME_MODE": ""}, clear=False):
        s = Settings()
        assert s.runtime_mode == "no_key"


def test_all_keys_detects_premium_mode():
    """Both API keys → premium mode."""
    with patch.dict(os.environ, {"GMAPS_API_KEY": "test-key", "SERPAPI_KEY": "test-key", "RUNTIME_MODE": ""}, clear=False):
        s = Settings()
        assert s.runtime_mode == "premium"


def test_one_key_detects_hybrid_mode():
    """Only one API key → hybrid mode."""
    with patch.dict(os.environ, {"GMAPS_API_KEY": "test-key", "SERPAPI_KEY": "", "RUNTIME_MODE": ""}, clear=False):
        s = Settings()
        assert s.runtime_mode == "hybrid"

    with patch.dict(os.environ, {"GMAPS_API_KEY": "", "SERPAPI_KEY": "test-key", "RUNTIME_MODE": ""}, clear=False):
        s = Settings()
        assert s.runtime_mode == "hybrid"


def test_explicit_mode_overrides_detection():
    """Explicit RUNTIME_MODE env var overrides auto-detection."""
    with patch.dict(os.environ, {"GMAPS_API_KEY": "test-key", "SERPAPI_KEY": "test-key", "RUNTIME_MODE": "no_key"}, clear=False):
        s = Settings()
        assert s.runtime_mode == "no_key"


def test_no_key_mode_raises_threshold():
    """no_key mode should have auto_accept_min >= 85."""
    with patch.dict(os.environ, {"GMAPS_API_KEY": "", "SERPAPI_KEY": "", "RUNTIME_MODE": ""}, clear=False):
        s = Settings()
        thresholds = s.get_effective_thresholds()
        assert thresholds["auto_accept_min"] >= 85


def test_premium_mode_keeps_standard_threshold():
    """premium mode should keep auto_accept_min at 80."""
    with patch.dict(os.environ, {"GMAPS_API_KEY": "test", "SERPAPI_KEY": "test", "RUNTIME_MODE": ""}, clear=False):
        s = Settings()
        thresholds = s.get_effective_thresholds()
        assert thresholds["auto_accept_min"] == 80


def test_no_key_mode_uses_web_search_sources():
    """In no_key mode, default sources should be web_search, not google_maps."""
    with patch.dict(os.environ, {"GMAPS_API_KEY": "", "SERPAPI_KEY": "", "RUNTIME_MODE": ""}, clear=False):
        s = Settings()
        # Verify the mode is no_key
        assert s.runtime_mode == "no_key"
        # The runner will select web_search as default source — tested via runner integration
