"""Capture domain persistence: batch_run lifecycle and raw_job upserts.

Merge rules (protocol #21 §5):
- power key = (source, ext_id); list tier and detail tier merge into one row;
- list_json/detail_json are preserved independently and never overwritten
  with parsed data;
- dup counts are authoritative server-side.
"""

import hashlib
import logging
import re
from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg.types.json import Json

from services.api.app.cleaning import (
    clean_company_name,
    parse_degree,
    parse_experience,
    parse_salary,
)
from services.api.app.db import connection
from services.api.app.event_models import CompanyPayload, RawJobPayload
from services.api.app.protocol import uuid7

logger = logging.getLogger("jobos.repo")

_SOURCE_IDS: dict[str, UUID] = {}
# capture_id -> duplicate row count (server-authoritative)
_DUP_COUNTS: dict[UUID, int] = {}

# Terminal batch notifications (status transitions driven by WS events).
# Subscribers are sync callables invoked fire-and-forget with (capture_id,
# status, stats); they must never raise.
_BATCH_DONE_SUBSCRIBERS: list[Callable[[UUID, str, dict[str, Any]], None]] = []
# Progress notifications (capture.phase), used as a liveness heartbeat by the
# enrich queue so "still working" is not mistaken for "gone silent".
_PROGRESS_SUBSCRIBERS: list[Callable[[UUID], None]] = []


def subscribe_batch_done(fn: Callable[[UUID, str, dict[str, Any]], None]) -> None:
    _BATCH_DONE_SUBSCRIBERS.append(fn)


def subscribe_progress(fn: Callable[[UUID], None]) -> None:
    _PROGRESS_SUBSCRIBERS.append(fn)


def _notify_progress(capture_id: UUID) -> None:
    for subscriber in list(_PROGRESS_SUBSCRIBERS):
        try:
            subscriber(capture_id)
        except Exception:  # noqa: BLE001 - subscriber bugs must not break persistence
            logger.exception("progress subscriber failed")

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
    _notify_progress(capture_id)


async def upsert_raw_job(job: RawJobPayload) -> bool:
    """Insert or merge a raw job. Returns True when a new row was created."""
    source_id = await get_source_id(job.source)
    fingerprint = compute_fingerprint(job)
    # Cleaning is server-side: recompute clean columns from raw text.
    clean_low, clean_high, clean_unit = parse_salary(job.salary_text)
    exp_min_years, exp_max_years = parse_experience(job.exp_text)
    degree_code = parse_degree(job.degree)
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
                title, company, city, district, salary_text,
                low_salary, high_salary, salary_unit,
                exp_text, exp_min_years, exp_max_years,
                degree, degree_code,
                industry, stage, scale, address, active_at,
                list_tags, skill_tags, ats_direct_post, boss_json,
                active_time, list_at, detail_at, company_desc,
                list_url, boss_name
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s, %s,
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
                district     = COALESCE(EXCLUDED.district, raw_job.district),
                salary_text  = COALESCE(EXCLUDED.salary_text, raw_job.salary_text),
                low_salary   = COALESCE(EXCLUDED.low_salary, raw_job.low_salary),
                high_salary  = COALESCE(EXCLUDED.high_salary, raw_job.high_salary),
                salary_unit  = CASE WHEN EXCLUDED.salary_unit <> 'unknown'
                                    THEN EXCLUDED.salary_unit ELSE raw_job.salary_unit END,
                exp_text     = COALESCE(EXCLUDED.exp_text, raw_job.exp_text),
                exp_min_years = CASE WHEN EXCLUDED.exp_text IS NOT NULL
                                     THEN EXCLUDED.exp_min_years ELSE raw_job.exp_min_years END,
                exp_max_years = CASE WHEN EXCLUDED.exp_text IS NOT NULL
                                     THEN EXCLUDED.exp_max_years ELSE raw_job.exp_max_years END,
                degree       = COALESCE(EXCLUDED.degree, raw_job.degree),
                degree_code  = CASE WHEN EXCLUDED.degree IS NOT NULL
                                    THEN EXCLUDED.degree_code ELSE raw_job.degree_code END,
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
                job.district,
                job.salary_text,
                clean_low if job.low_salary is None else job.low_salary,
                clean_high if job.high_salary is None else job.high_salary,
                clean_unit if job.salary_unit == "unknown" else job.salary_unit,
                job.exp_text,
                exp_min_years,
                exp_max_years,
                job.degree,
                degree_code,
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


# ------------------------------------------------------------------ company


async def upsert_company(company: CompanyPayload) -> bool:
    """Insert or merge a gongsi-page snapshot. Returns True for a new row."""
    source_id = await get_source_id(company.source)
    safe_name = clean_company_name(company.name)
    async with connection() as conn:
        cursor = await conn.execute(
            """
            INSERT INTO raw_company (source_id, ext_company_id, name, sections, raw_json)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (source_id, ext_company_id) DO UPDATE SET
                name     = COALESCE(raw_company.name, EXCLUDED.name),
                sections = raw_company.sections || EXCLUDED.sections,
                raw_json = COALESCE(EXCLUDED.raw_json, raw_company.raw_json),
                updated_at = now()
            RETURNING (xmax = 0) AS inserted
            """,
            [
                source_id,
                company.ext_company_id,
                safe_name,
                Json(company.sections),
                Json(company.raw_json) if company.raw_json is not None else None,
            ],
        )
        row = await cursor.fetchone()
    return bool(row and row[0])


async def list_companies(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    async with connection() as conn:
        cursor = await conn.execute(
            """
            SELECT id, ext_company_id, name, sections, updated_at
              FROM raw_company
             ORDER BY updated_at DESC
             LIMIT %s OFFSET %s
            """,
            [min(max(limit, 1), 200), max(offset, 0)],
        )
        rows = await cursor.fetchall()
    return [
        {
            "id": str(row[0]),
            "ext_company_id": row[1],
            "name": row[2],
            "sections": row[3],
            "updated_at": row[4].isoformat(),
        }
        for row in rows
    ]


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
    for subscriber in list(_BATCH_DONE_SUBSCRIBERS):
        try:
            subscriber(capture_id, status, final_stats)
        except Exception:  # noqa: BLE001 - subscriber bugs must not break persistence
            logger.exception("batch-done subscriber failed")
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
            SELECT r.id, r.ext_id, r.title, r.company, r.city, r.district,
                   r.salary_text, r.low_salary, r.high_salary, r.salary_unit,
                   r.exp_text, r.exp_min_years, r.exp_max_years,
                   r.degree, r.degree_code,
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
            "district": row[5],
            "salary_text": row[6],
            "low_salary": float(row[7]) if row[7] is not None else None,
            "high_salary": float(row[8]) if row[8] is not None else None,
            "salary_unit": row[9],
            "exp_text": row[10],
            "exp_min_years": row[11],
            "exp_max_years": row[12],
            "degree": row[13],
            "degree_code": row[14],
            "list_at": row[15].isoformat() if row[15] else None,
            "detail_at": row[16].isoformat() if row[16] else None,
            "batch_id": str(row[17]) if row[17] else None,
        }
        for row in rows
    ]


# -------------------------------------------------------------- job profile
# 岗位详情面板投影：raw_job 原文 + 公司画像。list_json 仅供端点内部推导
# ext_company_id，不对外输出（导航数据只在本机流转）。


async def get_job_profile(ext_id: str, source: str = "boss") -> dict[str, Any] | None:
    source_id = await get_source_id(source)
    async with connection() as conn:
        cursor = await conn.execute(
            """
            SELECT id, ext_id, title, company, city, district, salary_text,
                   exp_text, degree, industry, stage, scale, address, boss_name,
                   active_time, skill_tags, jd_text, detail_at, list_json
              FROM raw_job
             WHERE source_id = %s AND ext_id = %s
            """,
            [source_id, ext_id],
        )
        row = await cursor.fetchone()
    if row is None:
        return None
    return {
        "id": str(row[0]),
        "ext_id": row[1],
        "title": row[2],
        "company": row[3],
        "city": row[4],
        "district": row[5],
        "salary_text": row[6],
        "exp_text": row[7],
        "degree": row[8],
        "industry": row[9],
        "stage": row[10],
        "scale": row[11],
        "address": row[12],
        "boss_name": row[13],
        "active_time": row[14],
        "skill_tags": list(row[15] or []),
        "jd_text": row[16],
        "detail_at": row[17].isoformat() if row[17] else None,
        "list_json": row[18],
    }


async def get_company_by_ext_id(
    ext_company_id: str, source: str = "boss"
) -> dict[str, Any] | None:
    source_id = await get_source_id(source)
    async with connection() as conn:
        cursor = await conn.execute(
            """
            SELECT ext_company_id, name, sections, updated_at
              FROM raw_company
             WHERE source_id = %s AND ext_company_id = %s
            """,
            [source_id, ext_company_id],
        )
        row = await cursor.fetchone()
    if row is None:
        return None
    return {
        "ext_company_id": row[0],
        "name": row[1],
        "sections": row[2],
        "updated_at": row[3].isoformat() if row[3] else None,
    }


# ---------------------------------------------------------------- shortlist
# 岗位池：入池即进入按需补全队列（enrich）。沿用 0001 baseline 表结构，零 DDL。


class ShortlistExists(RuntimeError):
    """Raised when the job already has an active confirmed shortlist row."""


async def get_raw_job_by_ext_id(ext_id: str, source: str = "boss") -> dict[str, Any] | None:
    source_id = await get_source_id(source)
    async with connection() as conn:
        cursor = await conn.execute(
            """
            SELECT id, ext_id, title, detail_at, list_json
              FROM raw_job
             WHERE source_id = %s AND ext_id = %s
            """,
            [source_id, ext_id],
        )
        row = await cursor.fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "ext_id": row[1],
        "title": row[2],
        "detail_at": row[3],
        "list_json": row[4],
    }


async def get_raw_job_for_enrich(raw_job_id: UUID) -> dict[str, Any] | None:
    async with connection() as conn:
        cursor = await conn.execute(
            """
            SELECT id, ext_id, title, detail_at, list_json, jd_text
              FROM raw_job
             WHERE id = %s
            """,
            [raw_job_id],
        )
        row = await cursor.fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "ext_id": row[1],
        "title": row[2],
        "detail_at": row[3],
        "list_json": row[4],
        "jd_text": row[5],
    }


async def add_to_shortlist(ext_id: str, note: str | None = None) -> dict[str, Any] | None:
    """Insert a confirmed shortlist row. Returns None when the job is unknown."""
    job = await get_raw_job_by_ext_id(ext_id)
    if job is None:
        return None
    async with connection() as conn:
        cursor = await conn.execute(
            """
            SELECT id FROM shortlist
             WHERE raw_job_id = %s AND status = 'confirmed'
            """,
            [job["id"]],
        )
        if await cursor.fetchone() is not None:
            raise ShortlistExists(ext_id)
        cursor = await conn.execute(
            """
            INSERT INTO shortlist (raw_job_id, status, note)
            VALUES (%s, 'confirmed', %s)
            RETURNING id, decided_at
            """,
            [job["id"], note],
        )
        row = await cursor.fetchone()
    assert row is not None
    return {
        "id": row[0],
        "raw_job_id": job["id"],
        "ext_id": job["ext_id"],
        "status": "confirmed",
        "note": note,
        "added_at": row[1],
    }


async def get_shortlist_row(shortlist_id: UUID) -> dict[str, Any] | None:
    async with connection() as conn:
        cursor = await conn.execute(
            """
            SELECT sl.id, sl.raw_job_id, r.ext_id, r.title, r.company, r.city,
                   r.salary_text, sl.status, sl.note, sl.created_at,
                   r.detail_at, r.list_json, r.jd_text
              FROM shortlist sl
              JOIN raw_job r ON r.id = sl.raw_job_id
             WHERE sl.id = %s
            """,
            [shortlist_id],
        )
        row = await cursor.fetchone()
    return _shortlist_mapping(row) if row is not None else None


async def list_shortlist() -> list[dict[str, Any]]:
    """Active pool entries (confirmed) joined with raw_job for display."""
    async with connection() as conn:
        cursor = await conn.execute(
            """
            SELECT sl.id, sl.raw_job_id, r.ext_id, r.title, r.company, r.city,
                   r.salary_text, sl.status, sl.note, sl.created_at,
                   r.detail_at, r.list_json, r.jd_text
              FROM shortlist sl
              JOIN raw_job r ON r.id = sl.raw_job_id
             WHERE sl.status = 'confirmed'
               AND NOT EXISTS (
                   SELECT 1 FROM screening_entry se WHERE se.raw_job_id = sl.raw_job_id
               )
             ORDER BY sl.created_at DESC
            """
        )
        rows = await cursor.fetchall()
    return [row_dict for row in rows if (row_dict := _shortlist_mapping(row)) is not None]


async def remove_shortlist(shortlist_id: UUID) -> dict[str, Any] | None:
    row = await get_shortlist_row(shortlist_id)
    if row is None or row["status"] != "confirmed":
        return row  # already removed or absent
    async with connection() as conn:
        await conn.execute(
            "UPDATE shortlist SET status = 'removed', updated_at = now() WHERE id = %s",
            [shortlist_id],
        )
    row["status"] = "removed"
    return row


def _shortlist_mapping(row: tuple) -> dict[str, Any]:
    return {
        "id": row[0],
        "raw_job_id": row[1],
        "ext_id": row[2],
        "title": row[3],
        "company": row[4],
        "city": row[5],
        "salary_text": row[6],
        "status": row[7],
        "note": row[8],
        "added_at": row[9],
        "detail_at": row[10],
        "list_json": row[11],
        "jd_text": row[12],
    }


async def list_company_ext_ids() -> set[str]:
    async with connection() as conn:
        cursor = await conn.execute("SELECT ext_company_id FROM raw_company")
        rows = await cursor.fetchall()
    return {row[0] for row in rows}


async def get_pool_status(raw_job_id: UUID) -> str | None:
    """Latest pool status for a raw job (None when it never entered the pool)."""
    async with connection() as conn:
        cursor = await conn.execute(
            """
            SELECT status FROM shortlist
             WHERE raw_job_id = %s
             ORDER BY created_at DESC
             LIMIT 1
            """,
            [raw_job_id],
        )
        row = await cursor.fetchone()
    return row[0] if row is not None else None


# ---------------------------------------------------------------- screening
# 筛选池：岗位池补全完成（enrich done）后自动流入；进入候选区必须人工确认
# （ARCH-GOV-002）。一个 raw_job 只流转一次（uq_screening_entry_raw_job），
# dismissed 也不回岗位池，避免自动重流转环路。


class ScreeningTransitionInvalid(RuntimeError):
    """Raised when a screening entry status transition is not allowed."""


_ALLOWED_SCREENING_TRANSITIONS: dict[str, set[str]] = {
    "screened": {"candidate", "dismissed"},
    "candidate": {"screened"},
}

_ENTRY_COLUMNS = """
    se.id, se.raw_job_id, r.ext_id, r.title, r.company, r.city,
    r.salary_text, se.status, se.entered_at
"""


async def create_screening_entry(raw_job_id: UUID) -> bool:
    """Move a completed pool job into the screening pool. Idempotent."""
    async with connection() as conn:
        cursor = await conn.execute(
            """
            INSERT INTO screening_entry (raw_job_id)
            VALUES (%s)
            ON CONFLICT (raw_job_id) DO NOTHING
            RETURNING id
            """,
            [raw_job_id],
        )
        row = await cursor.fetchone()
    return row is not None


async def list_screening_entries(
    *, status: str = "screened", limit: int = 50, offset: int = 0
) -> list[dict[str, Any]]:
    async with connection() as conn:
        cursor = await conn.execute(
            f"""
            SELECT {_ENTRY_COLUMNS}
              FROM screening_entry se
              JOIN raw_job r ON r.id = se.raw_job_id
             WHERE se.status = %s
             ORDER BY se.entered_at DESC
             LIMIT %s OFFSET %s
            """,
            [status, min(max(limit, 1), 200), max(offset, 0)],
        )
        rows = await cursor.fetchall()
    return [_entry_mapping(row) for row in rows]


async def get_screening_entry(entry_id: UUID) -> dict[str, Any] | None:
    async with connection() as conn:
        cursor = await conn.execute(
            f"""
            SELECT {_ENTRY_COLUMNS}
              FROM screening_entry se
              JOIN raw_job r ON r.id = se.raw_job_id
             WHERE se.id = %s
            """,
            [entry_id],
        )
        row = await cursor.fetchone()
    return _entry_mapping(row) if row is not None else None


async def update_screening_entry_status(
    entry_id: UUID, *, to_status: str
) -> dict[str, Any] | None:
    """Apply a human-declared transition. None = unknown entry; invalid = raise."""
    existing = await get_screening_entry(entry_id)
    if existing is None:
        return None
    if to_status not in _ALLOWED_SCREENING_TRANSITIONS.get(existing["status"], set()):
        raise ScreeningTransitionInvalid(f"{existing['status']} -> {to_status}")
    async with connection() as conn:
        await conn.execute(
            "UPDATE screening_entry SET status = %s, updated_at = now() WHERE id = %s",
            [to_status, entry_id],
        )
    return await get_screening_entry(entry_id)


def _entry_mapping(row: tuple) -> dict[str, Any]:
    return {
        "id": str(row[0]),
        "raw_job_id": str(row[1]),
        "ext_id": row[2],
        "title": row[3],
        "company": row[4],
        "city": row[5],
        "salary_text": row[6],
        "status": row[7],
        "entered_at": row[8].isoformat() if row[8] else None,
    }
