"""DB integration: clean columns + raw_company merge (protocol #21 §5).

Skipped by default. Run inside the compose network with RUN_DB_TESTS=1.
"""

import asyncio
import os
from datetime import UTC, datetime
from uuid import UUID

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"), reason="set RUN_DB_TESTS=1 to run DB integration tests"
)


async def _scenario() -> None:
    from services.api.app.capture_repo import (
        create_batch_run,
        create_screening_entry,
        list_companies,
        list_raw_jobs,
        upsert_company,
        upsert_raw_job,
    )
    from services.api.app.db import close_pool, connection, init_pool
    from services.api.app.event_models import CompanyPayload, RawJobPayload

    await init_pool()
    try:
        async with connection() as conn:
            await conn.execute("TRUNCATE raw_job, raw_company CASCADE")

        batch = await create_batch_run(kind="list", trigger="console")

        # --- list tier: seven visible fields + clean columns derived server-side
        list_job = RawJobPayload(
            source="boss",
            ext_id="clean-1",
            tier="list",
            title="数据工程师",
            company="乙公司",
            city="杭州",
            district="西湖区",
            salary_text="15-25K",
            exp_text="1-3年",
            degree="本科",
            list_json={"jobName": "数据工程师"},
            batch_id=batch,
            captured_at=datetime.now(UTC),
        )
        assert await upsert_raw_job(list_job) is True

        # --- detail tier fills jd but must not wipe clean columns
        detail_job = RawJobPayload(
            source="boss",
            ext_id="clean-1",
            tier="detail",
            jd_text="JD：负责数据管道",
            batch_id=batch,
        )
        assert await upsert_raw_job(detail_job) is False

        items = await list_raw_jobs(limit=10)
        row = next(i for i in items if i["ext_id"] == "clean-1")
        # Before the enrich funnel the screening marker must stay absent, so
        # the capture center keeps offering "加入岗位池".
        assert row["screening_status"] is None
        assert row["title"] == "数据工程师"
        assert row["company"] == "乙公司"
        assert row["city"] == "杭州"
        assert row["district"] == "西湖区"
        assert row["salary_text"] == "15-25K"
        assert row["low_salary"] == 15.0
        assert row["high_salary"] == 25.0
        assert row["salary_unit"] == "month_K"
        assert row["exp_min_years"] == 1
        assert row["exp_max_years"] == 3
        assert row["degree"] == "本科"
        assert row["degree_code"] == "bachelor"

        async with connection() as conn:
            cursor = await conn.execute(
                "SELECT list_json FROM raw_job WHERE ext_id = %s", ["clean-1"]
            )
            assert (await cursor.fetchone())[0] == {"jobName": "数据工程师"}

        # --- company upsert + merge
        first = CompanyPayload(
            ext_company_id="tok-abc",
            name="乙公司",
            sections={"talent": "双通道晋升", "benefits": "弹性工作"},
            captured_at=datetime.now(UTC),
        )
        assert await upsert_company(first) is True
        second = CompanyPayload(
            ext_company_id="tok-abc",
            name=None,
            sections={"benefits": "六险一金", "business": {"legal": "乙公司"}},
        )
        assert await upsert_company(second) is False

        companies = await list_companies(limit=10)
        comp = next(c for c in companies if c["ext_company_id"] == "tok-abc")
        assert comp["name"] == "乙公司"
        # sections deep-merge: existing keys kept, new keys added
        assert comp["sections"]["talent"] == "双通道晋升"
        assert comp["sections"]["benefits"] == "六险一金"
        assert comp["sections"]["business"] == {"legal": "乙公司"}

        # --- once the job flowed into screening the list marker flips, and the
        # capture center must stop offering a second pool entry for it
        assert await create_screening_entry(UUID(row["id"])) is True
        flowed = next(
            i for i in await list_raw_jobs(limit=10) if i["ext_id"] == "clean-1"
        )
        assert flowed["screening_status"] == "screened"
    finally:
        await close_pool()


def test_clean_columns_and_company_merge() -> None:
    asyncio.run(_scenario())
