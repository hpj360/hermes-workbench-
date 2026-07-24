"""操作审计日志：记录所有 API 请求用于追踪与调试。

审计日志以 JSON Lines 格式持久化到 ``state/audit.jsonl``，每行一条记录。
通过 ``GET /audit`` 端点可查询最近的操作记录。

审计字段：
- ``timestamp``: Unix 时间戳
- ``method``: HTTP 方法 (GET/POST/PUT/DELETE/PATCH)
- ``path``: 请求路径
- ``status``: HTTP 响应状态码
- ``duration_ms``: 请求处理耗时（毫秒）
- ``client_ip``: 客户端 IP
- ``user_agent``: User-Agent 头
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hermes.workbench.persistence import atomic_append_jsonl


@dataclass
class AuditEntry:
    """一条审计日志记录。"""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)
    method: str = ""
    path: str = ""
    status: int = 0
    duration_ms: float = 0.0
    client_ip: str = ""
    user_agent: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "method": self.method,
            "path": self.path,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "client_ip": self.client_ip,
            "user_agent": self.user_agent,
            "error": self.error,
        }


class AuditLog:
    """审计日志记录与查询服务。

    日志以 JSON Lines 追加写入 ``state/audit.jsonl``，查询时倒序读取。
    内存中缓存最近 ``buffer_size`` 条以加速查询。
    """

    def __init__(self, state_dir: Path, buffer_size: int = 500) -> None:
        self._path = state_dir / "audit.jsonl"
        state_dir.mkdir(parents=True, exist_ok=True)
        self._buffer_size = buffer_size
        self._buffer: list[AuditEntry] = []
        self._lock = threading.Lock()
        self._load_buffer()

    def _load_buffer(self) -> None:
        """启动时加载最近 N 条到内存。"""
        if not self._path.exists():
            return
        try:
            lines = self._path.read_text(encoding="utf-8").strip().split("\n")
            entries = []
            for line in lines[-self._buffer_size:]:
                if line.strip():
                    d = json.loads(line)
                    entries.append(AuditEntry(
                        id=d.get("id", ""),
                        timestamp=d.get("timestamp", 0),
                        method=d.get("method", ""),
                        path=d.get("path", ""),
                        status=d.get("status", 0),
                        duration_ms=d.get("duration_ms", 0),
                        client_ip=d.get("client_ip", ""),
                        user_agent=d.get("user_agent", ""),
                        error=d.get("error"),
                    ))
            self._buffer = entries
        except (OSError, ValueError):
            pass

    def record(self, entry: AuditEntry) -> None:
        """记录一条审计日志。"""
        with self._lock:
            self._buffer.append(entry)
            if len(self._buffer) > self._buffer_size:
                self._buffer = self._buffer[-self._buffer_size:]
        atomic_append_jsonl(self._path, entry.to_dict())

    def query(
        self,
        limit: int = 50,
        method: str | None = None,
        path_prefix: str | None = None,
        min_status: int | None = None,
        max_status: int | None = None,
    ) -> list[dict[str, Any]]:
        """查询审计日志，返回倒序列表（最新在前）。"""
        with self._lock:
            entries = list(self._buffer)

        result = entries
        if method:
            result = [e for e in result if e.method == method]
        if path_prefix:
            result = [e for e in result if e.path.startswith(path_prefix)]
        if min_status is not None:
            result = [e for e in result if e.status >= min_status]
        if max_status is not None:
            result = [e for e in result if e.status <= max_status]

        result = sorted(result, key=lambda e: e.timestamp, reverse=True)
        return [e.to_dict() for e in result[:limit]]

    def stats(self) -> dict[str, Any]:
        """返回审计统计摘要。"""
        with self._lock:
            entries = list(self._buffer)
        total = len(entries)
        if not total:
            return {"total": 0, "errors": 0, "avg_duration_ms": 0}
        errors = sum(1 for e in entries if e.status >= 400)
        avg_duration = sum(e.duration_ms for e in entries) / total
        return {
            "total": total,
            "errors": errors,
            "error_rate": round(errors / total, 3),
            "avg_duration_ms": round(avg_duration, 1),
        }

    def clear(self) -> int:
        """清空所有审计日志，返回清除的条数。"""
        with self._lock:
            count = len(self._buffer)
            self._buffer = []
        if self._path.exists():
            self._path.write_text("", encoding="utf-8")
        return count


# ---------------------------------------------------------------------------
# 全局审计日志（单例）
# ---------------------------------------------------------------------------

_global_audit: AuditLog | None = None
_audit_lock = threading.Lock()


def get_audit_log() -> AuditLog | None:
    """获取全局审计日志单例（未初始化时返回 None）。"""
    return _global_audit


def init_audit_log(state_dir: Path) -> AuditLog:
    """初始化全局审计日志。"""
    global _global_audit
    with _audit_lock:
        if _global_audit is not None:
            return _global_audit
        _global_audit = AuditLog(state_dir=state_dir)
        return _global_audit


def reset_audit_log() -> None:
    """重置全局审计日志（用于测试隔离）。"""
    global _global_audit
    with _audit_lock:
        _global_audit = None
