"""Exporter JSON -> raw_job (list tier) import.

The browser-side exporter produces ``{pageUrl, jobs: [...]}``; importing it
replaces list capture entirely (plan: ext-json-import-pool-enrich §4.1).

Contract notes:
- Every entry is mapped to a ``RawJobPayload(tier="list")``; the whole item is
  preserved verbatim in ``list_json`` (audit trail + navigation material for the
  enrich queue, e.g. securityId / companyUrl).
- Idempotent by ``(source, ext_id)``: re-import merges through the existing
  ``upsert_raw_job`` (list_json keeps the first value).
- Invalid entries are reported per index and never abort the whole import.
"""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from services.api.app import capture_repo
from services.api.app.event_models import BossJson, RawJobPayload

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_JOBS = 500

# batch_run.kind is the frozen capture_kind enum (list|detail|chat); the import
# run is a list-tier provenance batch distinguished by its trigger.
IMPORT_TRIGGER = "console-import"


class ExportFormatError(ValueError):
    """Raised when the uploaded file is not an exporter JSON at all."""


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _tags(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for item in value if (text := _text(item)) is not None]


def parse_export(
    payload: dict[str, Any], *, batch_id: UUID
) -> tuple[list[RawJobPayload], list[dict[str, Any]]]:
    """Map an exporter document to payloads; returns (jobs, invalid entries)."""
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        raise ExportFormatError("exporter JSON must contain a jobs array")
    page_url = _text(payload.get("pageUrl"))
    captured_at = datetime.now(UTC)
    parsed: list[RawJobPayload] = []
    invalid: list[dict[str, Any]] = []

    for index, item in enumerate(jobs):
        if not isinstance(item, dict):
            invalid.append({"index": index, "reason": "entry is not an object"})
            continue
        ext_id = _text(item.get("jobId"))
        title = _text(item.get("title"))
        company = _text(item.get("company"))
        if not ext_id:
            invalid.append({"index": index, "reason": "missing jobId"})
            continue
        if not title or not company:
            invalid.append({"index": index, "reason": "missing title or company", "ext_id": ext_id})
            continue

        raw = item.get("raw") if isinstance(item.get("raw"), dict) else {}
        boss_name = _text(raw.get("bossName"))
        parsed.append(
            RawJobPayload(
                source="boss",
                ext_id=ext_id,
                tier="list",
                batch_id=batch_id,
                list_url=page_url,
                title=title,
                company=company,
                city=_text(item.get("city")),
                district=_text(item.get("district")),
                salary_text=_text(item.get("salary")),
                exp_text=_text(item.get("experience")),
                degree=_text(item.get("degree")),
                list_tags=_tags(raw.get("jobLabels")),
                skill_tags=_tags(raw.get("skills")),
                industry=_text(raw.get("brandIndustry")),
                stage=_text(raw.get("brandStageName")),
                scale=_text(raw.get("brandScaleName")),
                ats_direct_post=raw.get("atsDirectPost")
                if isinstance(raw.get("atsDirectPost"), bool)
                else None,
                boss_name=boss_name,
                boss_json=BossJson(name=boss_name, title=_text(raw.get("bossTitle"))),
                list_json=item,
                captured_at=captured_at,
            )
        )
    return parsed, invalid


def load_export(data: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExportFormatError("file is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ExportFormatError("exporter JSON must be an object")
    if len(payload.get("jobs", [])) > MAX_JOBS:
        raise ExportFormatError(f"jobs exceeds the {MAX_JOBS} entry import cap")
    return payload


async def run_import(data: bytes) -> dict[str, Any]:
    """Persist an exported list; returns the JobImportResult body."""
    payload = load_export(data)
    batch_id = await capture_repo.create_batch_run(kind="list", trigger=IMPORT_TRIGGER)
    jobs, invalid = parse_export(payload, batch_id=batch_id)
    created = 0
    merged = 0
    for job in jobs:
        if await capture_repo.upsert_raw_job(job):
            created += 1
        else:
            merged += 1
    stats = {
        "success": created,
        "dup": merged,
        "invalid": len(invalid),
        "risk_halted": False,
    }
    await capture_repo.complete_batch(batch_id, status="completed", stats=stats)
    return {
        "batch_id": str(batch_id),
        "total": len(jobs),
        "created": created,
        "merged": merged,
        "invalid": invalid[:50],
    }