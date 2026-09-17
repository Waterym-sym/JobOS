from ipaddress import ip_address
from pathlib import Path

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings with local-only and account-risk invariants."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host_bind: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    ws_port: int = Field(default=8788, ge=1, le=65535)
    pairing_token: SecretStr | None = None
    pairing_token_file: Path = Path("config/.local/pairing.token")
    container_mode: bool = False
    capture_min_delay_ms: int = Field(default=1800, ge=1800)
    # 红线：采集并发恒为 1（env 以字符串传入，Literal 不做 str→int 强转，故用区间约束表达恒 1）
    capture_concurrency: int = Field(default=1, ge=1, le=1)
    detail_limit_per_batch: int = Field(default=30, ge=1)
    database_url: str = "postgresql://jobos:jobos@127.0.0.1:5432/jobos"
    storage_dir: Path = Path("./data")
    chat_to_third_party: bool = False
    public_mode: bool = False
    web_origin: str = "http://127.0.0.1:4173"
    session_cookie_secure: bool = False

    @field_validator("host_bind")
    @classmethod
    def require_loopback(cls, value: str) -> str:
        if not ip_address(value).is_loopback:
            raise ValueError("HOST_BIND must be a loopback address")
        return value

    @model_validator(mode="after")
    def require_secure_public_edge(self) -> "Settings":
        if self.public_mode:
            raise ValueError("PUBLIC_MODE remains disabled until all legacy data paths have account isolation and security review")
        return self


def get_settings() -> Settings:
    return Settings()
