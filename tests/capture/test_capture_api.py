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
        return {"paired": False, "instances": []}


class FakeRepo:
    def __init__(self) -> None:
        self.completed: list[dict[str, Any]] = []
        self.profiles: dict[str, dict[str, Any]] = {}
        self.companies: dict[str, dict[str, Any]] = {}
        self.pool_rows: list[dict[str, Any]] = []
        self.company_ids: set[str] = set()
        self.entries: dict[UUID, dict[str, Any]] = {}
        self.upserted: list[dict[str, Any]] = []
        self._upserted_ext_ids: set[str] = set()

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

    async def upsert_raw_job(self, job: Any) -> bool:
        self.upserted.append(
            {"ext_id": job.ext_id, "tier": job.tier, "batch_id": job.batch_id}
        )
        if job.ext_id in self._upserted_ext_ids:
            return False
        self._upserted_ext_ids.add(job.ext_id)
        return True

    async def get_job_profile(self, ext_id: str, source: str = "boss") -> dict[str, Any] | None:
        return self.profiles.get(ext_id)

    async def get_company_by_ext_id(
        self, ext_company_id: str, source: str = "boss"
    ) -> dict[str, Any] | None:
        return self.companies.get(ext_company_id)

    async def list_shortlist(self) -> list[dict[str, Any]]:
        return self.pool_rows

    async def list_company_ext_ids(self) -> set[str]:
        return self.company_ids

    async def list_screening_entries(
        self, *, status: str = "screened", limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        items = [entry for entry in self.entries.values() if entry["status"] == status]
        return items[offset : offset + limit]

    async def update_screening_entry_status(
        self, entry_id: UUID, *, to_status: str
    ) -> dict[str, Any] | None:
        entry = self.entries.get(entry_id)
        if entry is None:
            return None
        allowed = {"screened": {"candidate", "dismissed"}, "candidate": {"screened"}}
        if to_status not in allowed.get(entry["status"], set()):
            raise repo_mod.ScreeningTransitionInvalid(f"{entry['status']} -> {to_status}")
        entry["status"] = to_status
        return dict(entry)


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch) -> tuple[FakeRegistry, FakeRepo]:
    monkeypatch.setenv("PAIRING_TOKEN", TOKEN)
    fake_registry = FakeRegistry()
    fake_repo = FakeRepo()
    monkeypatch.setattr("services.api.app.main.registry", fake_registry)
    monkeypatch.setattr(repo_mod, "create_batch_run", fake_repo.create_batch_run)
    monkeypatch.setattr(repo_mod, "get_batch", fake_repo.get_batch)
    monkeypatch.setattr(repo_mod, "complete_batch", fake_repo.complete_batch)
    monkeypatch.setattr(repo_mod, "upsert_raw_job", fake_repo.upsert_raw_job)
    monkeypatch.setattr(repo_mod, "get_job_profile", fake_repo.get_job_profile)
    monkeypatch.setattr(repo_mod, "get_company_by_ext_id", fake_repo.get_company_by_ext_id)
    monkeypatch.setattr(repo_mod, "list_shortlist", fake_repo.list_shortlist)
    monkeypatch.setattr(repo_mod, "list_company_ext_ids", fake_repo.list_company_ext_ids)
    monkeypatch.setattr(repo_mod, "list_screening_entries", fake_repo.list_screening_entries)
    monkeypatch.setattr(
        repo_mod, "update_screening_entry_status", fake_repo.update_screening_entry_status
    )
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
    assert response.json() == {"paired": False, "instances": []}


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


# --------------------------------------------------------- job profile panel


def profile_job() -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "ext_id": "synth-job-0001",
        "title": "合成岗位一",
        "company": "合成科技有限公司",
        "city": "杭州",
        "district": "西湖区",
        "salary_text": "15-25K",
        "exp_text": "3-5年",
        "degree": "本科",
        "industry": "企业服务",
        "stage": "B轮",
        "scale": "100-499人",
        "address": "杭州市西湖区合成路 1 号",
        "boss_name": "合成招聘官",
        "active_time": "今日活跃",
        "skill_tags": ["React", "TypeScript"],
        "jd_text": "负责合成系统的前端开发。",
        "detail_at": NOW.isoformat(),
        "list_json": {
            "jobId": "synth-job-0001",
            "raw": {"encryptBrandId": "synthBrand0001~"},
        },
    }


def test_job_profile_reads_jd_and_linked_company(
    wired: tuple[FakeRegistry, FakeRepo],
) -> None:
    _registry, fake_repo = wired
    fake_repo.profiles["synth-job-0001"] = profile_job()
    fake_repo.companies["synthBrand0001~"] = {
        "ext_company_id": "synthBrand0001~",
        "name": "合成科技有限公司",
        "sections": {"intro": "合成公司简介"},
        "updated_at": NOW.isoformat(),
    }

    response = TestClient(api_app, client=("127.0.0.1", 50000)).get(
        "/api/v1/raw-jobs/synth-job-0001", headers=AUTH
    )

    assert response.status_code == 200
    body = response.json()
    assert body["job"]["jd_text"] == "负责合成系统的前端开发。"
    assert body["job"]["skill_tags"] == ["React", "TypeScript"]
    assert body["company"]["sections"] == {"intro": "合成公司简介"}
    # 导航数据只在本机内部推导公司主键，不出接口。
    assert "list_json" not in body["job"]


def test_job_profile_without_company_snapshot_returns_null_company(
    wired: tuple[FakeRegistry, FakeRepo],
) -> None:
    _registry, fake_repo = wired
    fake_repo.profiles["synth-job-0001"] = profile_job()

    response = TestClient(api_app, client=("127.0.0.1", 50000)).get(
        "/api/v1/raw-jobs/synth-job-0001", headers=AUTH
    )

    assert response.status_code == 200
    assert response.json()["company"] is None


def test_job_profile_unknown_ext_id_returns_404(
    wired: tuple[FakeRegistry, FakeRepo],
) -> None:
    response = TestClient(api_app, client=("127.0.0.1", 50000)).get(
        "/api/v1/raw-jobs/synth-job-missing", headers=AUTH
    )

    assert response.status_code == 404
    assert response.json()["code"] == "JOB_NOT_FOUND"


# ------------------------------------------------- extension list direct push


def pushed_job(ext_id: str, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source": "boss",
        "ext_id": ext_id,
        "tier": "list",
        "title": f"直传岗位 {ext_id}",
        "company": "直传科技有限公司",
        "salary_text": "15-25K",
        "list_json": {"encryptJobId": ext_id, "jobName": f"直传岗位 {ext_id}"},
        "captured_at": NOW.isoformat(),
    }
    payload.update(overrides)
    return payload


def test_post_raw_jobs_ingests_passively_without_dispatching_commands(
    wired: tuple[FakeRegistry, FakeRepo],
) -> None:
    fake_registry, fake_repo = wired

    response = TestClient(api_app, client=("127.0.0.1", 50000)).post(
        "/api/v1/raw-jobs",
        headers=AUTH,
        json={
            "source": "boss",
            "tier": "list",
            "jobs": [pushed_job("push-0001"), pushed_job("push-0002")],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "batch_id": str(CAPTURE_ID),
        "total": 2,
        "created": 2,
        "merged": 0,
        "invalid": [],
    }
    assert [row["ext_id"] for row in fake_repo.upserted] == ["push-0001", "push-0002"]
    assert all(row["batch_id"] == CAPTURE_ID for row in fake_repo.upserted)
    assert fake_repo.completed[0]["status"] == "completed"
    # Red line: list direct push is passive ingestion; it must never dispatch
    # capture_list/capture_details or any other extension command.
    assert fake_registry.commands == []


def test_post_raw_jobs_repeated_push_reports_merged(
    wired: tuple[FakeRegistry, FakeRepo],
) -> None:
    client = TestClient(api_app, client=("127.0.0.1", 50000))
    envelope = {"source": "boss", "tier": "list", "jobs": [pushed_job("push-0001")]}

    first = client.post("/api/v1/raw-jobs", headers=AUTH, json=envelope)
    second = client.post("/api/v1/raw-jobs", headers=AUTH, json=envelope)

    assert first.json()["created"] == 1
    assert second.json() == {
        "batch_id": str(CAPTURE_ID),
        "total": 1,
        "created": 0,
        "merged": 1,
        "invalid": [],
    }


def test_post_raw_jobs_reports_invalid_items_without_aborting(
    wired: tuple[FakeRegistry, FakeRepo],
) -> None:
    _fake_registry, fake_repo = wired

    response = TestClient(api_app, client=("127.0.0.1", 50000)).post(
        "/api/v1/raw-jobs",
        headers=AUTH,
        json={
            "source": "boss",
            "tier": "list",
            "jobs": [
                pushed_job("push-0001", title=""),
                {"source": "boss", "ext_id": "push-0002", "tier": "detail"},
                pushed_job("push-0003"),
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["created"] == 1
    assert [entry["index"] for entry in body["invalid"]] == [0, 1]
    assert [row["ext_id"] for row in fake_repo.upserted] == ["push-0003"]


def test_post_raw_jobs_rejects_bad_envelope(
    wired: tuple[FakeRegistry, FakeRepo],
) -> None:
    fake_registry, fake_repo = wired
    client = TestClient(api_app, client=("127.0.0.1", 50000))

    empty_jobs = client.post(
        "/api/v1/raw-jobs",
        headers=AUTH,
        json={"source": "boss", "tier": "list", "jobs": []},
    )
    assert empty_jobs.status_code == 422
    assert empty_jobs.json()["code"] == "PAYLOAD_INVALID"

    wrong_tier = client.post(
        "/api/v1/raw-jobs",
        headers=AUTH,
        json={"source": "boss", "tier": "detail", "jobs": [pushed_job("push-0001")]},
    )
    assert wrong_tier.status_code == 422

    extra_field = client.post(
        "/api/v1/raw-jobs",
        headers=AUTH,
        json={
            "source": "boss",
            "tier": "list",
            "jobs": [pushed_job("push-0001")],
            "extra": 1,
        },
    )
    assert extra_field.status_code == 422

    oversized = client.post(
        "/api/v1/raw-jobs",
        headers=AUTH,
        json={
            "source": "boss",
            "tier": "list",
            "jobs": [pushed_job(f"push-{i:04d}") for i in range(101)],
        },
    )
    assert oversized.status_code == 422

    # Rejected envelopes ingest nothing and still dispatch no commands.
    assert fake_repo.upserted == []
    assert fake_registry.commands == []


def test_post_raw_jobs_requires_pairing_token(
    wired: tuple[FakeRegistry, FakeRepo],
) -> None:
    response = TestClient(api_app, client=("127.0.0.1", 50000)).post(
        "/api/v1/raw-jobs",
        json={"source": "boss", "tier": "list", "jobs": [pushed_job("push-0001")]},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "PAIRING_TOKEN_INVALID"


# ------------------------------------------------------- pool state derivation


def pool_row(raw_job_id: UUID, *, detail_at: Any, jd_text: str | None) -> dict[str, Any]:
    return {
        "id": uuid4(),
        "raw_job_id": raw_job_id,
        "ext_id": "synth-job-0001",
        "title": "合成岗位一",
        "company": "合成科技有限公司",
        "city": "杭州",
        "salary_text": "15-25K",
        "status": "confirmed",
        "note": None,
        "added_at": NOW,
        "detail_at": detail_at,
        "list_json": {"raw": {"encryptBrandId": "synthBrand0001~"}},
        "jd_text": jd_text,
    }


def test_pool_states_ignore_the_paused_queue(
    wired: tuple[FakeRegistry, FakeRepo],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """队列暂停只属于队列：岗位状态继续按数据推导（需求 1 的回归锚点）。"""
    monkeypatch.setattr("services.api.app.enrich.is_paused", lambda: True)
    _registry, fake_repo = wired
    done_id = uuid4()
    detail_only_id = uuid4()
    fake_repo.company_ids = {"synthBrand0001~"}
    fake_repo.pool_rows = [
        pool_row(done_id, detail_at=NOW, jd_text="合成 JD"),
        pool_row(detail_only_id, detail_at=NOW, jd_text=None),
    ]

    response = TestClient(api_app, client=("127.0.0.1", 50000)).get(
        "/api/v1/shortlist", headers=AUTH
    )

    assert response.status_code == 200
    states = [item["enrich_state"] for item in response.json()]
    assert states == ["done", "pending"]
    assert "paused" not in states


# ------------------------------------------------------------ screening pool


def screening_entry(entry_id: UUID, *, status: str = "screened") -> dict[str, Any]:
    return {
        "id": str(entry_id),
        "raw_job_id": str(uuid4()),
        "ext_id": "synth-job-0001",
        "title": "合成岗位一",
        "company": "合成科技有限公司",
        "city": "杭州",
        "salary_text": "15-25K",
        "status": status,
        "entered_at": NOW.isoformat(),
    }


def screening_url(entry_id: UUID, action: str) -> str:
    return f"/api/v1/screening-entries/{entry_id}/{action}"


def test_screening_entries_list_defaults_to_the_screening_pool(
    wired: tuple[FakeRegistry, FakeRepo],
) -> None:
    _registry, fake_repo = wired
    screened_id, candidate_id = uuid4(), uuid4()
    fake_repo.entries[screened_id] = screening_entry(screened_id)
    fake_repo.entries[candidate_id] = screening_entry(candidate_id, status="candidate")

    response = TestClient(api_app, client=("127.0.0.1", 50000)).get(
        "/api/v1/screening-entries", headers=AUTH
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["items"]] == [str(screened_id)]
    assert body["limit"] == 50
    assert body["offset"] == 0


def test_screening_entry_promote_and_revert_are_human_transitions(
    wired: tuple[FakeRegistry, FakeRepo],
) -> None:
    _registry, fake_repo = wired
    entry_id = uuid4()
    fake_repo.entries[entry_id] = screening_entry(entry_id)
    client = TestClient(api_app, client=("127.0.0.1", 50000))

    promoted = client.post(screening_url(entry_id, "promote"), headers=AUTH)
    assert promoted.status_code == 200
    assert promoted.json()["status"] == "candidate"

    in_candidates = client.get("/api/v1/screening-entries?status=candidate", headers=AUTH)
    assert [item["id"] for item in in_candidates.json()["items"]] == [str(entry_id)]

    reverted = client.post(screening_url(entry_id, "revert"), headers=AUTH)
    assert reverted.status_code == 200
    assert reverted.json()["status"] == "screened"


def test_screening_entry_dismiss_is_terminal(
    wired: tuple[FakeRegistry, FakeRepo],
) -> None:
    _registry, fake_repo = wired
    entry_id = uuid4()
    fake_repo.entries[entry_id] = screening_entry(entry_id)
    client = TestClient(api_app, client=("127.0.0.1", 50000))

    dismissed = client.post(screening_url(entry_id, "dismiss"), headers=AUTH)
    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "dismissed"

    # 终态：不能从 dismissed 再推进，也不能退回。
    again = client.post(screening_url(entry_id, "promote"), headers=AUTH)
    assert again.status_code == 409
    assert again.json()["code"] == "SCREENING_TRANSITION_INVALID"


def test_screening_entry_unknown_id_returns_404(
    wired: tuple[FakeRegistry, FakeRepo],
) -> None:
    response = TestClient(api_app, client=("127.0.0.1", 50000)).post(
        screening_url(uuid4(), "promote"), headers=AUTH
    )

    assert response.status_code == 404
    assert response.json()["code"] == "SCREENING_ENTRY_NOT_FOUND"
