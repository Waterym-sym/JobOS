import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from services.api.app.config import Settings
from services.api.app.registry import ALLOWED_COMMANDS, ExtensionRegistry

ROOT = Path(__file__).resolve().parents[2]


def test_runtime_defaults_keep_account_risk_limits() -> None:
    settings = Settings(_env_file=None)
    assert settings.host_bind == "127.0.0.1"
    assert settings.capture_min_delay_ms >= 1800
    assert settings.capture_concurrency == 1
    assert settings.chat_to_third_party is False


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.20", "8.8.8.8"])
def test_non_loopback_bind_is_rejected(host: str) -> None:
    with pytest.raises(ValidationError):
        Settings(host_bind=host, _env_file=None)


def test_risk_limits_cannot_be_relaxed() -> None:
    with pytest.raises(ValidationError):
        Settings(capture_min_delay_ms=1799, _env_file=None)
    with pytest.raises(ValidationError):
        Settings(capture_concurrency=2, _env_file=None)


def test_compose_publishes_only_to_loopback() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    published_lines = [line.strip() for line in compose.splitlines() if "${HOST_BIND" in line]
    assert published_lines
    assert all("127.0.0.1" in line for line in published_lines)


def test_command_registry_contains_only_frozen_safe_command_set() -> None:
    assert {
        "capture_list",
        "capture_details",
        "abort",
        "fill_online_resume",
        "copy_greeting",
        "capture_chat",
    } == ALLOWED_COMMANDS
    assert not {
        "send_message",
        "deliver",
        "auto_apply",
        "auto_greet",
        "auto_next_page",
        "auto_upload",
    } & ALLOWED_COMMANDS


def test_forbidden_command_cannot_be_dispatched() -> None:
    registry = ExtensionRegistry()
    with pytest.raises(ValueError, match="not registered"):
        asyncio.run(registry.send_command("send_message", {}))


def test_browser_bundle_has_no_pairing_token_fetcher() -> None:
    browser_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "apps" / "web" / "src").rglob("*")
        if path.suffix in {".ts", ".tsx"}
    )
    assert "extension/pairing-token" not in browser_sources
    assert "fetchPairingToken" not in browser_sources
