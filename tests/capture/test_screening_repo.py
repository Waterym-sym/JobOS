"""Screening entry persistence: idempotent flow, pool exclusion, transitions.

DB-gated — set RUN_DB_TESTS=1 only against a disposable database; this TRUNCATEs
capture tables and must never point at the working business database.
"""

import asyncio
import os
from uuid import UUID, uuid4

import pytest

from services.api.app import capture_repo

db_only = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"), reason="set RUN_DB_TESTS=1 to run DB integration tests"
)

BOSS_SOURCE_ID = UUID("01993f9c-4c00-7000-8000-000000000001")


async def seed_pooled_job(ext_id: str = "synth-job-0001") -> UUID:
    from services.api.app.db import connection

    raw_job_id = uuid4()
    async with connection() as conn:
        await conn.execute(
            "TRUNCATE screening_entry, shortlist, raw_job, batch_run RESTART IDENTITY CASCADE"
        )
        await conn.execute(
            """
            INSERT INTO raw_job (id, source_id, ext_id, fingerprint, title, jd_text)
            VALUES (%s, %s, %s, 'synth-fingerprint', '合成岗位一', '合成 JD')
            """,
            [raw_job_id, BOSS_SOURCE_ID, ext_id],
        )
        await conn.execute("INSERT INTO shortlist (raw_job_id) VALUES (%s)", [raw_job_id])
    return raw_job_id


@db_only
def test_flow_is_idempotent_and_removes_the_job_from_the_pool() -> None:
    async def scenario() -> None:
        from services.api.app.db import close_pool, init_pool

        await init_pool()
        try:
            raw_job_id = await seed_pooled_job()

            assert await capture_repo.create_screening_entry(raw_job_id) is True
            # 幂等：重复流转不产生第二行（uq_screening_entry_raw_job）。
            assert await capture_repo.create_screening_entry(raw_job_id) is False

            entries = await capture_repo.list_screening_entries()
            assert [entry["ext_id"] for entry in entries] == ["synth-job-0001"]
            assert entries[0]["status"] == "screened"

            # 已流转岗位不再出现在岗位池（enrich 重启重建据此跳过）。
            assert await capture_repo.list_shortlist() == []
        finally:
            await close_pool()

    asyncio.run(scenario())


@db_only
def test_transitions_follow_the_human_workflow() -> None:
    async def scenario() -> None:
        from services.api.app.db import close_pool, init_pool

        await init_pool()
        try:
            raw_job_id = await seed_pooled_job()
            await capture_repo.create_screening_entry(raw_job_id)
            entry_id = UUID((await capture_repo.list_screening_entries())[0]["id"])

            promoted = await capture_repo.update_screening_entry_status(
                entry_id, to_status="candidate"
            )
            assert promoted is not None and promoted["status"] == "candidate"
            assert await capture_repo.list_screening_entries() == []
            assert len(await capture_repo.list_screening_entries(status="candidate")) == 1

            reverted = await capture_repo.update_screening_entry_status(
                entry_id, to_status="screened"
            )
            assert reverted is not None and reverted["status"] == "screened"

            dismissed = await capture_repo.update_screening_entry_status(
                entry_id, to_status="dismissed"
            )
            assert dismissed is not None and dismissed["status"] == "dismissed"

            # 终态：不再接受任何迁移。
            with pytest.raises(capture_repo.ScreeningTransitionInvalid):
                await capture_repo.update_screening_entry_status(entry_id, to_status="candidate")

            assert await capture_repo.update_screening_entry_status(uuid4(), to_status="candidate") is None
        finally:
            await close_pool()

    asyncio.run(scenario())