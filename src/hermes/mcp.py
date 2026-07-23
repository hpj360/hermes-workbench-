"""MCP (Model Context Protocol) integration for Hermes.

Provides controlled, structured, audited access to external systems.
Currently supports GitHub as the most universal external system.

Design principles (from Harness Engineering practice):
- Read more, write less: read methods are plentiful; write methods are
  minimal and curated.
- Write operations must have clear trigger points and be idempotent.
- All write operations are logged for audit trail.
- Failures degrade softly (warn, don't block main flow).
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("hermes.mcp")


@dataclass
class MCPCallRecord:
    """Audit record for a single MCP call."""
    timestamp: str
    server: str
    method: str
    args: dict[str, Any]
    success: bool
    error: str = ""


class GitHubMCPClient:
    """GitHub MCP client following read-more-write-less principle.

    Read methods: get_pr, get_issue, list_prs, list_issues, get_pr_reviews
    Write methods: post_pr_comment (idempotent), create_pr (idempotent by branch pair)

    All write operations:
    - Are idempotent (safe to retry)
    - Log to audit trail
    - Degrade softly on failure (return error dict, don't raise)
    """

    def __init__(self, token: str | None = None, repo: str | None = None) -> None:
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        self.repo = repo or os.environ.get("GITHUB_REPOSITORY", "")
        self._audit_log: list[MCPCallRecord] = []

    @property
    def available(self) -> bool:
        """Check if GitHub token is configured."""
        return bool(self.token)

    def _record(self, method: str, args: dict, success: bool, error: str = "") -> None:
        self._audit_log.append(MCPCallRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            server="github",
            method=method,
            args=args,
            success=success,
            error=error,
        ))

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

    def get_pr(self, pr_number: int) -> dict[str, Any]:
        """Read: Get PR details. Returns dict with 'success' key."""
        url = f"https://api.github.com/repos/{self.repo}/pulls/{pr_number}"
        try:
            req = urllib.request.Request(url, headers=self._headers())
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            self._record("get_pr", {"pr_number": pr_number}, True)
            # 借鉴 ai-berkshire 双源交叉验证：读方法返回 _sources 字段标记数据来源。
            # 当前仅 GitHub 单源，audit_loop 检查 _sources 字段数，单源产生 warning。
            # 未来扩展多 MCP 时，同一字段从两个独立 API 取数即可达成双源验证。
            return {"success": True, "pr": data, "_sources": ["github-api"]}
        except Exception as e:
            self._record("get_pr", {"pr_number": pr_number}, False, str(e))
            logger.warning("GitHub MCP get_pr failed (soft degradation): %s", e)
            return {"success": False, "error": str(e)}

    def get_issue(self, issue_number: int) -> dict[str, Any]:
        """Read: Get issue details."""
        url = f"https://api.github.com/repos/{self.repo}/issues/{issue_number}"
        try:
            req = urllib.request.Request(url, headers=self._headers())
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            self._record("get_issue", {"issue_number": issue_number}, True)
            return {"success": True, "issue": data, "_sources": ["github-api"]}
        except Exception as e:
            self._record("get_issue", {"issue_number": issue_number}, False, str(e))
            logger.warning("GitHub MCP get_issue failed (soft degradation): %s", e)
            return {"success": False, "error": str(e)}

    def list_prs(self, state: str = "open") -> dict[str, Any]:
        """Read: List PRs. state: open/closed/all."""
        url = f"https://api.github.com/repos/{self.repo}/pulls?state={state}&per_page=100"
        try:
            req = urllib.request.Request(url, headers=self._headers())
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            self._record("list_prs", {"state": state}, True)
            return {"success": True, "prs": data, "_sources": ["github-api"]}
        except Exception as e:
            self._record("list_prs", {"state": state}, False, str(e))
            logger.warning("GitHub MCP list_prs failed (soft degradation): %s", e)
            return {"success": False, "error": str(e)}

    def post_pr_comment(self, pr_number: int, body: str) -> dict[str, Any]:
        """Write: Post a comment on a PR. Idempotent.

        If a comment with the same body already exists, skips posting.
        """
        # Idempotency check: look for existing comment with same body
        list_url = (
            f"https://api.github.com/repos/{self.repo}/issues/{pr_number}/comments"
        )
        try:
            req = urllib.request.Request(list_url, headers=self._headers())
            with urllib.request.urlopen(req, timeout=30) as resp:
                existing = json.loads(resp.read())
            for comment in existing:
                if comment.get("body", "").strip() == body.strip():
                    self._record("post_pr_comment", {"pr_number": pr_number}, True)
                    return {
                        "success": True,
                        "comment": comment,
                        "skipped": True,
                        "message": "Idempotent skip: identical comment already exists",
                    }
        except Exception:
            pass  # Soft degradation on idempotency check failure

        # Post new comment
        url = f"https://api.github.com/repos/{self.repo}/issues/{pr_number}/comments"
        payload = json.dumps({"body": body}).encode()
        try:
            req = urllib.request.Request(
                url, data=payload, headers=self._headers(), method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            self._record("post_pr_comment", {"pr_number": pr_number}, True)
            return {"success": True, "comment": data, "skipped": False}
        except Exception as e:
            self._record("post_pr_comment", {"pr_number": pr_number}, False, str(e))
            logger.warning("GitHub MCP post_pr_comment failed (soft degradation): %s", e)
            return {"success": False, "error": str(e)}

    def create_pr(
        self, head: str, base: str, title: str, body: str = ""
    ) -> dict[str, Any]:
        """Write: Create a PR. Idempotent by head:base pair.

        Checks for existing open PR with same head:base first.
        """
        # Idempotency check: look for existing open PR with same head/base
        list_url = (
            f"https://api.github.com/repos/{self.repo}/pulls"
            f"?state=open&head={head}&base={base}"
        )
        try:
            req = urllib.request.Request(list_url, headers=self._headers())
            with urllib.request.urlopen(req, timeout=30) as resp:
                existing = json.loads(resp.read())
            if existing:
                self._record("create_pr", {"head": head, "base": base}, True)
                return {
                    "success": True,
                    "pr": existing[0],
                    "skipped": True,
                    "message": "Idempotent skip: PR already exists for this head:base",
                }
        except Exception:
            pass  # Soft degradation

        url = f"https://api.github.com/repos/{self.repo}/pulls"
        payload = json.dumps(
            {"title": title, "body": body, "head": head, "base": base}
        ).encode()
        try:
            req = urllib.request.Request(
                url, data=payload, headers=self._headers(), method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            self._record("create_pr", {"head": head, "base": base}, True)
            return {"success": True, "pr": data, "skipped": False}
        except Exception as e:
            self._record("create_pr", {"head": head, "base": base}, False, str(e))
            logger.warning("GitHub MCP create_pr failed (soft degradation): %s", e)
            return {"success": False, "error": str(e)}

    def get_audit_log(self) -> list[dict[str, Any]]:
        """Return the audit trail of all MCP calls."""
        return [
            {
                "timestamp": r.timestamp,
                "server": r.server,
                "method": r.method,
                "args": r.args,
                "success": r.success,
                "error": r.error,
            }
            for r in self._audit_log
        ]


# MCP Registry — extensible registry for future MCP servers
MCP_REGISTRY: dict[str, type] = {
    "github": GitHubMCPClient,
}


def get_mcp_client(server: str = "github", **kwargs: Any) -> Any:
    """Get an MCP client by server name. Returns None if server not registered."""
    cls = MCP_REGISTRY.get(server)
    if cls is None:
        logger.warning("MCP server '%s' not registered", server)
        return None
    return cls(**kwargs)
