"""Tests for workbench.projects module.

Covers ProjectConnection dataclass, ProjectRegistry CRUD, summary,
and ping health-check for local/github/api project types.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from hermes.workbench.projects import ProjectConnection, ProjectRegistry


# ---------------------------------------------------------------------------
# ProjectConnection dataclass
# ---------------------------------------------------------------------------


def test_project_connection_defaults():
    p = ProjectConnection(id="prj-1", name="x", type="local")
    assert p.url == ""
    assert p.status == "disconnected"
    assert p.token == ""
    assert p.skills_count == 0
    assert p.config == {}


def test_project_connection_to_dict_hides_token():
    p = ProjectConnection(
        id="prj-1",
        name="x",
        type="github",
        token="secret-token",
    )
    d = p.to_dict()
    assert "token" not in d
    assert d["has_token"] is True


def test_project_connection_to_dict_no_token():
    p = ProjectConnection(id="prj-1", name="x", type="local")
    d = p.to_dict()
    assert d["has_token"] is False


def test_project_connection_roundtrip():
    p = ProjectConnection(
        id="prj-1",
        name="x",
        type="github",
        url="github.com/owner/repo",
        token="tok",
        skills_count=5,
        agents_count=2,
        knowledge_count=10,
        config={"repo": "owner/repo"},
    )
    d = p.to_dict() | {"token": "tok"}
    restored = ProjectConnection.from_dict(d)
    assert restored.id == "prj-1"
    assert restored.token == "tok"
    assert restored.skills_count == 5
    assert restored.config == {"repo": "owner/repo"}


def test_project_connection_from_dict_tolerates_missing():
    p = ProjectConnection.from_dict({"id": "p", "name": "n", "type": "local"})
    assert p.url == ""
    assert p.skills_count == 0


# ---------------------------------------------------------------------------
# ProjectRegistry CRUD
# ---------------------------------------------------------------------------


@pytest.fixture
def registry(tmp_path: Path) -> ProjectRegistry:
    return ProjectRegistry(state_dir=tmp_path)


def test_registry_add_local(registry: ProjectRegistry, tmp_path: Path):
    p = registry.add(name="local-proj", project_type="local", url=str(tmp_path))
    assert p.id.startswith("prj-")
    assert p.type == "local"
    assert p.url == str(tmp_path)


def test_registry_add_github(registry: ProjectRegistry):
    p = registry.add(
        name="gh",
        project_type="github",
        url="github.com/owner/repo",
        token="tok",
    )
    assert p.type == "github"
    assert p.token == "tok"


def test_registry_add_api(registry: ProjectRegistry):
    p = registry.add(
        name="api-proj",
        project_type="api",
        url="https://example.com",
        config={"region": "us"},
    )
    assert p.type == "api"
    assert p.config == {"region": "us"}


def test_registry_add_invalid_type_raises(registry: ProjectRegistry):
    with pytest.raises(ValueError, match="无效的项目类型"):
        registry.add(name="x", project_type="invalid")


def test_registry_get(registry: ProjectRegistry):
    p = registry.add(name="x", project_type="local")
    fetched = registry.get(p.id)
    assert fetched is not None
    assert fetched.name == "x"


def test_registry_get_missing_returns_none(registry: ProjectRegistry):
    assert registry.get("prj-nonexistent") is None


def test_registry_list(registry: ProjectRegistry):
    registry.add(name="a", project_type="local")
    registry.add(name="b", project_type="local")
    assert len(registry.list()) == 2


def test_registry_remove(registry: ProjectRegistry):
    p = registry.add(name="x", project_type="local")
    assert registry.remove(p.id) is True
    assert registry.get(p.id) is None


def test_registry_remove_missing_returns_false(registry: ProjectRegistry):
    assert registry.remove("prj-nonexistent") is False


def test_registry_update_status(registry: ProjectRegistry):
    p = registry.add(name="x", project_type="local")
    updated = registry.update_status(
        p.id,
        status="connected",
        skills_count=10,
        agents_count=3,
        knowledge_count=5,
    )
    assert updated is not None
    assert updated.status == "connected"
    assert updated.skills_count == 10
    assert updated.agents_count == 3
    assert updated.knowledge_count == 5
    assert updated.last_sync > 0


def test_registry_update_status_missing_returns_none(registry: ProjectRegistry):
    assert registry.update_status("prj-x", status="connected") is None


def test_registry_summary(registry: ProjectRegistry):
    registry.add(name="a", project_type="local")
    p = registry.add(name="b", project_type="local")
    registry.update_status(p.id, status="connected", skills_count=4)
    summary = registry.summary()
    assert summary["total"] == 2
    assert summary["connected"] == 1
    assert summary["disconnected"] == 1
    assert summary["total_skills"] == 4


def test_registry_summary_empty(registry: ProjectRegistry):
    summary = registry.summary()
    assert summary["total"] == 0
    assert summary["connected"] == 0
    assert summary["total_skills"] == 0


def test_registry_persists_across_instances(tmp_path: Path):
    r1 = ProjectRegistry(state_dir=tmp_path)
    p = r1.add(name="x", project_type="local")
    r2 = ProjectRegistry(state_dir=tmp_path)
    fetched = r2.get(p.id)
    assert fetched is not None
    assert fetched.name == "x"


# ---------------------------------------------------------------------------
# ping (health check)
# ---------------------------------------------------------------------------


def test_ping_missing_project_returns_error(registry: ProjectRegistry):
    result = registry.ping("prj-nonexistent")
    assert result["reachable"] is False
    assert result["error"] == "not found"


def test_ping_local_existing_dir(registry: ProjectRegistry, tmp_path: Path):
    p = registry.add(name="x", project_type="local", url=str(tmp_path))
    result = registry.ping(p.id)
    assert result["reachable"] is True
    assert result["status"] == "connected"
    assert result["latency_ms"] >= 0
    assert result["error"] is None


def test_ping_local_missing_dir(registry: ProjectRegistry):
    p = registry.add(name="x", project_type="local", url="/nonexistent/path/xyz")
    result = registry.ping(p.id)
    assert result["reachable"] is False
    assert result["status"] == "error"
    assert "not found" in (result["error"] or "")


def test_ping_local_empty_url(registry: ProjectRegistry):
    p = registry.add(name="x", project_type="local", url="")
    result = registry.ping(p.id)
    assert result["reachable"] is False
    assert "empty" in (result["error"] or "")


def test_ping_github_success(registry: ProjectRegistry):
    """GitHub ping returns reachable when the urlopen call succeeds."""
    p = registry.add(
        name="gh",
        project_type="github",
        url="github.com/owner/repo",
        token="tok",
    )
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.read.return_value = b"{}"
        result = registry.ping(p.id)
    assert result["reachable"] is True
    assert result["status"] == "connected"


def test_ping_github_no_repo(registry: ProjectRegistry):
    p = registry.add(name="gh", project_type="github", url="")
    result = registry.ping(p.id)
    assert result["reachable"] is False
    assert "empty" in (result["error"] or "")


def test_ping_github_unreachable(registry: ProjectRegistry):
    from urllib.error import URLError

    p = registry.add(
        name="gh",
        project_type="github",
        url="github.com/owner/repo",
    )
    with patch("urllib.request.urlopen", side_effect=URLError("no connection")):
        result = registry.ping(p.id)
    assert result["reachable"] is False
    assert result["status"] == "error"
    assert "unreachable" in (result["error"] or "")


def test_ping_api_success(registry: ProjectRegistry):
    p = registry.add(
        name="api",
        project_type="api",
        url="https://example.com",
    )
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.read.return_value = b"{}"
        result = registry.ping(p.id)
    assert result["reachable"] is True


def test_ping_api_empty_url(registry: ProjectRegistry):
    p = registry.add(name="api", project_type="api", url="")
    result = registry.ping(p.id)
    assert result["reachable"] is False
    assert "empty" in (result["error"] or "")


def test_ping_api_unreachable(registry: ProjectRegistry):
    from urllib.error import URLError

    p = registry.add(
        name="api",
        project_type="api",
        url="https://example.com",
    )
    with patch("urllib.request.urlopen", side_effect=URLError("timeout")):
        result = registry.ping(p.id)
    assert result["reachable"] is False
    assert "unreachable" in (result["error"] or "")


def test_ping_updates_status(registry: ProjectRegistry, tmp_path: Path):
    """A successful ping should flip status to 'connected'."""
    p = registry.add(name="x", project_type="local", url=str(tmp_path))
    assert registry.get(p.id).status == "disconnected"
    registry.ping(p.id)
    assert registry.get(p.id).status == "connected"
