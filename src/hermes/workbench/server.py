"""Dashboard HTTP API.

Exposes workbench capabilities (skills/memory/tasks) as a RESTful JSON API
using only the standard library (http.server). The server is a stateless
adapter: all state flows through the cli.py service factories. Errors map
to HTTP status codes via workbench.errors.

Run via ``hermes workbench serve --host 127.0.0.1 --port 8080``.
"""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

from hermes.workbench.errors import NotFoundError, ValidationError, WorkbenchError, status_code_for

__all__ = ["DashboardHandler", "make_server", "run_server"]


# Route table: (method, regex, handler_name). Named groups become kwargs.
_ROUTES: list[tuple[str, str, str]] = [
    ("GET", r"^/health$", "h_get_health"),
    ("GET", r"^/skills$", "h_get_skills"),
    ("GET", r"^/skills/(?P<name>[^/]+)$", "h_get_skill"),
    ("GET", r"^/memory/facts$", "h_get_facts"),
    ("POST", r"^/memory/facts$", "h_post_facts"),
    ("GET", r"^/memory/facts/(?P<key>[^/]+)$", "h_get_fact"),
    ("DELETE", r"^/memory/facts/(?P<key>[^/]+)$", "h_delete_fact"),
    ("GET", r"^/memory/episodes$", "h_get_episodes"),
    ("GET", r"^/memory/profile$", "h_get_profile"),
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
]


class DashboardHandler(BaseHTTPRequestHandler):
    """HTTP handler dispatching to workbench services."""

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass

    # Dispatch -----------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch("DELETE")

    def do_PUT(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_PATCH(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def _dispatch(self, method: str) -> None:
        path = urlsplit(self.path).path
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

    # Services (injected by make_server) ---------------------------------
    # These are set as class attributes by make_server via type().

    # health -------------------------------------------------------------

    def h_get_health(self) -> None:
        self._send_json(200, {"status": "ok", "services": ["skills", "memory", "tasks"]})

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
        episodes = _make_memory().list_episodes(kind=params.get("kind"))
        self._send_json(200, {"episodes": [e.__dict__ for e in episodes]})

    # memory profile -----------------------------------------------------

    def h_get_profile(self) -> None:
        from hermes.workbench.cli import _make_memory

        profile = _make_memory().get_user_profile()
        self._send_json(200, profile)

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
        try:
            service = GitHubSyncService.from_env(repo=repo)
        except ValidationError:
            raise
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
