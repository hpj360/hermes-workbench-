"""SSE 事件总线：进程内发布-订阅事件系统。

为工作流执行、任务状态变更、健康检查等提供实时事件推送能力。
事件以 JSON 格式通过 ``text/event-stream`` 推送到所有订阅的 SSE 客户端。

使用方式::

    broker = EventBroker()
    broker.publish("workflow.started", {"workflow_id": "wf-xxx", "name": "晨报"})
    # 在 SSE handler 中:
    for event in broker.subscribe():
        yield event.to_sse()
"""

from __future__ import annotations

import queue
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Event:
    """一个 SSE 事件。"""

    type: str  # 事件类型，如 workflow.started / task.completed / health.beat
    data: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)

    def to_sse(self) -> str:
        """序列化为 SSE 协议格式的字符串。"""
        import json
        payload = json.dumps(
            {"type": self.type, "data": self.data, "id": self.id, "ts": self.timestamp},
            ensure_ascii=False,
        )
        return f"id: {self.id}\nevent: {self.type}\ndata: {payload}\n\n"


class EventBroker:
    """进程内事件代理，支持多订阅者。

    每个订阅者拥有独立的事件队列，慢消费者不会阻塞其他订阅者。
    队列有上限防止内存泄漏，超过上限时丢弃最旧事件。
    """

    def __init__(self, max_queue_size: int = 256) -> None:
        self._subscribers: list[queue.Queue[Event | None]] = []
        self._lock = threading.Lock()
        self._max_queue_size = max_queue_size
        self._last_event_id: str = ""

    def publish(self, event_type: str, data: dict[str, Any] | None = None) -> Event:
        """发布一个事件到所有订阅者。

        Args:
            event_type: 事件类型（点分隔，如 ``workflow.step.completed``）
            data: 事件负载数据

        Returns:
            已发布的 Event 对象
        """
        event = Event(type=event_type, data=data or {})
        with self._lock:
            self._last_event_id = event.id
            for sub in self._subscribers:
                try:
                    sub.put_nowait(event)
                except queue.Full:
                    # 队列满：丢弃最旧事件后重试
                    try:
                        sub.get_nowait()
                        sub.put_nowait(event)
                    except (queue.Empty, queue.Full):
                        pass
        return event

    def subscribe(self, last_event_id: str = "") -> Iterator[Event]:
        """订阅事件流（生成器）。

        Args:
            last_event_id: 客户端最后收到的事件 ID，用于断线重连时跳过已读事件。
                           当前实现为简单队列，重连后从新事件开始。

        Yields:
            Event 对象，直到订阅者被取消或连接关闭
        """
        q: queue.Queue[Event | None] = queue.Queue(maxsize=self._max_queue_size)
        with self._lock:
            self._subscribers.append(q)
        try:
            while True:
                try:
                    event = q.get(timeout=30.0)
                except queue.Empty:
                    # 发送心跳保活
                    yield Event(type="heartbeat", data={"ts": time.time()})
                    continue
                if event is None:
                    # 订阅被取消
                    break
                yield event
        finally:
            with self._lock:
                if q in self._subscribers:
                    self._subscribers.remove(q)

    def unsubscribe_all(self) -> None:
        """取消所有订阅（用于测试清理）。"""
        with self._lock:
            for sub in self._subscribers:
                try:
                    sub.put_nowait(None)
                except queue.Full:
                    pass
            self._subscribers.clear()

    @property
    def subscriber_count(self) -> int:
        """当前订阅者数量。"""
        with self._lock:
            return len(self._subscribers)


# ---------------------------------------------------------------------------
# 全局事件代理（单例）
# ---------------------------------------------------------------------------

_global_broker: EventBroker | None = None
_global_lock = threading.Lock()


def get_event_broker() -> EventBroker:
    """获取全局事件代理单例。"""
    global _global_broker
    if _global_broker is None:
        with _global_lock:
            if _global_broker is None:
                _global_broker = EventBroker()
    return _global_broker


def reset_event_broker() -> None:
    """重置全局事件代理（用于测试隔离）。"""
    global _global_broker
    with _global_lock:
        if _global_broker is not None:
            _global_broker.unsubscribe_all()
        _global_broker = None
