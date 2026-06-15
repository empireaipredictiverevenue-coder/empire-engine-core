"""Run one cycle of StormDispatchBridge and print results."""
import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
)

from workers.storm_dispatch import StormDispatchBridge


async def main():
    bridge = StormDispatchBridge()
    result = await bridge.run_cycle()
    print("\n=== CYCLE RESULT ===")
    print(result)
    print("\n=== BRIDGE SNAPSHOT ===")
    print(bridge.snapshot())


if __name__ == "__main__":
    asyncio.run(main())
