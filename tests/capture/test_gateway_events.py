"""Event dispatch tests (protocol #21 §4): fakes the repo layer."""

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from services.api.app import ws_gateway
from services.api.app.event_models import EventEnvelope

NOW = datetime.now(UTC)


def run(coro: Any) -> Any:
    return asyncio.run(coro)


class FakeRepo:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.upserts: list[Any] = []
        self.progress: list[tuple[Any, Any]] = []
        self.completed: list[dict[str, Any]] = []
        monkeypatch.setattr(ws_gateway, "upsert_raw_job", self.upsert_raw_job)
        monkeypatch.setattr(ws_gateway, "mark_progress", self._mark_progress)
        monkeypatch.setattr(ws_gateway, "complete_batch", self._complete_batch)
        monkeypatch.setattr(ws_gateway, "reserve_event", self._reserve_event)
        monkeypatch.setattr(ws_gateway, "release_event", self._release_event)
        self.event_ids: set[Any] = set()

    async def upsert_raw_job(self, payload: Any) -> bool:
        self.upserts.append(payload)
        return True

    async def _mark_progress(self, capture_id: Any, progress: Any) -> None:
        self.progress.append((capture_id, progress))

    async def _complete_batch(self, capture_id: Any, **kwargs: Any) -> dict[str, Any]:
        record = {"capture_id": capture_id, **kwargs}
        self.completed.append(record)
        return kwargs.get("stats") or {}

    async def _reserve_event(self, event_id: Any, _type: str, _capture_id: Any) -> bool:
        if event_id in self.event_ids:
            return False
        self.event_ids.add(event_id)
        return True

    async def _release_event(self, event_id: Any) -> None:
        self.event_ids.discard(event_id)


def event_envelope(
    type_: str,
    payload: dict[str, Any],
    *,
    capture_id: Any = None,
) -> EventEnvelope:
    return EventEnvelope(
        v=1, kind="event", id=uuid4(), type=type_, payload=payload, capture_id=capture_id
    )


def list_job(ext_id: str = "ext-1", **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source": "boss",
        "ext_id": ext_id,
        "tier": "list",
        "title": "Python 工程师",
        "company": "Acme",
        "list_json": {"a": 1},
        "list_tags": ["经验不限"],
        "salary_text": "15-25K",
    }
    payload.update(extra)
    return payload


def test_job_captured_persists_raw_job(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = FakeRepo(monkeypatch)

    run(ws_gateway.handle_event(event_envelope("job.captured", list_job())))

    assert len(repo.upserts) == 1
    job = repo.upserts[0]
    assert job.ext_id == "ext-1"
    assert job.tier == "list"
    assert job.list_json == {"a": 1}


def test_duplicate_event_id_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = FakeRepo(monkeypatch)
    envelope = event_envelope("job.captured", list_job())
    run(ws_gateway.handle_event(envelope))
    run(ws_gateway.handle_event(envelope))
    assert len(repo.upserts) == 1


def test_job_updated_persists_raw_job(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = FakeRepo(monkeypatch)
    detail = list_job("ext-2", tier="detail", title=None, company=None)
    detail.pop("list_tags")
    detail.update(jd_text="JD 正文", detail_json={"b": 2}, skill_tags=["Python"])

    run(ws_gateway.handle_event(event_envelope("job.updated", detail)))

    assert repo.upserts[0].tier == "detail"
    assert repo.upserts[0].detail_json == {"b": 2}


def test_unknown_event_type_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeRepo(monkeypatch)
    with pytest.raises(ValueError, match="unknown event type"):
        run(ws_gateway.handle_event(event_envelope("nope.event", {})))


def test_phase_marks_progress(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = FakeRepo(monkeypatch)
    capture_id = uuid4()
    payload = {"phase": "list", "done": 5, "total": 30, "current": "ext-1"}

    run(
        ws_gateway.handle_event(
            event_envelope("capture.phase", payload, capture_id=capture_id)
        )
    )

    assert repo.progress == [(capture_id, payload)]


def test_phase_without_capture_id_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = FakeRepo(monkeypatch)
    payload = {"phase": "detail", "done": 1, "total": 3, "current": "ext-1"}

    run(ws_gateway.handle_event(event_envelope("capture.phase", payload)))

    assert repo.progress == []


def test_completed_completes_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = FakeRepo(monkeypatch)
    capture_id = uuid4()
    payload = {
        "capture_id": str(capture_id),
        "stats": {"success": 28, "dup": 2, "risk_halted": False},
        "finished_at": NOW.isoformat(),
    }

    run(
        ws_gateway.handle_event(
            event_envelope("capture.completed", payload, capture_id=capture_id)
        )
    )

    assert len(repo.completed) == 1
    record = repo.completed[0]
    assert record["capture_id"] == capture_id
    assert record["status"] == "completed"
    assert record["stats"] == {"success": 28, "dup": 2, "risk_halted": False}
    assert record["finished_at"] == NOW


def test_risk_error_halts_batch_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FakeRepo(monkeypatch)
    capture_id = uuid4()
    payload = {
        "code": "RISK_PAGE",
        "message": "账户存在异常",
        "recoverable": False,
        "risk": True,
    }

    run(
        ws_gateway.handle_event(
            event_envelope("capture.error", payload, capture_id=capture_id)
        )
    )

    # Exactly one terminal transition: risk_halted, no auto-retry.
    assert len(repo.completed) == 1
    record = repo.completed[0]
    assert record["status"] == "risk_halted"
    assert record["stats"] == {"success": 0, "dup": 0, "risk_halted": True}


def test_nonrisk_error_fails_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = FakeRepo(monkeypatch)
    capture_id = uuid4()
    payload = {
        "code": "LOGIN_EXPIRED",
        "message": "登录态失效",
        "recoverable": True,
        "risk": False,
    }

    run(
        ws_gateway.handle_event(
            event_envelope("capture.error", payload, capture_id=capture_id)
        )
    )

    assert repo.completed[0]["status"] == "failed"


def test_dispatch_rejects_non_dict() -> None:
    with pytest.raises(TypeError, match="JSON object"):
        run(ws_gateway.dispatch_message(["not", "an", "object"]))


def test_dispatch_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError, match="unexpected message kind"):
        run(
            ws_gateway.dispatch_message(
                {"v": 1, "kind": "command", "id": str(uuid4())}
            )
        )


def test_dispatch_accepts_receipt() -> None:
    # Receipts are audit-only and must not raise.
    run(
        ws_gateway.dispatch_message(
            {
                "v": 1,
                "kind": "receipt",
                "id": str(uuid4()),
                "type": "command.completed",
                "command_id": str(uuid4()),
            }
        )
    )
