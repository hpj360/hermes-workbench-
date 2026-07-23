"""Shared pytest fixtures for Hermes tests."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def reset_settings() -> Iterator[None]:
    """Clear the settings singleton before and after the test."""
    from hermes import config as _config
    _config._hermes_settings = None
    yield
    _config._hermes_settings = None


@pytest.fixture
def tmp_state_dir(
    tmp_path: Path, reset_settings: Iterator[None], monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Redirect HERMES_STATE_DIR/CACHE_DIR/PROFILE_PATH to tmp_path and reload settings."""
    state = tmp_path / "state"
    cache = tmp_path / "cache"
    profile = tmp_path / "profile.json"
    state.mkdir()
    cache.mkdir()
    monkeypatch.setenv("HERMES_STATE_DIR", str(state))
    monkeypatch.setenv("HERMES_CACHE_DIR", str(cache))
    monkeypatch.setenv("HERMES_PROFILE_PATH", str(profile))
    from hermes.config import get_settings
    get_settings(force_reload=True)
    yield tmp_path
