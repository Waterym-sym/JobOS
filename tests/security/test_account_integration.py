"""Destructive account integration test; only an empty disposable database."""

import os
from pathlib import Path
from urllib.parse import urlparse

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from services.api.app.bootstrap_admin import bootstrap
from services.api.app.main import api_app

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_ACCOUNT_INTEGRATION") != "1",
    reason="requires an empty disposable jobos_account_test database",
)


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["jobos_csrf"]}


def test_invite_login_private_profile_reset_upload_delete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = os.getenv("DATABASE_URL", "")
    if urlparse(url).path != "/jobos_account_test":
        pytest.fail("account integration is restricted to jobos_account_test")
    engine = sa.create_engine(url.replace("postgresql://", "postgresql+psycopg://", 1))
    try:
        if sa.inspect(engine).get_table_names():
            pytest.fail("account integration requires a completely empty database")
        monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
        config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
        command.upgrade(config, "head")
        bootstrap("admin@example.test", "a strong admin password 123")

        admin = TestClient(api_app, client=("127.0.0.1", 50101))
        assert admin.post("/api/v1/auth/login", json={
            "email": "admin@example.test", "password": "a strong admin password 123"
        }).status_code == 200

        accounts = []
        for index, role in enumerate(("seeker", "seeker", "recruiter")):
            invite_response = admin.post("/api/v1/auth/invitations", json={"role": role},
                                         headers=_csrf(admin))
            assert invite_response.status_code == 201
            invite = invite_response.json()["token"]
            email = f"person{index}@example.test"
            password = f"a strong user password {index}"
            client = TestClient(api_app, client=("127.0.0.1", 50200 + index))
            assert client.post("/api/v1/auth/register", json={
                "email": email, "password": password, "invite_token": invite,
            }).status_code == 201
            assert client.post("/api/v1/auth/register", json={
                "email": f"repeat{index}@example.test", "password": password,
                "invite_token": invite,
            }).status_code == 400
            assert client.post("/api/v1/auth/login", json={
                "email": email, "password": password,
            }).status_code == 200
            assert client.get("/api/v1/me").json()["role"] == role
            accounts.append((client, email, password))

        seeker_a, seeker_b, recruiter = (item[0] for item in accounts)
        assert seeker_a.put("/api/v1/me/profile", headers=_csrf(seeker_a), json={
            "display_name": "Alice", "basic": {"name": "Alice"},
            "education": {}, "job_preference": {}, "onboarding_step": "basic",
        }).status_code == 200
        assert seeker_a.get("/api/v1/me/profile").json()["basic"] == {"name": "Alice"}
        assert seeker_b.get("/api/v1/me/profile").json()["basic"] == {}
        assert recruiter.get("/api/v1/me/profile").json()["basic"] == {}
        assert seeker_b.put("/api/v1/me/profile", json={
            "basic": {}, "education": {}, "job_preference": {}, "onboarding_step": "entry"
        }).status_code == 403

        upload = seeker_a.post("/api/v1/me/resumes", headers=_csrf(seeker_a),
                               files={"file": ("resume.pdf", b"%PDF-1.4\nsynthetic", "application/pdf")})
        assert upload.status_code == 201
        with engine.connect() as conn:
            row = conn.execute(sa.text("SELECT user_id, storage_key FROM resume_file")).one()
        assert str(row.user_id) == seeker_a.get("/api/v1/me").json()["id"]
        assert (tmp_path / row.storage_key).exists()

        reset = admin.post("/api/v1/auth/password-resets", headers=_csrf(admin),
                           json={"email": accounts[1][1]})
        assert reset.status_code == 201
        assert seeker_b.post("/api/v1/auth/password-reset", json={
            "token": reset.json()["token"], "password": "new strong password 456"
        }).status_code == 204
        assert seeker_b.get("/api/v1/me").status_code == 401
        assert seeker_b.post("/api/v1/auth/login", json={
            "email": accounts[1][1], "password": "new strong password 456"
        }).status_code == 200

        assert admin.delete("/api/v1/me", headers=_csrf(admin)).status_code == 409
        assert seeker_a.delete("/api/v1/me", headers=_csrf(seeker_a)).status_code == 204
        assert not (tmp_path / row.storage_key).exists()
        assert seeker_a.get("/api/v1/me").status_code == 401
    finally:
        engine.dispose()
