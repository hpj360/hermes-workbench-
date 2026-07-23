"""Tests for workbench.server module.

Uses http.client against a real ThreadingHTTPServer on an ephemeral port.
"""

from __future__ import annotations

import http.client
import json
import threading
from pathlib import Path
from typing import Any

import pytest

from hermes.workbench.server import make_server


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def skills_dir(tmp_path: Path) -> Path:
    base = tmp_path / "skills"
    for name in ("alpha", "beta"):
        s = base / name
        s.mkdir(parents=True)
        (s / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {name} skill\n---\n# {name}\nHello {name}.\n",
            encoding="utf-8",
        )
    return base


@pytest.fixture
def patched_services(monkeypatch, skills_dir, tmp_path):
    """Patch cli factories to use tmp-based isolated services."""
    from hermes.workbench import cli as cli_mod
    from hermes.workbench.memory import MemoryService
    from hermes.workbench.skill_runner import SkillRunner

    state = tmp_path / "state"
    state.mkdir()
    runner = SkillRunner(base_dir=skills_dir)
    memory = MemoryService(state_dir=state)
    store = cli_mod.TaskStore(state_dir=state)
    registry = cli_mod.TaskRegistry()
    scheduler = cli_mod.TaskScheduler(
        store=store, registry=registry, runner=runner, memory=memory
    )

    monkeypatch.setattr(cli_mod, "_make_runner", lambda: runner)
    monkeypatch.setattr(cli_mod, "_make_memory", lambda: memory)
    monkeypatch.setattr(cli_mod, "_make_store", lambda: store)
    monkeypatch.setattr(cli_mod, "_make_registry", lambda: registry)
    monkeypatch.setattr(cli_mod, "_make_scheduler", lambda: scheduler)
    return {"store": store, "registry": registry, "scheduler": scheduler}


@pytest.fixture
def server(patched_services):
    srv = make_server(host="127.0.0.1", port=0)
    srv.daemon_threads = True
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv
    srv.shutdown()
    srv.server_close()
    thread.join(timeout=2)


@pytest.fixture
def client(server):
    host, port = server.server_address[:2]

    def request(method: str, path: str, body: Any = None) -> http.client.HTTPResponse:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        if body is None:
            conn.request(method, path)
        else:
            data = json.dumps(body)
            conn.request(method, path, body=data, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        resp.text = resp.read().decode("utf-8")  # type: ignore[attr-defined]
        conn.close()
        return resp

    return request


def _json(resp):
    return json.loads(resp.text)


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------


def test_health(client):
    resp = client("GET", "/health")
    assert resp.status == 200
    assert _json(resp)["status"] == "ok"


def test_unknown_route_404(client):
    resp = client("GET", "/nonexistent")
    assert resp.status == 404


def test_method_not_allowed(client):
    resp = client("PUT", "/skills")
    assert resp.status == 405


# ---------------------------------------------------------------------------
# skills
# ---------------------------------------------------------------------------


def test_skills_list(client):
    resp = client("GET", "/skills")
    assert resp.status == 200
    names = [s["name"] for s in _json(resp)["skills"]]
    assert "alpha" in names


def test_skill_detail(client):
    resp = client("GET", "/skills/alpha")
    assert resp.status == 200
    assert _json(resp)["name"] == "alpha"


def test_skill_detail_missing(client):
    resp = client("GET", "/skills/nonexistent")
    assert resp.status == 404


# ---------------------------------------------------------------------------
# memory facts
# ---------------------------------------------------------------------------


def test_facts_empty(client):
    resp = client("GET", "/memory/facts")
    assert resp.status == 200
    assert _json(resp)["facts"] == []


def test_facts_create_and_get(client):
    resp = client("POST", "/memory/facts", body={"key": "city", "value": "Shanghai"})
    assert resp.status == 201
    resp = client("GET", "/memory/facts/city")
    assert resp.status == 200
    assert _json(resp)["value"] == "Shanghai"


def test_facts_get_missing(client):
    resp = client("GET", "/memory/facts/nonexistent")
    assert resp.status == 404


def test_facts_delete(client):
    client("POST", "/memory/facts", body={"key": "temp", "value": "x"})
    resp = client("DELETE", "/memory/facts/temp")
    assert resp.status == 204
    assert client("GET", "/memory/facts/temp").status == 404


def test_facts_delete_missing(client):
    resp = client("DELETE", "/memory/facts/nonexistent")
    assert resp.status == 404


def test_facts_create_missing_key(client):
    resp = client("POST", "/memory/facts", body={"value": "x"})
    assert resp.status == 400


# ---------------------------------------------------------------------------
# memory episodes + profile
# ---------------------------------------------------------------------------


def test_episodes_empty(client):
    resp = client("GET", "/memory/episodes")
    assert resp.status == 200
    assert _json(resp)["episodes"] == []


def test_profile(client):
    resp = client("GET", "/memory/profile")
    assert resp.status == 200
    assert "version" in _json(resp)


# ---------------------------------------------------------------------------
# tasks
# ---------------------------------------------------------------------------


def test_tasks_create_and_run(client):
    resp = client("POST", "/tasks", body={"plan": [{"skill": "alpha"}], "run": True})
    assert resp.status == 200
    data = _json(resp)
    assert "task_id" in data
    assert data["status"] in ("COMPLETED", "FAILED")


def test_tasks_list_empty(client):
    resp = client("GET", "/tasks")
    assert resp.status == 200
    assert _json(resp)["tasks"] == []


def test_tasks_list_after_create(client):
    client("POST", "/tasks", body={"plan": [{"skill": "alpha"}], "run": False})
    resp = client("GET", "/tasks")
    assert resp.status == 200
    assert len(_json(resp)["tasks"]) == 1


def test_task_detail(client):
    create = client("POST", "/tasks", body={"plan": [{"skill": "alpha"}], "run": False})
    task_id = _json(create)["task_id"]
    resp = client("GET", f"/tasks/{task_id}")
    assert resp.status == 200
    assert _json(resp)["task_id"] == task_id


def test_task_detail_missing(client):
    resp = client("GET", "/tasks/nonexistent")
    assert resp.status == 404


def test_task_cancel(client):
    create = client("POST", "/tasks", body={"plan": [{"skill": "alpha"}], "run": False})
    task_id = _json(create)["task_id"]
    resp = client("POST", f"/tasks/{task_id}/cancel")
    assert resp.status == 200
    assert _json(resp)["status"] == "CANCELLED"


def test_task_cancel_missing(client):
    resp = client("POST", "/tasks/nonexistent/cancel")
    assert resp.status == 404


def test_task_create_missing_plan(client):
    resp = client("POST", "/tasks", body={"mode": "oneshot"})
    assert resp.status == 400


# ---------------------------------------------------------------------------
# github sync (mocked)
# ---------------------------------------------------------------------------


def test_github_sync_no_repo(client):
    resp = client("GET", "/github/sync")
    assert resp.status == 400


def test_github_sync_no_token(client, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    resp = client("GET", "/github/sync?repo=owner/repo")
    assert resp.status == 400
