"""Tests for hermes.skills discovery and helpers."""

from __future__ import annotations

from pathlib import Path

import hermes.skills as skills_mod
from hermes.skills import (
    discover_skills,
    get_skill_path,
    knowledge_dir,
    list_knowledge_docs,
    skills_dir,
)


def test_discover_skills_returns_nonempty_list() -> None:
    skills = discover_skills()
    assert isinstance(skills, list)
    assert len(skills) > 0


def test_each_skill_has_name_and_path() -> None:
    for s in discover_skills():
        assert isinstance(s.name, str) and s.name
        assert isinstance(s.path, Path)


def test_discover_finds_agent_browser() -> None:
    names = [s.name for s in discover_skills()]
    assert "agent-browser" in names


def test_get_skill_path_returns_dir_for_existing() -> None:
    p = get_skill_path("agent-browser")
    assert p is not None
    assert p.is_dir()


def test_get_skill_path_returns_none_for_missing() -> None:
    assert get_skill_path("does-not-exist-skill-xyz") is None


def test_list_knowledge_docs_returns_at_least_four_markdown() -> None:
    docs = list_knowledge_docs()
    assert len(docs) >= 4
    for d in docs:
        assert d.suffix == ".md"


def test_list_knowledge_docs_sorted() -> None:
    docs = list_knowledge_docs()
    names = [d.name for d in docs]
    assert names == sorted(names)


def test_skills_dir_path_ends_with_skills() -> None:
    assert skills_dir().name == "skills"


def test_knowledge_dir_path_ends_with_knowledge() -> None:
    assert knowledge_dir().name == "knowledge"


def test_discover_skills_handles_missing_dir(monkeypatch, tmp_path) -> None:
    nonexistent = tmp_path / "nonexistent"
    monkeypatch.setattr(skills_mod, "skills_dir", lambda: nonexistent)
    assert discover_skills() == []


def test_discover_skills_count_matches_manifest() -> None:
    # The disk has 33 real skills (24 original + 9 UI/design skills from Hermes).
    assert len(discover_skills()) == 33
