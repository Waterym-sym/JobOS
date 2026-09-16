"""Registry of paired extension connections.

Holds at most one active instance conceptually: MV3 reconnects produce a new
instance_id; older sockets for the same extension are displaced.
"""

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import WebSocket

from services.api.app.protocol import uuid7

logger = logging.getLogger("jobos.registry")

ALLOWED_COMMANDS = frozenset(
    {
        "capture_list",
        "capture_details",
        "capture_company",
        "abort",
        "fill_online_resume",
        "copy_greeting",
        "capture_chat",
    }
)

# Capabilities a paired client may announce in auth_ping. Pool-enrich commands
# are routed to an instance that announced the matching capability; commands
# without a capability keep the legacy "newest instance wins" routing so the
# external bridge keeps serving list capture.
POOL_CAPABILITIES = frozenset({"capture_details_urls", "capture_company"})

COMMAND_CAPABILITIES: dict[str, str] = {
    "capture_company": "capture_company",
}


class NoExtensionConnected(RuntimeError):
    """Raised when a command must be delivered but no extension is paired."""


@dataclass
class ExtensionInstance:
    instance_id: str
    websocket: WebSocket
    extension_version: str
    protocol_version: int
    connected_at: datetime
    capabilities: frozenset[str] = frozenset()
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def send(self, message: dict[str, Any]) -> None:
        # Serialize frames; abort/dispatch may originate from different tasks.
        async with self.send_lock:
            await self.websocket.send_json(message)


class ExtensionRegistry:
    def __init__(self) -> None:
        self._instances: dict[str, ExtensionInstance] = {}
        self._connect_subscribers: list[Callable[[], None]] = []

    def subscribe_connected(self, fn: Callable[[], None]) -> None:
        """Notify when an instance pairs (used to wake capability-gated work)."""
        self._connect_subscribers.append(fn)

    async def register(self, instance: ExtensionInstance) -> None:
        # Displace any previous sockets for the same browser extension.
        stale = [
            (iid, inst)
            for iid, inst in self._instances.items()
            if inst.websocket.headers.get("origin")
            == instance.websocket.headers.get("origin")
            and iid != instance.instance_id
        ]
        for iid, inst in stale:
            self._instances.pop(iid, None)
            with suppress(Exception):
                await inst.websocket.close(code=1000, reason="reconnected")
        self._instances[instance.instance_id] = instance
        for subscriber in list(self._connect_subscribers):
            try:
                subscriber()
            except Exception:  # noqa: BLE001 - subscriber bugs must not break pairing
                logger.exception("connect subscriber failed")

    def unregister(self, instance_id: str) -> None:
        self._instances.pop(instance_id, None)

    def current(self) -> ExtensionInstance | None:
        if not self._instances:
            return None
        # Newest registered instance wins.
        return self._instances[max(self._instances, key=lambda k: self._instances[k].connected_at)]

    def select(self, type_: str, payload: dict[str, Any]) -> ExtensionInstance | None:
        """Pick the instance that should run a command.

        Capability-routed commands go to the newest instance announcing that
        capability (None when nobody can run them). Legacy commands prefer an
        instance without pool capabilities — the external bridge — so list
        capture keeps working while both clients are paired.
        """
        capability = COMMAND_CAPABILITIES.get(type_)
        if capability is None and type_ == "capture_details" and payload.get("urls"):
            capability = "capture_details_urls"
        if capability is not None:
            for instance in reversed(self._by_age()):
                if capability in instance.capabilities:
                    return instance
            return None
        legacy = [i for i in self._by_age() if not (i.capabilities & POOL_CAPABILITIES)]
        if legacy:
            return legacy[-1]
        return self.current()

    def _by_age(self) -> list[ExtensionInstance]:
        return sorted(self._instances.values(), key=lambda i: i.connected_at)

    def capable(self, capability: str) -> bool:
        """True when a paired instance announced the capability."""
        return any(capability in instance.capabilities for instance in self._instances.values())

    async def send_command(
        self,
        type_: str,
        payload: dict[str, Any],
        *,
        capture_id: UUID | None = None,
    ) -> str:
        if type_ not in ALLOWED_COMMANDS:
            raise ValueError(f"command type is not registered: {type_}")
        instance = self.select(type_, payload)
        if instance is None:
            raise NoExtensionConnected(f"no paired extension can run {type_}")
        command_id = uuid7()
        envelope: dict[str, Any] = {
            "v": 1,
            "kind": "command",
            "id": uuid7(),
            "type": type_,
            "command_id": command_id,
            "payload": payload,
        }
        if capture_id is not None:
            envelope["capture_id"] = str(capture_id)
        await instance.send(envelope)
        return command_id

    def status(self) -> dict[str, Any]:
        instance = self.current()
        if instance is None:
            return {"paired": False}
        return {
            "paired": True,
            "instance_id": instance.instance_id,
            "extension_version": instance.extension_version,
            "protocol_version": instance.protocol_version,
            "connected_at": instance.connected_at.isoformat(),
        }


registry = ExtensionRegistry()
