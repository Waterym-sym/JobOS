"""Exporter JSON import: mapping, validation and idempotency.

Unit part runs anywhere; the persistence part is DB-gated:
    docker compose run --rm -e RUN_DB_TESTS=1 api python -m pytest tests/capture -q
"""

import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

from services.api.app import job_import

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "exporter-sample.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_parse_export_maps_exporter_fields() -> None:
    batch_id = uuid4()

    jobs, invalid = job_import.parse_export(load_fixture(), batch_id=batch_id)

    assert [job.ext_id for job in jobs] == ["synth-job-0001", "synth-job-0002"]
    assert len(invalid) == 1
    assert invalid[0]["index"] == 2
    assert invalid[0]["reason"] == "missing title or company"

    first = jobs[0]
    assert first.tier == "list"
    assert first.batch_id == batch_id
    assert first.title == "合成岗位一 · 前端工程师"
    assert first.company == "合成科技有限公司"
    assert first.district == "西湖区"
    assert first.salary_text == "15-25K"
    assert first.exp_text == "3-5年"
    assert first.degree == "本科"
    assert first.list_tags == ["3-5年", "本科"]
    assert first.skill_tags == ["React", "TypeScript"]
    assert first.stage == "B轮"
    assert first.industry == "企业服务"
    assert first.scale == "100-499人"
    assert first.boss_name == "合成招聘官"
    assert first.boss_json.name == "合成招聘官"
    assert first.boss_json.title == "HRBP"
    assert first.ats_direct_post is False
    assert first.list_url is not None and first.list_url.startswith("https://www.zhipin.com/")
    # The whole exporter item is preserved verbatim for audit + enrich navigation.
    assert first.list_json is not None
    assert first.list_json["securityId"] == "synthSecurityId0001"
    assert first.list_json["raw"]["encryptBrandId"] == "synthBrand0001~"


def test_parse_export_rejects_non_exporter_documents() -> None:
    with pytest.raises(job_import.ExportFormatError):
        job_import.parse_export({"items": []}, batch_id=uuid4())


def test_load_export_enforces_the_entry_cap() -> None:
    oversized = {"jobs": [{"jobId": f"j{i}"} for i in range(job_import.MAX_JOBS + 1)]}
    with pytest.raises(job_import.ExportFormatError, match="import cap"):
        job_import.load_export(json.dumps(oversized).encode("utf-8"))


def test_load_export_rejects_non_json_payloads() -> None:
    with pytest.raises(job_import.ExportFormatError, match="valid UTF-8 JSON"):
        job_import.load_export(b"not json")


# --------------------------------------------------------------- persistence

db_only = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"), reason="set RUN_DB_TESTS=1 to run DB integration tests"
)


@db_only
def test_import_is_idempotent_and_cleans_server_side() -> None:
    async def scenario() -> None:
        from services.api.app.db import close_pool, connection, init_pool

        await init_pool()
        try:
            async with connection() as conn:
                await conn.execute("TRUNCATE raw_job, batch_run RESTART IDENTITY CASCADE")

            data = FIXTURE.read_bytes()
            first = await job_import.run_import(data)
            assert first["total"] == 2
            assert first["created"] == 2
            assert first["merged"] == 0
            assert len(first["invalid"]) == 1

            second = await job_import.run_import(data)
            assert second["created"] == 0
            assert second["merged"] == 2

            async with connection() as conn:
                cursor = await conn.execute(
                    """
                    SELECT ext_id, salary_text, low_salary, high_salary, salary_unit,
                           degree, degree_code, list_json
                      FROM raw_job ORDER BY ext_id
                    """
                )
                rows = await cursor.fetchall()
            assert len(rows) == 2
            assert rows[0][1] == "15-25K"
            assert float(rows[0][2]) == 15
            assert float(rows[0][3]) == 25
            assert rows[0][4] == "month_K"
            assert rows[0][5] == "本科"
            assert rows[0][6] == "bachelor"
            # list_json survives a re-import untouched.
            assert rows[0][7]["securityId"] == "synthSecurityId0001"

            # Import batches are list-tier provenance runs distinguished by trigger.
            async with connection() as conn:
                cursor = await conn.execute(
                    "SELECT kind, trigger, status FROM batch_run ORDER BY created_at"
                )
                batches = await cursor.fetchall()
            assert [(row[0], row[1], row[2]) for row in batches] == [
                ("list", job_import.IMPORT_TRIGGER, "completed"),
                ("list", job_import.IMPORT_TRIGGER, "completed"),
            ]
        finally:
            await close_pool()

    asyncio.run(scenario())