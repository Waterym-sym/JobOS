import hmac
import os
import secrets
from pathlib import Path


class PairingTokenStore:
    def __init__(self, token_file: Path, configured_token: str | None = None) -> None:
        self._token_file = token_file
        self._configured_token = configured_token.strip() if configured_token else None

    def load_or_create(self) -> str:
        if self._configured_token:
            return self._validate(self._configured_token)

        self._token_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._token_file.open("x", encoding="utf-8") as handle:
                token = secrets.token_urlsafe(32)
                handle.write(token)
            os.chmod(self._token_file, 0o600)
            return token
        except FileExistsError:
            return self._validate(self._token_file.read_text(encoding="utf-8").strip())

    def matches(self, candidate: str) -> bool:
        expected = self.load_or_create()
        return hmac.compare_digest(expected.encode(), candidate.encode())

    @staticmethod
    def _validate(token: str) -> str:
        if len(token) < 16:
            raise ValueError("Pairing token must contain at least 16 characters")
        return token
