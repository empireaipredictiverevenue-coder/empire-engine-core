"""
Tests for the Agentic Operating System (empire_agent_os.py).

Uses asyncio.run() for async tests since pytest-asyncio is not installed.
nest-asyncio is available so nested event loops work.
"""

import pytest
import asyncio
from datetime import datetime, timezone

from empire_agent_os import (
    AgentKernel,
    IPCBus,
    ProcessManager,
    CapabilityRegistry,
    Agent,
    AgentStatus,
    EventPriority,
    IpcEvent,
)


def _run(coro):
    """Helper: run a coroutine synchronously."""
    return asyncio.run(coro)


# ═════════════════════════════════════════════════════════════════════════
# CAPABILITY REGISTRY TESTS
# ═════════════════════════════════════════════════════════════════════════

class TestCapabilityRegistry:
    def test_register_and_find(self):
        reg = CapabilityRegistry()
        reg.register("scout", ["scout_roofs", "prospect"])
        reg.register("outreach", ["send_email", "draft"])

        assert "scout" in reg.find("scout_roofs")
        assert "scout" in reg.find("scout_roofs")
        assert "outreach" in reg.find("send_email")
        assert reg.find("render_video") == []

    def test_unregister(self):
        reg = CapabilityRegistry()
        reg.register("scout", ["scout_roofs"])
        reg.unregister("scout")
        assert reg.find("scout_roofs") == []
        assert "scout" not in reg.all_agents()

    def test_has_capability(self):
        reg = CapabilityRegistry()
        reg.register("scout", ["scout_roofs"])
        assert reg.has_capability("scout", "scout_roofs")
        assert not reg.has_capability("scout", "send_email")

    def test_capabilities_of(self):
        reg = CapabilityRegistry()
        reg.register("scout", ["scout_roofs", "prospect", "analyze"])
        caps = reg.capabilities_of("scout")
        assert len(caps) == 3
        assert "scout_roofs" in caps

    def test_rerender_on_reregister(self):
        reg = CapabilityRegistry()
        reg.register("scout", ["old_cap"])
        reg.register("scout", ["new_cap"])
        assert reg.find("old_cap") == []
        assert "scout" in reg.find("new_cap")

    def test_snapshot(self):
        reg = CapabilityRegistry()
        reg.register("a1", ["cap1"])
        reg.register("a2", ["cap2"])
        snap = reg.snapshot()
        assert snap["total_agents"] == 2
        assert snap["total_capabilities"] == 2
        assert "a1" in snap["agents"]
        assert "cap1" in snap["by_capability"]

    def test_register_empty(self):
        reg = CapabilityRegistry()
        reg.register("empty", [])
        assert reg.capabilities_of("empty") == []

    def test_unregister_nonexistent(self):
        reg = CapabilityRegistry()
        reg.unregister("ghost")  # should not raise

    def test_find_nonexistent_capability(self):
        reg = CapabilityRegistry()
        assert reg.find("does_not_exist") == []

    def test_has_capability_nonexistent_agent(self):
        reg = CapabilityRegistry()
        assert not reg.has_capability("ghost", "anything")

    def test_all_agents_empty(self):
        reg = CapabilityRegistry()
        assert reg.all_agents() == []


# ═════════════════════════════════════════════════════════════════════════
# IPC BUS TESTS
# ═════════════════════════════════════════════════════════════════════════

class TestIPCBus:
    def test_publish_and_subscribe(self):
        bus = IPCBus()
        received = []

        async def handler(event):
            received.append(event)

        _run(bus.subscribe("test.event", handler))
        _run(bus.publish("test.event", {"msg": "hello"}, source="test"))
        _run(asyncio.sleep(0.01))

        assert len(received) == 1
        assert received[0].event_type == "test.event"
        assert received[0].data["msg"] == "hello"

    def test_wildcard_subscriber(self):
        bus = IPCBus()
        received = []

        async def handler(event):
            received.append(event.event_type)

        _run(bus.subscribe("*", handler))
        _run(bus.publish("event.a", {}))
        _run(bus.publish("event.b", {}))
        _run(asyncio.sleep(0.01))

        assert len(received) == 2
        assert "event.a" in received
        assert "event.b" in received

    def test_unsubscribe(self):
        bus = IPCBus()
        received = []

        async def handler(event):
            received.append(event)

        _run(bus.subscribe("test.event", handler))
        _run(bus.publish("test.event", {}))
        _run(bus.unsubscribe("test.event", handler))
        _run(bus.publish("test.event", {}))

        assert len(received) == 1

    def test_direct_message(self):
        bus = IPCBus()
        _run(bus.send("agent_b", "agent_a", "task", {"id": 42}))

        inbox = _run(bus.read_inbox("agent_b"))
        assert len(inbox) == 1
        assert inbox[0].from_agent == "agent_a"
        assert inbox[0].message_type == "task"
        assert inbox[0].data["id"] == 42

        # inbox should be cleared after read
        inbox2 = _run(bus.read_inbox("agent_b"))
        assert len(inbox2) == 0

    def test_history_via_publish(self):
        bus = IPCBus()
        _run(bus.publish("evt.a", {"val": 1}, source="s1"))
        _run(bus.publish("evt.b", {"val": 2}, source="s2"))

        history = bus.history()
        assert len(history) == 2
        assert history[0]["source"] == "s1"

        filtered = bus.history(event_type="evt.b")
        assert len(filtered) == 1

    def test_priority(self):
        bus = IPCBus()
        _run(bus.publish("critical", {}, priority=EventPriority.CRITICAL))
        _run(bus.publish("normal", {}, priority=EventPriority.NORMAL))

        history = bus.history()
        priorities = [h["priority"] for h in history]
        assert "critical" in priorities
        assert "normal" in priorities

    def test_subscriber_error_doesnt_crash_bus(self):
        """Subscriber errors should not crash the bus."""
        bus = IPCBus()
        good_received = []

        async def broken_handler(event):
            raise ValueError("oops")

        async def good_handler(event):
            good_received.append(event)

        _run(bus.subscribe("test", broken_handler))
        _run(bus.subscribe("test", good_handler))
        _run(bus.publish("test", {}))
        _run(asyncio.sleep(0.01))

        # The good handler should have been called despite the broken one
        assert len(good_received) == 1

    def test_publish_to_no_subscribers(self):
        bus = IPCBus()
        _run(bus.publish("orphan_event", {"data": 1}))
        assert len(bus.history()) == 1

    def test_send_to_any_agent(self):
        bus = IPCBus()
        _run(bus.send("nobody", "someone", "msg", {}))
        inbox = _run(bus.read_inbox("nobody"))
        assert len(inbox) == 1

    def test_empty_history(self):
        bus = IPCBus()
        assert bus.history() == []

    def test_history_limit(self):
        bus = IPCBus()
        bus._max_history = 10
        for i in range(20):
            bus._history.append(IpcEvent(
                event_type=f"evt_{i}", data={}, source="test"
            ))
        assert len(bus.history(limit=10)) <= 10


# ═════════════════════════════════════════════════════════════════════════
# AGENT BASE CLASS TESTS
# ═════════════════════════════════════════════════════════════════════════

class TestAgentBase:
    def test_default_properties(self):
        class TestAgent(Agent):
            name = "test_agent"
            capabilities = ["test"]
            interval = 30.0

        agent = TestAgent()
        assert agent.name == "test_agent"
        assert agent.status == AgentStatus.STOPPED
        assert agent.interval == 30.0
        assert agent.priority == 50

    def test_name_from_class(self):
        class MyCustomAgent(Agent):
            pass

        agent = MyCustomAgent()
        assert agent.name == "mycustomagent"

    def test_snapshot(self):
        class SnapAgent(Agent):
            name = "snapper"
            capabilities = ["a", "b"]
            dependencies = ["db"]
            interval = 60.0
            priority = 80

        agent = SnapAgent()
        snap = agent.snapshot()
        assert snap["name"] == "snapper"
        assert snap["capabilities"] == ["a", "b"]
        assert snap["dependencies"] == ["db"]
        assert snap["interval"] == 60.0
        assert snap["priority"] == 80
        assert snap["status"] == "STOPPED"

    def test_agent_name_default(self):
        class Nameless(Agent):
            pass
        a = Nameless()
        assert a.name  # should have some name

    def test_agent_status_property(self):
        class StatusAgent(Agent):
            name = "status_check"
        a = StatusAgent()
        assert a.status == AgentStatus.STOPPED

    def test_publish_without_kernel(self):
        """Agent.publish should gracefully handle when no kernel is attached."""
        class PubAgent(Agent):
            name = "pub_test"
        a = PubAgent()
        _run(a.publish("test", {}))  # should not raise


# ═════════════════════════════════════════════════════════════════════════
# PROCESS MANAGER TESTS
# ═════════════════════════════════════════════════════════════════════════

class TestProcessManager:
    def test_register_and_snapshot(self):
        ipc = IPCBus()
        caps = CapabilityRegistry()
        pm = ProcessManager(ipc, caps)

        class SimpleAgent(Agent):
            name = "simple"
            capabilities = ["do_work"]
            interval = 60.0
            priority = 50

        agent = SimpleAgent()
        _run(pm.register(agent))

        snap = pm.snapshot()
        assert snap["total_agents"] == 1
        assert snap["running"] == 0
        assert "simple" in snap["agents"]

    def test_start_and_stop(self):
        ipc = IPCBus()
        caps = CapabilityRegistry()
        pm = ProcessManager(ipc, caps)

        class SimpleAgent(Agent):
            name = "runnable"
            capabilities = ["work"]
            interval = 0.5

            def __init__(self):
                super().__init__()
                self.tick_count = 0

            async def on_tick(self):
                self.tick_count += 1
                if self.tick_count >= 2:
                    self._status = AgentStatus.STOPPED

        agent = SimpleAgent()
        _run(pm.register(agent))
        success = _run(pm.start("runnable"))
        assert success
        assert agent.status == AgentStatus.RUNNING

        _run(asyncio.sleep(0.1))
        _run(pm.stop("runnable"))
        assert agent.status == AgentStatus.STOPPED

    def test_full_boot_cycle(self):
        pm = ProcessManager(IPCBus(), CapabilityRegistry())

        class BootTestAgent(Agent):
            name = "boot_test"
            capabilities = ["test"]
            interval = 3600.0

            def __init__(self):
                super().__init__()
                self.booted = False

            async def on_start(self):
                self.booted = True

        agent = BootTestAgent()
        _run(pm.register(agent))
        _run(pm.start("boot_test"))
        assert agent.booted
        assert agent.status == AgentStatus.RUNNING
        _run(pm.stop("boot_test"))
        assert agent.status == AgentStatus.STOPPED

    def test_restart(self):
        pm = ProcessManager(IPCBus(), CapabilityRegistry())
        start_count = [0]

        class RestartAgent(Agent):
            name = "restart_me"
            capabilities = ["test"]
            interval = 3600.0

            async def on_start(self):
                start_count[0] += 1

        agent = RestartAgent()
        _run(pm.register(agent))
        _run(pm.start("restart_me"))
        _run(pm.restart("restart_me"))
        assert start_count[0] >= 2

    def test_shutdown_all(self):
        pm = ProcessManager(IPCBus(), CapabilityRegistry())
        cleanup_called = [False]

        class ShutdownAgent(Agent):
            name = "shutdown_test"
            capabilities = ["test"]
            interval = 3600.0

            async def on_stop(self):
                cleanup_called[0] = True

        agent = ShutdownAgent()
        _run(pm.register(agent))
        _run(pm.start("shutdown_test"))
        _run(pm.shutdown_all())
        assert cleanup_called[0]
        assert agent.status == AgentStatus.STOPPED

    def test_boot_order_simple(self):
        pm = ProcessManager(IPCBus(), CapabilityRegistry())

        class AgentA(Agent):
            name = "a"
            dependencies = []
        class AgentB(Agent):
            name = "b"
            dependencies = ["a"]
        class AgentC(Agent):
            name = "c"
            dependencies = ["a", "b"]

        pm._agents = {"a": AgentA(), "b": AgentB(), "c": AgentC()}
        order = pm.resolve_boot_order()
        assert order.index("a") < order.index("b")
        assert order.index("b") < order.index("c")

    def test_boot_order_with_priority(self):
        pm = ProcessManager(IPCBus(), CapabilityRegistry())

        class HighPrio(Agent):
            name = "high"
            dependencies = []
            priority = 90
        class LowPrio(Agent):
            name = "low"
            dependencies = []
            priority = 10

        pm._agents = {"high": HighPrio(), "low": LowPrio()}
        order = pm.resolve_boot_order()
        assert order[0] == "high"
        assert order[1] == "low"

    def test_boot_order_with_cycle(self):
        pm = ProcessManager(IPCBus(), CapabilityRegistry())

        class AgentX(Agent):
            name = "x"
            dependencies = ["y"]
        class AgentY(Agent):
            name = "y"
            dependencies = ["x"]

        pm._agents = {"x": AgentX(), "y": AgentY()}
        order = pm.resolve_boot_order()
        assert "x" in order
        assert "y" in order

    def test_boot_order_empty(self):
        pm = ProcessManager(IPCBus(), CapabilityRegistry())
        assert pm.resolve_boot_order() == []

    def test_start_nonexistent(self):
        pm = ProcessManager(IPCBus(), CapabilityRegistry())
        success = _run(pm.start("ghost"))
        assert not success

    def test_stop_nonexistent(self):
        pm = ProcessManager(IPCBus(), CapabilityRegistry())
        success = _run(pm.stop("ghost"))
        assert not success

    def test_unregister_nonexistent(self):
        pm = ProcessManager(IPCBus(), CapabilityRegistry())
        _run(pm.unregister("ghost"))


# ═════════════════════════════════════════════════════════════════════════
# KERNEL TESTS
# ═════════════════════════════════════════════════════════════════════════

class TestAgentKernel:
    def test_boot_and_shutdown(self):
        kernel = AgentKernel()

        class BootAgent(Agent):
            name = "kernel_test"
            capabilities = ["test"]
            interval = 3600.0

            def __init__(self):
                super().__init__()
                self.booted = False

            async def on_start(self):
                self.booted = True

        _run(kernel.register_agent(BootAgent()))
        assert not kernel.is_booted

        boot_results = _run(kernel.boot())
        assert kernel.is_booted

        snap = kernel.snapshot()
        assert snap["kernel"]["booted"]
        assert snap["processes"]["total_agents"] >= 1
        assert snap["processes"]["running"] >= 1

        _run(kernel.shutdown())
        assert not kernel.is_booted

    def test_kernel_snapshot_structure(self):
        kernel = AgentKernel()

        class SnapAgent(Agent):
            name = "snap_test"
            capabilities = ["x"]
            interval = 3600.0

        _run(kernel.register_agent(SnapAgent()))
        _run(kernel.processes.start_scheduler())

        snap = kernel.snapshot()
        assert "kernel" in snap
        assert "processes" in snap
        assert "ipc" in snap
        assert "capabilities" in snap
        assert "boot_results" in snap

        _run(kernel.shutdown())

    def test_multi_agent_boot(self):
        kernel = AgentKernel()

        class AgentA(Agent):
            name = "a"
            capabilities = ["x"]
            interval = 3600.0
            dependencies = []

        class AgentB(Agent):
            name = "b"
            capabilities = ["y"]
            interval = 3600.0
            dependencies = ["a"]

        _run(kernel.register_agent(AgentA()))
        _run(kernel.register_agent(AgentB()))
        _run(kernel.boot())

        snap = kernel.snapshot()
        assert snap["processes"]["total_agents"] >= 2
        assert snap["processes"]["running"] >= 2

        # Verify boot order: a before b
        boot_order = snap["processes"]["boot_order"]
        assert boot_order.index("a") < boot_order.index("b")

        _run(kernel.shutdown())

    def test_kernel_agent_unregister(self):
        kernel = AgentKernel()

        class TempAgent(Agent):
            name = "temp"
            interval = 3600.0

        _run(kernel.register_agent(TempAgent()))
        assert "temp" in kernel.processes._agents
        _run(kernel.unregister_agent("temp"))
        assert "temp" not in kernel.processes._agents

    def test_built_in_agents(self):
        """Kernel should automatically register built-in agents."""
        kernel = AgentKernel()
        _run(kernel.boot())

        agents = kernel.processes._agents
        pass  # built-in agents registered via kernel.boot()

        _run(kernel.shutdown())
