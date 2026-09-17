"""Enrich queue behaviour: navigation mapping, serialization, risk pause.

The worker is exercised with a fake repo + fake extension so the assertions are
about pacing/serialization/red-line halting, not about the database.
"""

import asyncio
import time
from typing import Any
from uuid import UUID, uuid4

import pytest

from services.api.app import capture_repo, enrich

SAMPLE_ITEM = {
    "jobId": "synth-job-0001",
    "companyUrl": "https://www.zhipin.com/gongsi/synthBrand0001~.html",
    "securityId": "synthSecurityId0001",
    "raw": {"encryptJobId": "synth-job-0001", "encryptBrandId": "synthBrand0001~"},
}


def run(coro: Any) -> Any:
    return asyncio.run(coro)


async def wait_until(predicate: Any, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return False


class FakeRepo:
    """In-memory stand-in for capture_repo (same coroutine signatures)."""

    def __init__(self, jobs: dict[UUID, dict[str, Any]]) -> None:
        self.jobs = jobs
        self.detail_at: dict[UUID, Any] = {}
        self.jd_text: dict[UUID, str] = {}
        self.companies: set[str] = set()
        self.batches: dict[UUID, dict[str, Any]] = {}
        self.subscribers: list[Any] = []
        self.pool: dict[UUID, str] = {raw_job_id: "confirmed" for raw_job_id in jobs}
        # 筛选池流转：集合即幂等（一个岗位一条）。
        self.screening: set[UUID] = set()
        self.screening_error = False

    async def create_screening_entry(self, raw_job_id: UUID) -> bool:
        if self.screening_error:
            raise RuntimeError("screening write failed")
        if raw_job_id in self.screening:
            return False
        self.screening.add(raw_job_id)
        return True

    async def create_batch_run(self, *, kind: str, trigger: str, **_: Any) -> UUID:
        batch_id = uuid4()
        self.batches[batch_id] = {"kind": kind, "trigger": trigger}
        return batch_id

    async def complete_batch(
        self, capture_id: UUID, *, status: str = "completed", stats: Any = None, **_: Any
    ) -> dict[str, Any]:
        final = dict(stats or {})
        for subscriber in list(self.subscribers):
            subscriber(capture_id, status, final)
        return final

    def subscribe_batch_done(self, fn: Any) -> None:
        self.subscribers.append(fn)

    def subscribe_progress(self, _fn: Any) -> None:
        return None

    async def get_raw_job_for_enrich(self, raw_job_id: UUID) -> dict[str, Any] | None:
        meta = self.jobs.get(raw_job_id)
        if meta is None:
            return None
        return {
            "id": raw_job_id,
            "ext_id": meta["ext_id"],
            "title": meta["title"],
            "detail_at": self.detail_at.get(raw_job_id),
            "list_json": meta["list_json"],
            "jd_text": self.jd_text.get(raw_job_id),
        }

    async def get_pool_status(self, raw_job_id: UUID) -> str | None:
        return self.pool.get(raw_job_id)

    async def list_company_ext_ids(self) -> set[str]:
        return set(self.companies)

    async def list_shortlist(self) -> list[dict[str, Any]]:
        return []


class FakeExtension:
    """Emulates the paired bridge: one command at a time, async completion."""

    def __init__(self, repo: FakeRepo, *, risk: bool = False) -> None:
        self.repo = repo
        self.risk = risk
        self.commands: list[tuple[str, dict[str, Any], UUID]] = []
        self.in_flight = 0
        self.peak_in_flight = 0
        self.offline = False
        self.ever_capable = False
        self.fail_command: str | None = None
        self.connect_subscribers: list[Any] = []

    def subscribe_connected(self, fn: Any) -> None:
        self.connect_subscribers.append(fn)

    def notify_connected(self) -> None:
        for subscriber in list(self.connect_subscribers):
            subscriber()

    def current(self) -> Any:
        return None if self.offline else "instance"

    def capable(self, capability: str) -> bool:
        return not self.offline and capability in {"capture_details_urls", "capture_company"}

    def was_capable(self, capability: str) -> bool:
        return self.ever_capable

    async def send_command(
        self, type_: str, payload: dict[str, Any], *, capture_id: UUID | None = None
    ) -> str:
        assert capture_id is not None
        self.in_flight += 1
        self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
        self.commands.append((type_, payload, capture_id))
        asyncio.get_running_loop().create_task(self._finish(type_, payload, capture_id))
        return "command-id"

    async def _finish(self, type_: str, payload: dict[str, Any], capture_id: UUID) -> None:
        try:
            await asyncio.sleep(0.02)
            if self.risk and type_ == "capture_company":
                await self.repo.complete_batch(
                    capture_id,
                    status="risk_halted",
                    stats={"success": 0, "dup": 0, "risk_halted": True},
                )
                return
            if self.fail_command == type_:
                await self.repo.complete_batch(
                    capture_id, status="failed", stats={"reason": "extract empty"}
                )
                return
            if type_ == "capture_details":
                for target in payload["urls"]:
                    raw_job_id = _RAW_JOB_BY_EXT[target["ext_id"]]
                    self.repo.detail_at[raw_job_id] = "now"
                    self.repo.jd_text[raw_job_id] = "合成 JD 正文"
            elif type_ == "capture_company":
                self.repo.companies.add(payload["ext_company_id"])
            await self.repo.complete_batch(
                capture_id,
                status="completed",
                stats={"success": 1, "dup": 0, "risk_halted": False},
            )
        finally:
            self.in_flight -= 1


_RAW_JOB_BY_EXT: dict[str, UUID] = {}


@pytest.fixture(autouse=True)
def clean_enrich_state() -> Any:
    enrich._pending.clear()
    enrich._queued.clear()
    enrich._failed.clear()
    enrich._running = None
    enrich._running_stage = None
    enrich._paused = False
    enrich._paused_reason = None
    yield


def wire(
    monkeypatch: pytest.MonkeyPatch,
    ext_ids: list[str],
    *,
    shared_brand: bool = False,
) -> tuple[FakeRepo, FakeExtension]:
    jobs: dict[UUID, dict[str, Any]] = {}
    _RAW_JOB_BY_EXT.clear()
    for index, ext_id in enumerate(ext_ids, start=1):
        brand = "synthBrand0001~" if shared_brand else f"synthBrand{index:04d}~"
        raw_job_id = uuid4()
        jobs[raw_job_id] = {
            "ext_id": ext_id,
            "title": f"合成岗位{index}",
            "list_json": {
                "jobId": ext_id,
                "companyUrl": f"https://www.zhipin.com/gongsi/{brand}.html",
                "securityId": f"synthSecurityId{index:04d}",
                "raw": {"encryptJobId": ext_id, "encryptBrandId": brand},
            },
        }
        _RAW_JOB_BY_EXT[ext_id] = raw_job_id
    repo = FakeRepo(jobs)
    extension = FakeExtension(repo)
    monkeypatch.setattr(capture_repo, "create_batch_run", repo.create_batch_run)
    monkeypatch.setattr(capture_repo, "complete_batch", repo.complete_batch)
    monkeypatch.setattr(capture_repo, "subscribe_batch_done", repo.subscribe_batch_done)
    monkeypatch.setattr(capture_repo, "subscribe_progress", repo.subscribe_progress)
    monkeypatch.setattr(capture_repo, "get_raw_job_for_enrich", repo.get_raw_job_for_enrich)
    monkeypatch.setattr(capture_repo, "get_pool_status", repo.get_pool_status)
    monkeypatch.setattr(capture_repo, "list_company_ext_ids", repo.list_company_ext_ids)
    monkeypatch.setattr(capture_repo, "list_shortlist", repo.list_shortlist)
    monkeypatch.setattr(capture_repo, "create_screening_entry", repo.create_screening_entry)
    monkeypatch.setattr(enrich, "registry", extension)
    monkeypatch.setattr(enrich, "BATCH_TIMEOUT_S", 5.0)
    return repo, extension


async def drain_queue() -> None:
    await wait_until(lambda: not enrich._pending and enrich._running is None)


def job_id(ext_id: str) -> UUID:
    return _RAW_JOB_BY_EXT[ext_id]


# ------------------------------------------------------------------ mapping


def test_navigation_builds_boss_urls_from_the_preserved_item() -> None:
    nav = enrich._navigation(SAMPLE_ITEM)

    assert nav["detail_url"] == (
        "https://www.zhipin.com/job_detail/synth-job-0001.html?securityId=synthSecurityId0001"
    )
    assert nav["company_url"] == "https://www.zhipin.com/gongsi/synthBrand0001~.html"
    assert nav["ext_company_id"] == "synthBrand0001~"


def test_navigation_omits_security_id_when_absent() -> None:
    nav = enrich._navigation({"jobId": "j1", "raw": {"encryptJobId": "j1"}})

    assert nav["detail_url"] == "https://www.zhipin.com/job_detail/j1.html"
    assert nav["security_id"] is None


def test_navigation_refuses_foreign_company_hosts() -> None:
    nav = enrich._navigation(
        {
            "companyUrl": "https://evil.example.com/gongsi/synthBrand0001~.html",
            "raw": {"encryptBrandId": "synthBrand0001~"},
        }
    )

    assert nav["company_url"] is None


def test_navigation_builds_urls_from_flat_direct_push_card() -> None:
    # mapListJob preserves the Vue card verbatim: ids at top level, no raw/links.
    nav = enrich._navigation(
        {
            "encryptJobId": "flatJob0001",
            "securityId": "flatSecurity0001",
            "encryptBrandId": "flatBrand0001~",
            "jobName": "电子工程师",
        }
    )

    assert nav["detail_url"] == (
        "https://www.zhipin.com/job_detail/flatJob0001.html?securityId=flatSecurity0001"
    )
    assert nav["security_id"] == "flatSecurity0001"
    assert nav["company_url"] == "https://www.zhipin.com/gongsi/flatBrand0001~.html"
    assert nav["ext_company_id"] == "flatBrand0001~"


def test_navigation_flat_card_without_brand_has_no_company_link() -> None:
    nav = enrich._navigation({"encryptJobId": "flatJob0002", "securityId": "s2"})

    assert nav["detail_url"] == "https://www.zhipin.com/job_detail/flatJob0002.html?securityId=s2"
    assert nav["company_url"] is None
    assert nav["ext_company_id"] is None


def test_navigation_flat_card_without_job_id_has_no_detail_link() -> None:
    nav = enrich._navigation({"encryptBrandId": "flatBrand0002"})

    assert nav["detail_url"] is None
    assert nav["company_url"] == "https://www.zhipin.com/gongsi/flatBrand0002.html"


def test_navigation_flat_card_rejects_brand_id_with_path_characters() -> None:
    # A card-derived id must never inject path/query parts into the built URL.
    nav = enrich._navigation(
        {"encryptJobId": "j", "encryptBrandId": "x/../../evil"}
    )

    assert nav["company_url"] is None
    assert nav["ext_company_id"] is None


def test_navigation_flat_card_sanitises_job_and_security_tokens() -> None:
    nav = enrich._navigation(
        {"encryptJobId": "j/../x", "securityId": "a&evil=1"}
    )

    assert nav["detail_url"] is None
    assert nav["security_id"] is None


def test_navigation_envelope_brand_id_never_bypasses_foreign_url_redline() -> None:
    # Even with a usable brand id, the envelope branch must not construct a
    # canonical URL when the supplied link points off-host.
    nav = enrich._navigation(
        {
            "jobId": "j1",
            "companyUrl": "https://evil.example.com/gongsi/b1.html",
            "raw": {"encryptJobId": "j1", "encryptBrandId": "b1"},
        }
    )

    assert nav["company_url"] is None


class _BlockedStatusStub:
    def __init__(self, *, current: Any, capable: bool, was_capable: bool) -> None:
        self._current = current
        self._capable = capable
        self._was_capable = was_capable

    def current(self) -> Any:
        return self._current

    def capable(self, capability: str) -> bool:
        return self._capable

    def was_capable(self, capability: str) -> bool:
        return self._was_capable


def test_blocked_reason_is_silent_without_work(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(enrich, "registry", _BlockedStatusStub(current="x", capable=True, was_capable=True))
    assert enrich._blocked_reason(has_work=False) is None


def test_blocked_reason_reports_unpaired_when_no_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(enrich, "registry", _BlockedStatusStub(current=None, capable=False, was_capable=False))
    assert "扩展未配对" in enrich._blocked_reason(has_work=True)


def test_blocked_reason_guides_install_when_pool_bridge_never_paired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(enrich, "registry", _BlockedStatusStub(current="list", capable=False, was_capable=False))
    reason = enrich._blocked_reason(has_work=True)
    assert reason is not None
    assert "不具备按 URL 补全" in reason
    assert "岗位池补全桥" in reason


def test_blocked_reason_says_reconnecting_when_capability_was_seen_before(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # MV3 sleep gap: list bridge still online, pool bridge momentarily away.
    monkeypatch.setattr(enrich, "registry", _BlockedStatusStub(current="list", capable=False, was_capable=True))
    reason = enrich._blocked_reason(has_work=True)
    assert reason is not None
    assert "正在重连" in reason
    assert "自动继续" in reason


def test_blocked_reason_is_silent_when_capable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(enrich, "registry", _BlockedStatusStub(current="pool", capable=True, was_capable=True))
    assert enrich._blocked_reason(has_work=True) is None


def test_inter_stage_delay_jitters_upward_only(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        recorded.append(seconds)

    monkeypatch.setattr(enrich.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(enrich.random, "uniform", lambda low, high: high)
    run(enrich._inter_stage_delay())
    monkeypatch.setattr(enrich.random, "uniform", lambda low, high: low)
    run(enrich._inter_stage_delay())

    # Never below the 1800ms floor; jitter only extends the interval.
    assert recorded == [pytest.approx(2.16), pytest.approx(1.8)]


# ------------------------------------------------------------------ worker


def test_queue_runs_detail_then_company_serially(monkeypatch: pytest.MonkeyPatch) -> None:
    repo, extension = wire(monkeypatch, ["synth-job-0001", "synth-job-0002"])
    monkeypatch.setattr(enrich, "_inter_stage_delay", _no_delay)

    async def scenario() -> None:
        await enrich.start()
        try:
            enrich.enqueue(job_id("synth-job-0001"))
            enrich.enqueue(job_id("synth-job-0002"))
            await drain_queue()
        finally:
            await enrich.stop()

    run(scenario())

    assert [command[0] for command in extension.commands] == [
        "capture_details",
        "capture_company",
        "capture_details",
        "capture_company",
    ]
    # Concurrency is 1: the second job never overlaps the first.
    assert extension.peak_in_flight == 1
    assert extension.commands[0][1]["delay_ms"] >= 1800
    assert extension.commands[0][1]["detail_limit"] == 1
    assert extension.commands[0][1]["urls"][0]["ext_id"] == "synth-job-0001"
    assert extension.commands[1][1]["company_url"].startswith("https://www.zhipin.com/")
    assert extension.commands[1][1]["ext_company_id"] == "synthBrand0001~"
    assert repo.companies == {"synthBrand0001~", "synthBrand0002~"}


def test_shared_company_page_is_captured_once(monkeypatch: pytest.MonkeyPatch) -> None:
    repo, extension = wire(monkeypatch, ["synth-job-0001", "synth-job-0002"], shared_brand=True)
    monkeypatch.setattr(enrich, "_inter_stage_delay", _no_delay)

    async def scenario() -> None:
        await enrich.start()
        try:
            enrich.enqueue(job_id("synth-job-0001"))
            enrich.enqueue(job_id("synth-job-0002"))
            await drain_queue()
        finally:
            await enrich.stop()

    run(scenario())

    # One /gongsi/ open for both jobs: the company snapshot is shared.
    assert [command[0] for command in extension.commands] == [
        "capture_details",
        "capture_company",
        "capture_details",
    ]
    assert repo.companies == {"synthBrand0001~"}


def test_existing_pool_entries_are_rebuilt_on_start(monkeypatch: pytest.MonkeyPatch) -> None:
    repo, extension = wire(monkeypatch, ["synth-job-0001"])
    monkeypatch.setattr(enrich, "_inter_stage_delay", _no_delay)
    raw_job_id = job_id("synth-job-0001")

    async def scenario() -> None:
        async def list_shortlist() -> list[dict[str, Any]]:
            return [{"raw_job_id": raw_job_id}]

        monkeypatch.setattr(capture_repo, "list_shortlist", list_shortlist)
        await enrich.start()
        try:
            await drain_queue()
        finally:
            await enrich.stop()

    run(scenario())

    assert [command[0] for command in extension.commands] == [
        "capture_details",
        "capture_company",
    ]


def test_risk_halt_pauses_until_manual_resume(monkeypatch: pytest.MonkeyPatch) -> None:
    _repo, extension = wire(monkeypatch, ["synth-job-0001"])
    extension.risk = True
    monkeypatch.setattr(enrich, "_inter_stage_delay", _no_delay)
    raw_job_id = job_id("synth-job-0001")

    async def scenario() -> None:
        await enrich.start()
        try:
            enrich.enqueue(raw_job_id)
            assert await wait_until(lambda: enrich.is_paused())
            # While paused nothing else is dispatched: no auto-retry.
            await asyncio.sleep(0.1)
            assert len(extension.commands) == 2

            extension.risk = False
            await enrich.resume()
            await drain_queue()
        finally:
            await enrich.stop()

    run(scenario())

    assert enrich.is_paused() is False
    # resume retried the company stage (detail was already persisted).
    assert [command[0] for command in extension.commands] == [
        "capture_details",
        "capture_company",
        "capture_company",
    ]


def test_offline_extension_parks_without_issuing_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _repo, extension = wire(monkeypatch, ["synth-job-0001"])
    extension.offline = True
    raw_job_id = job_id("synth-job-0001")

    async def scenario() -> None:
        await enrich.start()
        try:
            enrich.enqueue(raw_job_id)
            # Parked: the entry stays at the head of the queue, nothing is sent
            # and nothing is retried on a timer.
            assert await wait_until(lambda: enrich._running is None and bool(enrich._pending))
            await asyncio.sleep(0.15)
            assert extension.commands == []
            assert enrich.failure(raw_job_id) is None

            # Pairing a capable extension wakes the queue exactly once.
            extension.offline = False
            extension.notify_connected()
            await drain_queue()
        finally:
            await enrich.stop()

    run(scenario())

    assert [command[0] for command in extension.commands] == [
        "capture_details",
        "capture_company",
    ]
    assert enrich.failure(raw_job_id) is None


def test_failed_entry_is_recorded_once_and_leaves_the_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _repo, extension = wire(monkeypatch, ["synth-job-0001", "synth-job-0002"])
    extension.fail_command = "capture_details"
    monkeypatch.setattr(enrich, "_inter_stage_delay", _no_delay)
    first = job_id("synth-job-0001")

    async def scenario() -> None:
        await enrich.start()
        try:
            enrich.enqueue(first)
            enrich.enqueue(job_id("synth-job-0002"))
            await drain_queue()
        finally:
            await enrich.stop()

    run(scenario())

    # One detail attempt for the failing entry — no retry loop — and the next
    # entry still gets processed. The extension's own message is kept.
    assert [command[0] for command in extension.commands] == [
        "capture_details",
        "capture_details",
    ]
    assert enrich.failure(first) == "failed: extract empty"
    assert first not in enrich._pending

    async def retry() -> None:
        await enrich.start()
        try:
            await enrich.resume()
            await drain_queue()
        finally:
            await enrich.stop()

    extension.fail_command = None
    run(retry())

    # Human resume is the only retry path.
    assert enrich.failure(first) is None
    assert extension.commands[-2][0] == "capture_details"


def test_entry_removed_from_the_pool_is_dropped_silently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, extension = wire(monkeypatch, ["synth-job-0001"])
    monkeypatch.setattr(enrich, "_inter_stage_delay", _no_delay)
    raw_job_id = job_id("synth-job-0001")
    repo.pool[raw_job_id] = "removed"

    async def scenario() -> None:
        await enrich.start()
        try:
            enrich.enqueue(raw_job_id)
            await drain_queue()
        finally:
            await enrich.stop()

    run(scenario())

    assert extension.commands == []
    assert enrich.failure(raw_job_id) is None
    assert raw_job_id not in enrich._pending


# ------------------------------------------------------------ screening flow


def test_completed_entry_flows_into_the_screening_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    repo, extension = wire(monkeypatch, ["synth-job-0001", "synth-job-0002"])
    monkeypatch.setattr(enrich, "_inter_stage_delay", _no_delay)

    async def scenario() -> None:
        await enrich.start()
        try:
            enrich.enqueue(job_id("synth-job-0001"))
            enrich.enqueue(job_id("synth-job-0002"))
            await drain_queue()
        finally:
            await enrich.stop()

    run(scenario())

    # 只有补全完成的岗位流转；队列仍是串行的。
    assert repo.screening == {job_id("synth-job-0001"), job_id("synth-job-0002")}
    assert extension.peak_in_flight == 1


def test_failed_entry_never_reaches_the_screening_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    repo, extension = wire(monkeypatch, ["synth-job-0001"])
    extension.fail_command = "capture_details"
    monkeypatch.setattr(enrich, "_inter_stage_delay", _no_delay)

    async def scenario() -> None:
        await enrich.start()
        try:
            enrich.enqueue(job_id("synth-job-0001"))
            await drain_queue()
        finally:
            await enrich.stop()

    run(scenario())

    assert repo.screening == set()
    assert enrich.failure(job_id("synth-job-0001")) is not None


def test_screening_write_failure_does_not_break_the_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, extension = wire(monkeypatch, ["synth-job-0001", "synth-job-0002"])
    repo.screening_error = True
    monkeypatch.setattr(enrich, "_inter_stage_delay", _no_delay)

    async def scenario() -> None:
        await enrich.start()
        try:
            enrich.enqueue(job_id("synth-job-0001"))
            enrich.enqueue(job_id("synth-job-0002"))
            await drain_queue()
        finally:
            await enrich.stop()

    run(scenario())

    # 流转是旁路：写入失败只记日志，条目照常出队、后续岗位继续处理。
    assert repo.screening == set()
    assert enrich._pending == []
    assert [command[0] for command in extension.commands] == [
        "capture_details",
        "capture_company",
        "capture_details",
        "capture_company",
    ]


async def _no_delay() -> None:
    return None