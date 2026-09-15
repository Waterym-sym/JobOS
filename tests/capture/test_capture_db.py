"""End-to-end persistence tests against PostgreSQL (protocol #21 §5/§10).

Skipped by default. Run inside the compose network:
    docker compose run --rm -e RUN_DB_TESTS=1 api python -m pytest tests/capture -q
"""

import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"), reason="set RUN_DB_TESTS=1 to run DB integration tests"
)


async def _scenario() -> None:
    from services.api.app.capture_repo import (
        complete_batch,
        create_batch_run,
        get_batch,
        reserve_event,
        upsert_raw_job,
    )
    from services.api.app.db import close_pool, connection, init_pool
    from services.api.app.event_models import RawJobPayload

    await init_pool()
    try:
        async with connection() as conn:
            await conn.execute(
                "TRUNCATE raw_job, batch_run RESTART IDENTITY CASCADE"
            )

        batch = await create_batch_run(kind="list", trigger="console")
        assert batch.version == 7

        list_job = RawJobPayload(
            source="boss",
            ext_id="it-1",
            tier="list",
            title="后端工程师",
            company="甲公司",
            salary_text="15-25K",
            list_tags=["经验不限", "本科"],
            list_json={"raw": "list"},
            batch_id=batch,
            captured_at=datetime.now(UTC),
        )
        assert await upsert_raw_job(list_job) is True
        # Same power key in the same batch -> duplicate, server counts it.
        assert await upsert_raw_job(list_job) is False

        detail_job = RawJobPayload(
            source="boss",
            ext_id="it-1",
            tier="detail",
            jd_text="JD 正文：做后端系统",
            skill_tags=["Python", "PostgreSQL"],
            industry="互联网",
            stage="B 轮",
            scale="100-499 人",
            detail_json={"raw": "detail"},
            boss_json={"name": "BOSS 李", "title": "招聘总监"},
            batch_id=batch,
        )
        assert await upsert_raw_job(detail_job) is False

        stats = await complete_batch(
            batch,
            status="completed",
            stats={"success": 1, "dup": 0, "risk_halted": False},
        )
        # dup must be server-authoritative even if the extension sent 0.
        assert stats["dup"] == 1

        stored = await get_batch(batch)
        assert stored is not None
        assert stored["status"] == "completed"

        async with connection() as conn:
            cursor = await conn.execute(
                """
                SELECT id, title, company, salary_text, jd_text,
                       list_json, detail_json, list_tags, skill_tags,
                       boss_json, industry, stage,
                       list_at IS NOT NULL, detail_at IS NOT NULL,
                       fingerprint
                  FROM raw_job WHERE ext_id = %s
                """,
                ["it-1"],
            )
            row = await cursor.fetchone()
        assert row is not None
        assert row[0].version == 7
        assert row[1] == "后端工程师"
        assert row[2] == "甲公司"
        assert row[3] == "15-25K"
        assert row[4] == "JD 正文：做后端系统"
        # Original JSON blobs are preserved independently, never overwritten
        # by the other tier.
        assert row[5] == {"raw": "list"}
        assert row[6] == {"raw": "detail"}
        assert row[7] == ["经验不限", "本科"]
        assert row[8] == ["Python", "PostgreSQL"]
        assert row[9]["name"] == "BOSS 李"
        assert row[9]["title"] == "招聘总监"
        assert row[10] == "互联网"
        assert row[11] == "B 轮"
        assert row[12] is True  # list_at
        assert row[13] is True  # detail_at

        # A repeated list upsert after detail must not revert the fingerprint
        # computed with jd_text.
        detail_fingerprint = row[14]
        assert await upsert_raw_job(list_job) is False
        async with connection() as conn:
            cursor = await conn.execute(
                "SELECT fingerprint FROM raw_job WHERE ext_id = %s", ["it-1"]
            )
            assert (await cursor.fetchone())[0] == detail_fingerprint

        event_id = uuid4()
        assert await reserve_event(event_id, "job.captured", batch) is True
        assert await reserve_event(event_id, "job.captured", batch) is False
    finally:
        await close_pool()


def test_list_detail_merge_and_dup_count() -> None:
    asyncio.run(_scenario())
