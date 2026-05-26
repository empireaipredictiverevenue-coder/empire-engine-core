"""
EMPIRE V49 · LANE CONTROLLER
============================
Async concurrency primitive for the orchestrator.
Replaces the stub that stored strings in a dict.
"""
import asyncio
import logging
from typing import Awaitable, Callable, List, Any

log = logging.getLogger("empire.lane")


class LaneController:
    """
    Wraps asyncio.Semaphore to cap concurrent tasks.
    Use as: async with controller.lane(): await work()
    """

    def __init__(self, lane_count: int = 6):
        self.lane_count = lane_count
        self._sem = asyncio.Semaphore(lane_count)
        self.active = 0
        self.completed = 0
        self.failed = 0

    def lane(self):
        return self._LaneContext(self)

    class _LaneContext:
        def __init__(self, controller):
            self.controller = controller
        async def __aenter__(self):
            await self.controller._sem.acquire()
            self.controller.active += 1
            return self
        async def __aexit__(self, exc_type, exc, tb):
            self.controller.active -= 1
            if exc_type:
                self.controller.failed += 1
            else:
                self.controller.completed += 1
            self.controller._sem.release()

    async def gather(self, coros: List[Awaitable]) -> List[Any]:
        """Run a list of coroutines bounded by lane_count."""
        async def _bounded(coro):
            async with self.lane():
                return await coro
        return await asyncio.gather(*(_bounded(c) for c in coros), return_exceptions=True)
