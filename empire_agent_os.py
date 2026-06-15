"""
EMPIRE V49 · AGENTIC OPERATING SYSTEM
======================================
The Kernel — a unified runtime for all agents.

Provides:
  - Agent base class    — shared lifecycle (on_start/tick/stop/error)
  - IPCBus              — publish/subscribe message passing
  - CapabilityRegistry  — dynamic capability discovery
  - ProcessManager      — supervisor: spawn, kill, restart, schedule
  - AgentKernel         — the unified runtime that ties everything together
  - BootProtocol        — dependency-resolved ordered startup/shutdown
  - Adapters            — wrap existing Empire agents into the Agent class
  - API routes          — REST endpoints for the SPA dashboard
"""

import asyncio
import logging
import time
import json
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Optional

log = logging.getLogger("empire.agent_os")


# ═════════════════════════════════════════════════════════════════════════
# ENUMS / CONSTANTS
# ═════════════════════════════════════════════════════════════════════════

class AgentStatus(str, Enum):
    STOPPED  = "STOPPED"
    RUNNING  = "RUNNING"
    ERROR    = "ERROR"
    PAUSED   = "PAUSED"
    BOOTING  = "BOOTING"
    SHUTDOWN = "SHUTDOWN"


class EventPriority(str, Enum):
    LOW    = "low"
    NORMAL = "normal"
    HIGH   = "high"
    CRITICAL = "critical"


# ═════════════════════════════════════════════════════════════════════════
# DATA CONTRACTS
# ═════════════════════════════════════════════════════════════════════════

@dataclass
class IpcEvent:
    """A single event on the IPC bus."""
    event_type: str
    data: dict
    source: str = "system"
    priority: EventPriority = EventPriority.NORMAL
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_id: str = field(default_factory=lambda: f"evt_{int(time.time()*1000000)}")


@dataclass
class IpcMessage:
    """A direct message between two agents."""
    to_agent: str
    from_agent: str
    message_type: str
    data: dict
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    msg_id: str = field(default_factory=lambda: f"msg_{int(time.time()*1000000)}")


# ═════════════════════════════════════════════════════════════════════════
# CAPABILITY REGISTRY
# ═════════════════════════════════════════════════════════════════════════

class CapabilityRegistry:
    """Dynamic capability discovery and routing.

    Agents register their capabilities (e.g. "send_email", "scout_roofs",
    "render_video"). Other systems can query which agents can perform
    a given capability.
    """

    def __init__(self):
        # capability -> set of agent names
        self._registry: dict[str, set[str]] = defaultdict(set)
        # agent_name -> set of capabilities
        self._agent_caps: dict[str, set[str]] = defaultdict(set)

    def register(self, agent_name: str, capabilities: list[str]) -> None:
        """Register an agent's capabilities."""
        # Remove any previous capabilities for this agent
        old_caps = self._agent_caps.get(agent_name, set())
        for cap in old_caps:
            self._registry[cap].discard(agent_name)

        # Add new capabilities
        for cap in capabilities:
            self._registry[cap].add(agent_name)
        self._agent_caps[agent_name] = set(capabilities)

    def unregister(self, agent_name: str) -> None:
        """Remove an agent from the registry entirely."""
        caps = self._agent_caps.pop(agent_name, set())
        for cap in caps:
            self._registry[cap].discard(agent_name)

    def find(self, capability: str) -> list[str]:
        """Find all agents that have a given capability."""
        return sorted(self._registry.get(capability, set()))

    def has_capability(self, agent_name: str, capability: str) -> bool:
        """Check if an agent has a specific capability."""
        return capability in self._agent_caps.get(agent_name, set())

    def capabilities_of(self, agent_name: str) -> list[str]:
        """Return all capabilities of a given agent."""
        return sorted(self._agent_caps.get(agent_name, set()))

    def all_agents(self) -> list[str]:
        """Return all registered agent names."""
        return sorted(self._agent_caps.keys())

    def snapshot(self) -> dict:
        """Full registry snapshot for dashboard."""
        return {
            "total_agents": len(self._agent_caps),
            "total_capabilities": len(self._registry),
            "agents": {
                name: sorted(caps)
                for name, caps in sorted(self._agent_caps.items())
            },
            "by_capability": {
                cap: sorted(agents)
                for cap, agents in sorted(self._registry.items())
                if agents
            },
        }


# ═════════════════════════════════════════════════════════════════════════
# IPC BUS
# ═════════════════════════════════════════════════════════════════════════

class IPCBus:
    """Centralized event/message bus for inter-agent communication.

    Supports:
      - Publish/subscribe: agents subscribe to event types
      - Direct messaging: agent-to-agent with inbox
      - Event history: for debugging and replay
      - Priority handling: HIGH/CRITICAL events delivered first
    """

    def __init__(self, max_history: int = 200):
        self._max_history = max_history
        # event_type -> list of callbacks
        self._subscriptions: dict[str, list[Callable]] = defaultdict(list)
        # agent_name -> list of messages
        self._inboxes: dict[str, list[IpcMessage]] = defaultdict(list)
        # event history for dashboard/replay
        self._history: list[IpcEvent] = []
        self._lock = asyncio.Lock()

    async def publish(
        self,
        event_type: str,
        data: dict,
        source: str = "system",
        priority: EventPriority = EventPriority.NORMAL,
    ) -> None:
        """Publish an event to all subscribers."""
        event = IpcEvent(
            event_type=event_type,
            data=data,
            source=source,
            priority=priority,
        )

        async with self._lock:
            # Add to history
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

            # Deliver to subscribers
            subscribers = list(self._subscriptions.get(event_type, []))
            # Also deliver to wildcard subscribers
            subscribers.extend(self._subscriptions.get("*", []))

        # Deliver outside the lock to prevent deadlocks
        for callback in subscribers:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                log.warning(f"[ipc] subscriber error for '{event_type}': {e}")

    async def subscribe(self, event_type: str, callback: Callable) -> None:
        """Subscribe to an event type. Use '*' for all events."""
        async with self._lock:
            if callback not in self._subscriptions[event_type]:
                self._subscriptions[event_type].append(callback)

    async def unsubscribe(self, event_type: str, callback: Callable) -> None:
        """Unsubscribe from an event type."""
        async with self._lock:
            if callback in self._subscriptions.get(event_type, []):
                self._subscriptions[event_type].remove(callback)

    async def send(
        self,
        to_agent: str,
        from_agent: str,
        message_type: str,
        data: dict,
    ) -> None:
        """Send a direct message to an agent's inbox."""
        msg = IpcMessage(
            to_agent=to_agent,
            from_agent=from_agent,
            message_type=message_type,
            data=data,
        )

        async with self._lock:
            self._inboxes[to_agent].append(msg)

        # Also publish a notification event
        await self.publish(
            "ipc.message",
            {"to": to_agent, "from": from_agent, "type": message_type},
            source=from_agent,
        )

    async def read_inbox(self, agent_name: str) -> list[IpcMessage]:
        """Read and clear an agent's inbox."""
        async with self._lock:
            messages = list(self._inboxes.get(agent_name, []))
            self._inboxes[agent_name] = []
            return messages

    def history(
        self,
        event_type: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """Get event history, optionally filtered by type."""
        events = self._history
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return [
            {
                "event_id": e.event_id,
                "event_type": e.event_type,
                "source": e.source,
                "priority": e.priority.value,
                "ts": e.ts,
                "data": e.data,
            }
            for e in events[-limit:]
        ]

    def snapshot(self) -> dict:
        """IPC bus snapshot for dashboard."""
        subscriptions = {
            event_type: len(callbacks)
            for event_type, callbacks in self._subscriptions.items()
        }
        inbox_sizes = {
            agent: len(msgs)
            for agent, msgs in self._inboxes.items()
        }
        return {
            "total_events_tracked": len(self._history),
            "subscriptions": subscriptions,
            "inbox_sizes": inbox_sizes,
            "recent_events": self.history(limit=20),
        }


# ═════════════════════════════════════════════════════════════════════════
# AGENT BASE CLASS
# ═════════════════════════════════════════════════════════════════════════

class Agent:
    """Base class for all agents in the Empire Agentic OS.

    Subclass this and implement the lifecycle hooks you need.
    The minimum required is `name` and at least one of `on_tick` or
    `handle_message`.

    Lifecycle:
      registered → on_register → BOOTING → on_start → RUNNING
        → on_tick (every `interval` seconds) → on_stop → STOPPED
      Error: → on_error → retry or STOPPED
      Message: → handle_message

    Example:
        class MyAgent(Agent):
            name = "my_agent"
            capabilities = ["send_email", "filter_leads"]
            interval = 60.0

            async def on_tick(self):
                # Do work every 60 seconds
                pass
    """

    # ── Override these in subclasses ────────────────────────────────
    name: str = ""
    capabilities: list[str] = []
    dependencies: list[str] = []
    interval: float = 60.0        # how often to call on_tick (seconds)
    priority: int = 50            # 1-100, higher = more critical
    max_retries: int = 3          # max retries before going ERROR
    retry_delay: float = 10.0     # seconds between retries

    # ── Set by the kernel when registered ───────────────────────────
    _kernel: Optional['AgentKernel'] = None
    _status: AgentStatus = AgentStatus.STOPPED
    _retry_count: int = 0
    _task: Optional[asyncio.Task] = None

    def __init__(self):
        if not self.name:
            self.name = self.__class__.__name__.lower()

    # ── Lifecycle hooks (override these) ────────────────────────────

    async def on_register(self) -> None:
        """Called when the agent is first registered with the kernel.
        Use this for one-time setup (connecting to DB, loading config, etc.)
        """
        pass

    async def on_start(self) -> None:
        """Called when the agent transitions from BOOTING to RUNNING.
        Use this to start background tasks or open connections.
        """
        pass

    async def on_tick(self) -> None:
        """Called on every scheduler tick (every `interval` seconds).
        Override this to do periodic work.
        """
        pass

    async def on_stop(self) -> None:
        """Called when the agent is being stopped.
        Use this to clean up resources, close connections, save state.
        """
        pass

    async def on_error(self, error: Exception) -> None:
        """Called when an unhandled error occurs in on_tick or handle_message.
        If on_error itself raises, the agent is marked ERROR and stopped.
        """
        log.warning(f"[agent.{self.name}] error: {error}")

    async def handle_message(self, msg: IpcMessage) -> None:
        """Called when the agent receives a direct message.
        Override this to handle messages from other agents.
        """
        pass

    # ── Built-in helpers (call these from your agent) ──────────────

    @property
    def status(self) -> AgentStatus:
        return self._status

    @property
    def kernel(self) -> Optional['AgentKernel']:
        return self._kernel

    async def publish(
        self,
        event_type: str,
        data: dict,
        priority: EventPriority = EventPriority.NORMAL,
    ) -> None:
        """Publish an event to the IPC bus."""
        if self._kernel:
            await self._kernel.ipc.publish(event_type, data, source=self.name, priority=priority)

    async def subscribe(self, event_type: str, callback: Callable) -> None:
        """Subscribe to IPC events."""
        if self._kernel:
            await self._kernel.ipc.subscribe(event_type, callback)

    async def send(self, to_agent: str, message_type: str, data: dict) -> None:
        """Send a direct message to another agent."""
        if self._kernel:
            await self._kernel.ipc.send(to_agent, self.name, message_type, data)

    async def log(self, msg: str, level: str = "info") -> None:
        """Log a message with the agent's name prefixed."""
        getattr(log, level, log.info)(f"[agent.{self.name}] {msg}")

    def snapshot(self) -> dict:
        """Return a snapshot of the agent's state for the dashboard."""
        return {
            "name": self.name,
            "status": self._status.value,
            "capabilities": self.capabilities,
            "dependencies": self.dependencies,
            "interval": self.interval,
            "priority": self.priority,
            "retry_count": self._retry_count,
            "max_retries": self.max_retries,
        }


# ═════════════════════════════════════════════════════════════════════════
# PROCESS MANAGER
# ═════════════════════════════════════════════════════════════════════════

class ProcessManager:
    """Supervisor that manages agent lifecycles.

    Handles:
      - Registration/unregistration
      - Spawn/kill/restart
      - Scheduling on_tick calls
      - Health checks
      - Dependency-resolved boot ordering
      - Graceful shutdown
      - Auto-recovery for errored agents
    """

    def __init__(self, ipc: IPCBus, capabilities: CapabilityRegistry):
        self._ipc = ipc
        self._capabilities = capabilities
        self._agents: dict[str, Agent] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._running = False
        self._scheduler_task: Optional[asyncio.Task] = None

    # ── Registration ────────────────────────────────────────────────

    async def register(self, agent: Agent) -> None:
        """Register an agent with the process manager.
        This does NOT start it — use start() or boot_all() for that.
        """
        if agent.name in self._agents:
            log.warning(f"[pm] agent '{agent.name}' already registered — replacing")
            await self.unregister(agent.name)

        # _kernel is set by AgentKernel.register_agent() before calling us
        self._agents[agent.name] = agent
        self._capabilities.register(agent.name, agent.capabilities)

        try:
            await agent.on_register()
        except Exception as e:
            log.warning(f"[pm] agent '{agent.name}' on_register error: {e}")

        log.info(f"[pm] registered agent '{agent.name}' ({len(agent.capabilities)} caps)")

    async def unregister(self, agent_name: str) -> None:
        """Unregister an agent. Stops it first if running."""
        await self.stop(agent_name)
        agent = self._agents.pop(agent_name, None)
        if agent:
            self._capabilities.unregister(agent_name)
            log.info(f"[pm] unregistered agent '{agent_name}'")

    # ── Lifecycle control ───────────────────────────────────────────

    async def start(self, agent_name: str) -> bool:
        """Start a registered agent. Returns True if started successfully."""
        agent = self._agents.get(agent_name)
        if not agent:
            log.warning(f"[pm] cannot start '{agent_name}' — not registered")
            return False

        if agent._status == AgentStatus.RUNNING:
            return True

        if agent._status == AgentStatus.BOOTING:
            log.warning(f"[pm] '{agent_name}' already booting")
            return False

        agent._status = AgentStatus.BOOTING
        agent._retry_count = 0

        try:
            await agent.on_start()
            agent._status = AgentStatus.RUNNING

            # Create the agent's tick task
            async def _agent_loop():
                try:
                    while agent._status == AgentStatus.RUNNING:
                        # Process inbox first
                        if self._ipc:
                            messages = await self._ipc.read_inbox(agent.name)
                            for msg in messages:
                                try:
                                    await agent.handle_message(msg)
                                except Exception as e:
                                    log.warning(f"[pm] '{agent.name}' handle_message error: {e}")
                                    agent._retry_count += 1
                                    if agent._retry_count >= agent.max_retries:
                                        agent._status = AgentStatus.ERROR
                                        await agent.on_error(e)
                                        return

                        # Then tick
                        try:
                            await agent.on_tick()
                            agent._retry_count = 0
                        except Exception as e:
                            agent._retry_count += 1
                            await agent.on_error(e)
                            if agent._retry_count >= agent.max_retries:
                                agent._status = AgentStatus.ERROR
                                return

                        # Wait for next tick
                        await asyncio.sleep(agent.interval)
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    log.error(f"[pm] '{agent_name}' loop crashed: {e}")
                    agent._status = AgentStatus.ERROR
                    await agent.on_error(e)

            self._tasks[agent_name] = asyncio.create_task(_agent_loop())
            log.info(f"[pm] started agent '{agent_name}' (interval={agent.interval}s)")
            return True

        except Exception as e:
            agent._status = AgentStatus.ERROR
            log.error(f"[pm] failed to start agent '{agent_name}': {e}")
            await agent.on_error(e)
            return False

    async def stop(self, agent_name: str, graceful: bool = True) -> bool:
        """Stop a running agent. Returns True if stopped."""
        agent = self._agents.get(agent_name)
        if not agent:
            return False

        if agent._status not in (AgentStatus.RUNNING, AgentStatus.ERROR, AgentStatus.BOOTING):
            return True

        try:
            if graceful:
                await agent.on_stop()
        except Exception as e:
            log.warning(f"[pm] '{agent_name}' on_stop error: {e}")

        # Cancel the agent's task
        task = self._tasks.pop(agent_name, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        agent._status = AgentStatus.STOPPED
        log.info(f"[pm] stopped agent '{agent_name}'")
        return True

    async def restart(self, agent_name: str) -> bool:
        """Restart an agent (stop + start)."""
        await self.stop(agent_name)
        return await self.start(agent_name)

    # ── Boot / Shutdown ─────────────────────────────────────────────

    def resolve_boot_order(self) -> list[str]:
        """Topological sort of agents by dependency graph.

        Uses Kahn's algorithm. Agents with no dependencies boot first.
        If there's a cycle, the agents involved boot last (in arbitrary order).
        """
        graph = {}
        for name, agent in self._agents.items():
            deps = [d for d in agent.dependencies if d in self._agents]
            graph[name] = set(deps)

        # Kahn's algorithm
        in_degree = {name: 0 for name in graph}
        for name, deps in graph.items():
            for dep in deps:
                in_degree[name] = in_degree.get(name, 0) + 1

        queue = [name for name, deg in in_degree.items() if deg == 0]
        order = []

        while queue:
            # Sort by priority (highest first) within the same dependency level
            queue.sort(key=lambda n: self._agents[n].priority, reverse=True)
            node = queue.pop(0)
            order.append(node)

            for other, deps in graph.items():
                if node in deps:
                    deps.remove(node)
                    in_degree[other] -= 1
                    if in_degree[other] == 0:
                        queue.append(other)

        # Any remaining agents (cycle) get appended
        remaining = [n for n in graph if n not in order]
        remaining.sort(key=lambda n: self._agents[n].priority, reverse=True)
        order.extend(remaining)

        return order

    async def boot_all(self) -> dict[str, bool]:
        """Start all agents in dependency-resolved order.
        Returns dict of agent_name -> success.
        """
        boot_order = self.resolve_boot_order()
        results = {}

        log.info(f"[pm] booting {len(boot_order)} agents in order: {', '.join(boot_order)}")

        await self._ipc.publish("pm.boot_starting", {
            "agent_count": len(boot_order),
            "order": boot_order,
        }, source="process_manager", priority=EventPriority.HIGH)

        for name in boot_order:
            success = await self.start(name)
            results[name] = success
            await self._ipc.publish("pm.boot_progress", {
                "agent": name,
                "success": success,
                "boot_order": boot_order,
                "completed": sum(1 for r in results.values()),
                "total": len(boot_order),
            }, source="process_manager")

        await self._ipc.publish("pm.boot_complete", {
            "total": len(boot_order),
            "successful": sum(1 for r in results.values() if r),
            "failed": sum(1 for r in results.values() if not r),
            "results": results,
        }, source="process_manager", priority=EventPriority.HIGH)

        log.info(f"[pm] boot complete: {sum(1 for r in results.values() if r)}/{len(boot_order)} agents running")
        return results

    async def shutdown_all(self, graceful: bool = True) -> None:
        """Stop all agents in reverse boot order."""
        boot_order = self.resolve_boot_order()
        shutdown_order = list(reversed(boot_order))

        log.info(f"[pm] shutting down {len(shutdown_order)} agents")

        await self._ipc.publish("pm.shutdown_starting", {
            "agent_count": len(shutdown_order),
            "order": shutdown_order,
        }, source="process_manager", priority=EventPriority.CRITICAL)

        for name in shutdown_order:
            await self.stop(name, graceful=graceful)

        await self._ipc.publish("pm.shutdown_complete", {
            "total": len(shutdown_order),
        }, source="process_manager", priority=EventPriority.CRITICAL)

        log.info("[pm] shutdown complete")

    # ── Scheduler ───────────────────────────────────────────────────

    async def _scheduler_loop(self) -> None:
        """Background loop that manages agent scheduling.
        Runs health checks and handles ERROR agents.
        """
        while self._running:
            await asyncio.sleep(30)

            # Auto-recover errored agents
            for name, agent in list(self._agents.items()):
                if agent._status == AgentStatus.ERROR:
                    log.info(f"[pm] attempting auto-recovery for '{name}'")
                    await self.restart(name)

    async def start_scheduler(self) -> None:
        """Start the background scheduler loop."""
        self._running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        log.info("[pm] scheduler started")

    async def stop_scheduler(self) -> None:
        """Stop the background scheduler loop."""
        self._running = False
        if self._scheduler_task and not self._scheduler_task.done():
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        log.info("[pm] scheduler stopped")

    # ── Reporting ───────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Full process manager snapshot for dashboard."""
        agents = {}
        for name, agent in self._agents.items():
            agents[name] = agent.snapshot()

        boot_order = self.resolve_boot_order()

        return {
            "total_agents": len(self._agents),
            "running": sum(1 for a in self._agents.values() if a._status == AgentStatus.RUNNING),
            "stopped": sum(1 for a in self._agents.values() if a._status == AgentStatus.STOPPED),
            "error": sum(1 for a in self._agents.values() if a._status == AgentStatus.ERROR),
            "booting": sum(1 for a in self._agents.values() if a._status == AgentStatus.BOOTING),
            "agents": agents,
            "boot_order": boot_order,
            "scheduler_running": self._running,
        }


# ═════════════════════════════════════════════════════════════════════════
# AGENT KERNEL
# ═════════════════════════════════════════════════════════════════════════

class AgentKernel:
    """The unified runtime — the center of the Agentic OS.

    The kernel provides:
      - IPC bus for inter-agent communication
      - Capability registry for dynamic discovery
      - Process manager for lifecycle and scheduling
      - Boot protocol for ordered startup
      - Snapshot/API for the SPA dashboard

    Usage:
        kernel = AgentKernel()
        kernel.register_agent(MyAgent())
        kernel.register_agent(AnotherAgent())
        await kernel.boot()
        # ... system runs ...
        await kernel.shutdown()
    """

    def __init__(self):
        self.ipc = IPCBus()
        self.capabilities = CapabilityRegistry()
        self.processes = ProcessManager(self.ipc, self.capabilities)
        self._booted = False
        self._boot_results: dict[str, bool] = {}
        self._started_at: Optional[str] = None

        # Register built-in agents
        self._builtin_agents: list[Agent] = []
        try:
            hm = _HealthMonitorAgent()
            hm._kernel = self
            self._builtin_agents.append(hm)
        except Exception as e:
            log.warning(f"[kernel] failed to create health_monitor agent: {e}")
        try:
            cl = _ClockAgent()
            cl._kernel = self
            self._builtin_agents.append(cl)
        except Exception as e:
            log.warning(f"[kernel] failed to create clock agent: {e}") 

    # ── Registration ────────────────────────────────────────────────

    async def register_agent(self, agent: Agent) -> None:
        """Register an agent with the kernel.
        Sets the agent's _kernel reference and registers with the process manager.
        """
        agent._kernel = self
        await self.processes.register(agent)

    async def unregister_agent(self, agent_name: str) -> None:
        """Unregister an agent from the kernel."""
        await self.processes.unregister(agent_name)

    # ── Boot / Shutdown ─────────────────────────────────────────────

    async def boot(self) -> dict[str, bool]:
        # Register built-in agents if not already registered
        for agent in self._builtin_agents:
            if agent.name not in self.processes._agents:
                await self.processes.register(agent)
        """Boot the kernel: start scheduler, boot all agents in order."""
        self._started_at = datetime.now(timezone.utc).isoformat()

        await self.ipc.publish("kernel.boot", {}, source="kernel", priority=EventPriority.CRITICAL)
        log.info("[kernel] boot sequence started")

        await self.processes.start_scheduler()
        self._boot_results = await self.processes.boot_all()
        self._booted = True

        await self.ipc.publish("kernel.boot_complete", {
            "results": self._boot_results,
            "total_agents": len(self._boot_results),
            "running": sum(1 for r in self._boot_results.values() if r),
        }, source="kernel", priority=EventPriority.CRITICAL)

        log.info(f"[kernel] boot complete — {sum(1 for r in self._boot_results.values() if r)}/{len(self._boot_results)} agents running")
        return self._boot_results

    async def shutdown(self, graceful: bool = True) -> None:
        """Shutdown the kernel: stop all agents, stop scheduler."""
        await self.ipc.publish("kernel.shutdown", {}, source="kernel", priority=EventPriority.CRITICAL)
        log.info("[kernel] shutdown initiated")

        await self.processes.shutdown_all(graceful=graceful)
        await self.processes.stop_scheduler()

        self._booted = False
        await self.ipc.publish("kernel.shutdown_complete", {}, source="kernel", priority=EventPriority.CRITICAL)
        log.info("[kernel] shutdown complete")

    # ── State ───────────────────────────────────────────────────────

    @property
    def is_booted(self) -> bool:
        return self._booted

    def snapshot(self) -> dict:
        """Full kernel snapshot for the SPA dashboard."""
        return {
            "kernel": {
                "booted": self._booted,
                "started_at": self._started_at,
                "uptime_seconds": (
                    (datetime.now(timezone.utc) - datetime.fromisoformat(self._started_at)).total_seconds()
                    if self._started_at else 0
                ),
            },
            "processes": self.processes.snapshot(),
            "ipc": self.ipc.snapshot(),
            "capabilities": self.capabilities.snapshot(),
            "boot_results": self._boot_results,
        }


# ═════════════════════════════════════════════════════════════════════════
# BUILT-IN AGENTS
# ═════════════════════════════════════════════════════════════════════════

class _HealthMonitorAgent(Agent):
    """Built-in agent that monitors all other agents and reports health."""
    name = "health_monitor"
    capabilities = ["system.health", "monitoring"]
    interval = 60.0
    priority = 90  # high priority

    async def on_tick(self) -> None:
        pm = self._kernel.processes
        snapshot = pm.snapshot()
        errors = snapshot.get("error", 0)
        running = snapshot.get("running", 0)
        total = snapshot.get("total_agents", 1)

        await self.publish("system.health.tick", {
            "running": running,
            "error": errors,
            "total": total,
            "health_pct": round((running / max(total, 1)) * 100, 1),
        })

        if errors > 0:
            await self.log(f"{errors}/{total} agents in ERROR state", level="warning")


class _ClockAgent(Agent):
    """Built-in agent that emits a time tick event on every interval."""
    name = "clock"
    capabilities = ["system.clock", "timing"]
    interval = 10.0
    priority = 10  # low priority

    async def on_tick(self) -> None:
        await self.publish("system.clock.tick", {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uptime": (
                (datetime.now(timezone.utc) - datetime.fromisoformat(self._kernel._started_at)).total_seconds()
                if self._kernel._started_at else 0
            ),
        })


# ═════════════════════════════════════════════════════════════════════════
# ADAPTERS — Wrap existing Empire agents into the Agent class
# ═════════════════════════════════════════════════════════════════════════

class _ExistingAgentAdapter(Agent):
    """Adapter wrapper for existing Empire agents that have their own run_loop.

    Instead of rewriting every existing agent, this adapter lets you
    register an existing agent's run_loop function into the kernel.
    """

    def __init__(
        self,
        name: str,
        run_loop_fn: Callable[[], Coroutine],
        capabilities: Optional[list[str]] = None,
        dependencies: Optional[list[str]] = None,
        interval: float = 300.0,
        priority: int = 50,
    ):
        self._run_loop_fn = run_loop_fn
        self.name = name
        self.capabilities = capabilities or []
        self.dependencies = dependencies or []
        self.interval = interval
        self.priority = priority
        super().__init__()

    async def on_register(self) -> None:
        await self.log("registered as adapter for existing agent")

    async def on_start(self) -> None:
        await self.log("adapter started — existing agent's run_loop will be called on each tick")

    async def on_tick(self) -> None:
        """Call the existing agent's run_loop function."""
        try:
            await self._run_loop_fn()
        except Exception as e:
            await self.log(f"run_loop error: {e}", level="error")
            raise


# ═════════════════════════════════════════════════════════════════════════
# API ROUTES
# ═════════════════════════════════════════════════════════════════════════

def register_agent_os_routes(app, kernel: AgentKernel, require_auth=None, get_db=None):
    """Register Agentic OS REST API routes on a FastAPI app."""

    from fastapi import Depends, HTTPException, Request, Body, Query

    @app.get("/api/agent-os/status")
    async def agent_os_status(auth=Depends(require_auth) if require_auth else None):
        """Full kernel snapshot: processes, IPC, capabilities."""
        return kernel.snapshot()

    @app.get("/api/agent-os/agents")
    async def agent_os_agents(auth=Depends(require_auth) if require_auth else None):
        """List all registered agents with their status."""
        pm = kernel.processes
        snap = pm.snapshot()
        return {
            "agents": snap["agents"],
            "total": snap["total_agents"],
            "running": snap["running"],
            "stopped": snap["stopped"],
            "error": snap["error"],
            "boot_order": snap["boot_order"],
        }

    @app.post("/api/agent-os/agents/{agent_name}/start")
    async def agent_os_agent_start(agent_name: str, auth=Depends(require_auth) if require_auth else None):
        """Start a registered agent."""
        success = await kernel.processes.start(agent_name)
        if not success:
            agent = kernel.processes._agents.get(agent_name)
            if not agent:
                raise HTTPException(404, f"Agent '{agent_name}' not found")
        return {"ok": success, "agent": agent_name, "status": kernel.processes._agents.get(agent_name, None) and kernel.processes._agents[agent_name]._status.value}

    @app.post("/api/agent-os/agents/{agent_name}/stop")
    async def agent_os_agent_stop(agent_name: str, auth=Depends(require_auth) if require_auth else None):
        """Stop a running agent."""
        success = await kernel.processes.stop(agent_name)
        return {"ok": True, "agent": agent_name}

    @app.post("/api/agent-os/agents/{agent_name}/restart")
    async def agent_os_agent_restart(agent_name: str, auth=Depends(require_auth) if require_auth else None):
        """Restart an agent."""
        success = await kernel.processes.restart(agent_name)
        return {"ok": success, "agent": agent_name}

    @app.post("/api/agent-os/boot")
    async def agent_os_boot(auth=Depends(require_auth) if require_auth else None):
        """Boot the kernel: start all agents in dependency order."""
        if kernel.is_booted:
            return {"ok": False, "error": "Kernel already booted", "running": sum(1 for r in kernel._boot_results.values() if r) if kernel._boot_results else 0}
        results = await kernel.boot()
        return {"ok": True, "results": results}

    @app.post("/api/agent-os/shutdown")
    async def agent_os_shutdown(auth=Depends(require_auth) if require_auth else None):
        """Shutdown the kernel gracefully."""
        await kernel.shutdown()
        return {"ok": True}

    @app.get("/api/agent-os/ipc/events")
    async def agent_os_ipc_events(
        event_type: Optional[str] = Query(None),
        limit: int = Query(50, ge=1, le=200),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Recent IPC bus events."""
        events = kernel.ipc.history(event_type=event_type, limit=limit)
        return {"events": events, "count": len(events)}

    @app.post("/api/agent-os/ipc/publish")
    async def agent_os_ipc_publish(
        payload: dict = Body(...),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Manually publish an IPC event."""
        event_type = payload.get("event_type", "")
        data = payload.get("data", {})
        if not event_type:
            raise HTTPException(400, "event_type required")
        await kernel.ipc.publish(event_type, data, source="api")
        return {"ok": True, "event_type": event_type}

    @app.get("/api/agent-os/capabilities")
    async def agent_os_capabilities(
        agent_name: Optional[str] = Query(None),
        capability: Optional[str] = Query(None),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Capability registry query."""
        if agent_name:
            caps = kernel.capabilities.capabilities_of(agent_name)
            return {"agent": agent_name, "capabilities": caps}
        if capability:
            agents = kernel.capabilities.find(capability)
            return {"capability": capability, "agents": agents}
        return kernel.capabilities.snapshot()

    @app.get("/api/agent-os/boot-order")
    async def agent_os_boot_order(auth=Depends(require_auth) if require_auth else None):
        """Show the calculated boot order without booting."""
        order = kernel.processes.resolve_boot_order()
        return {
            "boot_order": order,
            "agents": {
                name: {
                    "priority": kernel.processes._agents[name].priority,
                    "dependencies": kernel.processes._agents[name].dependencies,
                    "status": kernel.processes._agents[name]._status.value,
                }
                for name in order
            },
        }

    log.info("[agent-os] routes registered: /api/agent-os/*")
