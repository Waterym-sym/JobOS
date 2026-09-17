"""Extension registry status: per-instance roles and capability memory.

The REST status surface distinguishes the list capture bridge (no capabilities)
from the pool enrich bridge (capture_details_urls / capture_company), so the UI
can show two independent online indicators.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from services.api.app.registry import ExtensionInstance, ExtensionRegistry

LIST_ORIGIN = "chrome-extension://boss-helper"
POOL_ORIGIN = "chrome-extension://jobos-bridge"
POOL_CAPS = frozenset({"capture_details_urls", "capture_company"})


class FakeSocket:
    def __init__(self, origin: str) -> None:
        self.headers = {"origin": origin}
        self.closed: tuple[int, str] | None = None

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed = (code, reason)


def _instance(
    origin: str,
    version: str,
    *,
    connected_at: datetime,
    capabilities: frozenset[str] = frozenset(),
) -> ExtensionInstance:
    return ExtensionInstance(
        instance_id=str(uuid4()),
        websocket=FakeSocket(origin),
        extension_version=version,
        protocol_version=1,
        connected_at=connected_at,
        capabilities=capabilities,
    )


def test_status_is_empty_shape_when_nothing_paired() -> None:
    assert ExtensionRegistry().status() == {"paired": False, "instances": []}


def test_status_lists_both_bridges_with_roles_and_versions() -> None:
    registry = ExtensionRegistry()
    base = datetime(2026, 9, 17, tzinfo=timezone.utc)
    list_bridge = _instance(LIST_ORIGIN, "0.5.2.2", connected_at=base)
    pool_bridge = _instance(
        POOL_ORIGIN, "0.3.0", connected_at=base + timedelta(seconds=5), capabilities=POOL_CAPS
    )

    asyncio.run(registry.register(list_bridge))
    asyncio.run(registry.register(pool_bridge))

    status = registry.status()
    assert status["paired"] is True
    assert [item["role"] for item in status["instances"]] == ["list_bridge", "pool_bridge"]
    by_role = {item["role"]: item for item in status["instances"]}
    assert by_role["list_bridge"]["extension_version"] == "0.5.2.2"
    assert by_role["list_bridge"]["capabilities"] == []
    assert by_role["pool_bridge"]["extension_version"] == "0.3.0"
    assert by_role["pool_bridge"]["capabilities"] == ["capture_company", "capture_details_urls"]
    assert set(by_role["pool_bridge"]) == {
        "instance_id",
        "role",
        "extension_version",
        "protocol_version",
        "connected_at",
        "capabilities",
    }


def test_pool_capability_is_remembered_after_bridge_disconnects() -> None:
    # During an MV3 service-worker sleep gap the pool bridge socket is gone;
    # the registry still knows that capability existed so the UI can say
    # "reconnecting" rather than "never installed".
    registry = ExtensionRegistry()
    base = datetime(2026, 9, 17, tzinfo=timezone.utc)
    list_bridge = _instance(LIST_ORIGIN, "0.5.2.2", connected_at=base)
    pool_bridge = _instance(POOL_ORIGIN, "0.3.0", connected_at=base, capabilities=POOL_CAPS)

    asyncio.run(registry.register(list_bridge))
    asyncio.run(registry.register(pool_bridge))
    assert registry.capable("capture_company") is True

    registry.unregister(pool_bridge.instance_id)

    assert registry.capable("capture_company") is False
    assert registry.was_capable("capture_company") is True
    assert registry.was_capable("capture_details_urls") is True
    # The list bridge keeps the status paired while the pool bridge is away.
    status = registry.status()
    assert status["paired"] is True
    assert [item["role"] for item in status["instances"]] == ["list_bridge"]


def test_unknown_capability_was_never_seen() -> None:
    registry = ExtensionRegistry()

    assert registry.capable("capture_company") is False
    assert registry.was_capable("capture_company") is False
