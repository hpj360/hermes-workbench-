"""Tests for hermes.registry (unified registry across local + GitHub sources)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hermes.registry import (
    DEFAULT_GITHUB_REPOS,
    AgentEntry,
    GitHubSource,
    KnowledgeEntry,
    LocalSource,
    Registry,
    RegistrySource,
    SkillEntry,
    SourceKind,
    UserProfile,
    _extract_description,
    _parse_github_listing,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_local_tree(tmp_path: Path) -> Path:
    """Create a minimal local project tree with skills/knowledge/data/agents."""
    base = tmp_path / "project"
    # skills
    (base / "skills" / "weather").mkdir(parents=True)
    (base / "skills" / "weather" / "SKILL.md").write_text(
        "---\nname: weather\ndescription: Weather query skill\n---\n\n# Weather\n",
        encoding="utf-8",
    )
    (base / "skills" / "echo").mkdir(parents=True)
    (base / "skills" / "echo" / "SKILL.md").write_text(
        "---\nname: echo\ndescription: Echo skill\n---\n", encoding="utf-8"
    )
    (base / "skills" / "no-skill-md").mkdir(parents=True)
    # knowledge
    (base / "knowledge").mkdir(parents=True)
    (base / "knowledge" / "doc1.md").write_text("# Doc 1", encoding="utf-8")
    (base / "knowledge" / "doc2.md").write_text("# Doc 2", encoding="utf-8")
    # data/profile.json
    (base / "data").mkdir(parents=True)
    (base / "data" / "profile.json").write_text(
        json.dumps({"contact": {"github": "hpj360"}, "name": "Test"}), encoding="utf-8"
    )
    # agents (pm-team style)
    (base / "agents" / "architect").mkdir(parents=True)
    (base / "agents" / "architect" / "AGENT.md").write_text(
        "---\nname: architect\ndescription: System architect\n---\n", encoding="utf-8"
    )
    return base


def _make_mock_fetcher(responses: dict[str, list[dict[str, Any]]]):
    """Create a mock GitHubFetcher that returns scripted directory listings."""

    def fetcher(repo: str, path: str) -> bytes:
        key = f"{repo}:{path}"
        if key not in responses:
            return b"[]"
        return json.dumps(responses[key]).encode("utf-8")

    return fetcher


# ---------------------------------------------------------------------------
# Data model tests
# ---------------------------------------------------------------------------


def test_source_kind_values() -> None:
    assert SourceKind.LOCAL.value == "local"
    assert SourceKind.GITHUB.value == "github"


def test_registry_source_to_dict() -> None:
    s = RegistrySource(name="local", kind=SourceKind.LOCAL, location="/tmp")
    d = s.to_dict()
    assert d["name"] == "local"
    assert d["kind"] == "local"
    assert d["location"] == "/tmp"


def test_skill_entry_to_dict() -> None:
    e = SkillEntry(name="weather", source="local", kind=SourceKind.LOCAL, path="/skills/weather")
    d = e.to_dict()
    assert d["kind"] == "local"
    assert d["name"] == "weather"


def test_agent_entry_to_dict() -> None:
    e = AgentEntry(name="codex", source="local", kind=SourceKind.LOCAL, config_path="/cfg")
    assert e.to_dict()["kind"] == "local"


def test_knowledge_entry_to_dict() -> None:
    e = KnowledgeEntry(name="doc.md", source="local", kind=SourceKind.LOCAL, path="/k/doc.md", size=100)
    d = e.to_dict()
    assert d["size"] == 100
    assert d["kind"] == "local"


def test_user_profile_to_dict() -> None:
    p = UserProfile(source="local", kind=SourceKind.LOCAL, data={"name": "test"})
    assert p.to_dict()["data"] == {"name": "test"}


# ---------------------------------------------------------------------------
# _parse_github_listing tests
# ---------------------------------------------------------------------------


def test_parse_github_listing_valid() -> None:
    raw = json.dumps(
        [
            {"name": "weather", "type": "dir", "size": 0, "path": "skills/weather"},
            {"name": "doc.md", "type": "file", "size": 42, "path": "knowledge/doc.md"},
        ]
    ).encode("utf-8")
    result = _parse_github_listing(raw)
    assert len(result) == 2
    assert result[0]["name"] == "weather"
    assert result[0]["type"] == "dir"
    assert result[1]["size"] == 42


def test_parse_github_listing_empty() -> None:
    assert _parse_github_listing(b"[]") == []


def test_parse_github_listing_not_list() -> None:
    assert _parse_github_listing(b'{"message": "not found"}') == []


def test_parse_github_listing_invalid_json() -> None:
    assert _parse_github_listing(b"not json") == []


# ---------------------------------------------------------------------------
# _extract_description tests
# ---------------------------------------------------------------------------


def test_extract_description_from_front_matter() -> None:
    content = "---\nname: weather\ndescription: Weather query\n---\n\n# Weather"
    assert _extract_description(content) == "Weather query"


def test_extract_description_no_front_matter() -> None:
    content = "# Weather\n\nThis is a weather skill."
    assert _extract_description(content) == "Weather"


def test_extract_description_empty() -> None:
    assert _extract_description("") == ""
    assert _extract_description("---\n---\n") == ""


def test_extract_description_with_quotes() -> None:
    content = '---\ndescription: "A quoted desc"\n---\n'
    assert _extract_description(content) == "A quoted desc"


# ---------------------------------------------------------------------------
# LocalSource tests
# ---------------------------------------------------------------------------


def test_local_source_list_skills(tmp_path: Path) -> None:
    base = _make_local_tree(tmp_path)
    src = LocalSource(name="local", base_dir=base, agent_dirs=[])
    skills = src.list_skills()
    names = sorted(s.name for s in skills)
    assert names == ["echo", "no-skill-md", "weather"]
    weather = next(s for s in skills if s.name == "weather")
    assert weather.description == "Weather query skill"
    assert weather.has_skill_md is True
    assert weather.kind == SourceKind.LOCAL
    no_md = next(s for s in skills if s.name == "no-skill-md")
    assert no_md.has_skill_md is False


def test_local_source_list_skills_empty(tmp_path: Path) -> None:
    src = LocalSource(name="local", base_dir=tmp_path, agent_dirs=[])
    assert src.list_skills() == []


def test_local_source_list_agents(tmp_path: Path) -> None:
    base = _make_local_tree(tmp_path)
    src = LocalSource(name="local", base_dir=base, agent_dirs=[("test-agent", str(tmp_path / "fake-agent"))])
    agents = src.list_agents()
    # Should find the project-local agents/architect + non-existent test-agent
    names = [a.name for a in agents]
    assert "architect" in names
    architect = next(a for a in agents if a.name == "architect")
    assert architect.description == "System architect"
    assert architect.kind == SourceKind.LOCAL


def test_local_source_list_knowledge(tmp_path: Path) -> None:
    base = _make_local_tree(tmp_path)
    src = LocalSource(name="local", base_dir=base, agent_dirs=[])
    docs = src.list_knowledge()
    assert len(docs) == 2
    assert all(d.name.endswith(".md") for d in docs)
    assert all(d.size > 0 for d in docs)


def test_local_source_get_user_profile(tmp_path: Path) -> None:
    base = _make_local_tree(tmp_path)
    src = LocalSource(name="local", base_dir=base, agent_dirs=[])
    profile = src.get_user_profile()
    assert profile is not None
    assert profile.data["contact"]["github"] == "hpj360"
    assert profile.kind == SourceKind.LOCAL


def test_local_source_get_user_profile_missing(tmp_path: Path) -> None:
    src = LocalSource(name="local", base_dir=tmp_path, agent_dirs=[])
    assert src.get_user_profile() is None


def test_local_source_get_user_profile_corrupt(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "profile.json").write_text("not json", encoding="utf-8")
    src = LocalSource(name="local", base_dir=tmp_path, agent_dirs=[])
    assert src.get_user_profile() is None


# ---------------------------------------------------------------------------
# GitHubSource tests
# ---------------------------------------------------------------------------


def test_github_source_list_skills_with_mock(tmp_path: Path) -> None:
    fetcher = _make_mock_fetcher(
        {
            "hpj360/Hermes:skills": [
                {"name": "weather", "type": "dir", "size": 0, "path": "skills/weather"},
                {"name": "echo", "type": "dir", "size": 0, "path": "skills/echo"},
                {"name": "README.md", "type": "file", "size": 100, "path": "skills/README.md"},
            ]
        }
    )
    src = GitHubSource(name="hermes", repo="hpj360/Hermes", fetcher=fetcher, cache_dir=tmp_path / "cache")
    skills = src.list_skills()
    assert len(skills) == 2  # only dirs
    assert all(s.kind == SourceKind.GITHUB for s in skills)
    assert all(s.source == "hermes" for s in skills)
    assert skills[0].path.startswith("hpj360/Hermes/skills/")


def test_github_source_list_agents_with_mock(tmp_path: Path) -> None:
    fetcher = _make_mock_fetcher(
        {
            "hpj360/pm-team:agents": [
                {"name": "architect", "type": "dir", "size": 0, "path": "agents/architect"},
                {"name": "tester", "type": "dir", "size": 0, "path": "agents/tester"},
            ]
        }
    )
    src = GitHubSource(name="pm-team", repo="hpj360/pm-team", fetcher=fetcher, cache_dir=tmp_path / "cache")
    agents = src.list_agents()
    assert len(agents) == 2
    assert agents[0].config_path == "hpj360/pm-team/agents/architect/AGENT.md"


def test_github_source_list_knowledge_with_mock(tmp_path: Path) -> None:
    fetcher = _make_mock_fetcher(
        {
            "hpj360/Hermes:knowledge": [
                {"name": "doc1.md", "type": "file", "size": 100, "path": "knowledge/doc1.md"},
                {"name": "subdir", "type": "dir", "size": 0, "path": "knowledge/subdir"},
                {"name": "readme.txt", "type": "file", "size": 50, "path": "knowledge/readme.txt"},
            ]
        }
    )
    src = GitHubSource(name="hermes", repo="hpj360/Hermes", fetcher=fetcher, cache_dir=tmp_path / "cache")
    docs = src.list_knowledge()
    assert len(docs) == 1  # only .md files
    assert docs[0].name == "doc1.md"
    assert docs[0].size == 100


def test_github_source_get_user_profile(tmp_path: Path) -> None:
    fetcher = _make_mock_fetcher(
        {
            "hpj360/Hermes:data": [
                {"name": "profile.example.json", "type": "file", "size": 100, "path": "data/profile.example.json"},
            ]
        }
    )
    src = GitHubSource(name="hermes", repo="hpj360/Hermes", fetcher=fetcher, cache_dir=tmp_path / "cache")
    profile = src.get_user_profile()
    assert profile is not None
    assert profile.kind == SourceKind.GITHUB
    assert "profile.example.json" in profile.data["file"]


def test_github_source_get_user_profile_none(tmp_path: Path) -> None:
    fetcher = _make_mock_fetcher({"hpj360/Hermes:data": []})
    src = GitHubSource(name="hermes", repo="hpj360/Hermes", fetcher=fetcher, cache_dir=tmp_path / "cache")
    assert src.get_user_profile() is None


def test_github_source_fetch_error_returns_empty(tmp_path: Path) -> None:
    def failing_fetcher(repo: str, path: str) -> bytes:
        raise RuntimeError("network error")

    src = GitHubSource(name="hermes", repo="hpj360/Hermes", fetcher=failing_fetcher, cache_dir=tmp_path / "cache")
    assert src.list_skills() == []
    assert src.list_agents() == []


def test_github_source_cache(tmp_path: Path) -> None:
    call_count = [0]

    def counting_fetcher(repo: str, path: str) -> bytes:
        call_count[0] += 1
        return json.dumps([{"name": "skill1", "type": "dir", "size": 0, "path": "skills/skill1"}]).encode()

    cache = tmp_path / "cache"
    src = GitHubSource(name="hermes", repo="hpj360/Hermes", fetcher=counting_fetcher, cache_dir=cache)
    # First call hits fetcher
    skills1 = src.list_skills()
    assert call_count[0] == 1
    # Second call uses cache
    skills2 = src.list_skills()
    assert call_count[0] == 1  # no new fetch
    assert len(skills1) == len(skills2) == 1


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


def test_registry_list_sources(tmp_path: Path) -> None:
    base = _make_local_tree(tmp_path)
    local = LocalSource(name="local", base_dir=base, agent_dirs=[])
    gh = GitHubSource(
        name="hermes",
        repo="hpj360/Hermes",
        fetcher=_make_mock_fetcher({}),
        cache_dir=tmp_path / "cache",
    )
    reg = Registry(local_source=local, github_sources=[gh])
    sources = reg.list_sources()
    assert len(sources) == 2
    assert sources[0].name == "local"
    assert sources[1].name == "hermes"


def test_registry_list_skills_aggregates(tmp_path: Path) -> None:
    base = _make_local_tree(tmp_path)
    local = LocalSource(name="local", base_dir=base, agent_dirs=[])
    gh = GitHubSource(
        name="remote",
        repo="hpj360/Hermes",
        fetcher=_make_mock_fetcher(
            {"hpj360/Hermes:skills": [{"name": "remote-skill", "type": "dir", "size": 0, "path": "skills/remote-skill"}]}
        ),
        cache_dir=tmp_path / "cache",
    )
    reg = Registry(local_source=local, github_sources=[gh])
    skills = reg.list_skills()
    names = sorted(s.name for s in skills)
    assert "weather" in names  # local
    assert "remote-skill" in names  # github


def test_registry_list_skills_filter_by_source(tmp_path: Path) -> None:
    base = _make_local_tree(tmp_path)
    local = LocalSource(name="local", base_dir=base, agent_dirs=[])
    gh = GitHubSource(
        name="remote",
        repo="hpj360/Hermes",
        fetcher=_make_mock_fetcher(
            {"hpj360/Hermes:skills": [{"name": "remote-skill", "type": "dir", "size": 0, "path": "skills/remote-skill"}]}
        ),
        cache_dir=tmp_path / "cache",
    )
    reg = Registry(local_source=local, github_sources=[gh])
    local_only = reg.list_skills(source="local")
    assert all(s.source == "local" for s in local_only)
    remote_only = reg.list_skills(source="remote")
    assert all(s.source == "remote" for s in remote_only)
    assert any(s.name == "remote-skill" for s in remote_only)


def test_registry_list_agents_aggregates(tmp_path: Path) -> None:
    base = _make_local_tree(tmp_path)
    local = LocalSource(name="local", base_dir=base, agent_dirs=[])
    gh = GitHubSource(
        name="remote",
        repo="hpj360/pm-team",
        fetcher=_make_mock_fetcher(
            {"hpj360/pm-team:agents": [{"name": "tester", "type": "dir", "size": 0, "path": "agents/tester"}]}
        ),
        cache_dir=tmp_path / "cache",
    )
    reg = Registry(local_source=local, github_sources=[gh])
    agents = reg.list_agents()
    names = [a.name for a in agents]
    assert "architect" in names  # local
    assert "tester" in names  # github


def test_registry_list_knowledge_aggregates(tmp_path: Path) -> None:
    base = _make_local_tree(tmp_path)
    local = LocalSource(name="local", base_dir=base, agent_dirs=[])
    gh = GitHubSource(
        name="remote",
        repo="hpj360/Hermes",
        fetcher=_make_mock_fetcher(
            {"hpj360/Hermes:knowledge": [{"name": "remote-doc.md", "type": "file", "size": 200, "path": "knowledge/remote-doc.md"}]}
        ),
        cache_dir=tmp_path / "cache",
    )
    reg = Registry(local_source=local, github_sources=[gh])
    docs = reg.list_knowledge()
    names = [d.name for d in docs]
    assert "doc1.md" in names  # local
    assert "remote-doc.md" in names  # github


def test_registry_get_user_profile_merges(tmp_path: Path) -> None:
    base = _make_local_tree(tmp_path)
    local = LocalSource(name="local", base_dir=base, agent_dirs=[])
    gh = GitHubSource(
        name="remote",
        repo="hpj360/Hermes",
        fetcher=_make_mock_fetcher(
            {"hpj360/Hermes:data": [{"name": "profile.example.json", "type": "file", "size": 100, "path": "data/profile.example.json"}]}
        ),
        cache_dir=tmp_path / "cache",
    )
    reg = Registry(local_source=local, github_sources=[gh])
    profile = reg.get_user_profile()
    assert profile["contact"]["github"] == "hpj360"  # from local
    assert profile["_primary_source"] == "local"
    assert len(profile["_additional_sources"]) == 1


def test_registry_get_user_profile_no_sources() -> None:
    reg = Registry(local_source=None, github_sources=[])
    profile = reg.get_user_profile()
    assert "_note" in profile


def test_registry_refresh_clears_cache(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "test.json").write_text("[]", encoding="utf-8")
    (cache / "other.json").write_text("[]", encoding="utf-8")
    reg = Registry(local_source=None, github_sources=[], cache_dir=cache)
    result = reg.refresh()
    assert result["cleared_cache_files"] == 2
    assert not any(cache.glob("*.json"))


def test_registry_summary(tmp_path: Path) -> None:
    base = _make_local_tree(tmp_path)
    local = LocalSource(name="local", base_dir=base, agent_dirs=[])
    gh = GitHubSource(
        name="remote",
        repo="hpj360/Hermes",
        fetcher=_make_mock_fetcher(
            {"hpj360/Hermes:skills": [{"name": "rs", "type": "dir", "size": 0, "path": "skills/rs"}]}
        ),
        cache_dir=tmp_path / "cache",
    )
    reg = Registry(local_source=local, github_sources=[gh])
    s = reg.summary()
    assert s["sources"] == 2
    assert s["skills"] >= 3  # 3 local + 1 remote
    assert s["has_user_profile"] is True


def test_default_github_repos_contains_key_repos() -> None:
    repos = [repo for _, repo in DEFAULT_GITHUB_REPOS]
    assert "hpj360/Hermes" in repos
    assert "hpj360/pm-team" in repos
    assert len(repos) >= 4
