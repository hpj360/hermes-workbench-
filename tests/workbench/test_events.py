"""Tests for workbench.events module and SSE /events endpoint."""

from __future__ import annotations

import json
import threading
import time

import pytest

from hermes.workbench.events import Event, EventBroker, get_event_broker, reset_event_broker

# ---------------------------------------------------------------------------
# Event dataclass
# ---------------------------------------------------------------------------


def test_event_to_sse_format():
    """Event.to_sse() produces valid SSE protocol format."""
    event = Event(type="workflow.started", data={"id": "wf-1"}, id="abc123")
    sse = event.to_sse()
    assert "id: abc123" in sse
    assert "event: workflow.started" in sse
    assert sse.endswith("\n\n")
    # data line contains valid JSON
    data_line = next(l for l in sse.split("\n") if l.startswith("data: "))
    payload = json.loads(data_line[len("data: "):])
    assert payload["type"] == "workflow.started"
    assert payload["data"]["id"] == "wf-1"
    assert payload["id"] == "abc123"


def test_event_default_id_is_generated():
    """Event generates a unique id when not provided."""
    e1 = Event(type="x")
    e2 = Event(type="x")
    assert e1.id != e2.id
    assert len(e1.id) > 0


# ---------------------------------------------------------------------------
# EventBroker
# ---------------------------------------------------------------------------


def test_broker_publish_and_subscribe():
    """Published events are received by subscribers."""
    broker = EventBroker()
    events_received: list[Event] = []
    stop = threading.Event()

    def subscriber():
        for event in broker.subscribe():
            events_received.append(event)
            if len(events_received) >= 2 or stop.is_set():
                break

    t = threading.Thread(target=subscriber, daemon=True)
    t.start()
    time.sleep(0.1)  # let subscriber register

    broker.publish("test.event1", {"n": 1})
    broker.publish("test.event2", {"n": 2})
    t.join(timeout=2)
    stop.set()

    assert len(events_received) == 2
    assert events_received[0].type == "test.event1"
    assert events_received[0].data["n"] == 1
    assert events_received[1].type == "test.event2"


def test_broker_multiple_subscribers():
    """Multiple subscribers each receive the same event."""
    broker = EventBroker()
    received_a: list[Event] = []
    received_b: list[Event] = []
    stop = threading.Event()

    def sub(buf):
        for event in broker.subscribe():
            buf.append(event)
            if len(buf) >= 1 or stop.is_set():
                break

    t1 = threading.Thread(target=sub, args=(received_a,), daemon=True)
    t2 = threading.Thread(target=sub, args=(received_b,), daemon=True)
    t1.start()
    t2.start()
    time.sleep(0.1)

    broker.publish("broadcast", {"msg": "hello"})
    t1.join(timeout=2)
    t2.join(timeout=2)
    stop.set()

    assert len(received_a) == 1
    assert len(received_b) == 1
    assert received_a[0].data["msg"] == "hello"
    assert received_b[0].data["msg"] == "hello"


def test_broker_subscriber_count():
    """subscriber_count reflects active subscribers."""
    broker = EventBroker()
    assert broker.subscriber_count == 0

    stop = threading.Event()
    def subscriber():
        for _event in broker.subscribe():
            if stop.is_set():
                break

    t = threading.Thread(target=subscriber, daemon=True)
    t.start()
    time.sleep(0.1)
    assert broker.subscriber_count == 1

    stop.set()
    broker.unsubscribe_all()
    t.join(timeout=2)
    assert broker.subscriber_count == 0


def test_broker_unsubscribe_all_cleans_up():
    """unsubscribe_all removes all subscribers."""
    broker = EventBroker()
    stop = threading.Event()
    def subscriber():
        for _event in broker.subscribe():
            if stop.is_set():
                break

    for _ in range(3):
        threading.Thread(target=subscriber, daemon=True).start()
    time.sleep(0.1)
    assert broker.subscriber_count == 3

    broker.unsubscribe_all()
    time.sleep(0.1)
    assert broker.subscriber_count == 0


# ---------------------------------------------------------------------------
# Global broker singleton
# ---------------------------------------------------------------------------


def test_global_broker_singleton():
    """get_event_broker returns the same instance."""
    reset_event_broker()
    b1 = get_event_broker()
    b2 = get_event_broker()
    assert b1 is b2


def test_reset_event_broker():
    """reset_event_broker clears the singleton."""
    reset_event_broker()
    b1 = get_event_broker()
    reset_event_broker()
    b2 = get_event_broker()
    assert b1 is not b2


# ---------------------------------------------------------------------------
# Workflow event emission integration
# ---------------------------------------------------------------------------


def test_workflow_execute_emits_events(tmp_path):
    """WorkflowRunner.execute publishes SSE events for each step."""
    reset_event_broker()
    from hermes.workbench.skill_runner import SkillRunner
    from hermes.workbench.workflow import Workflow, WorkflowRunner, WorkflowStep

    # Create a skill to run
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "echo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: echo\ndescription: echo skill\n---\n# echo\nHello.\n",
        encoding="utf-8",
    )

    broker = get_event_broker()
    received: list[Event] = []
    stop = threading.Event()

    def subscriber():
        for event in broker.subscribe():
            received.append(event)
            if stop.is_set():
                break

    t = threading.Thread(target=subscriber, daemon=True)
    t.start()
    time.sleep(0.1)

    runner = SkillRunner(base_dir=skills_dir)
    wf_runner = WorkflowRunner(runner=runner, state_dir=tmp_path)

    wf = Workflow(
        id="wf-test",
        name="测试工作流",
        steps=[WorkflowStep(id="s1", skill="echo")],
    )
    wf_runner.execute(wf)

    stop.set()
    t.join(timeout=2)

    event_types = [e.type for e in received]
    assert "workflow.started" in event_types
    assert "workflow.step.completed" in event_types
    assert "workflow.completed" in event_types

    reset_event_broker()


# ---------------------------------------------------------------------------
# SSE /events endpoint
# ---------------------------------------------------------------------------


@pytest.fixture
def sse_server(monkeypatch, skills_dir, tmp_path):
    """Start server with isolated services and reset event broker."""
    from hermes.workbench import cli as cli_mod
    from hermes.workbench.memory import MemoryService
    from hermes.workbench.projects import ProjectRegistry
    from hermes.workbench.skill_runner import SkillRunner
    from hermes.workbench.sync import AssetSync
    from hermes.workbench.triggers import TriggerStore
    from hermes.workbench.workflow import WorkflowRunner, WorkflowStore

    reset_event_broker()
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

    from hermes.workbench.server import make_server
    srv = make_server(host="127.0.0.1", port=0)
    srv.daemon_threads = True
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv
    srv.shutdown()
    srv.server_close()
    thread.join(timeout=2)
    reset_event_broker()


def test_events_endpoint_streams_sse(sse_server):
    """/events endpoint returns text/event-stream and sends connected event."""
    import http.client
    host, port = sse_server.server_address[:2]
    conn = http.client.HTTPConnection(host, port, timeout=5)
    conn.request("GET", "/events")
    resp = conn.getresponse()
    assert resp.status == 200
    assert "text/event-stream" in resp.getheader("Content-Type", "")
    # Read the initial connected event
    # Use a small read to get the first event
    raw = resp.fp.read1(4096).decode("utf-8")
    assert "event: connected" in raw
    conn.close()


def test_events_endpoint_delivers_published_events(sse_server):
    """Events published to broker are delivered to SSE subscriber."""
    import http.client

    from hermes.workbench.events import get_event_broker

    host, port = sse_server.server_address[:2]
    conn = http.client.HTTPConnection(host, port, timeout=5)
    conn.request("GET", "/events")
    resp = conn.getresponse()

    # Consume the initial connected event
    resp.fp.read1(4096)
    # 等待订阅队列就绪，避免事件在订阅前发布
    time.sleep(0.2)

    # Publish an event
    broker = get_event_broker()
    broker.publish("test.sse", {"msg": "hello sse"})

    # Read the published event
    raw = resp.fp.read1(4096).decode("utf-8")
    assert "event: test.sse" in raw
    assert "hello sse" in raw
    conn.close()
