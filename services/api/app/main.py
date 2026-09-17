from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from ipaddress import ip_address
from typing import Annotated, Any, Literal
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from services.api.app import account_routes, capture_repo, enrich, job_import, raw_jobs_push
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


class ShortlistCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ext_id: str = Field(min_length=1)
    note: str | None = Field(default=None, max_length=500)


class RawJobsUpload(BaseModel):
    """扩展翻页列表直传信封（contracts/ws/raw-job.schema.json 的 list 档）。"""

    model_config = ConfigDict(extra="forbid")

    source: Literal["boss"]
    tier: Literal["list"]
    jobs: list[dict[str, Any]] = Field(
        min_length=1, max_length=raw_jobs_push.MAX_JOBS
    )


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


def derive_enrich_state(
    *,
    failed_reason: str | None,
    detail_at: Any,
    jd_text: str | None,
    ext_company_id: str | None,
    company_ids: set[str],
) -> str:
    """Per-job enrich state, derived from stored data only.

    The queue-wide pause is deliberately not projected here: a paused queue is
    reported by /enrich/queue, never on an individual job (otherwise completed
    jobs would look unfinished).
    """
    if failed_reason is not None:
        return "failed"
    if detail_at is None or not jd_text:
        return "pending"
    if ext_company_id is None or ext_company_id in company_ids:
        return "done"
    return "detail_done"


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
        # Browser extension service workers send "chrome-extension://<id>" on
        # non-GET requests; they are trusted local clients (loopback peer is
        # enforced separately, and the pairing token is still required).
        if parsed.scheme in {"chrome-extension", "moz-extension", "safari-extension"}:
            return True
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
    await enrich.start()
    try:
        yield
    finally:
        await enrich.stop()


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

    @router.post("/raw-jobs", tags=["capture"])
    async def upload_raw_jobs(body: RawJobsUpload) -> dict[str, Any]:
        """扩展翻页列表直传：被动幂等入库，不登记采集、不下发任何 WS 命令。"""
        try:
            return await raw_jobs_push.run_push(body.model_dump())
        except raw_jobs_push.RawJobsUploadError as exc:
            raise ApiProblem(422, "PAYLOAD_INVALID", str(exc)) from exc

    @router.get("/raw-jobs/{ext_id}", tags=["capture"])
    async def read_job_profile(ext_id: str) -> dict[str, Any]:
        profile = await capture_repo.get_job_profile(ext_id)
        if profile is None:
            raise ApiProblem(
                404, "JOB_NOT_FOUND", "unknown ext_id; import the job list first"
            )
        # 导航数据（list_json）只用于内部推导公司主键，不对外输出。
        ext_company_id = enrich.company_ext_id(profile.pop("list_json", None))
        company = (
            await capture_repo.get_company_by_ext_id(ext_company_id)
            if ext_company_id
            else None
        )
        return {"job": profile, "company": company}

    @router.get("/companies", tags=["capture"])
    async def read_companies(limit: int = 50, offset: int = 0) -> dict[str, Any]:
        safe_limit = min(max(limit, 1), 200)
        safe_offset = max(offset, 0)
        items = await capture_repo.list_companies(limit=safe_limit, offset=safe_offset)
        return {"items": items, "limit": safe_limit, "offset": safe_offset}

    @router.post("/jobs/import", tags=["capture"])
    async def import_jobs(file: Annotated[UploadFile, File()]) -> dict[str, Any]:
        data = await file.read()
        if len(data) > job_import.MAX_FILE_BYTES:
            raise ApiProblem(
                413,
                "PAYLOAD_INVALID",
                f"file exceeds {job_import.MAX_FILE_BYTES} bytes",
            )
        try:
            return await job_import.run_import(data)
        except job_import.ExportFormatError as exc:
            raise ApiProblem(422, "PAYLOAD_INVALID", str(exc)) from exc

    def _shortlist_item(row: dict[str, Any], company_ids: set[str]) -> dict[str, Any]:
        raw_job_id = row["raw_job_id"]
        failure_reason = enrich.failure(raw_job_id)
        state = derive_enrich_state(
            failed_reason=failure_reason,
            detail_at=row["detail_at"],
            jd_text=row["jd_text"],
            ext_company_id=enrich.company_ext_id(row["list_json"]),
            company_ids=company_ids,
        )
        return {
            "id": str(row["id"]),
            "raw_job_id": str(raw_job_id),
            "ext_id": row["ext_id"],
            "title": row["title"],
            "company": row["company"],
            "city": row["city"],
            "salary_text": row["salary_text"],
            "status": row["status"],
            "note": row["note"],
            "enrich_state": state,
            "failure_reason": failure_reason,
            "detail_at": row["detail_at"].isoformat() if row["detail_at"] else None,
            "added_at": row["added_at"].isoformat() if row["added_at"] else None,
        }

    @router.post("/shortlist", status_code=201, tags=["shortlist"])
    async def add_shortlist(body: ShortlistCreate) -> dict[str, Any]:
        try:
            created = await capture_repo.add_to_shortlist(body.ext_id, body.note)
        except capture_repo.ShortlistExists as exc:
            raise ApiProblem(409, "SHORTLIST_CONFLICT", "job is already in the pool") from exc
        if created is None:
            raise ApiProblem(
                404, "JOB_NOT_FOUND", "unknown ext_id; import the job list first"
            )
        enrich.enqueue(created["raw_job_id"])
        row = await capture_repo.get_shortlist_row(created["id"])
        assert row is not None
        return _shortlist_item(row, await capture_repo.list_company_ext_ids())

    @router.get("/shortlist", tags=["shortlist"])
    async def read_shortlist() -> list[dict[str, Any]]:
        rows = await capture_repo.list_shortlist()
        company_ids = await capture_repo.list_company_ext_ids()
        return [_shortlist_item(row, company_ids) for row in rows]

    @router.post("/shortlist/{shortlist_id}/remove", tags=["shortlist"])
    async def remove_shortlist(shortlist_id: UUID) -> dict[str, Any]:
        existing = await capture_repo.get_shortlist_row(shortlist_id)
        if existing is None:
            raise ApiProblem(404, "CAPTURE_NOT_FOUND", "pool entry was not found")
        await capture_repo.remove_shortlist(shortlist_id)
        enrich.discard(existing["raw_job_id"])
        row = await capture_repo.get_shortlist_row(shortlist_id)
        assert row is not None
        return _shortlist_item(row, await capture_repo.list_company_ext_ids())

    @router.get("/enrich/queue", tags=["enrich"])
    async def read_enrich_queue() -> dict[str, Any]:
        return await enrich.status()

    @router.post("/enrich/resume", tags=["enrich"])
    async def resume_enrich() -> dict[str, Any]:
        return await enrich.resume()

    @router.get("/screening-entries", tags=["screening"])
    async def read_screening_entries(
        status: Literal["screened", "candidate"] = "screened",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        safe_limit = min(max(limit, 1), 200)
        safe_offset = max(offset, 0)
        items = await capture_repo.list_screening_entries(
            status=status, limit=safe_limit, offset=safe_offset
        )
        return {"items": items, "limit": safe_limit, "offset": safe_offset}

    async def _transition_screening_entry(entry_id: UUID, to_status: str) -> dict[str, Any]:
        try:
            entry = await capture_repo.update_screening_entry_status(
                entry_id, to_status=to_status
            )
        except capture_repo.ScreeningTransitionInvalid as exc:
            raise ApiProblem(
                409, "SCREENING_TRANSITION_INVALID", "transition is not allowed"
            ) from exc
        if entry is None:
            raise ApiProblem(
                404, "SCREENING_ENTRY_NOT_FOUND", "screening entry was not found"
            )
        return entry

    @router.post("/screening-entries/{entry_id}/promote", tags=["screening"])
    async def promote_screening_entry(entry_id: UUID) -> dict[str, Any]:
        """人工确认进入候选区；系统不会自动推进（ARCH-GOV-002）。"""
        return await _transition_screening_entry(entry_id, "candidate")

    @router.post("/screening-entries/{entry_id}/dismiss", tags=["screening"])
    async def dismiss_screening_entry(entry_id: UUID) -> dict[str, Any]:
        """忽略该岗位（终态，数据保留可审计）。"""
        return await _transition_screening_entry(entry_id, "dismissed")

    @router.post("/screening-entries/{entry_id}/revert", tags=["screening"])
    async def revert_screening_entry(entry_id: UUID) -> dict[str, Any]:
        """候选区退回筛选池。"""
        return await _transition_screening_entry(entry_id, "screened")

    app.include_router(router)


api_app = build_app("api")
api_app.add_exception_handler(account_routes.AccountProblem, account_routes.account_problem_handler)
api_app.include_router(account_routes.router)
register_capture_routes(api_app)
gateway_app = build_app("ws-gateway")
gateway_app.websocket("/ws")(websocket_gateway)
