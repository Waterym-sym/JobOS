"""REST surface tests (protocol #21 §3/§8): fakes registry and repo."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from services.api.app import capture_repo as repo_mod
from services.api.app.main import api_app
from services.api.app.registry import NoExtensionConnected

CAPTURE_ID = uuid4()
NOW = datetime.now(UTC)
TOKEN = "synthetic-pairing-token-00000001"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class FakeRegistry:
    def __init__(self) -> None:
        self.online = True
        self.commands: list[tuple[str, dict[str, Any], UUID | None]] = []

    async def send_command(
        self,
        type_: str,
        payload: dict[str, Any],
        capture_id: UUID | None = None,
    ) -> str:
        if not self.online:
            raise NoExtensionConnected("no paired extension")
        self.commands.append((type_, payload, capture_id))
        return "command-id"

    def status(self) -> dict[str, Any]:
        return {"paired": False}


class FakeRepo:
    def __init__(self) -> None:
        self.completed: list[dict[str, Any]] = []

    async def create_batch_run(self, **kwargs: Any) -> UUID:
        return CAPTURE_ID

    async def get_batch(self, capture_id: UUID) -> dict[str, Any]:
        return {
            "id": str(capture_id),
            "source": "boss",
            "kind": "list",
            "status": "running",
            "stats": {},
            "risk_halted": False,
            "trigger": "console",
            "started_at": NOW.isoformat(),
            "finished_at": None,
        }

    async def complete_batch(self, capture_id: UUID, **kwargs: Any) -> dict[str, Any]:
        record = {"capture_id": capture_id, **kwargs}
        self.completed.append(record)
        return kwargs.get("stats") or {}


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch) -> tuple[FakeRegistry, FakeRepo]:
    monkeypatch.setenv("PAIRING_TOKEN", TOKEN)
    fake_registry = FakeRegistry()
    fake_repo = FakeRepo()
    monkeypatch.setattr("services.api.app.main.registry", fake_registry)
    monkeypatch.setattr(repo_mod, "create_batch_run", fake_repo.create_batch_run)
    monkeypatch.setattr(repo_mod, "get_batch", fake_repo.get_batch)
    monkeypatch.setattr(repo_mod, "complete_batch", fake_repo.complete_batch)
    return fake_registry, fake_repo


def test_create_list_capture_dispatches_capture_list(
    wired: tuple[FakeRegistry, FakeRepo],
) -> None:
    fake_registry, _ = wired
    response = TestClient(api_app, client=("127.0.0.1", 50000)).post(
        "/api/v1/captures",
        headers=AUTH,
        json={"kind": "list", "max_items": 30, "delay_ms": 1800},
    )

    assert response.status_code == 202
    assert response.json()["id"] == str(CAPTURE_ID)
    assert len(fake_registry.commands) == 1
    type_, payload, capture_id = fake_registry.commands[0]
    assert type_ == "capture_list"
    assert capture_id == CAPTURE_ID
    assert payload == {
        "query_url": None,
        "list_params": None,
        "max_items": 30,
        "delay_ms": 1800,
        "auto_next_page": False,
    }


def test_create_detail_capture_shape_has_no_paging(
    wired: tuple[FakeRegistry, FakeRepo],
) -> None:
    fake_registry, _ = wired
    response = TestClient(api_app, client=("127.0.0.1", 50000)).post(
        "/api/v1/captures",
        headers=AUTH,
        json={
            "kind": "detail",
            "ext_ids": ["ext-1", "ext-2"],
            "detail_limit": 10,
            "delay_ms": 2000,
        },
    )

    assert response.status_code == 202
    type_, payload, capture_id = fake_registry.commands[0]
    assert type_ == "capture_details"
    assert capture_id == CAPTURE_ID
    assert payload == {
        "ext_ids": ["ext-1", "ext-2"],
        "detail_limit": 10,
        "delay_ms": 2000,
    }
    assert "auto_next_page" not in payload


def test_create_capture_without_extension_returns_409(
    wired: tuple[FakeRegistry, FakeRepo],
) -> None:
    fake_registry, fake_repo = wired
    fake_registry.online = False

    response = TestClient(api_app, client=("127.0.0.1", 50000)).post(
        "/api/v1/captures", headers=AUTH, json={"kind": "list", "delay_ms": 1800}
    )

    assert response.status_code == 409
    assert response.json()["code"] == "EXTENSION_OFFLINE"
    assert fake_repo.completed[0]["status"] == "failed"


def test_abort_dispatches_abort_and_completes_batch(
    wired: tuple[FakeRegistry, FakeRepo],
) -> None:
    fake_registry, fake_repo = wired
    response = TestClient(api_app, client=("127.0.0.1", 50000)).post(
        f"/api/v1/captures/{CAPTURE_ID}/abort", headers=AUTH, json={"reason": "manual"}
    )

    assert response.status_code == 200
    type_, payload, capture_id = fake_registry.commands[0]
    assert type_ == "abort"
    assert payload == {"reason": "manual"}
    assert capture_id == CAPTURE_ID
    assert fake_repo.completed[0]["status"] == "aborted"


def test_abort_without_extension_returns_409(
    wired: tuple[FakeRegistry, FakeRepo],
) -> None:
    fake_registry, _ = wired
    fake_registry.online = False

    response = TestClient(api_app, client=("127.0.0.1", 50000)).post(
        f"/api/v1/captures/{CAPTURE_ID}/abort", headers=AUTH, json={}
    )

    assert response.status_code == 409


def test_delay_below_floor_is_rejected(
    wired: tuple[FakeRegistry, FakeRepo],
) -> None:
    fake_registry, _ = wired
    response = TestClient(api_app, client=("127.0.0.1", 50000)).post(
        "/api/v1/captures", headers=AUTH, json={"kind": "list", "delay_ms": 1000}
    )

    assert response.status_code == 422
    assert fake_registry.commands == []


def test_extension_status_endpoint(
    wired: tuple[FakeRegistry, FakeRepo],
) -> None:
    response = TestClient(api_app, client=("127.0.0.1", 50000)).get(
        "/api/v1/extension/status", headers=AUTH
    )

    assert response.status_code == 200
    assert response.json() == {"paired": False}


def test_capture_api_rejects_missing_token(
    wired: tuple[FakeRegistry, FakeRepo],
) -> None:
    response = TestClient(api_app, client=("127.0.0.1", 50000)).get(
        "/api/v1/extension/status"
    )
    assert response.status_code == 401
    assert response.json()["code"] == "PAIRING_TOKEN_INVALID"
    assert set(response.json()) == {"code", "message", "trace_id", "details"}


def test_capture_api_rejects_non_loopback(
    wired: tuple[FakeRegistry, FakeRepo],
) -> None:
    response = TestClient(api_app, client=("192.168.1.10", 50000)).get(
        "/api/v1/extension/status", headers=AUTH
    )
    assert response.status_code == 403
    assert response.json()["code"] == "LOOPBACK_ONLY"


def test_api_has_no_pairing_token_disclosure_route(
    wired: tuple[FakeRegistry, FakeRepo],
) -> None:
    response = TestClient(api_app, client=("127.0.0.1", 50000)).get(
        "/api/v1/extension/pairing-token", headers=AUTH
    )
    assert response.status_code == 404
