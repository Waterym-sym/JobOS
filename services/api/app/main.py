from datetime import UTC, datetime
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from services.api.app.ws_gateway import websocket_gateway


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    time: datetime


def build_app(service_name: str) -> FastAPI:
    app = FastAPI(
        title=f"AI Resume OS {service_name}",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
    )

    @app.get("/healthz", response_model=HealthResponse, tags=["system"])
    async def health() -> HealthResponse:
        return HealthResponse(service=service_name, time=datetime.now(UTC))

    return app


api_app = build_app("api")
gateway_app = build_app("ws-gateway")
gateway_app.websocket("/ws")(websocket_gateway)
