"""Dashboard HTTP API.

Exposes workbench capabilities (skills/memory/tasks) as a RESTful JSON API
using only the standard library (http.server). The server is a stateless
adapter: all state flows through the cli.py service factories. Errors map
to HTTP status codes via workbench.errors.

Run via ``hermes workbench serve --host 127.0.0.1 --port 8080``.
"""

from __future__ import annotations

import hmac
import json
import mimetypes
import os
import re
import shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from hermes.config import get_settings
from hermes.workbench.errors import NotFoundError, ValidationError, WorkbenchError, status_code_for

__all__ = ["DashboardHandler", "make_server", "run_server"]


# Route table: (method, regex, handler_name). Named groups become kwargs.
_ROUTES: list[tuple[str, str, str]] = [
    ("GET", r"^/health$", "h_get_health"),
    ("GET", r"^/$", "h_get_index"),
    ("GET", r"^/skills$", "h_get_skills"),
    ("GET", r"^/skills/(?P<name>[^/]+)$", "h_get_skill"),
    ("POST", r"^/skills/(?P<name>[^/]+)/run$", "h_post_skill_run"),
    ("GET", r"^/memory/facts$", "h_get_facts"),
    ("POST", r"^/memory/facts$", "h_post_facts"),
    ("GET", r"^/memory/facts/(?P<key>[^/]+)$", "h_get_fact"),
    ("DELETE", r"^/memory/facts/(?P<key>[^/]+)$", "h_delete_fact"),
    ("GET", r"^/memory/episodes$", "h_get_episodes"),
    ("GET", r"^/memory/profile$", "h_get_profile"),
    ("PUT", r"^/memory/profile$", "h_put_profile"),
    ("POST", r"^/tasks$", "h_post_tasks"),
    ("GET", r"^/tasks$", "h_get_tasks"),
    ("GET", r"^/tasks/(?P<task_id>[^/]+)$", "h_get_task"),
    ("POST", r"^/tasks/(?P<task_id>[^/]+)/cancel$", "h_post_task_cancel"),
    ("POST", r"^/tasks/(?P<task_id>[^/]+)/run$", "h_post_task_run"),
    ("GET", r"^/github/sync$", "h_get_github_sync"),
    ("GET", r"^/registry/sources$", "h_get_registry_sources"),
    ("GET", r"^/registry/skills$", "h_get_registry_skills"),
    ("GET", r"^/registry/agents$", "h_get_registry_agents"),
    ("GET", r"^/registry/knowledge$", "h_get_registry_knowledge"),
    ("GET", r"^/registry/user$", "h_get_registry_user"),
    ("GET", r"^/registry/summary$", "h_get_registry_summary"),
    ("GET", r"^/search$", "h_search"),
    # Phase 2: workflows & triggers
    ("GET", r"^/workflows$", "h_get_workflows"),
    ("POST", r"^/workflows$", "h_post_workflows"),
    ("GET", r"^/workflows/(?P<wf_id>[^/]+)$", "h_get_workflow"),
    ("PUT", r"^/workflows/(?P<wf_id>[^/]+)$", "h_put_workflow"),
    ("DELETE", r"^/workflows/(?P<wf_id>[^/]+)$", "h_delete_workflow"),
    ("POST", r"^/workflows/(?P<wf_id>[^/]+)/execute$", "h_post_workflow_execute"),
    ("GET", r"^/workflows/(?P<wf_id>[^/]+)/executions$", "h_get_workflow_executions"),
    ("GET", r"^/triggers$", "h_get_triggers"),
    ("POST", r"^/triggers$", "h_post_triggers"),
    ("DELETE", r"^/triggers/(?P<tr_id>[^/]+)$", "h_delete_trigger"),
    ("PATCH", r"^/triggers/(?P<tr_id>[^/]+)$", "h_patch_trigger"),
    # Phase 3: projects & sync
    ("GET", r"^/projects$", "h_get_projects"),
    ("POST", r"^/projects$", "h_post_projects"),
    ("GET", r"^/projects/summary$", "h_get_projects_summary"),
    ("GET", r"^/projects/(?P<prj_id>[^/]+)$", "h_get_project"),
    ("DELETE", r"^/projects/(?P<prj_id>[^/]+)$", "h_delete_project"),
    ("POST", r"^/projects/(?P<prj_id>[^/]+)/sync$", "h_post_project_sync"),
]

# Paths exempt from authentication (public endpoints).
_AUTH_EXEMPT_PATHS = {"/health", "/"}

# Prototype directory for static file serving.
_PROTOYPE_DIR = Path(__file__).resolve().parents[3] / "prototype"


class DashboardHandler(BaseHTTPRequestHandler):
    """HTTP handler dispatching to workbench services."""

    def log_message(self, format: str, *args: Any) -> None:
        pass

    # Dispatch -----------------------------------------------------------

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")

    def do_PUT(self) -> None:
        self._dispatch("PUT")

    def do_PATCH(self) -> None:
        self._dispatch("PATCH")

    def _dispatch(self, method: str) -> None:
        path = urlsplit(self.path).path
        # Auth: public endpoints are exempt. When HERMES_API_TOKEN is set,
        # every other endpoint requires an ``Authorization: Bearer <token>`` header.
        if path not in _AUTH_EXEMPT_PATHS and not self._check_auth():
            self._send_json(401, {"error": "unauthorized", "type": "AuthError"})
            return
        for route_method, pattern, handler_name in _ROUTES:
            if route_method != method:
                continue
            match = re.match(pattern, path)
            if match:
                handler = getattr(self, handler_name)
                try:
                    handler(**match.groupdict())
                except WorkbenchError as e:
                    self._send_json(status_code_for(e), {"error": str(e), "type": type(e).__name__})
                except Exception as e:  # noqa: BLE001 - boundary
                    self._send_json(500, {"error": str(e), "type": type(e).__name__})
                return
        # No route matched: 405 if path matches another method, else 404.
        for _m, pattern, _h in _ROUTES:
            if re.match(pattern, path):
                self._method_not_allowed()
                return
        self._send_json(404, {"error": "not found", "path": path})

    # Helpers ------------------------------------------------------------

    def _send_json(self, status: int, obj: Any) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_no_content(self) -> None:
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _read_json_body(self) -> Any:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ValidationError(f"invalid JSON body: {e}") from e

    def _query_params(self) -> dict[str, str]:
        parsed = parse_qs(urlsplit(self.path).query)
        return {k: v[0] for k, v in parsed.items() if v}

    def _method_not_allowed(self) -> None:
        self._send_json(405, {"error": "method not allowed"})

    def _check_auth(self) -> bool:
        """Return True if the request is authorized (or auth is disabled).

        Auth is disabled when ``HERMES_API_TOKEN`` is unset/empty, keeping the
        server backward compatible. When set, the request must carry an
        ``Authorization: Bearer <token>`` header matching the configured token.
        """
        token = get_settings().hermes_api_token
        if not token:
            return True  # auth disabled
        expected = f"Bearer {token}"
        provided = self.headers.get("Authorization", "")
        return hmac.compare_digest(provided, expected)

    # Services (injected by make_server) ---------------------------------
    # These are set as class attributes by make_server via type().

    # health -------------------------------------------------------------

    def h_get_health(self) -> None:
        from hermes.workbench.cli import _make_runner

        settings = get_settings()
        providers = settings.configured_providers()
        specs = _make_runner().discover()
        skills_total = len(specs)
        skills_ready = sum(1 for s in specs if _check_skill_status(s) == "ready")
        self._send_json(
            200,
            {
                "status": "ok",
                "services": ["skills", "memory", "tasks"],
                "providers": providers,
                "providers_count": len(providers),
                "skills_total": skills_total,
                "skills_ready": skills_ready,
                "memory_layers": ["L1", "L2", "L3"],
            },
        )

    # skills -------------------------------------------------------------

    def h_get_skills(self) -> None:
        from hermes.workbench.cli import _make_runner

        specs = _make_runner().discover()
        self._send_json(
            200,
            {
                "skills": [
                    {
                        "name": s.name,
                        "runtime": s.runtime,
                        "description": s.description,
                        "entrypoint": s.entrypoint,
                        "requires_bins": s.requires_bins,
                        "requires_env": s.requires_env,
                        "status": _check_skill_status(s),
                    }
                    for s in specs
                ]
            },
        )

    def h_get_skill(self, name: str) -> None:
        from hermes.workbench.cli import _make_runner

        spec = _make_runner().get(name)
        if spec is None:
            raise NotFoundError(f"skill not found: {name}")
        self._send_json(
            200,
            {
                "name": spec.name,
                "path": str(spec.path),
                "runtime": spec.runtime,
                "entrypoint": spec.entrypoint,
                "description": spec.description,
                "requires_bins": spec.requires_bins,
                "requires_env": spec.requires_env,
                "status": _check_skill_status(spec),
            },
        )

    def h_post_skill_run(self, name: str) -> None:
        """Run a skill by name. Body: {"args": ["--flag", "value"]}."""
        from hermes.workbench.cli import _make_runner

        body = self._read_json_body()
        if not isinstance(body, dict):
            raise ValidationError("body must be a JSON object")
        args = body.get("args", [])
        if not isinstance(args, list):
            raise ValidationError("'args' must be a JSON array")
        timeout = body.get("timeout")
        if timeout is not None and not isinstance(timeout, (int, float)):
            raise ValidationError("'timeout' must be a number")

        result = _make_runner().run(name, args=[str(a) for a in args], timeout=timeout)
        self._send_json(
            200,
            {
                "skill": result.skill,
                "ok": result.ok,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
                "duration": result.duration,
                "error": result.error,
            },
        )

    # memory facts -------------------------------------------------------

    def h_get_facts(self) -> None:
        from hermes.workbench.cli import _make_memory

        facts = _make_memory().list_facts()
        self._send_json(200, {"facts": facts})

    def h_post_facts(self) -> None:
        from hermes.workbench.cli import _make_memory

        body = self._read_json_body()
        if not isinstance(body, dict) or "key" not in body or "value" not in body:
            raise ValidationError("body must contain 'key' and 'value'")
        _make_memory().remember_fact(body["key"], body["value"])
        self._send_json(201, {"key": body["key"], "value": body["value"]})

    def h_get_fact(self, key: str) -> None:
        from hermes.workbench.cli import _make_memory

        fact = _make_memory().get_fact(key)
        if fact is None:
            raise NotFoundError(f"fact not found: {key}")
        self._send_json(200, fact)

    def h_delete_fact(self, key: str) -> None:
        from hermes.workbench.cli import _make_memory

        if not _make_memory().forget_fact(key):
            raise NotFoundError(f"fact not found: {key}")
        self._send_no_content()

    # memory episodes ----------------------------------------------------

    def h_get_episodes(self) -> None:
        from hermes.workbench.cli import _make_memory

        params = self._query_params()
        limit = int(params.get("limit", "1000"))
        episodes = _make_memory().list_episodes(kind=params.get("kind"), limit=limit)
        self._send_json(200, {"episodes": [e.__dict__ for e in episodes]})

    # memory profile -----------------------------------------------------

    def h_get_profile(self) -> None:
        from hermes.workbench.cli import _make_memory

        profile = _make_memory().get_user_profile()
        self._send_json(200, profile)

    def h_put_profile(self) -> None:
        """Update the user profile. Body: full profile JSON object."""
        from hermes.workbench.cli import _make_memory

        body = self._read_json_body()
        if not isinstance(body, dict):
            raise ValidationError("body must be a JSON object")
        _make_memory().save_user_profile(body)
        self._send_json(200, body)

    # tasks --------------------------------------------------------------

    def h_post_tasks(self) -> None:
        """Create and optionally run a task in one call.

        Body: {"plan": [...], "mode": "oneshot", "run": true, "task_id": "..."}
        """
        from hermes.workbench.cli import Task, _make_registry, _make_store

        body = self._read_json_body()
        if not isinstance(body, dict) or "plan" not in body:
            raise ValidationError("body must contain 'plan'")
        plan = body["plan"]
        if not isinstance(plan, list):
            raise ValidationError("'plan' must be a JSON array")

        import uuid

        task_id = body.get("task_id") or f"task-{uuid.uuid4().hex[:8]}"
        task = Task(
            task_id=task_id,
            plan=plan,
            mode=body.get("mode", "oneshot"),
            max_rounds=body.get("max_rounds", 1),
            max_runs=body.get("max_runs", 1),
            interval=body.get("interval", 0.0),
        )
        _make_registry().register(task)
        _make_store().save(task)

        run_now = body.get("run", True)
        if run_now:
            from hermes.workbench.cli import _make_scheduler

            result = _make_scheduler().run(task_id)
            task_dict = _make_store().get(task_id)
            if task_dict is None:
                raise NotFoundError(f"task vanished after run: {task_id}")
            task_dict["result_ok"] = getattr(result, "ok", False) if result else False
            self._send_json(200, task_dict)
        else:
            self._send_json(201, task.to_dict())

    def h_get_tasks(self) -> None:
        from hermes.workbench.cli import _make_store

        tasks = _make_store().list()
        self._send_json(200, {"tasks": tasks})

    def h_get_task(self, task_id: str) -> None:
        from hermes.workbench.cli import _make_store

        task = _make_store().get(task_id)
        if task is None:
            raise NotFoundError(f"task not found: {task_id}")
        self._send_json(200, task)

    def h_post_task_run(self, task_id: str) -> None:
        """Run a previously-registered task."""
        from hermes.workbench.cli import _make_scheduler, _make_store

        existing = _make_store().get(task_id)
        if existing is None:
            raise NotFoundError(f"task not found: {task_id}")
        # Re-register if the in-memory registry lost it (e.g. new request).
        from hermes.workbench.cli import Task, _make_registry

        if _make_registry().get(task_id) is None:
            task = Task(
                task_id=existing["task_id"],
                plan=existing["plan"],
                mode=existing.get("mode", "oneshot"),
                max_rounds=existing.get("max_rounds", 1),
                max_runs=existing.get("max_runs", 1),
                interval=existing.get("interval", 0.0),
            )
            task.rounds = existing.get("rounds", [])
            task.status = existing.get("status", "PENDING")
            _make_registry().register(task)

        result = _make_scheduler().run(task_id)
        task_dict = _make_store().get(task_id)
        if task_dict is None:
            raise NotFoundError(f"task vanished after run: {task_id}")
        task_dict["result_ok"] = getattr(result, "ok", False) if result else False
        self._send_json(200, task_dict)

    def h_post_task_cancel(self, task_id: str) -> None:
        from hermes.workbench.cli import _make_scheduler, _make_store

        existing = _make_store().get(task_id)
        if existing is None:
            raise NotFoundError(f"task not found: {task_id}")
        # Re-register if needed so scheduler.cancel can find it.
        from hermes.workbench.cli import Task, _make_registry

        if _make_registry().get(task_id) is None:
            task = Task(
                task_id=existing["task_id"],
                plan=existing["plan"],
                mode=existing.get("mode", "oneshot"),
            )
            task.rounds = existing.get("rounds", [])
            task.status = existing.get("status", "PENDING")
            _make_registry().register(task)

        _make_scheduler().cancel(task_id)
        task_dict = _make_store().get(task_id)
        self._send_json(200, task_dict or {"task_id": task_id, "status": "CANCELLED"})

    # github sync --------------------------------------------------------

    def h_get_github_sync(self) -> None:
        """Trigger a GitHub sync cycle (pull issues → run → push results).

        Query params: ?repo=owner/name&label=workbench
        """
        from hermes.workbench.github_sync import GitHubSyncService

        params = self._query_params()
        repo = params.get("repo")
        if not repo:
            raise ValidationError("query param 'repo' is required (e.g. owner/name)")
        label = params.get("label", "workbench")
        service = GitHubSyncService.from_env(repo=repo)
        result = service.sync(label=label)
        self._send_json(200, result)

    # Registry -----------------------------------------------------------

    def _get_registry(self):
        from hermes.workbench.cli import _make_unified_registry

        return _make_unified_registry()

    def h_get_registry_sources(self) -> None:
        """List all registry sources (local + GitHub repos)."""
        registry = self._get_registry()
        sources = [s.to_dict() for s in registry.list_sources()]
        self._send_json(200, {"sources": sources, "total": len(sources)})

    def h_get_registry_skills(self) -> None:
        """List skills across all sources. Query: ?source=name"""
        registry = self._get_registry()
        params = self._query_params()
        source = params.get("source")
        skills = [s.to_dict() for s in registry.list_skills(source=source)]
        self._send_json(200, {"skills": skills, "total": len(skills)})

    def h_get_registry_agents(self) -> None:
        """List agents across all sources. Query: ?source=name"""
        registry = self._get_registry()
        params = self._query_params()
        source = params.get("source")
        agents = [a.to_dict() for a in registry.list_agents(source=source)]
        self._send_json(200, {"agents": agents, "total": len(agents)})

    def h_get_registry_knowledge(self) -> None:
        """List knowledge docs across all sources. Query: ?source=name"""
        registry = self._get_registry()
        params = self._query_params()
        source = params.get("source")
        docs = [d.to_dict() for d in registry.list_knowledge(source=source)]
        self._send_json(200, {"knowledge": docs, "total": len(docs)})

    def h_get_registry_user(self) -> None:
        """Show merged user profile across sources."""
        registry = self._get_registry()
        profile = registry.get_user_profile()
        self._send_json(200, profile)

    def h_get_registry_summary(self) -> None:
        """Show registry summary statistics."""
        registry = self._get_registry()
        self._send_json(200, registry.summary())

    # search --------------------------------------------------------------

    def h_search(self) -> None:
        """Global search across skills, memory facts, and tasks."""
        from hermes.workbench.cli import _make_memory, _make_runner, _make_store

        params = self._query_params()
        q = params.get("q", "").lower().strip()
        if not q:
            self._send_json(200, {"results": [], "total": 0})
            return

        results: list[dict[str, Any]] = []

        # Search skills
        for spec in _make_runner().discover():
            if q in spec.name.lower() or q in (spec.description or "").lower():
                results.append({
                    "type": "skill",
                    "name": spec.name,
                    "description": spec.description,
                    "runtime": spec.runtime,
                    "url": "#/skills",
                })

        # Search memory facts
        for fact in _make_memory().list_facts():
            key = fact.get("key", "")
            value = fact.get("value")
            if q in key.lower() or q in str(value).lower():
                results.append({
                    "type": "fact",
                    "name": key,
                    "description": str(value)[:200],
                    "url": "#/memory",
                })

        # Search tasks
        for task in _make_store().list():
            tid = task.get("task_id", "")
            if q in tid.lower() or q in str(task.get("plan", "")).lower():
                results.append({
                    "type": "task",
                    "name": tid,
                    "description": f"状态: {task.get('status', '?')}, 模式: {task.get('mode', '?')}",
                    "url": "#/tasks",
                })

        self._send_json(200, {"results": results, "total": len(results)})

    # Phase 2: workflows -------------------------------------------------

    def h_get_workflows(self) -> None:
        from hermes.workbench.cli import _make_workflow_store

        wfs = _make_workflow_store().list()
        self._send_json(200, {"workflows": [w.to_dict() for w in wfs], "total": len(wfs)})

    def h_post_workflows(self) -> None:
        from hermes.workbench.cli import _make_workflow_store

        body = self._read_json_body()
        if not isinstance(body, dict):
            raise ValidationError("body must be a JSON object")
        name = body.get("name", "")
        if not name:
            raise ValidationError("'name' is required")
        description = body.get("description", "")
        steps = body.get("steps", [])
        if not isinstance(steps, list):
            raise ValidationError("'steps' must be a list")
        wf = _make_workflow_store().create(name, description, steps)
        self._send_json(201, wf.to_dict())

    def h_get_workflow(self, wf_id: str) -> None:
        from hermes.workbench.cli import _make_workflow_store

        wf = _make_workflow_store().get(wf_id)
        if wf is None:
            raise NotFoundError(f"workflow not found: {wf_id}")
        self._send_json(200, wf.to_dict())

    def h_put_workflow(self, wf_id: str) -> None:
        from hermes.workbench.cli import _make_workflow_store

        body = self._read_json_body()
        if not isinstance(body, dict):
            raise ValidationError("body must be a JSON object")
        wf = _make_workflow_store().update(
            wf_id,
            name=body.get("name"),
            description=body.get("description"),
            steps=body.get("steps"),
        )
        if wf is None:
            raise NotFoundError(f"workflow not found: {wf_id}")
        self._send_json(200, wf.to_dict())

    def h_delete_workflow(self, wf_id: str) -> None:
        from hermes.workbench.cli import _make_workflow_store

        if _make_workflow_store().delete(wf_id):
            self._send_json(200, {"deleted": True})
        else:
            raise NotFoundError(f"workflow not found: {wf_id}")

    def h_post_workflow_execute(self, wf_id: str) -> None:
        from hermes.workbench.cli import _make_workflow_runner, _make_workflow_store

        wf = _make_workflow_store().get(wf_id)
        if wf is None:
            raise NotFoundError(f"workflow not found: {wf_id}")
        body = self._read_json_body() if self.command == "POST" else {}
        timeout = body.get("timeout") if isinstance(body, dict) else None
        execution = _make_workflow_runner().execute(wf, timeout=timeout)
        self._send_json(200, execution.to_dict())

    def h_get_workflow_executions(self, wf_id: str) -> None:
        from hermes.workbench.cli import _make_workflow_runner

        params = self._query_params()
        limit = int(params.get("limit", "20"))
        execs = _make_workflow_runner().list_executions(wf_id, limit=limit)
        self._send_json(200, {"executions": execs, "total": len(execs)})

    # Phase 2: triggers --------------------------------------------------

    def h_get_triggers(self) -> None:
        from hermes.workbench.cli import _make_trigger_store

        params = self._query_params()
        wf_id = params.get("workflow_id")
        triggers = _make_trigger_store().list(workflow_id=wf_id)
        self._send_json(200, {"triggers": [t.to_dict() for t in triggers], "total": len(triggers)})

    def h_post_triggers(self) -> None:
        from hermes.workbench.cli import _make_trigger_store

        body = self._read_json_body()
        if not isinstance(body, dict):
            raise ValidationError("body must be a JSON object")
        wf_id = body.get("workflow_id", "")
        if not wf_id:
            raise ValidationError("'workflow_id' is required")
        trigger_type = body.get("type", "")
        if not trigger_type:
            raise ValidationError("'type' is required")
        config = body.get("config", {})
        trigger = _make_trigger_store().create(wf_id, trigger_type, config)
        self._send_json(201, trigger.to_dict())

    def h_delete_trigger(self, tr_id: str) -> None:
        from hermes.workbench.cli import _make_trigger_store

        if _make_trigger_store().delete(tr_id):
            self._send_json(200, {"deleted": True})
        else:
            raise NotFoundError(f"trigger not found: {tr_id}")

    def h_patch_trigger(self, tr_id: str) -> None:
        from hermes.workbench.cli import _make_trigger_store

        body = self._read_json_body()
        if not isinstance(body, dict):
            raise ValidationError("body must be a JSON object")
        enabled = body.get("enabled")
        if enabled is None:
            raise ValidationError("'enabled' is required")
        trigger = _make_trigger_store().toggle(tr_id, bool(enabled))
        if trigger is None:
            raise NotFoundError(f"trigger not found: {tr_id}")
        self._send_json(200, trigger.to_dict())

    # Phase 3: projects --------------------------------------------------

    def h_get_projects(self) -> None:
        from hermes.workbench.cli import _make_project_registry

        projects = _make_project_registry().list()
        self._send_json(200, {"projects": [p.to_dict() for p in projects], "total": len(projects)})

    def h_post_projects(self) -> None:
        from hermes.workbench.cli import _make_project_registry

        body = self._read_json_body()
        if not isinstance(body, dict):
            raise ValidationError("body must be a JSON object")
        name = body.get("name", "")
        if not name:
            raise ValidationError("'name' is required")
        project_type = body.get("type", "local")
        url = body.get("url", "")
        token = body.get("token", "")
        config = body.get("config", {})
        try:
            project = _make_project_registry().add(name, project_type, url, token, config)
        except ValueError as e:
            raise ValidationError(str(e)) from e
        self._send_json(201, project.to_dict())

    def h_get_projects_summary(self) -> None:
        from hermes.workbench.cli import _make_project_registry

        self._send_json(200, _make_project_registry().summary())

    def h_get_project(self, prj_id: str) -> None:
        from hermes.workbench.cli import _make_project_registry

        project = _make_project_registry().get(prj_id)
        if project is None:
            raise NotFoundError(f"project not found: {prj_id}")
        self._send_json(200, project.to_dict())

    def h_delete_project(self, prj_id: str) -> None:
        from hermes.workbench.cli import _make_project_registry

        if _make_project_registry().remove(prj_id):
            self._send_json(200, {"deleted": True})
        else:
            raise NotFoundError(f"project not found: {prj_id}")

    def h_post_project_sync(self, prj_id: str) -> None:
        from hermes.workbench.cli import _make_asset_sync, _make_project_registry

        project = _make_project_registry().get(prj_id)
        if project is None:
            raise NotFoundError(f"project not found: {prj_id}")
        body = self._read_json_body() if self.command == "POST" else {}
        asset_type = body.get("asset_type", "all") if isinstance(body, dict) else "all"

        sync = _make_asset_sync()
        if asset_type == "skills":
            results = [sync.sync_skills(prj_id, "local")]
        elif asset_type == "memory":
            results = [sync.sync_memory(prj_id, "local")]
        elif asset_type == "profile":
            results = [sync.sync_profile([prj_id])]
        else:
            results = sync.sync_all(prj_id, "local")

        self._send_json(200, {"results": [r.to_dict() for r in results], "ok": all(r.ok for r in results)})

    # static files -------------------------------------------------------

    def h_get_index(self) -> None:
        """Serve the prototype index.html."""
        index_path = _PROTOYPE_DIR / "index.html"
        if not index_path.exists():
            self._send_json(404, {"error": "prototype not found", "path": str(index_path)})
            return
        self._serve_static_file(index_path)

    def _serve_static_file(self, file_path: Path) -> None:
        """Serve a static file with correct content type."""
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if mime_type is None:
            mime_type = "application/octet-stream"
        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _check_skill_status(spec: Any) -> str:
    """Check if a skill's binary and env requirements are met."""
    for bin_name in spec.requires_bins:
        if not shutil.which(bin_name):
            return "missing"
    for env_name in spec.requires_env:
        if not os.environ.get(env_name):
            return "missing"
    return "ready"


def make_server(host: str, port: int) -> ThreadingHTTPServer:
    """Create a ThreadingHTTPServer bound to *host:port*."""
    return ThreadingHTTPServer((host, port), DashboardHandler)


def run_server(host: str = "127.0.0.1", port: int = 8080) -> None:
    """Start the dashboard server (blocking)."""
    httpd = make_server(host, port)
    print(f"Hermes workbench dashboard listening on http://{host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        httpd.shutdown()
        httpd.server_close()
