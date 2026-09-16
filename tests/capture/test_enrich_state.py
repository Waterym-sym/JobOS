"""岗位补全状态推导：只按本机数据，队列暂停不投影到岗位（需求 1）。"""

from datetime import UTC, datetime

from services.api.app.main import derive_enrich_state

NOW = datetime.now(UTC)


def state(**overrides: object) -> str:
    base: dict[str, object] = {
        "failed_reason": None,
        "detail_at": NOW,
        "jd_text": "合成 JD",
        "ext_company_id": "synthBrand0001~",
        "company_ids": {"synthBrand0001~"},
    }
    base.update(overrides)
    return derive_enrich_state(**base)  # type: ignore[arg-type]


def test_failed_wins_over_the_stored_data() -> None:
    assert state(failed_reason="failed: extract empty") == "failed"


def test_missing_detail_is_pending() -> None:
    assert state(detail_at=None) == "pending"
    assert state(jd_text=None) == "pending"
    assert state(jd_text="") == "pending"


def test_detail_without_company_snapshot_is_detail_done() -> None:
    assert state(company_ids=set()) == "detail_done"


def test_job_without_company_navigation_is_done() -> None:
    assert state(ext_company_id=None, company_ids=set()) == "done"


def test_completed_job_is_done() -> None:
    assert state() == "done"