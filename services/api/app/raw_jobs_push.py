"""Extension list-direct-push ingestion (``POST /api/v1/raw-jobs``).

When the user manually turns a BOSS list page, the extension reads the already
loaded cards out of page Vue memory and pushes them in one passive HTTP call
(see docs/architecture/21 §5 and contracts/ws/raw-job.schema.json). The push
neither registers a capture nor expects a WS command in return. For audit and
funnel provenance each push is still recorded as a completed list-tier
``batch_run`` (``trigger='extension-list-push'``), mirroring the console JSON
import path (job_import).

Contract notes:
- Every item is validated as a ``RawJobPayload`` (tier='list'); malformed cards
  are reported per index and never abort the whole push.
- The per-push provenance batch id is stamped onto every accepted item.
- Idempotency is the existing ``(source, ext_id)`` upsert: re-pushing the same
  page merges, ``list_json`` keeps its first value, and salary/experience/
  degree are cleaned server-side.
- This module performs persistence only; it must never dispatch extension
  commands or any other outbound action.
"""

import logging
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from services.api.app import capture_repo
from services.api.app.event_models import RawJobPayload

logger = logging.getLogger("jobos.repo")

# Extension caps one page at maxItems=100 (a BOSS page holds far fewer); the
# server cap keeps the contract tight.
MAX_JOBS = 100

# batch_run.trigger is free text (no DB CHECK; see the 0001 migration); the
# OpenAPI BatchRun enum only summarises the console/ws triggers.
PUSH_TRIGGER = "extension-list-push"

_MAX_INVALID_REPORTED = 50


class RawJobsUploadError(ValueError):
    """Envelope-level rejection (bad source/tier or jobs missing/oversized)."""


def parse_upload(
    body: dict[str, Any], *, batch_id: UUID
) -> tuple[list[RawJobPayload], list[dict[str, Any]]]:
    """Map a push envelope to payloads; returns (jobs, invalid entries)."""
    source = body.get("source")
    tier = body.get("tier")
    jobs = body.get("jobs")
    if source != "boss" or tier != "list" or not isinstance(jobs, list):
        raise RawJobsUploadError(
            "body must be an object {source: 'boss', tier: 'list', jobs: [...]}"
        )
    if not jobs:
        raise RawJobsUploadError("jobs must not be empty")
    if len(jobs) > MAX_JOBS:
        raise RawJobsUploadError(f"jobs exceeds the {MAX_JOBS} entry push cap")

    parsed: list[RawJobPayload] = []
    invalid: list[dict[str, Any]] = []
    for index, item in enumerate(jobs):
        if not isinstance(item, dict):
            invalid.append({"index": index, "reason": "entry is not an object"})
            continue
        try:
            payload = RawJobPayload.model_validate(item)
        except ValidationError:
            invalid.append({"index": index, "reason": "payload fails raw-job schema"})
            continue
        if payload.source != source or payload.tier != tier:
            invalid.append({"index": index, "reason": "source/tier does not match envelope"})
            continue
        # Provenance: the accepted item belongs to this push, regardless of any
        # batch_id the client happened to send (direct push sends none).
        payload.batch_id = batch_id
        parsed.append(payload)
    return parsed, invalid


async def run_push(body: dict[str, Any]) -> dict[str, Any]:
    """Persist a direct-push page; returns the RawJobsUploadResult body."""
    batch_id = await capture_repo.create_batch_run(kind="list", trigger=PUSH_TRIGGER)
    jobs, invalid = parse_upload(body, batch_id=batch_id)
    created = 0
    merged = 0
    for job in jobs:
        if await capture_repo.upsert_raw_job(job):
            created += 1
        else:
            merged += 1
    await capture_repo.complete_batch(
        batch_id,
        status="completed",
        stats={
            "success": created,
            "dup": merged,
            "invalid": len(invalid),
            "risk_halted": False,
        },
    )
    logger.info(
        "raw_jobs_push accepted=%s created=%s merged=%s invalid=%s",
        len(jobs),
        created,
        merged,
        len(invalid),
    )
    return {
        "batch_id": str(batch_id),
        "total": len(jobs),
        "created": created,
        "merged": merged,
        "invalid": invalid[:_MAX_INVALID_REPORTED],
    }
