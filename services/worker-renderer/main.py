import asyncio
import json


async def run() -> None:
    print(json.dumps({"event": "process.ready", "service": "worker-renderer"}), flush=True)
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(run())
