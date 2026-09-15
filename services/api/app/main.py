from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from ipaddress import ip_address
from typing import Annotated, Any, Literal
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from services.api.app import capture_repo
from services.api.app.config import Settings, get_settings
from services.api.app.errors import ErrorEnvelope
from services.api.app.pairing import PairingTokenStore
from services.api.app.protocol import uuid7
from services.api.app.registry import NoExtensionConnected, registry
from services.api.app.ws_gateway import websocket_gateway


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    time: datetime


class CaptureCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["list", "detail"]
    query_url: str | None = None
    list_params: dict[str, Any] | None = None
    max_items: int = Field(default=30, ge=1, le=500)
    ext_ids: list[str] | None = Field(default=None, min_length=1)
    detail_limit: int = Field(default=30, ge=1, le=100)
    delay_ms: int = Field(default=1800, ge=1800)


class AbortRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(default="manual abort", min_length=1, max_length=200)


class ApiProblem(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.envelope = ErrorEnvelope(
            code=code,
            message=message,
            trace_id=uuid7(),
            details=details or {},
        )


bearer = HTTPBearer(auto_error=False)


def _token_store(settings: Settings) -> PairingTokenStore:
    configured = settings.pairing_token.get_secret_value() if settings.pairing_token else None
    return PairingTokenStore(settings.pairing_token_file, configured)


def _is_local_peer(host: str | None, *, container_mode: bool) -> bool:
    if not host:
        return False
    try:
        address = ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or (container_mode and address.is_private)


def _is_local_origin(origin: str | None) -> bool:
    if origin is None:
        return True
    try:
        parsed = urlparse(origin)
        return parsed.scheme in {"http", "https"} and bool(
            parsed.hostname and ip_address(parsed.hostname).is_loopback
        )
    except ValueError:
        return False


async def require_local_auth(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    settings = get_settings()
    peer = request.client.host if request.client else None
    if not _is_local_peer(peer, container_mode=settings.container_mode) or not _is_local_origin(
        request.headers.get("origin")
    ):
        raise ApiProblem(403, "LOOPBACK_ONLY", "REST API accepts local clients only")
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not _token_store(settings).matches(credentials.credentials)
    ):
        raise ApiProblem(401, "PAIRING_TOKEN_INVALID", "Pairing token is invalid")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    _token_store(get_settings()).load_or_create()
    yield


def build_app(service_name: str) -> FastAPI:
    app = FastAPI(
        title=f"AI Resume OS {service_name}",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )

    @app.exception_handler(ApiProblem)
    async def api_problem_handler(_: Request, exc: ApiProblem) -> JSONResponse:
        return JSONResponse(exc.envelope.model_dump(), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        safe_errors = [
            {
                "type": error.get("type"),
                "loc": error.get("loc"),
                "msg": error.get("msg"),
            }
            for error in exc.errors()
        ]
        envelope = ErrorEnvelope(
            code="PAYLOAD_INVALID",
            message="Request failed validation",
            trace_id=uuid7(),
            details={"errors": safe_errors},
        )
        return JSONResponse(envelope.model_dump(), status_code=422)

    @app.get("/healthz", response_model=HealthResponse, tags=["system"])
    async def health() -> HealthResponse:
        return HealthResponse(service=service_name, time=datetime.now(UTC))

    return app


def register_capture_routes(app: FastAPI) -> None:
    router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_local_auth)])

    @router.get("/extension/status", tags=["extension"])
    async def extension_status() -> dict[str, Any]:
        return registry.status()

    @router.post("/captures", status_code=202, tags=["capture"])
    async def create_capture(body: CaptureCreate) -> dict[str, Any]:
        if body.kind == "detail" and not body.ext_ids:
            raise ApiProblem(422, "PAYLOAD_INVALID", "ext_ids are required for detail capture")
        capture_id = await capture_repo.create_batch_run(kind=body.kind, trigger="console")
        try:
            if body.kind == "list":
                await registry.send_command(
                    "capture_list",
                    {
                        "query_url": body.query_url,
                        "list_params": body.list_params,
                        "max_items": body.max_items,
                        "delay_ms": body.delay_ms,
                        "auto_next_page": False,
                    },
                    capture_id=capture_id,
                )
            else:
                await registry.send_command(
                    "capture_details",
                    {
                        "ext_ids": body.ext_ids,
                        "detail_limit": body.detail_limit,
                        "delay_ms": body.delay_ms,
                    },
                    capture_id=capture_id,
                )
        except NoExtensionConnected as exc:
            await capture_repo.complete_batch(
                capture_id, status="failed", stats={"reason": "extension offline"}
            )
            raise ApiProblem(409, "EXTENSION_OFFLINE", "No paired extension") from exc
        batch = await capture_repo.get_batch(capture_id)
        if batch is None:
            raise ApiProblem(404, "CAPTURE_NOT_FOUND", "Capture batch was not found")
        return batch

    @router.get("/captures/{capture_id}", tags=["capture"])
    async def read_capture(capture_id: UUID) -> dict[str, Any]:
        batch = await capture_repo.get_batch(capture_id)
        if batch is None:
            raise ApiProblem(404, "CAPTURE_NOT_FOUND", "Capture batch was not found")
        return batch

    @router.post("/captures/{capture_id}/abort", tags=["capture"])
    async def abort_capture(capture_id: UUID, body: AbortRequest) -> dict[str, Any]:
        if await capture_repo.get_batch(capture_id) is None:
            raise ApiProblem(404, "CAPTURE_NOT_FOUND", "Capture batch was not found")
        try:
            await registry.send_command("abort", {"reason": body.reason}, capture_id=capture_id)
        except NoExtensionConnected as exc:
            raise ApiProblem(409, "EXTENSION_OFFLINE", "No paired extension") from exc
        await capture_repo.complete_batch(
            capture_id,
            status="aborted",
            stats={"success": 0, "dup": 0, "risk_halted": False},
        )
        result = await capture_repo.get_batch(capture_id)
        if result is None:
            raise ApiProblem(404, "CAPTURE_NOT_FOUND", "Capture batch was not found")
        return result

    @router.get("/raw-jobs", tags=["capture"])
    async def read_raw_jobs(
        limit: int = 50,
        offset: int = 0,
        batch_id: UUID | None = None,
    ) -> dict[str, Any]:
        safe_limit = min(max(limit, 1), 200)
        safe_offset = max(offset, 0)
        items = await capture_repo.list_raw_jobs(
            limit=safe_limit, offset=safe_offset, batch_id=batch_id
        )
        return {"items": items, "limit": safe_limit, "offset": safe_offset}

    app.include_router(router)


api_app = build_app("api")
register_capture_routes(api_app)
gateway_app = build_app("ws-gateway")
gateway_app.websocket("/ws")(websocket_gateway)
