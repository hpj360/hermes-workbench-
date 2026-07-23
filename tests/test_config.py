"""Basic tests for Hermes configuration."""

from __future__ import annotations

from hermes.config import Settings, get_settings
from hermes.skills import discover_skills, list_knowledge_docs, skills_dir, knowledge_dir


def test_settings_defaults() -> None:
    settings = get_settings(force_reload=True)
    assert isinstance(settings, Settings)
    assert settings.openclaw_gateway_port == 18789
    assert settings.openclaw_model_primary == "anthropic/claude-sonnet-4-5"
    assert settings.openclaw_model_fallback == "openai/gpt-4o"
    assert settings.hermes_project_root.exists()


def test_provider_detection_includes_ollama_by_default() -> None:
    settings = get_settings()
    providers = settings.configured_providers()
    assert "ollama" in providers


def test_state_dirs_created() -> None:
    settings = get_settings(force_reload=True)
    assert settings.hermes_state_dir.exists()
    assert settings.hermes_cache_dir.exists()


def test_skills_discovery() -> None:
    root = skills_dir()
    assert root.exists()
    skills = discover_skills()
    assert len(skills) > 0
    assert any(s.name == "agent-browser" for s in skills)


def test_knowledge_discovery() -> None:
    root = knowledge_dir()
    assert root.exists()
    docs = list_knowledge_docs()
    assert len(docs) >= 4
