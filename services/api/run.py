import argparse
import asyncio

import uvicorn

from services.api.app.config import get_settings


async def serve(container: bool) -> None:
    settings = get_settings()
    bind_host = "0.0.0.0" if container else settings.host_bind
    api = uvicorn.Server(
        uvicorn.Config(
            "services.api.app.main:api_app",
            host=bind_host,
            port=settings.api_port,
            log_config=None,
        )
    )
    gateway = uvicorn.Server(
        uvicorn.Config(
            "services.api.app.main:gateway_app",
            host=bind_host,
            port=settings.ws_port,
            log_config=None,
        )
    )
    await asyncio.gather(api.serve(), gateway.serve())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--container",
        action="store_true",
        help="Bind inside the container; Compose still publishes only to loopback.",
    )
    args = parser.parse_args()
    asyncio.run(serve(container=args.container))


if __name__ == "__main__":
    main()
