"""GitHub sync layer (P4).

Bridges GitHub Issues and the Workbench task system:
- **Pull**: fetch open issues tagged with a label (default ``workbench``),
  parse a JSON plan from the issue body, create + register a Task.
- **Run**: execute the task via TaskScheduler.
- **Push**: post the task result back as a comment on the source issue.

Uses only the standard library (urllib) — zero new dependencies. The
``GitHubClient`` accepts an injectable ``request_executor`` so tests can
mock HTTP without touching the network.

Issue body format (JSON, optionally inside a ```json fence):

    {"plan": [{"skill": "weather"}], "mode": "oneshot", "issue_number": 42}

If the body is not valid JSON, the issue is skipped (recorded as a parse
error in the sync result).
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

from hermes.workbench.errors import AuthError, UpstreamError, ValidationError

__all__ = ["GitHubClient", "GitHubSyncService", "SyncResult"]

GITHUB_API = "https://api.github.com"

RequestExecutor = Callable[[urllib.request.Request], bytes]


def _default_executor(req: urllib.request.Request) -> bytes:
    """Default executor: perform the real HTTP call via urllib.

    Lets ``HTTPError``/``URLError`` propagate; ``GitHubClient._request``
    is responsible for translating them into Workbench errors so that
    the same translation applies to mocked executors in tests.
    """
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        return resp.read()


def _translate_http_error(e: urllib.error.HTTPError) -> Exception:
    """Map an urllib HTTPError to the appropriate WorkbenchError."""
    if e.code == 401:
        return AuthError(f"GitHub auth failed (401): {e.reason}")
    if e.code == 404:
        return UpstreamError(f"GitHub resource not found (404): {e.reason}")
    return UpstreamError(f"GitHub API error ({e.code}): {e.reason}")


_JSON_FENCE_RE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)


def _extract_plan_from_body(body: str) -> dict[str, Any] | None:
    """Extract a plan dict from an issue body.

    Tries a ```json fenced block first, then the raw body.
    Returns None if no valid JSON plan is found.
    """
    match = _JSON_FENCE_RE.search(body)
    candidates = [match.group(1)] if match else []
    candidates.append(body.strip())
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict):
            return data
    return None


@dataclass
class GitHubClient:
    """Thin wrapper over the GitHub REST API (urllib, zero deps)."""

    token: str
    repo: str  # "owner/name"
    request_executor: RequestExecutor = field(default=_default_executor)

    def _request(self, method: str, path: str, body: Any = None) -> Any:
        url = f"{GITHUB_API}/repos/{self.repo}{path}"
        data = None
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            raw = self.request_executor(req)
        except urllib.error.HTTPError as e:
            raise _translate_http_error(e) from e
        except urllib.error.URLError as e:
            raise UpstreamError(f"GitHub network error: {e.reason}") from e
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))

    def list_issues(self, label: str = "workbench", state: str = "open") -> list[dict[str, Any]]:
        """List issues with *label* (default 'workbench')."""
        data = self._request("GET", f"/issues?labels={label}&state={state}&per_page=100")
        if not isinstance(data, list):
            return []
        # GitHub returns PRs in /issues too; filter them out.
        return [i for i in data if "pull_request" not in i]

    def get_issue(self, number: int) -> dict[str, Any]:
        """Fetch a single issue by number."""
        data = self._request("GET", f"/issues/{number}")
        if not isinstance(data, dict):
            raise UpstreamError(f"unexpected response for issue #{number}")
        return data

    def create_comment(self, issue_number: int, body: str) -> dict[str, Any]:
        """Post a comment on issue *issue_number*."""
        data = self._request("POST", f"/issues/{issue_number}/comments", body={"body": body})
        if not isinstance(data, dict):
            raise UpstreamError(f"unexpected response commenting on #{issue_number}")
        return data

    def add_labels(self, issue_number: int, labels: list[str]) -> list[str]:
        """Add labels to an issue. Returns the resulting label list."""
        data = self._request(
            "POST", f"/issues/{issue_number}/labels", body={"labels": labels}
        )
        if not isinstance(data, list):
            return []
        return [str(label.get("name", "")) for label in data]


@dataclass
class SyncResult:
    """Summary of one sync cycle."""

    pulled: int = 0
    ran: int = 0
    pushed: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    task_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pulled": self.pulled,
            "ran": self.ran,
            "pushed": self.pushed,
            "skipped": self.skipped,
            "errors": self.errors,
            "task_ids": self.task_ids,
        }


class GitHubSyncService:
    """Orchestrates the pull → run → push cycle.

    Pulls GitHub issues as workbench tasks, runs them, and pushes results
    back as issue comments.
    """

    def __init__(
        self,
        client: GitHubClient,
        scheduler: Any,  # cli.TaskScheduler
        store: Any,  # cli.TaskStore
        registry: Any,  # cli.TaskRegistry
    ) -> None:
        self.client = client
        self.scheduler = scheduler
        self.store = store
        self.registry = registry

    @classmethod
    def from_env(cls, repo: str, token: str | None = None) -> GitHubSyncService:
        """Build a service from environment (GITHUB_TOKEN). Raises if no token."""
        token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not token:
            raise ValidationError("GITHUB_TOKEN (or GH_TOKEN) env var is required")
        # Import here to avoid circular import at module load.
        from hermes.workbench.cli import _make_registry, _make_scheduler, _make_store

        client = GitHubClient(token=token, repo=repo)
        return cls(
            client=client,
            scheduler=_make_scheduler(),
            store=_make_store(),
            registry=_make_registry(),
        )

    def pull_issues(self, label: str = "workbench") -> list[dict[str, Any]]:
        """Fetch tagged issues and create+register tasks from their bodies.

        Returns a list of {"issue_number", "task_id", "plan"} dicts.
        Issues without a valid JSON plan are skipped.
        """
        from hermes.workbench.cli import Task

        issues = self.client.list_issues(label=label)
        created: list[dict[str, Any]] = []
        for issue in issues:
            number = issue.get("number")
            body = issue.get("body") or ""
            plan_data = _extract_plan_from_body(body)
            if plan_data is None or "plan" not in plan_data:
                continue
            import uuid

            task_id = plan_data.get("task_id") or f"gh-{number}-{uuid.uuid4().hex[:6]}"
            task = Task(
                task_id=task_id,
                plan=plan_data["plan"],
                mode=plan_data.get("mode", "oneshot"),
                max_rounds=plan_data.get("max_rounds", 1),
                max_runs=plan_data.get("max_runs", 1),
                interval=plan_data.get("interval", 0.0),
            )
            self.registry.register(task)
            self.store.save(task)
            created.append(
                {"issue_number": number, "task_id": task_id, "plan": plan_data["plan"]}
            )
        return created

    def push_result(self, task_id: str, issue_number: int) -> dict[str, Any]:
        """Post the task's latest round result as a comment on the issue."""
        task = self.store.get(task_id)
        if task is None:
            raise ValidationError(f"task not found: {task_id}")
        rounds = task.get("rounds", [])
        status = task.get("status", "UNKNOWN")
        last = rounds[-1] if rounds else {}
        ok = last.get("ok", False) if last else False
        comment = (
            f"## Workbench Task Result\n\n"
            f"- **Task ID:** `{task_id}`\n"
            f"- **Status:** {status}\n"
            f"- **Rounds:** {len(rounds)}\n"
            f"- **Last round OK:** {ok}\n"
        )
        if last.get("error"):
            comment += f"- **Error:** {last['error']}\n"
        comment += "\n_Synced by Hermes Workbench_"
        return self.client.create_comment(issue_number, comment)

    def sync(self, label: str = "workbench") -> dict[str, Any]:
        """Full cycle: pull issues → run tasks → push results.

        Returns a SyncResult dict.
        """
        result = SyncResult()
        try:
            created = self.pull_issues(label=label)
        except Exception as e:  # noqa: BLE001
            result.errors.append(f"pull failed: {e}")
            return result.to_dict()

        result.pulled = len(created)
        for item in created:
            task_id = item["task_id"]
            issue_number = item["issue_number"]
            result.task_ids.append(task_id)
            try:
                self.scheduler.run(task_id)
                result.ran += 1
            except Exception as e:  # noqa: BLE001
                result.errors.append(f"run {task_id} failed: {e}")
                continue
            try:
                self.push_result(task_id, issue_number)
                result.pushed += 1
            except Exception as e:  # noqa: BLE001
                result.errors.append(f"push {task_id} → #{issue_number} failed: {e}")
        return result.to_dict()
