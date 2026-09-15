"""Capture domain persistence: batch_run lifecycle and raw_job upserts.

Merge rules (protocol #21 §5):
- power key = (source, ext_id); list tier and detail tier merge into one row;
- list_json/detail_json are preserved independently and never overwritten
  with parsed data;
- dup counts are authoritative server-side.
"""

import hashlib
import re
from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg.types.json import Json

from services.api.app.db import connection
from services.api.app.event_models import RawJobPayload
from services.api.app.protocol import uuid7

_SOURCE_IDS: dict[str, UUID] = {}
# capture_id -> duplicate row count (server-authoritative)
_DUP_COUNTS: dict[UUID, int] = {}

_WS_RE = re.compile(r"\s+")


def _normalize(value: str | None) -> str:
    if not value:
        return ""
    return _WS_RE.sub(" ", value.strip().lower())


def compute_fingerprint(job: RawJobPayload) -> str:
    parts = [_normalize(job.title), _normalize(job.company)]
    if job.jd_text:
        parts.append(_normalize(job.jd_text)[:200])
    digest = hashlib.sha256("|".join(parts).encode("utf-8"))
    return digest.hexdigest()


async def get_source_id(code: str = "boss") -> UUID:
    if code not in _SOURCE_IDS:
        async with connection() as conn:
            cursor = await conn.execute(
                "SELECT id FROM capture_source WHERE code = %s",
                [code],
            )
            row = await cursor.fetchone()
        if row is None:
            raise ValueError(f"unknown capture source: {code}")
        _SOURCE_IDS[code] = row[0]
    return _SOURCE_IDS[code]


async def create_batch_run(
    *,
    kind: str,
    trigger: str,
    batch_id: UUID | None = None,
) -> UUID:
    source_id = await get_source_id()
    batch_id = batch_id or UUID(uuid7())
    async with connection() as conn:
        cursor = await conn.execute(
            """
            INSERT INTO batch_run (id, source_id, kind, status, trigger, started_at)
            VALUES (%s, %s, %s, 'running', %s, now())
            RETURNING id
            """,
            [batch_id, source_id, kind, trigger],
        )
        row = await cursor.fetchone()
    assert row is not None
    created_id = row[0]
    if not isinstance(created_id, UUID):
        raise TypeError("database returned a non-UUID batch id")
    _DUP_COUNTS.setdefault(created_id, 0)
    return created_id


async def mark_progress(capture_id: UUID, progress: dict[str, Any]) -> None:
    async with connection() as conn:
        await conn.execute(
            "UPDATE batch_run SET stats_json = stats_json || %s::jsonb, updated_at = now() "
            "WHERE id = %s",
            [Json({"progress": progress}), capture_id],
        )


async def upsert_raw_job(job: RawJobPayload) -> bool:
    """Insert or merge a raw job. Returns True when a new row was created."""
    source_id = await get_source_id(job.source)
    fingerprint = compute_fingerprint(job)
    if job.tier == "list":
        list_at = job.captured_at
        detail_at = None
    else:
        list_at = None
        detail_at = job.captured_at or datetime.now()

    async with connection() as conn:
        cursor = await conn.execute(
            """
            INSERT INTO raw_job (
                id, source_id, ext_id, batch_id, fingerprint,
                list_json, detail_json, jd_text,
                title, company, city, salary_text, low_salary, high_salary, salary_unit,
                exp_text, degree, industry, stage, scale, address, active_at,
                list_tags, skill_tags, ats_direct_post, boss_json,
                active_time, list_at, detail_at, company_desc,
                list_url, boss_name
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s
            )
            ON CONFLICT (source_id, ext_id) DO UPDATE SET
                batch_id     = COALESCE(raw_job.batch_id, EXCLUDED.batch_id),
                fingerprint  = CASE WHEN EXCLUDED.jd_text IS NOT NULL
                                    THEN EXCLUDED.fingerprint ELSE raw_job.fingerprint END,
                list_json    = COALESCE(raw_job.list_json, EXCLUDED.list_json),
                detail_json  = COALESCE(EXCLUDED.detail_json, raw_job.detail_json),
                jd_text      = COALESCE(EXCLUDED.jd_text, raw_job.jd_text),
                title        = COALESCE(raw_job.title, EXCLUDED.title),
                company      = COALESCE(raw_job.company, EXCLUDED.company),
                city         = COALESCE(EXCLUDED.city, raw_job.city),
                salary_text  = COALESCE(EXCLUDED.salary_text, raw_job.salary_text),
                low_salary   = COALESCE(EXCLUDED.low_salary, raw_job.low_salary),
                high_salary  = COALESCE(EXCLUDED.high_salary, raw_job.high_salary),
                salary_unit  = CASE WHEN EXCLUDED.salary_unit <> 'unknown'
                                    THEN EXCLUDED.salary_unit ELSE raw_job.salary_unit END,
                exp_text     = COALESCE(EXCLUDED.exp_text, raw_job.exp_text),
                degree       = COALESCE(EXCLUDED.degree, raw_job.degree),
                industry     = COALESCE(EXCLUDED.industry, raw_job.industry),
                stage        = COALESCE(EXCLUDED.stage, raw_job.stage),
                scale        = COALESCE(EXCLUDED.scale, raw_job.scale),
                address      = COALESCE(EXCLUDED.address, raw_job.address),
                active_at    = COALESCE(EXCLUDED.active_at, raw_job.active_at),
                company_desc = COALESCE(EXCLUDED.company_desc, raw_job.company_desc),
                list_tags    = CASE WHEN cardinality(EXCLUDED.list_tags) > 0
                                    THEN EXCLUDED.list_tags ELSE raw_job.list_tags END,
                skill_tags   = CASE WHEN cardinality(EXCLUDED.skill_tags) > 0
                                    THEN EXCLUDED.skill_tags ELSE raw_job.skill_tags END,
                ats_direct_post = COALESCE(EXCLUDED.ats_direct_post, raw_job.ats_direct_post),
                boss_json    = raw_job.boss_json || EXCLUDED.boss_json,
                active_time  = COALESCE(EXCLUDED.active_time, raw_job.active_time),
                list_at      = COALESCE(raw_job.list_at, EXCLUDED.list_at),
                detail_at    = COALESCE(EXCLUDED.detail_at, raw_job.detail_at),
                list_url     = COALESCE(raw_job.list_url, EXCLUDED.list_url),
                boss_name    = COALESCE(raw_job.boss_name, EXCLUDED.boss_name),
                updated_at   = now()
            RETURNING (xmax = 0) AS inserted
            """,
            [
                UUID(uuid7()),
                source_id,
                job.ext_id,
                job.batch_id,
                fingerprint,
                Json(job.list_json) if job.list_json is not None else None,
                Json(job.detail_json) if job.detail_json is not None else None,
                job.jd_text,
                job.title,
                job.company,
                job.city,
                job.salary_text,
                job.low_salary,
                job.high_salary,
                job.salary_unit,
                job.exp_text,
                job.degree,
                job.industry,
                job.stage,
                job.scale,
                job.address,
                job.active_at,
                job.list_tags,
                job.skill_tags,
                job.ats_direct_post,
                Json(job.boss_json.model_dump(exclude_none=True)),
                job.active_time,
                list_at,
                detail_at,
                job.company_desc,
                job.list_url,
                job.boss_name,
            ],
        )
        row = await cursor.fetchone()
    inserted = bool(row and row[0])
    # Dup = repeated list-tier encounter of the same power key. Detail merges
    # into an existing row are a normal success path and must not inflate dup
    # (they would in chain mode, where list+detail share one batch).
    if not inserted and job.tier == "list" and job.batch_id is not None:
        _DUP_COUNTS[job.batch_id] = _DUP_COUNTS.get(job.batch_id, 0) + 1
    return inserted


async def complete_batch(
    capture_id: UUID,
    *,
    status: str = "completed",
    stats: dict[str, Any] | None = None,
    finished_at: datetime | None = None,
    risk_halted: bool | None = None,
) -> dict[str, Any]:
    final_stats = dict(stats or {})
    final_stats["dup"] = _DUP_COUNTS.get(capture_id, final_stats.get("dup", 0))
    if risk_halted is None:
        risk_halted = bool(final_stats.get("risk_halted", False))
    async with connection() as conn:
        await conn.execute(
            """
            UPDATE batch_run
               SET status = %s,
                   -- Merge: terminal stats override keys, but progress and
                   -- other accumulated evidence must survive completion.
                   stats_json = stats_json || %s::jsonb,
                   risk_halted = %s,
                   finished_at = COALESCE(%s, now()),
                   updated_at = now()
             WHERE id = %s
            """,
            [status, Json(final_stats), risk_halted, finished_at, capture_id],
        )
    _DUP_COUNTS.pop(capture_id, None)
    return final_stats


async def get_batch(capture_id: UUID) -> dict[str, Any] | None:
    async with connection() as conn:
        cursor = await conn.execute(
            """
            SELECT b.id, s.code, b.kind, b.status, b.stats_json, b.risk_halted,
                   b.trigger, b.started_at, b.finished_at
              FROM batch_run b
              JOIN capture_source s ON s.id = b.source_id
             WHERE b.id = %s
            """,
            [capture_id],
        )
        row = await cursor.fetchone()
    if row is None:
        return None
    return {
        "id": str(row[0]),
        "source": row[1],
        "kind": row[2],
        "status": row[3],
        "stats": row[4],
        "risk_halted": row[5],
        "trigger": row[6],
        "started_at": row[7].isoformat() if row[7] else None,
        "finished_at": row[8].isoformat() if row[8] else None,
    }


async def reserve_event(event_id: UUID, event_type: str, capture_id: UUID | None) -> bool:
    """Reserve a WS event ID without retaining its payload."""
    async with connection() as conn:
        cursor = await conn.execute(
            """
            INSERT INTO ws_event_inbox (id, event_type, capture_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            RETURNING id
            """,
            [event_id, event_type, capture_id],
        )
        return await cursor.fetchone() is not None


async def release_event(event_id: UUID) -> None:
    """Release a failed reservation so a later extension retry can be processed."""
    async with connection() as conn:
        await conn.execute("DELETE FROM ws_event_inbox WHERE id = %s", [event_id])


async def list_raw_jobs(
    *,
    limit: int = 50,
    offset: int = 0,
    batch_id: UUID | None = None,
) -> list[dict[str, Any]]:
    where = ""
    params: list[Any] = []
    if batch_id is not None:
        where = "WHERE r.batch_id = %s"
        params.append(batch_id)
    params.extend([limit, offset])
    async with connection() as conn:
        cursor = await conn.execute(
            f"""
            SELECT r.id, r.ext_id, r.title, r.company, r.city,
                   r.salary_text, r.exp_text, r.degree,
                   r.list_at, r.detail_at, r.batch_id
              FROM raw_job r
              {where}
             ORDER BY GREATEST(r.detail_at, r.list_at, r.created_at) DESC
             LIMIT %s OFFSET %s
            """,
            params,
        )
        rows = await cursor.fetchall()
    return [
        {
            "id": str(row[0]),
            "ext_id": row[1],
            "title": row[2],
            "company": row[3],
            "city": row[4],
            "salary_text": row[5],
            "exp_text": row[6],
            "degree": row[7],
            "list_at": row[8].isoformat() if row[8] else None,
            "detail_at": row[9].isoformat() if row[9] else None,
            "batch_id": str(row[10]) if row[10] else None,
        }
        for row in rows
    ]
