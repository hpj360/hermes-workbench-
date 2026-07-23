"""Tests for workbench.github_sync module.

Mocks the GitHubClient.request_executor so no network calls are made.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from hermes.workbench.cli import Task, TaskRegistry, TaskScheduler, TaskStore
from hermes.workbench.errors import AuthError, UpstreamError, ValidationError
from hermes.workbench.github_sync import (
    GitHubClient,
    GitHubSyncService,
    SyncResult,
    _extract_plan_from_body,
)


# ---------------------------------------------------------------------------
# _extract_plan_from_body
# ---------------------------------------------------------------------------


def test_extract_plan_raw_json():
    body = '{"plan": [{"skill": "weather"}], "mode": "oneshot"}'
    result = _extract_plan_from_body(body)
    assert result is not None
    assert result["plan"] == [{"skill": "weather"}]


def test_extract_plan_fenced_json():
    body = 'Some intro text\n\n```json\n{"plan": [{"skill": "weather"}]}\n```\n\nMore text'
    result = _extract_plan_from_body(body)
    assert result is not None
    assert result["plan"] == [{"skill": "weather"}]


def test_extract_plan_invalid_returns_none():
    assert _extract_plan_from_body("not json at all") is None


def test_extract_plan_empty_body():
    assert _extract_plan_from_body("") is None


def test_extract_plan_non_dict_json_returns_none():
    assert _extract_plan_from_body("[1, 2, 3]") is None


# ---------------------------------------------------------------------------
# GitHubClient (mocked)
# ---------------------------------------------------------------------------


def _make_client(
    responses: dict[str, Any], captured: list | None = None
) -> GitHubClient:
    """Create a GitHubClient with a mock executor that returns *responses* by path."""
    def executor(req: urllib.request.Request) -> bytes:
        if captured is not None:
            captured.append(req)
        # Extract path after /repos/{repo}: e.g. "/issues?labels=..."
        after_repos = req.full_url.split("/repos/")[1]
        # Strip the "owner/repo" prefix to get the API path.
        parts = after_repos.split("/", 1)
        api_path = "/" + parts[1] if len(parts) > 1 else ""
        # Drop query string for lookup.
        path_only = api_path.split("?", 1)[0]
        lookup_key = f"{req.method}:{path_only}"
        resp = responses.get(lookup_key)
        if resp is None:
            # Fallback: match by suffix.
            for k in responses:
                if path_only.endswith(k.split(":", 1)[1]) and k.startswith(req.method):
                    resp = responses[k]
                    break
        if isinstance(resp, Exception):
            raise resp
        return json.dumps(resp if resp is not None else {}).encode("utf-8")

    return GitHubClient(token="fake-token", repo="owner/repo", request_executor=executor)


def test_client_list_issues():
    client = _make_client(
        {"GET:/issues": [{"number": 1, "body": "{}", "labels": []}]}
    )
    issues = client.list_issues()
    assert len(issues) == 1
    assert issues[0]["number"] == 1


def test_client_list_issues_filters_prs():
    client = _make_client(
        {
            "GET:/issues": [
                {"number": 1, "body": "{}"},
                {"number": 2, "body": "{}", "pull_request": {"url": "..."}},
            ]
        }
    )
    issues = client.list_issues()
    assert len(issues) == 1
    assert issues[0]["number"] == 1


def test_client_create_comment():
    captured: list = []
    client = _make_client(
        {"POST:/issues/1/comments": {"id": 100, "body": "comment"}}, captured
    )
    result = client.create_comment(1, "hello")
    assert result["id"] == 100
    assert len(captured) == 1
    # Verify the request body contained our comment.
    req = captured[0]
    body = json.loads(req.data.decode())
    assert body["body"] == "hello"


def test_client_add_labels():
    client = _make_client(
        {"POST:/issues/1/labels": [{"name": "done"}, {"name": "workbench"}]}
    )
    labels = client.add_labels(1, ["done"])
    assert "done" in labels


def test_client_401_raises_auth_error():
    import urllib.error

    def executor(req: urllib.request.Request) -> bytes:
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    client = GitHubClient(token="bad", repo="o/r", request_executor=executor)
    with pytest.raises(AuthError):
        client.list_issues()


def test_client_404_raises_upstream_error():
    import urllib.error

    def executor(req: urllib.request.Request) -> bytes:
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    client = GitHubClient(token="bad", repo="o/r", request_executor=executor)
    with pytest.raises(UpstreamError):
        client.get_issue(999)


# ---------------------------------------------------------------------------
# GitHubSyncService
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> TaskStore:
    return TaskStore(state_dir=tmp_path)


@pytest.fixture
def registry() -> TaskRegistry:
    return TaskRegistry()


@pytest.fixture
def fake_runner(tmp_path: Path):
    """A SkillRunner pointed at an empty skills dir (tasks will fail gracefully)."""
    from hermes.workbench.skill_runner import SkillRunner

    return SkillRunner(base_dir=tmp_path / "empty_skills")


@pytest.fixture
def memory(tmp_path: Path):
    from hermes.workbench.memory import MemoryService

    return MemoryService(state_dir=tmp_path)


@pytest.fixture
def scheduler(store, registry, fake_runner, memory) -> TaskScheduler:
    return TaskScheduler(store=store, registry=registry, runner=fake_runner, memory=memory)


@pytest.fixture
def sync_service(scheduler, store, registry) -> GitHubSyncService:
    client = _make_client({})
    return GitHubSyncService(client=client, scheduler=scheduler, store=store, registry=registry)


def test_pull_issues_creates_tasks(sync_service, registry, store, monkeypatch):
    """Pull should create+register tasks from issue bodies with valid plans."""
    issues = [
        {"number": 1, "body": '{"plan": [{"skill": "weather"}], "mode": "oneshot"}'},
        {"number": 2, "body": "no plan here"},
        {"number": 3, "body": '```json\n{"plan": [{"skill": "summarize"}]}\n```'},
    ]
    monkeypatch.setattr(sync_service.client, "list_issues", lambda label="workbench", state="open": issues)

    created = sync_service.pull_issues()
    assert len(created) == 2  # issue 2 skipped
    assert created[0]["issue_number"] == 1
    assert created[1]["issue_number"] == 3
    # Tasks registered + saved
    assert registry.get(created[0]["task_id"]) is not None
    assert store.get(created[0]["task_id"]) is not None


def test_pull_issues_skips_invalid_bodies(sync_service, monkeypatch):
    monkeypatch.setattr(
        sync_service.client,
        "list_issues",
        lambda label="workbench", state="open": [{"number": 1, "body": "not json"}],
    )
    created = sync_service.pull_issues()
    assert created == []


def test_push_result_posts_comment(sync_service, store, monkeypatch):
    # Create a task with a round result.
    task = Task(task_id="t1", plan=[{"skill": "weather"}])
    task.status = "COMPLETED"
    task.rounds = [{"ok": True, "error": None}]
    store.save(task)

    captured: list = []
    monkeypatch.setattr(
        sync_service.client,
        "create_comment",
        lambda issue_number, body: captured.append((issue_number, body)) or {"id": 1},
    )

    sync_service.push_result("t1", issue_number=42)
    assert len(captured) == 1
    issue_num, comment = captured[0]
    assert issue_num == 42
    assert "COMPLETED" in comment
    assert "t1" in comment


def test_push_result_missing_task_raises(sync_service):
    with pytest.raises(ValidationError):
        sync_service.push_result("nonexistent", issue_number=1)


def test_sync_full_cycle(sync_service, store, registry, monkeypatch):
    """Full sync: pull → run → push."""
    issues = [
        {"number": 1, "body": '{"plan": [{"skill": "weather"}]}'},
    ]
    monkeypatch.setattr(sync_service.client, "list_issues", lambda label="workbench", state="open": issues)

    pushed: list = []
    monkeypatch.setattr(
        sync_service.client,
        "create_comment",
        lambda issue_number, body: pushed.append(issue_number) or {"id": 1},
    )

    result = sync_service.sync()
    assert result["pulled"] == 1
    assert result["ran"] == 1
    assert result["pushed"] == 1
    assert len(result["task_ids"]) == 1
    assert pushed == [1]


def test_sync_pull_failure_records_error(sync_service, monkeypatch):
    monkeypatch.setattr(
        sync_service.client,
        "list_issues",
        lambda label="workbench", state="open": (_ for _ in ()).throw(RuntimeError("network down")),
    )
    result = sync_service.sync()
    assert result["pulled"] == 0
    assert len(result["errors"]) == 1
    assert "pull failed" in result["errors"][0]


def test_sync_push_failure_continues(sync_service, store, registry, monkeypatch):
    """If push fails, the error is recorded but sync continues."""
    issues = [{"number": 1, "body": '{"plan": [{"skill": "weather"}]}'}]
    monkeypatch.setattr(sync_service.client, "list_issues", lambda label="workbench", state="open": issues)
    monkeypatch.setattr(
        sync_service.client,
        "create_comment",
        lambda issue_number, body: (_ for _ in ()).throw(UpstreamError("push failed")),
    )
    result = sync_service.sync()
    assert result["ran"] == 1
    assert result["pushed"] == 0
    assert len(result["errors"]) == 1


def test_from_env_requires_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    with pytest.raises(ValidationError):
        GitHubSyncService.from_env(repo="owner/repo")


def test_from_env_with_token(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_fake")
    # Patch the cli factories to avoid real state dir.
    import hermes.workbench.cli as cli_mod

    monkeypatch.setattr(cli_mod, "_make_store", lambda: TaskStore(state_dir=Path("/tmp/test_gh")))
    monkeypatch.setattr(cli_mod, "_make_registry", lambda: TaskRegistry())
    service = GitHubSyncService.from_env(repo="owner/repo", token="ghp_fake")
    assert service.client.token == "ghp_fake"
    assert service.client.repo == "owner/repo"


def test_syncresult_to_dict():
    r = SyncResult(pulled=2, ran=1, pushed=1, errors=["e1"])
    d = r.to_dict()
    assert d["pulled"] == 2
    assert d["ran"] == 1
    assert d["pushed"] == 1
    assert d["errors"] == ["e1"]
