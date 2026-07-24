"""触发器执行引擎：让触发器真正能自动触发工作流执行。

三类触发方式的激活逻辑：
- **cron**: 后台线程每 60 秒检查 cron 触发器，匹配当前时间则触发
- **webhook**: 由 ``POST /webhooks/<trigger_id>`` 端点接收外部请求，验证密钥后触发
- **github**: 复用 webhook 端点，接收 GitHub Webhook 事件后触发

使用方式::

    engine = TriggerEngine(trigger_store, workflow_store, workflow_runner)
    engine.start()  # 启动 cron 调度后台线程
    engine.fire(trigger_id)  # 手动触发
    engine.stop()  # 停止
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

from hermes.workbench.events import get_event_broker
from hermes.workbench.triggers import Trigger, TriggerStore
from hermes.workbench.workflow import WorkflowRunner, WorkflowStore


class CronScheduler:
    """Cron 触发器调度器：后台线程定时检查并触发。

    支持简化的 cron 表达式（5 字段：分 时 日 月 周），``*`` 表示任意值。
    """

    def __init__(
        self,
        trigger_store: TriggerStore,
        fire_callback: Any,
        check_interval: float = 60.0,
    ) -> None:
        self._store = trigger_store
        self._fire = fire_callback
        self._interval = check_interval
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_check: dict[str, float] = {}  # trigger_id -> last fired minute timestamp

    def start(self) -> None:
        """启动后台调度线程。"""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="cron-scheduler")
        self._thread.start()

    def stop(self) -> None:
        """停止后台调度线程。"""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._check_cron_triggers()
            except Exception:  # noqa: BLE001, S110 - 后台线程不能因异常退出
                pass
            self._stop_event.wait(self._interval)

    def _check_cron_triggers(self) -> None:
        """检查所有启用的 cron 触发器。"""
        now = datetime.now()  # noqa: DTZ005 - cron 使用本地时区
        current_minute = now.replace(second=0, microsecond=0)
        current_ts = current_minute.timestamp()

        for trigger in self._store.list():
            if not trigger.enabled or trigger.type != "cron":
                continue
            schedule = trigger.config.get("schedule", "")
            if not schedule:
                continue

            # 同一分钟内不重复触发
            last = self._last_check.get(trigger.id, 0)
            if last >= current_ts:
                continue

            if self._matches_cron(schedule, current_minute):
                self._last_check[trigger.id] = current_ts
                self._fire(trigger)

    @staticmethod
    def _matches_cron(schedule: str, dt: datetime) -> bool:
        """检查给定时间是否匹配 cron 表达式。

        支持 5 字段格式：``分 时 日 月 周``，``*`` 表示任意值。
        不支持 ``/``、``,``、``-`` 等高级语法（原型阶段简化）。
        """
        parts = schedule.strip().split()
        if len(parts) != 5:
            return False

        values = [dt.minute, dt.hour, dt.day, dt.month, dt.weekday()]
        # weekday: Python 0=Monday, cron 0=Sunday → 转换
        values[4] = (values[4] + 1) % 7

        for field, val in zip(parts, values, strict=False):
            if field == "*":
                continue
            try:
                if int(field) != val:
                    return False
            except ValueError:
                return False
        return True


class TriggerEngine:
    """触发器执行引擎：统一管理 cron/webhook/github 触发。

    调用 ``start()`` 启动后台 cron 调度；webhook/github 触发由
    ``fire_by_webhook()`` 方法处理（由 HTTP 端点调用）。
    """

    def __init__(
        self,
        trigger_store: TriggerStore,
        workflow_store: WorkflowStore,
        workflow_runner: WorkflowRunner,
    ) -> None:
        self._triggers = trigger_store
        self._workflows = workflow_store
        self._runner = workflow_runner
        self._scheduler = CronScheduler(trigger_store, self._fire_trigger)
        self._lock = threading.Lock()

    def start(self) -> None:
        """启动 cron 调度后台线程。"""
        self._scheduler.start()

    def stop(self) -> None:
        """停止 cron 调度。"""
        self._scheduler.stop()

    def fire(self, trigger_id: str) -> dict[str, Any] | None:
        """手动触发指定触发器关联的工作流。

        Returns:
            执行结果字典，触发器不存在时返回 None
        """
        trigger = self._triggers.get(trigger_id)
        if trigger is None:
            return None
        return self._fire_trigger(trigger)

    def fire_by_webhook(
        self, trigger_id: str, payload: dict[str, Any], signature: str = ""
    ) -> dict[str, Any] | None:
        """通过 webhook 触发工作流。

        Args:
            trigger_id: 触发器 ID
            payload: webhook 负载数据
            signature: 签名（用于验证，当前简化处理）

        Returns:
            执行结果字典，触发器不存在或签名不匹配时返回 None
        """
        trigger = self._triggers.get(trigger_id)
        if trigger is None or not trigger.enabled:
            return None
        if trigger.type not in ("webhook", "github"):
            return None

        # 验证 webhook 密钥（简化：仅检查是否配置了 secret）
        expected_secret = trigger.config.get("secret", "")
        if expected_secret and signature != expected_secret:
            return {"error": "invalid signature", "trigger_id": trigger_id}

        return self._fire_trigger(trigger)

    def _fire_trigger(self, trigger: Trigger) -> dict[str, Any]:
        """执行触发器关联的工作流。"""
        broker = get_event_broker()
        broker.publish("trigger.fired", {
            "trigger_id": trigger.id,
            "workflow_id": trigger.workflow_id,
            "trigger_type": trigger.type,
        })

        wf = self._workflows.get(trigger.workflow_id)
        if wf is None:
            broker.publish("trigger.failed", {
                "trigger_id": trigger.id,
                "error": f"workflow not found: {trigger.workflow_id}",
            })
            return {"error": "workflow not found", "trigger_id": trigger.id}

        with self._lock:
            execution = self._runner.execute(wf)
            self._triggers.mark_fired(trigger.id)

        broker.publish("trigger.completed", {
            "trigger_id": trigger.id,
            "execution_id": execution.id,
            "status": execution.status,
        })

        return {
            "trigger_id": trigger.id,
            "execution_id": execution.id,
            "status": execution.status,
            "workflow_id": trigger.workflow_id,
        }


# ---------------------------------------------------------------------------
# 全局触发器引擎（单例）
# ---------------------------------------------------------------------------

_global_engine: TriggerEngine | None = None
_engine_lock = threading.Lock()


def get_trigger_engine() -> TriggerEngine | None:
    """获取全局触发器引擎单例（未初始化时返回 None）。"""
    return _global_engine


def init_trigger_engine(
    trigger_store: TriggerStore,
    workflow_store: WorkflowStore,
    workflow_runner: WorkflowRunner,
    auto_start: bool = True,
) -> TriggerEngine:
    """初始化全局触发器引擎。"""
    global _global_engine
    with _engine_lock:
        if _global_engine is not None:
            _global_engine.stop()
        _global_engine = TriggerEngine(trigger_store, workflow_store, workflow_runner)
        if auto_start:
            _global_engine.start()
        return _global_engine


def stop_trigger_engine() -> None:
    """停止全局触发器引擎。"""
    global _global_engine
    with _engine_lock:
        if _global_engine is not None:
            _global_engine.stop()
            _global_engine = None
