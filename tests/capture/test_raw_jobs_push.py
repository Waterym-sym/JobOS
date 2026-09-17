"""Extension list-direct-push: envelope/item validation and idempotency.

Unit part runs anywhere; the persistence part is DB-gated:
    docker compose run --rm -e RUN_DB_TESTS=1 api python -m pytest tests/capture -q
"""

import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from services.api.app import raw_jobs_push


def push_item(ext_id: str = "push-job-0001", **overrides: object) -> dict:
    """A mapListJob-shaped list-tier payload (boss-helper extension)."""
    payload: dict = {
        "source": "boss",
        "ext_id": ext_id,
        "tier": "list",
        "title": "合成岗位A",
        "company": "合成公司A",
        "city": "杭州",
        "district": "西湖区",
        "salary_text": "15-25K",
        "exp_text": "3-5年",
        "degree": "本科",
        "list_tags": ["3-5年", "本科"],
        "boss_name": "招聘官甲",
        "list_url": f"https://www.zhipin.com/job_detail/{ext_id}.html",
        "list_json": {"encryptJobId": ext_id, "jobName": "合成岗位A"},
        "captured_at": "2026-09-17T08:00:00+00:00",
    }
    payload.update(overrides)
    return payload


def push_body(jobs: list) -> dict:
    return {"source": "boss", "tier": "list", "jobs": jobs}


# ----------------------------------------------------------------- parsing


def test_parse_upload_maps_extension_list_payloads() -> None:
    batch_id = uuid4()

    jobs, invalid = raw_jobs_push.parse_upload(
        push_body([push_item(), push_item("push-job-0002")]), batch_id=batch_id
    )

    assert invalid == []
    assert [job.ext_id for job in jobs] == ["push-job-0001", "push-job-0002"]
    first = jobs[0]
    assert first.source == "boss"
    assert first.tier == "list"
    assert first.batch_id == batch_id
    assert first.title == "合成岗位A"
    assert first.company == "合成公司A"
    assert first.district == "西湖区"
    assert first.list_tags == ["3-5年", "本科"]
    assert first.list_json == {"encryptJobId": "push-job-0001", "jobName": "合成岗位A"}
    assert first.captured_at == datetime(2026, 9, 17, 8, 0, tzinfo=UTC)


def test_parse_upload_stamps_the_push_batch_over_client_value() -> None:
    push_batch = uuid4()

    jobs, invalid = raw_jobs_push.parse_upload(
        push_body([push_item(batch_id=str(uuid4()))]), batch_id=push_batch
    )

    assert invalid == []
    assert jobs[0].batch_id == push_batch


def test_parse_upload_reports_invalid_items_per_index_without_aborting() -> None:
    body = push_body(
        [
            "not-an-object",
            push_item("push-job-0002", title=""),
            push_item("push-job-0003", unknown_field="x"),
            push_item("push-job-0004", tier="detail"),
            push_item("push-job-0005"),
        ]
    )

    jobs, invalid = raw_jobs_push.parse_upload(body, batch_id=uuid4())

    assert [job.ext_id for job in jobs] == ["push-job-0005"]
    assert [entry["index"] for entry in invalid] == [0, 1, 2, 3]
    assert all(entry["reason"] for entry in invalid)


@pytest.mark.parametrize(
    "body",
    [
        {"source": "other", "tier": "list", "jobs": []},
        {"source": "boss", "tier": "detail", "jobs": []},
        {"source": "boss", "tier": "list"},
        {"source": "boss", "tier": "list", "jobs": []},
        {"source": "boss", "tier": "list", "jobs": "not-a-list"},
    ],
)
def test_parse_upload_rejects_bad_envelopes(body: dict) -> None:
    with pytest.raises(raw_jobs_push.RawJobsUploadError):
        raw_jobs_push.parse_upload(body, batch_id=uuid4())


def test_parse_upload_enforces_push_cap() -> None:
    oversized = push_body(
        [push_item(f"push-job-{i:04d}") for i in range(raw_jobs_push.MAX_JOBS + 1)]
    )

    with pytest.raises(raw_jobs_push.RawJobsUploadError, match="push cap"):
        raw_jobs_push.parse_upload(oversized, batch_id=uuid4())


# --------------------------------------------------------------- persistence


db_only = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"), reason="set RUN_DB_TESTS=1 to run DB integration tests"
)


@db_only
def test_push_is_idempotent_keeps_first_raw_and_records_provenance() -> None:
    async def scenario() -> None:
        from services.api.app.db import close_pool, connection, init_pool

        await init_pool()
        try:
            async with connection() as conn:
                await conn.execute(
                    "TRUNCATE raw_job, batch_run RESTART IDENTITY CASCADE"
                )

            body = push_body(
                [
                    push_item(),
                    push_item("push-job-0002", salary_text="20-30K·14薪"),
                ]
            )
            first = await raw_jobs_push.run_push(body)
            assert first["total"] == 2
            assert first["created"] == 2
            assert first["merged"] == 0
            assert first["invalid"] == []

            second = await raw_jobs_push.run_push(body)
            assert second["created"] == 0
            assert second["merged"] == 2
            assert second["batch_id"] != first["batch_id"]

            # A third push with altered raw content must not overwrite the
            # first-encounter list_json (raw layer is append/merge only).
            altered = push_body(
                [push_item(list_json={"encryptJobId": "push-job-0001", "jobName": "篡改"})]
            )
            third = await raw_jobs_push.run_push(altered)
            assert third["total"] == 1
            assert third["merged"] == 1

            async with connection() as conn:
                cursor = await conn.execute("SELECT count(*) FROM raw_job")
                assert (await cursor.fetchone())[0] == 2
                cursor = await conn.execute(
                    """
                    SELECT ext_id, low_salary, high_salary, salary_unit, list_json
                      FROM raw_job ORDER BY ext_id
                    """
                )
                rows = await cursor.fetchall()
            assert rows[0][0] == "push-job-0001"
            assert float(rows[0][1]) == 15
            assert float(rows[0][2]) == 25
            assert rows[0][3] == "month_K"
            assert rows[0][4] == {"encryptJobId": "push-job-0001", "jobName": "合成岗位A"}
            assert float(rows[1][1]) == 20
            assert float(rows[1][2]) == 30

            async with connection() as conn:
                cursor = await conn.execute(
                    "SELECT kind, trigger, status FROM batch_run ORDER BY created_at"
                )
                batches = await cursor.fetchall()
            assert [(row[0], row[1], row[2]) for row in batches] == [
                ("list", raw_jobs_push.PUSH_TRIGGER, "completed"),
                ("list", raw_jobs_push.PUSH_TRIGGER, "completed"),
                ("list", raw_jobs_push.PUSH_TRIGGER, "completed"),
            ]
        finally:
            await close_pool()

    asyncio.run(scenario())
