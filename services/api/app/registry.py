"""Registry of paired extension connections.

Holds at most one active instance conceptually: MV3 reconnects produce a new
instance_id; older sockets for the same extension are displaced.
"""

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import WebSocket

from services.api.app.protocol import uuid7

ALLOWED_COMMANDS = frozenset(
    {
        "capture_list",
        "capture_details",
        "abort",
        "fill_online_resume",
        "copy_greeting",
        "capture_chat",
    }
)


class NoExtensionConnected(RuntimeError):
    """Raised when a command must be delivered but no extension is paired."""


@dataclass
class ExtensionInstance:
    instance_id: str
    websocket: WebSocket
    extension_version: str
    protocol_version: int
    connected_at: datetime
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def send(self, message: dict[str, Any]) -> None:
        # Serialize frames; abort/dispatch may originate from different tasks.
        async with self.send_lock:
            await self.websocket.send_json(message)


class ExtensionRegistry:
    def __init__(self) -> None:
        self._instances: dict[str, ExtensionInstance] = {}

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

    def unregister(self, instance_id: str) -> None:
        self._instances.pop(instance_id, None)

    def current(self) -> ExtensionInstance | None:
        if not self._instances:
            return None
        # Newest registered instance wins.
        return self._instances[max(self._instances, key=lambda k: self._instances[k].connected_at)]

    async def send_command(
        self,
        type_: str,
        payload: dict[str, Any],
        *,
        capture_id: UUID | None = None,
    ) -> str:
        if type_ not in ALLOWED_COMMANDS:
            raise ValueError(f"command type is not registered: {type_}")
        instance = self.current()
        if instance is None:
            raise NoExtensionConnected("no paired extension")
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
