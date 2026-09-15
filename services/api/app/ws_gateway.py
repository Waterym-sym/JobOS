import json
import logging
import re
import secrets
import time
from ipaddress import ip_address
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from services.api.app.config import Settings, get_settings
from services.api.app.pairing import PairingTokenStore

PROTOCOL_VERSION = 1
EXTENSION_ID_PATTERN = re.compile(r"^[a-p]{32}$")
logger = logging.getLogger("jobos.ws")


class AuthPingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=16)
    extension_version: str = Field(min_length=1)
    protocol_version: int = Field(ge=1)


class AuthPing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    v: Literal[1]
    kind: Literal["handshake"]
    id: UUID
    type: Literal["auth_ping"]
    payload: AuthPingPayload


def uuid7() -> str:
    timestamp_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    random_a = secrets.randbits(12)
    random_b = secrets.randbits(62)
    value = (timestamp_ms << 80) | (0x7 << 76) | (random_a << 64) | (0b10 << 62) | random_b
    return str(UUID(int=value))


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

    try:
        while True:
            message = await websocket.receive_json()
            audit(
                "ws.message",
                "ignored_unimplemented",
                str(message.get("id", uuid7())) if isinstance(message, dict) else uuid7(),
                message_type=message.get("type") if isinstance(message, dict) else None,
            )
    except (WebSocketDisconnect, ValueError, TypeError):
        return
