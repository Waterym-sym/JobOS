"""Invite-only accounts and private onboarding data (ADR-013).

These routes are not a public deployment switch. Legacy capture routes still
need ownership conversion before the Web edge may be exposed.
"""

import hashlib
import hmac
import io
import logging
import time
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from psycopg.types.json import Json

from services.api.app.account_security import (
    digest_secret,
    hash_password,
    issue_secret,
    normalize_email,
    verify_password,
)
from services.api.app.config import get_settings
from services.api.app.db import connection
from services.api.app.errors import ErrorEnvelope
from services.api.app.protocol import uuid7

logger = logging.getLogger("jobos.account")
router = APIRouter(prefix="/api/v1", tags=["auth"])
SESSION_HOURS = 12
INVITE_HOURS = 24
RESET_MINUTES = 15
MAX_RESUME_BYTES = 10 * 1024 * 1024
_attempts: dict[str, tuple[int, float]] = {}


class AccountProblem(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        self.status = status
        self.code = code
        self.message = message


async def account_problem_handler(_: Request, exc: AccountProblem) -> JSONResponse:
    body = ErrorEnvelope(code=exc.code, message=exc.message, trace_id=uuid7())
    return JSONResponse(body.model_dump(), status_code=exc.status)


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str
    password: str


class Registration(Credentials):
    invite_token: str
    display_name: str = Field(default="", max_length=80)


class InvitationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["seeker", "recruiter"]


class ResetIssueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str


class ResetConsumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str
    password: str


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str | None = Field(default=None, max_length=80)
    basic: dict[str, Any] = Field(default_factory=dict)
    education: dict[str, Any] = Field(default_factory=dict)
    job_preference: dict[str, Any] = Field(default_factory=dict)
    onboarding_step: Literal["entry", "basic", "education", "job-preference", "complete"]


def _email(value: str) -> str:
    try:
        return normalize_email(value)
    except ValueError as exc:
        raise AccountProblem(422, "PAYLOAD_INVALID", "Invalid email address") from exc


def _password(value: str) -> str:
    try:
        return hash_password(value)
    except ValueError as exc:
        raise AccountProblem(422, "PAYLOAD_INVALID", "Password must contain 12-128 characters") from exc


def _check_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    expected = get_settings().web_origin.rstrip("/")
    if origin is not None and origin.rstrip("/") != expected:
        raise AccountProblem(403, "CSRF_INVALID", "Origin is not allowed")
    if get_settings().public_mode and origin is None:
        raise AccountProblem(403, "CSRF_INVALID", "Origin is required")


def _rate_limit(request: Request, email: str) -> None:
    # Public mode remains disabled. This is a local defense, not a substitute
    # for a shared edge rate limiter before a future public Go/No-Go.
    key = digest_secret(f"{request.client.host if request.client else ''}:{email}")
    now = time.monotonic()
    count, start = _attempts.get(key, (0, now))
    if now - start >= 300:
        count, start = 0, now
    if count >= 10:
        raise AccountProblem(429, "AUTH_RATE_LIMITED", "Try again later")
    _attempts[key] = (count + 1, start)


def _account(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": str(row[0]),
        "email": row[1],
        "role": row[2],
        "is_admin": row[3],
        "display_name": row[4],
    }


async def current_account(request: Request) -> dict[str, Any]:
    token = request.cookies.get("jobos_session")
    if not token:
        raise AccountProblem(401, "AUTH_REQUIRED", "Sign in required")
    async with connection() as conn:
        cursor = await conn.execute(
            """SELECT u.id, u.email, u.role, u.is_admin, u.display_name, s.csrf_hash
                 FROM account_session s JOIN account_user u ON u.id = s.user_id
                WHERE s.token_hash = %s AND s.revoked_at IS NULL
                  AND s.expires_at > now() AND u.deleted_at IS NULL""",
            (digest_secret(token),),
        )
        row = await cursor.fetchone()
    if row is None:
        raise AccountProblem(401, "AUTH_REQUIRED", "Sign in required")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        _check_origin(request)
        csrf = request.headers.get("x-csrf-token", "")
        if not csrf or not hmac.compare_digest(digest_secret(csrf), row[5]):
            raise AccountProblem(403, "CSRF_INVALID", "CSRF token is invalid")
    return _account(row)


async def admin_account(
    account: Annotated[dict[str, Any], Depends(current_account)],
) -> dict[str, Any]:
    if not account["is_admin"]:
        raise AccountProblem(403, "ACCOUNT_FORBIDDEN", "Administrator required")
    return account


@router.post("/auth/register", status_code=201)
async def register(body: Registration, request: Request) -> dict[str, Any]:
    _check_origin(request)
    email = _email(body.email)
    _rate_limit(request, email)
    password_hash = _password(body.password)
    if not body.invite_token or len(body.invite_token) > 256:
        raise AccountProblem(400, "INVITE_INVALID", "Invite is invalid")
    user_id = uuid4()
    async with connection() as conn:
        cursor = await conn.execute(
            """SELECT id, role, expires_at, used_at FROM account_invite
                WHERE token_hash = %s FOR UPDATE""",
            (digest_secret(body.invite_token),),
        )
        invite = await cursor.fetchone()
        if invite is None or invite[3] is not None:
            raise AccountProblem(400, "INVITE_INVALID", "Invite is invalid")
        if invite[2] <= datetime.now(UTC):
            raise AccountProblem(400, "INVITE_EXPIRED", "Invite has expired")
        cursor = await conn.execute("SELECT 1 FROM account_user WHERE email = %s", (email,))
        if await cursor.fetchone() is not None:
            raise AccountProblem(409, "ACCOUNT_FORBIDDEN", "Account already exists")
        await conn.execute(
            """INSERT INTO account_user (id, email, password_hash, role, display_name)
               VALUES (%s, %s, %s, %s, %s)""",
            (user_id, email, password_hash, invite[1], body.display_name.strip() or email.split("@")[0]),
        )
        await conn.execute("INSERT INTO account_profile (user_id) VALUES (%s)", (user_id,))
        await conn.execute("UPDATE account_invite SET used_at = now() WHERE id = %s", (invite[0],))
    logger.info("account registered", extra={"user_id": str(user_id)})
    return {"id": str(user_id), "role": invite[1]}


@router.post("/auth/login")
async def login(body: Credentials, request: Request, response: Response) -> dict[str, Any]:
    _check_origin(request)
    email = _email(body.email)
    _rate_limit(request, email)
    async with connection() as conn:
        cursor = await conn.execute(
            """SELECT id, email, role, is_admin, display_name, password_hash
                 FROM account_user WHERE email = %s AND deleted_at IS NULL""",
            (email,),
        )
        row = await cursor.fetchone()
        if row is None or not verify_password(body.password, row[5]):
            raise AccountProblem(401, "AUTH_INVALID", "Email or password is incorrect")
        session_token = issue_secret()
        csrf_token = issue_secret()
        await conn.execute(
            """INSERT INTO account_session
               (id, user_id, token_hash, csrf_hash, expires_at)
               VALUES (%s, %s, %s, %s, %s)""",
            (uuid4(), row[0], digest_secret(session_token), digest_secret(csrf_token),
             datetime.now(UTC) + timedelta(hours=SESSION_HOURS)),
        )
    secure = get_settings().session_cookie_secure
    response.set_cookie("jobos_session", session_token, max_age=SESSION_HOURS * 3600,
                        httponly=True, secure=secure, samesite="lax", path="/")
    response.set_cookie("jobos_csrf", csrf_token, max_age=SESSION_HOURS * 3600,
                        httponly=False, secure=secure, samesite="lax", path="/")
    logger.info("account login", extra={"user_id": str(row[0])})
    return _account(row)


@router.post("/auth/logout", status_code=204)
async def logout(
    request: Request, response: Response,
    _: Annotated[dict[str, Any], Depends(current_account)],
) -> None:
    token = request.cookies.get("jobos_session")
    async with connection() as conn:
        await conn.execute("UPDATE account_session SET revoked_at = now() WHERE token_hash = %s",
                           (digest_secret(token or ""),))
    response.delete_cookie("jobos_session", path="/")
    response.delete_cookie("jobos_csrf", path="/")


@router.get("/me")
async def me(account: Annotated[dict[str, Any], Depends(current_account)]) -> dict[str, Any]:
    return account


@router.post("/auth/session-check")
async def check_admin_session(
    account: Annotated[dict[str, Any], Depends(admin_account)],
) -> dict[str, bool]:
    return {"authorized": bool(account["is_admin"])}


@router.post("/auth/invitations", status_code=201)
async def issue_invitation(
    body: InvitationRequest,
    account: Annotated[dict[str, Any], Depends(admin_account)],
) -> dict[str, str]:
    token = issue_secret()
    async with connection() as conn:
        await conn.execute(
            """INSERT INTO account_invite (id, token_hash, role, created_by, expires_at)
               VALUES (%s, %s, %s, %s, %s)""",
            (uuid4(), digest_secret(token), body.role, UUID(account["id"]),
             datetime.now(UTC) + timedelta(hours=INVITE_HOURS)),
        )
    return {"token": token, "expires_in_seconds": str(INVITE_HOURS * 3600)}


@router.post("/auth/password-resets", status_code=201)
async def issue_reset(
    body: ResetIssueRequest,
    account: Annotated[dict[str, Any], Depends(admin_account)],
) -> dict[str, str]:
    email = _email(body.email)
    async with connection() as conn:
        cursor = await conn.execute("SELECT id FROM account_user WHERE email = %s AND deleted_at IS NULL", (email,))
        row = await cursor.fetchone()
        if row is None:
            raise AccountProblem(404, "AUTH_INVALID", "Account not found")
        token = issue_secret()
        await conn.execute(
            """INSERT INTO account_reset (id, user_id, token_hash, created_by, expires_at)
               VALUES (%s, %s, %s, %s, %s)""",
            (uuid4(), row[0], digest_secret(token), UUID(account["id"]),
             datetime.now(UTC) + timedelta(minutes=RESET_MINUTES)),
        )
    return {"token": token, "expires_in_seconds": str(RESET_MINUTES * 60)}


@router.post("/auth/password-reset", status_code=204)
async def reset_password(body: ResetConsumeRequest, request: Request) -> None:
    _check_origin(request)
    _rate_limit(request, digest_secret(body.token))
    password_hash = _password(body.password)
    async with connection() as conn:
        cursor = await conn.execute(
            """SELECT id, user_id, expires_at, used_at FROM account_reset
                WHERE token_hash = %s FOR UPDATE""", (digest_secret(body.token),)
        )
        row = await cursor.fetchone()
        if row is None or row[3] is not None or row[2] <= datetime.now(UTC):
            raise AccountProblem(400, "AUTH_INVALID", "Reset token is invalid or expired")
        await conn.execute("UPDATE account_user SET password_hash = %s WHERE id = %s",
                           (password_hash, row[1]))
        await conn.execute("UPDATE account_reset SET used_at = now() WHERE id = %s", (row[0],))
        await conn.execute("UPDATE account_session SET revoked_at = now() WHERE user_id = %s",
                           (row[1],))


@router.get("/me/profile")
async def get_profile(
    account: Annotated[dict[str, Any], Depends(current_account)],
) -> dict[str, Any]:
    async with connection() as conn:
        cursor = await conn.execute(
            """SELECT basic_json, education_json, preference_json, onboarding_step
                 FROM account_profile WHERE user_id = %s""", (UUID(account["id"]),)
        )
        row = await cursor.fetchone()
    if row is None:
        raise AccountProblem(404, "RESOURCE_NOT_OWNED", "Profile not found")
    return {"display_name": account["display_name"], "basic": row[0], "education": row[1],
            "job_preference": row[2], "onboarding_step": row[3]}


@router.put("/me/profile")
async def put_profile(
    body: ProfileUpdate,
    account: Annotated[dict[str, Any], Depends(current_account)],
) -> dict[str, Any]:
    user_id = UUID(account["id"])
    async with connection() as conn:
        await conn.execute(
            """UPDATE account_profile
                  SET basic_json = %s, education_json = %s, preference_json = %s,
                      onboarding_step = %s, updated_at = now()
                WHERE user_id = %s""",
            (Json(body.basic), Json(body.education), Json(body.job_preference),
             body.onboarding_step, user_id),
        )
        if body.display_name is not None:
            await conn.execute("UPDATE account_user SET display_name = %s WHERE id = %s",
                               (body.display_name.strip(), user_id))
    return await get_profile({**account, "display_name": body.display_name or account["display_name"]})


def _resume_kind(filename: str, content: bytes) -> tuple[str, str]:
    suffix = Path(filename).suffix.casefold()
    if suffix == ".pdf" and content.startswith(b"%PDF-"):
        return "pdf", "application/pdf"
    if suffix == ".docx" and content.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as package:
                entries = package.infolist()
                names = {entry.filename for entry in entries}
                if len(entries) > 1000 or sum(entry.file_size for entry in entries) > 50 * 1024 * 1024:
                    raise AccountProblem(400, "RESUME_FILE_INVALID", "DOCX archive is too large")
                if "[Content_Types].xml" in names and "word/document.xml" in names:
                    return "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        except (zipfile.BadZipFile, OSError):
            pass
    raise AccountProblem(400, "RESUME_FILE_INVALID", "Only PDF or DOCX files are supported")


@router.post("/me/resumes", status_code=201)
async def upload_resume(
    file: Annotated[UploadFile, File()],
    account: Annotated[dict[str, Any], Depends(current_account)],
) -> dict[str, str]:
    content = await file.read(MAX_RESUME_BYTES + 1)
    if not content or len(content) > MAX_RESUME_BYTES:
        raise AccountProblem(400, "RESUME_FILE_INVALID", "File is empty or exceeds 10 MB")
    kind, media_type = _resume_kind(file.filename or "", content)
    user_id = UUID(account["id"])
    resume_id = uuid4()
    relative_key = f"user-resumes/{user_id}/{resume_id}.{kind}"
    destination = get_settings().storage_dir / relative_key
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    try:
        async with connection() as conn:
            await conn.execute(
                """INSERT INTO resume_file
                   (id, user_id, filename, content_type, storage_key, sha256)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (resume_id, user_id, Path(file.filename or "resume").name[:255],
                 media_type, relative_key, hashlib.sha256(content).hexdigest()),
            )
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return {"id": str(resume_id), "filename": Path(file.filename or "resume").name[:255],
            "status": "stored"}


@router.delete("/me", status_code=204)
async def delete_account(
    response: Response,
    account: Annotated[dict[str, Any], Depends(current_account)],
) -> None:
    user_id = UUID(account["id"])
    storage_root = get_settings().storage_dir.resolve()
    async with connection() as conn:
        if account["is_admin"]:
            cursor = await conn.execute(
                "SELECT id FROM account_user WHERE is_admin = true AND deleted_at IS NULL FOR UPDATE"
            )
            if len(await cursor.fetchall()) <= 1:
                raise AccountProblem(409, "ACCOUNT_LAST_ADMIN", "Transfer administrator access first")
        cursor = await conn.execute("SELECT storage_key FROM resume_file WHERE user_id = %s", (user_id,))
        file_keys = [row[0] for row in await cursor.fetchall()]
        for table in ("screening_entry", "shortlist", "raw_company", "ws_event_inbox",
                      "raw_job", "batch_run"):
            await conn.execute(f"DELETE FROM {table} WHERE owner_user_id = %s", (user_id,))
        await conn.execute("DELETE FROM resume_file WHERE user_id = %s", (user_id,))
        await conn.execute("DELETE FROM account_profile WHERE user_id = %s", (user_id,))
        await conn.execute("DELETE FROM account_session WHERE user_id = %s", (user_id,))
        await conn.execute("DELETE FROM account_reset WHERE user_id = %s OR created_by = %s",
                           (user_id, user_id))
        await conn.execute("DELETE FROM account_invite WHERE created_by = %s", (user_id,))
        await conn.execute("DELETE FROM account_user WHERE id = %s", (user_id,))
    for key in file_keys:
        destination = (storage_root / key).resolve()
        if storage_root not in destination.parents:
            logger.error("resume storage key escaped configured root", extra={"user_id": str(user_id)})
            continue
        destination.unlink(missing_ok=True)
    response.delete_cookie("jobos_session", path="/")
    response.delete_cookie("jobos_csrf", path="/")
