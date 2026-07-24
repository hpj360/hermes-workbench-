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
    from hermes.workbench.projects import ProjectRegistry
    from hermes.workbench.skill_runner import SkillRunner
    from hermes.workbench.sync import AssetSync
    from hermes.workbench.triggers import TriggerStore
    from hermes.workbench.workflow import WorkflowRunner, WorkflowStore

    state = tmp_path / "state"
    state.mkdir()
    runner = SkillRunner(base_dir=skills_dir)
    memory = MemoryService(state_dir=state)
    store = cli_mod.TaskStore(state_dir=state)
    registry = cli_mod.TaskRegistry()
    scheduler = cli_mod.TaskScheduler(
        store=store, registry=registry, runner=runner, memory=memory
    )
    wf_store = WorkflowStore(state_dir=state)
    wf_runner = WorkflowRunner(runner=runner, state_dir=state)
    trigger_store = TriggerStore(state_dir=state)
    project_registry = ProjectRegistry(state_dir=state)
    asset_sync = AssetSync(registry=project_registry, runner=runner, memory=memory)

    monkeypatch.setattr(cli_mod, "_make_runner", lambda: runner)
    monkeypatch.setattr(cli_mod, "_make_memory", lambda: memory)
    monkeypatch.setattr(cli_mod, "_make_store", lambda: store)
    monkeypatch.setattr(cli_mod, "_make_registry", lambda: registry)
    monkeypatch.setattr(cli_mod, "_make_scheduler", lambda: scheduler)
    monkeypatch.setattr(cli_mod, "_make_workflow_store", lambda: wf_store)
    monkeypatch.setattr(cli_mod, "_make_workflow_runner", lambda: wf_runner)
    monkeypatch.setattr(cli_mod, "_make_trigger_store", lambda: trigger_store)
    monkeypatch.setattr(cli_mod, "_make_project_registry", lambda: project_registry)
    monkeypatch.setattr(cli_mod, "_make_asset_sync", lambda: asset_sync)
    return {
        "store": store,
        "registry": registry,
        "scheduler": scheduler,
        "wf_store": wf_store,
        "wf_runner": wf_runner,
        "trigger_store": trigger_store,
        "project_registry": project_registry,
        "asset_sync": asset_sync,
    }


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

    def request(
        method: str,
        path: str,
        body: Any = None,
        headers: dict[str, str] | None = None,
    ) -> http.client.HTTPResponse:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        req_headers = dict(headers) if headers else {}
        if body is not None:
            data = json.dumps(body)
            req_headers.setdefault("Content-Type", "application/json")
            conn.request(method, path, body=data, headers=req_headers)
        else:
            conn.request(method, path, headers=req_headers)
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


# ---------------------------------------------------------------------------
# auth (HERMES_API_TOKEN)
# ---------------------------------------------------------------------------


def _set_api_token(monkeypatch, token):
    """Patch the server's get_settings so HERMES_API_TOKEN is *token*."""
    from types import SimpleNamespace

    monkeypatch.setattr(
        "hermes.workbench.server.get_settings",
        lambda: SimpleNamespace(hermes_api_token=token),
    )


def test_auth_disabled_when_token_unset(client, monkeypatch):
    # When HERMES_API_TOKEN is unset, requests work without Authorization.
    _set_api_token(monkeypatch, None)
    resp = client("GET", "/skills")
    assert resp.status == 200


def test_auth_returns_401_when_token_set_but_not_provided(client, monkeypatch):
    _set_api_token(monkeypatch, "secret")
    resp = client("GET", "/skills")
    assert resp.status == 401
    assert _json(resp) == {"error": "unauthorized", "type": "AuthError"}


def test_auth_works_with_correct_bearer_token(client, monkeypatch):
    _set_api_token(monkeypatch, "secret")
    resp = client("GET", "/skills", headers={"Authorization": "Bearer secret"})
    assert resp.status == 200


# ---------------------------------------------------------------------------
# enhanced health
# ---------------------------------------------------------------------------


def test_health_enhanced_fields(client):
    resp = client("GET", "/health")
    assert resp.status == 200
    data = _json(resp)
    assert "providers" in data
    assert "providers_count" in data
    assert "skills_total" in data
    assert "skills_ready" in data
    assert "memory_layers" in data
    assert isinstance(data["providers"], list)
    assert data["skills_total"] >= 0


# ---------------------------------------------------------------------------
# enhanced skills list
# ---------------------------------------------------------------------------


def test_skills_list_has_status_and_requires(client):
    resp = client("GET", "/skills")
    assert resp.status == 200
    skills = _json(resp)["skills"]
    assert len(skills) > 0
    s = skills[0]
    assert "requires_bins" in s
    assert "requires_env" in s
    assert "status" in s
    assert s["status"] in ("ready", "missing")


# ---------------------------------------------------------------------------
# skill run
# ---------------------------------------------------------------------------


def test_skill_run_prompt(client):
    """Running a prompt-type skill returns a RunResult."""
    resp = client("POST", "/skills/alpha/run", body={"args": []})
    assert resp.status == 200
    data = _json(resp)
    assert data["skill"] == "alpha"
    assert "ok" in data
    assert "stdout" in data
    assert "duration" in data


def test_skill_run_missing_skill(client):
    resp = client("POST", "/skills/nonexistent/run", body={"args": []})
    assert resp.status == 200  # run() never raises, returns error in result
    data = _json(resp)
    assert data["ok"] is False
    assert "not found" in (data["error"] or "")


def test_skill_run_invalid_body(client):
    resp = client("POST", "/skills/alpha/run", body={"args": "not-a-list"})
    assert resp.status == 400


# ---------------------------------------------------------------------------
# profile update (PUT)
# ---------------------------------------------------------------------------


def test_profile_update(client):
    resp = client("PUT", "/memory/profile", body={"version": "0.3.0", "test": True})
    assert resp.status == 200
    data = _json(resp)
    assert data["version"] == "0.3.0"
    # Verify it persisted
    resp2 = client("GET", "/memory/profile")
    assert _json(resp2)["version"] == "0.3.0"


def test_profile_update_invalid_body(client):
    resp = client("PUT", "/memory/profile", body="not-a-dict")
    assert resp.status == 400


# ---------------------------------------------------------------------------
# episodes limit
# ---------------------------------------------------------------------------


def test_episodes_limit(client, patched_services):
    """Verify limit query param is passed through."""
    from hermes.workbench import cli as cli_mod
    from hermes.workbench.memory import make_episode

    mem = cli_mod._make_memory()
    for i in range(10):
        mem.record_episode(make_episode("test", f"episode {i}"))

    resp = client("GET", "/memory/episodes?limit=3")
    assert resp.status == 200
    episodes = _json(resp)["episodes"]
    assert len(episodes) == 3


# ---------------------------------------------------------------------------
# static file serving
# ---------------------------------------------------------------------------


def test_index_page(client):
    """GET / should serve the prototype index.html."""
    resp = client("GET", "/")
    assert resp.status == 200
    assert "html" in resp.text.lower()


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


def test_search_empty_query(client):
    """Empty query returns empty results."""
    resp = client("GET", "/search?q=")
    assert resp.status == 200
    data = _json(resp)
    assert data["results"] == []
    assert data["total"] == 0


def test_search_skills(client):
    """Search matches skill names and descriptions."""
    resp = client("GET", "/search?q=alpha")
    assert resp.status == 200
    data = _json(resp)
    assert data["total"] >= 1
    skill_hits = [r for r in data["results"] if r["type"] == "skill"]
    assert any(r["name"] == "alpha" for r in skill_hits)


def test_search_facts(client):
    """Search matches memory facts."""
    client("POST", "/memory/facts", body={"key": "city", "value": "Shanghai"})
    resp = client("GET", "/search?q=city")
    assert resp.status == 200
    data = _json(resp)
    fact_hits = [r for r in data["results"] if r["type"] == "fact"]
    assert any(r["name"] == "city" for r in fact_hits)


# ---------------------------------------------------------------------------
# Phase 2: workflows
# ---------------------------------------------------------------------------

_WF_BODY = {
    "name": "晨报生成",
    "description": "每日早晨生成新闻摘要",
    "steps": [
        {"id": "step-1", "skill": "alpha", "args": [], "depends_on": []},
        {"id": "step-2", "skill": "beta", "args": [], "depends_on": ["step-1"]},
    ],
}


def test_workflows_empty(client):
    resp = client("GET", "/workflows")
    assert resp.status == 200
    data = _json(resp)
    assert data["workflows"] == []
    assert data["total"] == 0


def test_workflow_create_and_get(client):
    resp = client("POST", "/workflows", body=_WF_BODY)
    assert resp.status == 201
    wf = _json(resp)
    assert wf["name"] == "晨报生成"
    assert len(wf["steps"]) == 2
    wf_id = wf["id"]

    resp = client("GET", f"/workflows/{wf_id}")
    assert resp.status == 200
    assert _json(resp)["id"] == wf_id


def test_workflow_create_missing_name(client):
    resp = client("POST", "/workflows", body={"description": "no name"})
    assert resp.status == 400


def test_workflow_create_invalid_steps(client):
    resp = client("POST", "/workflows", body={"name": "x", "steps": "not-a-list"})
    assert resp.status == 400


def test_workflow_list(client):
    client("POST", "/workflows", body=_WF_BODY)
    resp = client("GET", "/workflows")
    assert resp.status == 200
    assert _json(resp)["total"] >= 1


def test_workflow_get_missing(client):
    resp = client("GET", "/workflows/wf-nonexistent")
    assert resp.status == 404


def test_workflow_update(client):
    wf_id = _json(client("POST", "/workflows", body=_WF_BODY))["id"]
    resp = client("PUT", f"/workflows/{wf_id}", body={"name": "晚报生成"})
    assert resp.status == 200
    assert _json(resp)["name"] == "晚报生成"


def test_workflow_update_missing(client):
    resp = client("PUT", "/workflows/wf-nonexistent", body={"name": "x"})
    assert resp.status == 404


def test_workflow_delete(client):
    wf_id = _json(client("POST", "/workflows", body=_WF_BODY))["id"]
    resp = client("DELETE", f"/workflows/{wf_id}")
    assert resp.status == 200
    assert _json(resp)["deleted"] is True
    assert client("GET", f"/workflows/{wf_id}").status == 404


def test_workflow_delete_missing(client):
    resp = client("DELETE", "/workflows/wf-nonexistent")
    assert resp.status == 404


def test_workflow_execute(client):
    """Execute a workflow and verify the execution record is persisted."""
    wf_id = _json(client("POST", "/workflows", body=_WF_BODY))["id"]
    resp = client("POST", f"/workflows/{wf_id}/execute", body={})
    assert resp.status == 200
    execution = _json(resp)
    assert execution["workflow_id"] == wf_id
    assert execution["status"] in {"COMPLETED", "FAILED"}
    assert len(execution["step_results"]) == 2


def test_workflow_execute_missing(client):
    resp = client("POST", "/workflows/wf-nonexistent/execute", body={})
    assert resp.status == 404


def test_workflow_executions_list(client):
    """Executions endpoint returns execution history for a workflow."""
    wf_id = _json(client("POST", "/workflows", body=_WF_BODY))["id"]
    client("POST", f"/workflows/{wf_id}/execute", body={})
    resp = client("GET", f"/workflows/{wf_id}/executions")
    assert resp.status == 200
    data = _json(resp)
    assert data["total"] >= 1
    assert data["executions"][0]["workflow_id"] == wf_id


def test_workflow_executions_empty(client):
    wf_id = _json(client("POST", "/workflows", body=_WF_BODY))["id"]
    resp = client("GET", f"/workflows/{wf_id}/executions")
    assert resp.status == 200
    assert _json(resp)["total"] == 0


# ---------------------------------------------------------------------------
# Phase 2: triggers
# ---------------------------------------------------------------------------


def _make_workflow(client) -> str:
    return _json(client("POST", "/workflows", body=_WF_BODY))["id"]


def test_triggers_empty(client):
    resp = client("GET", "/triggers")
    assert resp.status == 200
    data = _json(resp)
    assert data["triggers"] == []
    assert data["total"] == 0


def test_trigger_create_and_get(client):
    wf_id = _make_workflow(client)
    resp = client("POST", "/triggers", body={
        "workflow_id": wf_id,
        "type": "cron",
        "config": {"schedule": "0 9 * * 1-5"},
    })
    assert resp.status == 201
    trigger = _json(resp)
    assert trigger["workflow_id"] == wf_id
    assert trigger["type"] == "cron"
    assert trigger["enabled"] is True


def test_trigger_create_missing_workflow_id(client):
    resp = client("POST", "/triggers", body={"type": "cron", "config": {}})
    assert resp.status == 400


def test_trigger_create_missing_type(client):
    wf_id = _make_workflow(client)
    resp = client("POST", "/triggers", body={"workflow_id": wf_id, "config": {}})
    assert resp.status == 400


def test_trigger_list_by_workflow(client):
    wf_id = _make_workflow(client)
    client("POST", "/triggers", body={
        "workflow_id": wf_id, "type": "cron", "config": {"schedule": "0 9 * * *"},
    })
    resp = client("GET", f"/triggers?workflow_id={wf_id}")
    assert resp.status == 200
    assert _json(resp)["total"] == 1


def test_trigger_delete(client):
    wf_id = _make_workflow(client)
    tr_id = _json(client("POST", "/triggers", body={
        "workflow_id": wf_id, "type": "webhook", "config": {"secret": "x"},
    }))["id"]
    resp = client("DELETE", f"/triggers/{tr_id}")
    assert resp.status == 200
    assert _json(resp)["deleted"] is True


def test_trigger_delete_missing(client):
    resp = client("DELETE", "/triggers/tr-nonexistent")
    assert resp.status == 404


def test_trigger_toggle(client):
    """PATCH endpoint enables/disables a trigger."""
    wf_id = _make_workflow(client)
    tr_id = _json(client("POST", "/triggers", body={
        "workflow_id": wf_id, "type": "github", "config": {"repo": "o/r"},
    }))["id"]
    resp = client("PATCH", f"/triggers/{tr_id}", body={"enabled": False})
    assert resp.status == 200
    assert _json(resp)["enabled"] is False
    # Re-enable
    resp = client("PATCH", f"/triggers/{tr_id}", body={"enabled": True})
    assert _json(resp)["enabled"] is True


def test_trigger_toggle_missing(client):
    resp = client("PATCH", "/triggers/tr-nonexistent", body={"enabled": False})
    assert resp.status == 404


def test_trigger_toggle_missing_enabled(client):
    wf_id = _make_workflow(client)
    tr_id = _json(client("POST", "/triggers", body={
        "workflow_id": wf_id, "type": "cron", "config": {},
    }))["id"]
    resp = client("PATCH", f"/triggers/{tr_id}", body={})
    assert resp.status == 400


# ---------------------------------------------------------------------------
# Phase 3: projects
# ---------------------------------------------------------------------------


def test_projects_empty(client):
    resp = client("GET", "/projects")
    assert resp.status == 200
    data = _json(resp)
    assert data["projects"] == []
    assert data["total"] == 0


def test_project_create_and_get(client):
    resp = client("POST", "/projects", body={
        "name": "远程工作台",
        "type": "github",
        "url": "github.com/owner/repo",
        "token": "ghp_xxx",
    })
    assert resp.status == 201
    project = _json(resp)
    assert project["name"] == "远程工作台"
    assert project["type"] == "github"
    assert project["has_token"] is True
    prj_id = project["id"]

    resp = client("GET", f"/projects/{prj_id}")
    assert resp.status == 200
    assert _json(resp)["id"] == prj_id


def test_project_create_missing_name(client):
    resp = client("POST", "/projects", body={"type": "local", "url": "/tmp"})
    assert resp.status == 400


def test_project_create_invalid_type(client):
    resp = client("POST", "/projects", body={
        "name": "x", "type": "invalid", "url": "",
    })
    assert resp.status == 400


def test_project_list(client):
    client("POST", "/projects", body={"name": "p1", "type": "local", "url": "/tmp"})
    resp = client("GET", "/projects")
    assert resp.status == 200
    assert _json(resp)["total"] >= 1


def test_project_get_missing(client):
    resp = client("GET", "/projects/prj-nonexistent")
    assert resp.status == 404


def test_project_delete(client):
    prj_id = _json(client("POST", "/projects", body={
        "name": "p1", "type": "local", "url": "/tmp",
    }))["id"]
    resp = client("DELETE", f"/projects/{prj_id}")
    assert resp.status == 200
    assert _json(resp)["deleted"] is True
    assert client("GET", f"/projects/{prj_id}").status == 404


def test_project_delete_missing(client):
    resp = client("DELETE", "/projects/prj-nonexistent")
    assert resp.status == 404


def test_projects_summary(client):
    client("POST", "/projects", body={"name": "p1", "type": "local", "url": "/tmp"})
    resp = client("GET", "/projects/summary")
    assert resp.status == 200
    summary = _json(resp)
    assert summary["total"] >= 1
    assert "connected" in summary
    assert "disconnected" in summary


def test_project_sync_skills(client):
    """Sync skills from a registered project to local."""
    prj_id = _json(client("POST", "/projects", body={
        "name": "p1", "type": "local", "url": "/tmp",
    }))["id"]
    resp = client("POST", f"/projects/{prj_id}/sync", body={"asset_type": "skills"})
    assert resp.status == 200
    data = _json(resp)
    assert data["ok"] is True
    assert len(data["results"]) == 1
    assert data["results"][0]["asset_type"] == "skills"
    assert data["results"][0]["synced"] >= 0


def test_project_sync_all(client):
    """Sync all assets from a registered project to local."""
    prj_id = _json(client("POST", "/projects", body={
        "name": "p1", "type": "local", "url": "/tmp",
    }))["id"]
    resp = client("POST", f"/projects/{prj_id}/sync", body={"asset_type": "all"})
    assert resp.status == 200
    data = _json(resp)
    # sync_all returns 3 results: skills + memory + profile
    assert len(data["results"]) == 3


def test_project_sync_missing(client):
    resp = client("POST", "/projects/prj-nonexistent/sync", body={"asset_type": "all"})
    assert resp.status == 404
