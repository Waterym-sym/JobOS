import json
import logging
import re
from datetime import UTC, datetime
from ipaddress import ip_address
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from services.api.app.capture_repo import (
    complete_batch,
    mark_progress,
    release_event,
    reserve_event,
    upsert_company,
    upsert_raw_job,
)
from services.api.app.config import Settings, get_settings
from services.api.app.event_models import (
    EVENT_PAYLOAD_MODELS,
    EventEnvelope,
    ReceiptEnvelope,
)
from services.api.app.pairing import PairingTokenStore
from services.api.app.protocol import uuid7
from services.api.app.registry import ExtensionInstance, registry

PROTOCOL_VERSION = 1
EXTENSION_ID_PATTERN = re.compile(r"^[a-p]{32}$")
logger = logging.getLogger("jobos.ws")


class AuthPingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=16)
    extension_version: str = Field(min_length=1)
    protocol_version: int = Field(ge=1)
    # Optional capability declaration: commands that require a capability are
    # routed to an instance that announced it (see registry.COMMAND_CAPABILITIES).
    capabilities: list[str] = Field(default_factory=list)


class AuthPing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    v: Literal[1]
    kind: Literal["handshake"]
    id: UUID
    type: Literal["auth_ping"]
    payload: AuthPingPayload


def is_allowed_origin(origin: str | None) -> bool:
    if origin is None:
        return False
    try:
        parsed = urlparse(origin)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "chrome-extension"
        and parsed.hostname is not None
        and EXTENSION_ID_PATTERN.fullmatch(parsed.hostname) is not None
        and port is None
        and not parsed.path.strip("/")
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
    )


def is_local_peer(host: str | None, *, container_mode: bool) -> bool:
    if not host:
        return False
    try:
        address = ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or (container_mode and address.is_private)


def error_envelope(code: str, message: str, trace_id: str) -> dict[str, Any]:
    return {"code": code, "message": message, "trace_id": trace_id, "details": {}}


async def reject(websocket: WebSocket, code: str, message: str, trace_id: str) -> None:
    await websocket.accept()
    await websocket.send_json(error_envelope(code, message, trace_id))
    await websocket.close(code=1008, reason=code)


def audit(event: str, outcome: str, trace_id: str, **details: Any) -> None:
    logger.info(
        json.dumps(
            {"event": event, "outcome": outcome, "trace_id": trace_id, "details": details},
            ensure_ascii=True,
        )
    )


async def _handle_event_once(envelope: EventEnvelope) -> None:
    model_cls = EVENT_PAYLOAD_MODELS.get(envelope.type)
    if model_cls is None:
        raise ValueError(f"unknown event type: {envelope.type}")
    payload: Any = model_cls.model_validate(envelope.payload)
    capture_id = envelope.capture_id or getattr(payload, "batch_id", None)

    if envelope.type in ("job.captured", "job.updated"):
        if envelope.capture_id is not None and payload.batch_id is None:
            payload.batch_id = envelope.capture_id
        await upsert_raw_job(payload)
        audit(
            "extension.event",
            envelope.type,
            str(envelope.id),
            ext_id=payload.ext_id,
            tier=payload.tier,
        )
    elif envelope.type == "company.updated":
        # Protocol deviation (documented): gongsi-page snapshot, envelope stays
        # {v:1, kind:"event"}. Not tied to a batch.
        await upsert_company(payload)
        audit(
            "extension.event",
            "company.updated",
            str(envelope.id),
            ext_company_id=payload.ext_company_id,
        )
    elif envelope.type == "capture.phase":
        if capture_id is not None:
            await mark_progress(capture_id, payload.model_dump())
    elif envelope.type == "capture.completed":
        await complete_batch(
            payload.capture_id,
            status="completed",
            stats=payload.stats.model_dump(),
            finished_at=payload.finished_at,
        )
    elif envelope.type == "capture.error":
        audit(
            "extension.event",
            "capture.error",
            str(envelope.id),
            code=payload.code,
            risk=payload.risk,
            recoverable=payload.recoverable,
            # Field-extraction diagnostics only (page title/DOM hints); chat
            # text never reaches this path.
            message=payload.message[:300],
        )
        if capture_id is not None and payload.risk:
            # ADR-009: risk halt, never auto-retry.
            await complete_batch(
                capture_id,
                status="risk_halted",
                stats={"success": 0, "dup": 0, "risk_halted": True},
            )
        elif capture_id is not None:
            await complete_batch(
                capture_id,
                status="failed",
                stats={
                    "code": payload.code,
                    "message": payload.message,
                    "recoverable": payload.recoverable,
                },
            )


async def handle_event(envelope: EventEnvelope) -> None:
    if not await reserve_event(envelope.id, envelope.type, envelope.capture_id):
        audit("extension.event", "duplicate_ignored", str(envelope.id), type=envelope.type)
        return
    try:
        await _handle_event_once(envelope)
    except Exception:
        await release_event(envelope.id)
        raise


async def dispatch_message(message: Any) -> None:
    if not isinstance(message, dict):
        raise TypeError("message must be a JSON object")
    kind = message.get("kind")
    if kind == "event":
        await handle_event(EventEnvelope.model_validate(message))
    elif kind == "receipt":
        envelope = ReceiptEnvelope.model_validate(message)
        audit(
            "ws.receipt",
            envelope.type,
            str(envelope.id),
            command_id=str(envelope.command_id) if envelope.command_id else None,
        )
    else:
        raise ValueError(f"unexpected message kind: {kind}")


async def websocket_gateway(websocket: WebSocket) -> None:
    settings: Settings = get_settings()
    initial_trace_id = uuid7()
    peer = websocket.client.host if websocket.client else None
    if not is_local_peer(peer, container_mode=settings.container_mode):
        await reject(
            websocket,
            "LOOPBACK_ONLY",
            "WebSocket accepts local clients only",
            initial_trace_id,
        )
        return

    origin = websocket.headers.get("origin")
    if not is_allowed_origin(origin):
        await reject(
            websocket,
            "LOOPBACK_ONLY",
            "Extension Origin is not allowed",
            initial_trace_id,
        )
        return

    await websocket.accept()
    try:
        raw = await websocket.receive_json()
        ping = AuthPing.model_validate(raw)
    except (ValidationError, ValueError, TypeError):
        await websocket.send_json(
            error_envelope(
                "PAIRING_TOKEN_INVALID",
                "A valid auth_ping is required",
                initial_trace_id,
            )
        )
        await websocket.close(code=1008, reason="PAIRING_TOKEN_INVALID")
        return
    except WebSocketDisconnect:
        return

    trace_id = str(ping.id)
    if ping.payload.protocol_version != PROTOCOL_VERSION:
        await websocket.send_json(
            {
                "v": 1,
                "kind": "handshake",
                "id": uuid7(),
                "type": "auth_pong",
                "payload": {"supported": False, "min_version": PROTOCOL_VERSION},
            }
        )
        audit("extension.pair", "version_mismatch", trace_id)
        await websocket.close(code=1008, reason="EXTENSION_VERSION_MISMATCH")
        return

    configured = settings.pairing_token.get_secret_value() if settings.pairing_token else None
    token_store = PairingTokenStore(settings.pairing_token_file, configured)
    if not token_store.matches(ping.payload.token):
        await websocket.send_json(
            error_envelope("PAIRING_TOKEN_INVALID", "Pairing token is invalid", trace_id)
        )
        audit("extension.pair", "rejected", trace_id)
        await websocket.close(code=1008, reason="PAIRING_TOKEN_INVALID")
        return

    instance_id = uuid7()
    await websocket.send_json(
        {
            "v": 1,
            "kind": "handshake",
            "id": uuid7(),
            "type": "auth_pong",
            "payload": {
                "supported": True,
                "min_version": PROTOCOL_VERSION,
                "extension_instance_id": instance_id,
            },
        }
    )
    audit(
        "extension.pair",
        "accepted",
        trace_id,
        extension_version=ping.payload.extension_version,
        instance_id=instance_id,
    )

    instance = ExtensionInstance(
        instance_id=instance_id,
        websocket=websocket,
        extension_version=ping.payload.extension_version,
        protocol_version=ping.payload.protocol_version,
        connected_at=datetime.now(UTC),
        capabilities=frozenset(ping.payload.capabilities),
    )
    await registry.register(instance)

    try:
        while True:
            try:
                message = await websocket.receive_json()
            except ValueError:
                # Non-JSON frame; wait for the next one.
                continue
            trace = (
                str(message.get("id", uuid7()))
                if isinstance(message, dict)
                else uuid7()
            )
            try:
                await dispatch_message(message)
            except (ValidationError, ValueError, TypeError) as exc:
                audit("ws.message", "invalid", trace, reason=str(exc)[:200])
                await websocket.send_json(
                    error_envelope(
                        "MESSAGE_INVALID",
                        "Message failed protocol validation",
                        trace,
                    )
                )
            except Exception:  # noqa: BLE001 - keep the socket alive
                logger.exception("event dispatch failed")
                audit("ws.message", "error", trace)
                await websocket.send_json(
                    error_envelope("INTERNAL_ERROR", "Event handling failed", trace)
                )
    except WebSocketDisconnect:
        return
    finally:
        registry.unregister(instance_id)
