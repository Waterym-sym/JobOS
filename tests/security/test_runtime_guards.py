from pathlib import Path

import pytest
from pydantic import ValidationError

from services.api.app.config import Settings

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
