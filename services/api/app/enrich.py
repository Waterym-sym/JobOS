"""Serial enrich queue: shortlist -> job detail page -> company page.

Design (plan: ext-json-import-pool-enrich §4.3):

- One in-process asyncio worker; concurrency is hard-capped at 1 (red line).
- Each task issues two WS commands through the paired extension and waits for
  the batch to reach a terminal state, notified by ``complete_batch``.
- Throttling: 1800ms base gap (+/-20% jitter) between the detail and company
  stages; the extension applies its own per-page pacing on top.
- ``capture.error{risk:true}`` pauses the whole queue until a human calls
  resume; offline extensions back off and retry without burning attempts.
- Restart recovery rebuilds the queue from confirmed shortlist rows, which is
  naturally idempotent (completed stages are skipped).
"""

import asyncio
import logging
import random
import re
import time
from contextlib import suppress
from typing import Any
from uuid import UUID

from services.api.app import capture_repo
from services.api.app.config import get_settings
from services.api.app.registry import NoExtensionConnected, registry

logger = logging.getLogger("jobos.enrich")

BATCH_TIMEOUT_S = 90.0
ENRICH_TRIGGER = "pool-auto"
PENDING_PREVIEW = 200

_COMPANY_URL_RE = re.compile(r"/gongsi/([^/]+)\.html")
_COMPANY_HOST_PREFIX = "https://www.zhipin.com/"
# BOSS encrypt ids used in self-constructed company URLs are opaque tokens;
# only this shape may be interpolated into a path (flat cards carry no URL).
_COMPANY_ID_RE = re.compile(r"[A-Za-z0-9_.~-]+")
# securityId query values are long url-safe tokens; anything else is dropped.
_SECURITY_ID_RE = re.compile(r"[A-Za-z0-9_-]+")

# The pool worker is demand-driven: each entry gets exactly one detail attempt
# and one company attempt. A failure is recorded and the entry leaves the queue
# (only a human `resume` retries); when no capable extension is paired the
# worker parks instead of polling, and a pairing wakes it.
REQUIRED_CAPABILITIES = ("capture_details_urls", "capture_company")

# ---------------------------------------------------------------- queue state

_pending: list[UUID] = []
_queued: set[UUID] = set()
_running: UUID | None = None
_running_stage: str | None = None
_failed: dict[UUID, str] = {}
_paused = False
_paused_reason: str | None = None

_waiters: dict[UUID, asyncio.Future] = {}
_last_progress: dict[UUID, float] = {}
_worker: asyncio.Task | None = None
_wake_event: asyncio.Event | None = None
_resume_event: asyncio.Event | None = None
_capacity_event: asyncio.Event | None = None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def is_paused() -> bool:
    return _paused


def failure(raw_job_id: UUID) -> str | None:
    """Failure reason for an entry, or None when it is not failed."""
    return _failed.get(raw_job_id)


def company_ext_id(list_json: Any) -> str | None:
    """Company power key preserved in the exporter item (for state display)."""
    return _navigation(list_json)["ext_company_id"]


def discard(raw_job_id: UUID) -> None:
    """Drop an entry from the queue (pool removal). A running stage finishes."""
    _queued.discard(raw_job_id)
    with suppress(ValueError):
        _pending.remove(raw_job_id)
    _failed.pop(raw_job_id, None)


def _capable_available() -> bool:
    if registry.current() is None:
        return False
    return all(registry.capable(capability) for capability in REQUIRED_CAPABILITIES)


def _notify_capacity() -> None:
    if _capacity_event is not None:
        _capacity_event.set()


def _on_batch_progress(capture_id: UUID) -> None:
    """Heartbeat: the extension is still working on this batch."""
    _last_progress[capture_id] = time.monotonic()


def _on_batch_done(capture_id: UUID, status: str, stats: dict[str, Any]) -> None:
    """Batch terminal-state hook (subscribed to capture_repo).

    Invoked from the same event loop that awaits ``complete_batch`` (ws gateway
    or REST handlers), so resolving the future directly is loop-safe.
    """
    waiter = _waiters.get(capture_id)
    if waiter is not None and not waiter.done():
        waiter.set_result((status, stats))


def _pause(reason: str) -> None:
    global _paused, _paused_reason
    _paused = True
    _paused_reason = reason
    if _resume_event is not None:
        _resume_event.clear()
    logger.warning("enrich queue paused: %s", reason)


def enqueue(raw_job_id: UUID) -> None:
    """Idempotent append. Safe to call before ``start()``."""
    if raw_job_id in _queued or raw_job_id == _running:
        return
    _failed.pop(raw_job_id, None)
    _queued.add(raw_job_id)
    _pending.append(raw_job_id)
    if _wake_event is not None:
        _wake_event.set()


async def resume() -> dict[str, Any]:
    """Human acknowledgement: unpause and retry failed items."""
    global _paused, _paused_reason
    _paused = False
    _paused_reason = None
    if _resume_event is not None:
        _resume_event.set()
    for raw_job_id in list(_failed):
        _failed.pop(raw_job_id, None)
        enqueue(raw_job_id)
    if _wake_event is not None:
        _wake_event.set()
    if _capacity_event is not None:
        _capacity_event.set()
    return await status()


async def status() -> dict[str, Any]:
    running: dict[str, Any] | None = None
    if _running is not None:
        job = await capture_repo.get_raw_job_for_enrich(_running)
        running = {
            "raw_job_id": str(_running),
            "ext_id": job["ext_id"] if job else "",
            "stage": _running_stage,
        }
    pending: list[dict[str, Any]] = []
    for raw_job_id in _pending[:PENDING_PREVIEW]:
        job = await capture_repo.get_raw_job_for_enrich(raw_job_id)
        pending.append(
            {
                "raw_job_id": str(raw_job_id),
                "ext_id": job["ext_id"] if job else "",
                "title": job["title"] if job else None,
            }
        )
    return {
        "paused": _paused,
        "paused_reason": _paused_reason,
        "running": running,
        "pending": pending,
        "blocked_reason": _blocked_reason(has_work=bool(running or pending or _failed)),
    }


def _blocked_reason(*, has_work: bool) -> str | None:
    """Why nothing is progressing (only reported while there is work)."""
    if not has_work:
        return None
    if registry.current() is None:
        return "扩展未配对：请在扩展选项页填入配对码"
    missing = [
        name
        for name, capability in (
            ("capture_details", "capture_details_urls"),
            ("capture_company", "capture_company"),
        )
        if not registry.capable(capability)
    ]
    if missing:
        required_cap = {
            "capture_details": "capture_details_urls",
            "capture_company": "capture_company",
        }
        reconnecting = all(registry.was_capable(required_cap[name]) for name in missing)
        if reconnecting:
            return (
                "岗位池补全桥正在重连（浏览器扩展休眠后会自动恢复）："
                "队列已挂起，补全桥重连后自动继续，无需操作"
            )
        return (
            "当前配对的客户端不具备按 URL 补全的能力（"
            + "、".join(missing)
            + "）：请在 Chrome 加载/重载「JobOS 岗位池补全桥」扩展"
        )
    return None


# ------------------------------------------------------------- lifecycle


async def start() -> None:
    global _worker, _wake_event, _resume_event, _capacity_event
    if _worker is not None:
        return
    _wake_event = asyncio.Event()
    _resume_event = asyncio.Event()
    _resume_event.set()
    _capacity_event = asyncio.Event()
    capture_repo.subscribe_batch_done(_on_batch_done)
    capture_repo.subscribe_progress(_on_batch_progress)
    registry.subscribe_connected(_notify_capacity)
    await _rebuild()
    _worker = asyncio.create_task(_worker_loop(), name="enrich-worker")


async def stop() -> None:
    global _worker
    if _worker is None:
        return
    _worker.cancel()
    with suppress(asyncio.CancelledError):
        await _worker
    _worker = None


async def _rebuild() -> None:
    """Restart recovery: enqueue every confirmed pool entry.

    Already-flowed jobs are not in ``list_shortlist()`` (screening_entry exists),
    so they are never processed twice; completed ones still get their missing
    screening entry written on the first worker pass.
    """
    for row in await capture_repo.list_shortlist():
        enqueue(row["raw_job_id"])
    if _pending:
        logger.info("enrich queue rebuilt with %d pool entries", len(_pending))


# ----------------------------------------------------------------- worker


async def _worker_loop() -> None:
    global _running, _running_stage
    while True:
        if _paused:
            assert _resume_event is not None
            await _resume_event.wait()
            continue
        assert _wake_event is not None
        _wake_event.clear()
        if not _pending:
            await _wake_event.wait()
            continue
        raw_job_id = _pending.pop(0)
        _running = raw_job_id
        _running_stage = None
        try:
            outcome = await _enrich_one(raw_job_id)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a bad entry must not kill the worker
            logger.exception("enrich failed unexpectedly")
            outcome = "failed"
        finally:
            _running = None
            _running_stage = None
        if outcome == "done":
            # 补全完成即自动流入筛选池（内部状态迁移，非对外动作）；幂等写入，
            # 且流转失败不得拖垮 worker。
            try:
                await capture_repo.create_screening_entry(raw_job_id)
            except Exception:  # noqa: BLE001 - screening write is a side channel
                logger.exception("screening entry write failed")
            _queued.discard(raw_job_id)
            _failed.pop(raw_job_id, None)
        elif outcome == "failed":
            _queued.discard(raw_job_id)
        elif outcome == "stale":
            # Left the pool / job row is gone: drop silently, nothing to report.
            _queued.discard(raw_job_id)
            _failed.pop(raw_job_id, None)
        else:
            # "park" / "paused": keep the item at the head, still queued.
            _pending.insert(0, raw_job_id)
            if outcome == "park":
                await _wait_for_capacity()


async def _wait_for_capacity() -> None:
    """Block until a capable extension is paired — no polling, no requests."""
    assert _capacity_event is not None
    while not _capable_available():
        _capacity_event.clear()
        if _capable_available():
            return
        logger.info("enrich queue parked: no capability-announcing extension paired")
        await _capacity_event.wait()
    _capacity_event.clear()


async def _enrich_one(raw_job_id: UUID) -> str:
    job = await capture_repo.get_raw_job_for_enrich(raw_job_id)
    if job is None:
        return "stale"
    if await capture_repo.get_pool_status(raw_job_id) != "confirmed":
        # Removed from the pool while queued (or re-added later): stop here.
        return "stale"
    nav = _navigation(job["list_json"])

    # A detail capture is only complete once the JD text landed (detail_at is
    # set by any detail-tier write, including empty ones).
    if job["detail_at"] is None or not job["jd_text"]:
        if nav["detail_url"] is None:
            _failed[raw_job_id] = "list_json lacks detail navigation"
            return "failed"
        settings = get_settings()
        outcome, detail = await _run_stage(
            "capture_details",
            {
                "urls": [
                    {
                        "ext_id": job["ext_id"],
                        "url": nav["detail_url"],
                        **(
                            {"security_id": nav["security_id"]}
                            if nav["security_id"]
                            else {}
                        ),
                    }
                ],
                "detail_limit": 1,
                "delay_ms": settings.capture_min_delay_ms,
            },
            stage="detail",
        )
        if outcome != "ok":
            return await _after_failure(raw_job_id, outcome, detail=detail)
        refreshed = await capture_repo.get_raw_job_for_enrich(raw_job_id)
        if refreshed is None or not refreshed["jd_text"]:
            return await _after_failure(
                raw_job_id, "empty", reason="detail page yielded no data"
            )
        job = refreshed

    if nav["company_url"] is None or nav["ext_company_id"] is None:
        # No company navigation in the export; the job is as complete as it gets.
        return "done"
    if nav["ext_company_id"] in await capture_repo.list_company_ext_ids():
        return "done"

    await _inter_stage_delay()
    settings = get_settings()
    outcome, detail = await _run_stage(
        "capture_company",
        {
            "company_url": nav["company_url"],
            "ext_company_id": nav["ext_company_id"],
            "delay_ms": settings.capture_min_delay_ms,
        },
        stage="company",
    )
    if outcome != "ok":
        return await _after_failure(raw_job_id, outcome, detail=detail)
    if nav["ext_company_id"] not in await capture_repo.list_company_ext_ids():
        return await _after_failure(
            raw_job_id, "empty", reason="company page yielded no data"
        )
    return "done"


async def _after_failure(
    raw_job_id: UUID, outcome: str, *, reason: str | None = None, detail: str | None = None
) -> str:
    """Single-attempt policy: record the failure, never auto-retry."""
    if outcome == "risk":
        _pause("risk_halted: 扩展报告风控/验证码，需人工确认后恢复")
        return "paused"
    if outcome == "offline":
        # Nothing was attempted (no capable client): park until one pairs.
        return "park"
    text = reason or outcome
    if detail:
        text = f"{text}: {detail}"
    _failed[raw_job_id] = text[:400]
    logger.info("enrich entry failed (%s): %s", outcome, raw_job_id)
    return "failed"


async def _run_stage(command: str, payload: dict[str, Any], *, stage: str) -> tuple[str, str]:
    """Issue one WS command and wait for its batch to finish.

    Returns (outcome, detail) where detail carries the extension's own error
    message so failures stay visible without digging into batch stats.
    """
    global _running_stage
    if not _capable_available():
        # No capable client: do not create a doomed batch_run row.
        return "offline", ""
    batch_id = await capture_repo.create_batch_run(kind="detail", trigger=ENRICH_TRIGGER)
    try:
        await registry.send_command(command, payload, capture_id=batch_id)
    except NoExtensionConnected:
        await capture_repo.complete_batch(
            batch_id, status="failed", stats={"reason": "extension offline"}
        )
        return "offline", ""
    _running_stage = stage
    status, stats = await _wait_batch(batch_id)
    detail = str(stats.get("message") or stats.get("reason") or stats.get("code") or "")
    if status == "completed":
        return "ok", ""
    if status == "risk_halted":
        return "risk", detail
    if status == "timeout":
        await capture_repo.complete_batch(
            batch_id, status="failed", stats={"reason": "batch timeout"}
        )
        return "timeout", "batch timeout"
    return "failed", detail


async def _wait_batch(batch_id: UUID) -> tuple[str, dict[str, Any]]:
    """Wait for a terminal state, resetting the idle timer on heartbeats.

    A silent extension (service worker recycled mid-run) therefore still fails
    after BATCH_TIMEOUT_S of *inactivity*, while a slow but working one keeps
    its batch alive.
    """
    future: asyncio.Future = asyncio.get_running_loop().create_future()
    _waiters[batch_id] = future
    _last_progress[batch_id] = time.monotonic()
    try:
        while True:
            idle_for = time.monotonic() - _last_progress.get(batch_id, time.monotonic())
            if idle_for >= BATCH_TIMEOUT_S:
                logger.warning("enrich batch silent for %.0fs: %s", idle_for, batch_id)
                return "timeout", {}
            chunk = min(10.0, BATCH_TIMEOUT_S - idle_for)
            with suppress(TimeoutError):
                return await asyncio.wait_for(asyncio.shield(future), timeout=chunk)
            if future.done():
                return future.result()
    finally:
        _waiters.pop(batch_id, None)
        _last_progress.pop(batch_id, None)


async def _inter_stage_delay() -> None:
    # Jitter is upward only: the 1800ms floor is a red line (ADR-009).
    base = get_settings().capture_min_delay_ms / 1000
    await asyncio.sleep(base * random.uniform(1.0, 1.2))


def _navigation(list_json: Any) -> dict[str, str | None]:
    """Extract detail/company navigation from preserved list data.

    Two shapes occur: the exporter envelope (console JSON import — fields
    nested under ``raw`` plus top-level link fields) and the flat Vue card
    delivered by extension list direct-push (every field at top level, with
    no link fields; links are constructed from the site-provided encrypt ids).
    """
    item = list_json if isinstance(list_json, dict) else {}
    raw = item.get("raw") if isinstance(item.get("raw"), dict) else {}

    company_url_input: str | None = None
    if raw:
        encrypt_job_id = _text(raw.get("encryptJobId")) or _text(item.get("jobId"))
        security_id = _text(item.get("securityId")) or _text(raw.get("securityId"))
        company_url_input = _text(item.get("companyUrl"))
        ext_company_id = _text(raw.get("encryptBrandId"))
    else:
        # Flat Vue card: mapListJob preserves the card object verbatim. Ids
        # interpolated into self-built URLs must be opaque BOSS tokens.
        job_id = _text(item.get("encryptJobId"))
        encrypt_job_id = job_id if (job_id and _COMPANY_ID_RE.fullmatch(job_id)) else None
        sec_id = _text(item.get("securityId"))
        security_id = sec_id if (sec_id and _SECURITY_ID_RE.fullmatch(sec_id)) else None
        brand_id = _text(item.get("encryptBrandId"))
        ext_company_id = brand_id if (brand_id and _COMPANY_ID_RE.fullmatch(brand_id)) else None

    detail_url = None
    if encrypt_job_id:
        detail_url = f"https://www.zhipin.com/job_detail/{encrypt_job_id}.html"
        if security_id:
            detail_url = f"{detail_url}?securityId={security_id}"

    company_url = None
    if company_url_input and company_url_input.startswith(_COMPANY_HOST_PREFIX):
        # Red line: exporter-supplied links must point at BOSS company pages.
        company_url = company_url_input
    elif not raw and ext_company_id and _COMPANY_ID_RE.fullmatch(ext_company_id):
        # Flat cards carry no URL; build the canonical BOSS company page from
        # a constant host plus the validated opaque id.
        company_url = f"{_COMPANY_HOST_PREFIX}gongsi/{ext_company_id}.html"
    if not ext_company_id and company_url:
        match = _COMPANY_URL_RE.search(company_url)
        ext_company_id = match.group(1) if match else None
    return {
        "detail_url": detail_url,
        "security_id": security_id,
        "company_url": company_url,
        "ext_company_id": ext_company_id,
    }