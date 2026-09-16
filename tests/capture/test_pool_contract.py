"""Contract negatives + capability routing for the pool-enrich commands.

These tests pin the red lines: only BOSS company pages may be navigated to, the
1800ms delay floor is contractual, auto paging stays forbidden, and commands
that need a capability never go to an instance that did not announce it.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import jsonschema
import pytest
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from services.api.app.registry import (
    ALLOWED_COMMANDS,
    ExtensionInstance,
    ExtensionRegistry,
    NoExtensionConnected,
)

WS_DIR = Path(__file__).resolve().parents[2] / "contracts" / "ws"
COMMANDS = json.loads((WS_DIR / "commands.schema.json").read_text(encoding="utf-8"))
EVENTS = json.loads((WS_DIR / "events.schema.json").read_text(encoding="utf-8"))
HANDSHAKE = json.loads((WS_DIR / "handshake.schema.json").read_text(encoding="utf-8"))


def _ws_registry() -> Registry:
    """Resolve the ./x.schema.json cross-references between ws contracts."""
    resources: dict[str, Resource] = {}
    for path in WS_DIR.glob("*.schema.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        resources[schema["$id"]] = Resource.from_contents(
            schema, default_specification=DRAFT202012
        )
    return Registry().with_resources(resources.items())


def validate(schema: dict[str, Any], payload: dict[str, Any]) -> list[Any]:
    validator = jsonschema.Draft202012Validator(schema, registry=_ws_registry())
    return list(validator.iter_errors(payload))


def command(type_: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "v": 1,
        "kind": "command",
        "id": str(uuid4()),
        "type": type_,
        "command_id": str(uuid4()),
        "payload": payload,
    }


def event(type_: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "v": 1,
        "kind": "event",
        "id": str(uuid4()),
        "type": type_,
        "payload": payload,
    }


def test_capture_company_accepts_only_boss_company_pages() -> None:
    valid = command(
        "capture_company",
        {
            "company_url": "https://www.zhipin.com/gongsi/synthBrand0001~.html",
            "ext_company_id": "synthBrand0001~",
            "delay_ms": 1800,
        },
    )
    assert validate(COMMANDS, valid) == []

    foreign = command(
        "capture_company",
        {
            "company_url": "https://evil.example.com/gongsi/x.html",
            "ext_company_id": "x",
            "delay_ms": 1800,
        },
    )
    assert validate(COMMANDS, foreign) != []


def test_capture_company_rejects_delays_below_the_floor() -> None:
    payload = {
        "company_url": "https://www.zhipin.com/gongsi/x.html",
        "ext_company_id": "x",
        "delay_ms": 1799,
    }
    assert validate(COMMANDS, command("capture_company", payload)) != []


def test_capture_details_accepts_urls_form_and_requires_a_target() -> None:
    url_form = command(
        "capture_details",
        {
            "urls": [
                {
                    "ext_id": "synth-job-0001",
                    "url": "https://www.zhipin.com/job_detail/synth-job-0001.html?securityId=s1",
                    "security_id": "s1",
                }
            ],
            "detail_limit": 1,
            "delay_ms": 1800,
        },
    )
    assert validate(COMMANDS, url_form) == []

    ext_ids_form = command(
        "capture_details", {"ext_ids": ["synth-job-0001"], "detail_limit": 1, "delay_ms": 1800}
    )
    assert validate(COMMANDS, ext_ids_form) == []

    no_target = command("capture_details", {"detail_limit": 1, "delay_ms": 1800})
    assert validate(COMMANDS, no_target) != []


def test_capture_list_still_forbids_automatic_paging() -> None:
    payload = {"max_items": 30, "delay_ms": 1800, "auto_next_page": False}
    assert validate(COMMANDS, command("capture_list", payload)) == []

    payload["auto_next_page"] = True
    assert validate(COMMANDS, command("capture_list", payload)) != []


def test_registry_gate_rejects_commands_that_were_never_registered() -> None:
    registry = ExtensionRegistry()

    async def scenario() -> None:
        for forbidden in ("send_message", "auto_greet", "deliver", "auto_apply"):
            assert forbidden not in ALLOWED_COMMANDS
            with pytest.raises(ValueError, match="not registered"):
                await registry.send_command(forbidden, {})

    asyncio.run(scenario())


def test_company_updated_event_and_company_phase_are_contractual() -> None:
    payload = {
        "source": "boss",
        "ext_company_id": "synthBrand0001~",
        "name": "合成科技有限公司",
        "sections": {"intro": "合成公司简介"},
        "captured_at": datetime.now(UTC).isoformat(),
    }
    assert validate(EVENTS, event("company.updated", payload)) == []

    phase = {"phase": "company", "done": 1, "total": 1, "current": "合成科技有限公司"}
    assert validate(EVENTS, event("capture.phase", phase)) == []

    missing_id = event("company.updated", {"source": "boss", "sections": {}})
    assert validate(EVENTS, missing_id) != []


def test_handshake_capabilities_are_optional_and_typed() -> None:
    base = {
        "token": "0123456789abcdef",
        "extension_version": "0.2.0",
        "protocol_version": 1,
    }
    assert validate(HANDSHAKE, _ping(base)) == []
    assert validate(HANDSHAKE, _ping({**base, "capabilities": ["capture_company"]})) == []
    assert validate(HANDSHAKE, _ping({**base, "capabilities": [1]})) != []


def _ping(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "v": 1,
        "kind": "handshake",
        "id": str(uuid4()),
        "type": "auth_ping",
        "payload": payload,
    }


# ------------------------------------------------------------ capability routing


class FakeSocket:
    def __init__(self, origin: str) -> None:
        self.headers = {"origin": origin}
        self.sent: list[dict[str, Any]] = []

    async def send_json(self, message: dict[str, Any]) -> None:
        self.sent.append(message)

    async def close(self, **_kwargs: Any) -> None:
        return None


def register(registry: ExtensionRegistry, capabilities: set[str], *, age_s: int = 0) -> Any:
    # Distinct origins: register() displaces older sockets of the same origin.
    instance_id = str(uuid4())
    seed = instance_id.replace("-", "")
    origin = "chrome-extension://" + "".join("abcdefghijklmnop"[int(c, 16)] for c in seed[:32])
    instance = ExtensionInstance(
        instance_id=instance_id,
        websocket=FakeSocket(origin),
        extension_version="0.2.0",
        protocol_version=1,
        connected_at=datetime.now(UTC) - timedelta(seconds=age_s),
        capabilities=frozenset(capabilities),
    )
    asyncio.run(registry.register(instance))
    return instance


def test_versioned_commands_route_to_the_instance_that_announced_the_capability() -> None:
    registry = ExtensionRegistry()
    bridge = register(registry, set(), age_s=0)  # newest, but announces nothing
    pool = register(registry, {"capture_details_urls", "capture_company"}, age_s=30)

    async def scenario() -> None:
        await registry.send_command(
            "capture_company",
            {"company_url": "https://www.zhipin.com/gongsi/x.html", "ext_company_id": "x"},
        )
        await registry.send_command(
            "capture_details",
            {"urls": [{"ext_id": "j1", "url": "https://www.zhipin.com/job_detail/j1.html"}]},
        )
        # Legacy commands keep going to the external bridge.
        await registry.send_command("capture_list", {"max_items": 30, "delay_ms": 1800})

    asyncio.run(scenario())

    assert len(pool.websocket.sent) == 2
    assert len(bridge.websocket.sent) == 1
    assert pool.websocket.sent[0]["type"] == "capture_company"
    assert pool.websocket.sent[1]["type"] == "capture_details"
    assert bridge.websocket.sent[0]["type"] == "capture_list"


def test_capability_commands_fail_closed_without_a_capable_instance() -> None:
    registry = ExtensionRegistry()
    register(registry, set())

    async def scenario() -> None:
        with pytest.raises(NoExtensionConnected):
            await registry.send_command(
                "capture_company",
                {"company_url": "https://www.zhipin.com/gongsi/x.html", "ext_company_id": "x"},
            )

    asyncio.run(scenario())