import logging
import stat
from pathlib import Path

from fastapi.testclient import TestClient

from services.api.app.main import gateway_app
from services.api.app.pairing import PairingTokenStore
from services.api.app.ws_gateway import is_allowed_origin, is_local_peer, uuid7

TOKEN = "synthetic-pairing-token-00000001"
ORIGIN = "chrome-extension://abcdefghijklmnopabcdefghijklmnop"


def ping(token: str = TOKEN, protocol_version: int = 1) -> dict[str, object]:
    return {
        "v": 1,
        "kind": "handshake",
        "id": "01993f9c-4c00-7000-8000-000000000001",
        "type": "auth_ping",
        "payload": {
            "token": token,
            "extension_version": "0.1.0",
            "protocol_version": protocol_version,
        },
    }


def client() -> TestClient:
    return TestClient(gateway_app, client=("127.0.0.1", 50000))


def test_pairing_token_is_created_with_private_permissions(tmp_path: Path) -> None:
    token_path = tmp_path / "config" / "pairing.token"
    token = PairingTokenStore(token_path).load_or_create()

    assert len(token) >= 32
    assert token_path.read_text(encoding="utf-8") == token
    assert stat.S_IMODE(token_path.stat().st_mode) == 0o600


def test_valid_pairing_completes_handshake(monkeypatch) -> None:
    monkeypatch.setenv("PAIRING_TOKEN", TOKEN)
    with client().websocket_connect("/ws", headers={"origin": ORIGIN}) as websocket:
        websocket.send_json(ping())
        response = websocket.receive_json()

    assert response["kind"] == "handshake"
    assert response["type"] == "auth_pong"
    assert response["payload"]["supported"] is True
    assert response["payload"]["min_version"] == 1


def test_invalid_token_is_rejected_without_logging_secret(monkeypatch, caplog) -> None:
    monkeypatch.setenv("PAIRING_TOKEN", TOKEN)
    attempted = "synthetic-invalid-token-00000001"
    with (
        caplog.at_level(logging.INFO, logger="jobos.ws"),
        client().websocket_connect("/ws", headers={"origin": ORIGIN}) as websocket,
    ):
        websocket.send_json(ping(token=attempted))
        response = websocket.receive_json()

    assert response["code"] == "PAIRING_TOKEN_INVALID"
    assert attempted not in caplog.text
    assert TOKEN not in caplog.text


def test_protocol_mismatch_returns_unsupported_pong(monkeypatch) -> None:
    monkeypatch.setenv("PAIRING_TOKEN", TOKEN)
    with client().websocket_connect("/ws", headers={"origin": ORIGIN}) as websocket:
        websocket.send_json(ping(protocol_version=2))
        response = websocket.receive_json()

    assert response["type"] == "auth_pong"
    assert response["payload"] == {"supported": False, "min_version": 1}


def test_business_message_cannot_bypass_handshake(monkeypatch) -> None:
    monkeypatch.setenv("PAIRING_TOKEN", TOKEN)
    with client().websocket_connect("/ws", headers={"origin": ORIGIN}) as websocket:
        websocket.send_json(
            {"v": 1, "kind": "event", "id": "trace-004", "type": "capture.phase", "payload": {}}
        )
        response = websocket.receive_json()

    assert response["code"] == "PAIRING_TOKEN_INVALID"


def test_origin_and_peer_guards() -> None:
    assert is_allowed_origin(ORIGIN)
    assert not is_allowed_origin(None)
    assert not is_allowed_origin("http://127.0.0.1:4173")
    assert not is_allowed_origin("chrome-extension://invalid")
    assert not is_allowed_origin(f"{ORIGIN}:8788")
    assert not is_allowed_origin(f"{ORIGIN}:invalid")
    assert is_local_peer("127.0.0.1", container_mode=False)
    assert not is_local_peer("192.168.1.2", container_mode=False)
    assert is_local_peer("172.18.0.1", container_mode=True)


def test_server_message_ids_are_uuid7() -> None:
    assert uuid7().split("-")[2].startswith("7")
