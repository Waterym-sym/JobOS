import io
import sys
import zipfile

import pytest

from services.api.app import bootstrap_admin
from services.api.app.account_routes import AccountProblem, _resume_kind
from services.api.app.account_security import (
    digest_secret,
    hash_password,
    issue_secret,
    normalize_email,
    verify_password,
)


def test_password_hash_is_salted_and_rejects_wrong_password() -> None:
    first = hash_password("correct horse battery staple")
    second = hash_password("correct horse battery staple")
    assert first != second
    assert verify_password("correct horse battery staple", first)
    assert not verify_password("different password", first)
    assert not verify_password("correct horse battery staple", "bad hash")


def test_identity_normalization_and_secret_digest() -> None:
    assert normalize_email(" User@Example.COM ") == "user@example.com"
    first = issue_secret()
    second = issue_secret()
    assert first != second
    assert digest_secret(first) != digest_secret(second)


def test_resume_upload_rejects_disguised_zip_and_accepts_docx_structure() -> None:
    with pytest.raises(AccountProblem):
        _resume_kind("resume.docx", b"PK\x03\x04not-a-valid-document")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as package:
        package.writestr("[Content_Types].xml", "<Types/>")
        package.writestr("word/document.xml", "<document/>")
    assert _resume_kind("resume.docx", output.getvalue())[0] == "docx"


def test_bootstrap_cli_reports_short_password_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["bootstrap_admin", "--email", "admin@example.test"])
    monkeypatch.setattr(bootstrap_admin, "getpass", lambda _prompt: "short")
    with pytest.raises(SystemExit, match="password must contain 12-128 characters"):
        bootstrap_admin.main()
