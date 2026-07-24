"""Shared fixtures for workbench tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def skills_dir(tmp_path: Path) -> Path:
    """Create a tmp skills directory with alpha and beta skills."""
    base = tmp_path / "skills"
    for name in ("alpha", "beta"):
        s = base / name
        s.mkdir(parents=True)
        (s / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {name} skill\n---\n# {name}\nHello {name}.\n",
            encoding="utf-8",
        )
    return base
