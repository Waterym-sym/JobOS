"""Destructive migration roundtrip: only an empty, explicitly named test database."""

import os
from pathlib import Path
from urllib.parse import urlparse

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = os.getenv("DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_MIGRATION_ROUNDTRIP") != "1",
    reason="set RUN_MIGRATION_ROUNDTRIP=1 with an empty jobos_migration_test database",
)


def test_alembic_upgrade_downgrade_upgrade_roundtrip() -> None:
    if urlparse(DATABASE_URL).path != "/jobos_migration_test":
        pytest.fail("roundtrip is restricted to database jobos_migration_test")

    engine = sa.create_engine(DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1))
    try:
        inspector = sa.inspect(engine)
        if inspector.get_table_names():
            pytest.fail("roundtrip requires a completely empty disposable database")

        config = Config(str(ROOT / "alembic.ini"))
        command.upgrade(config, "head")
        inspector = sa.inspect(engine)
        assert {"capture_source", "batch_run", "raw_job", "raw_company",
                "shortlist", "screening_entry", "ws_event_inbox",
                "account_user", "account_session", "account_profile", "resume_file"} <= set(
            inspector.get_table_names()
        )
        assert "owner_user_id" in {column["name"] for column in inspector.get_columns("raw_job")}

        command.downgrade(config, "20260916_0001")
        inspector = sa.inspect(engine)
        assert "raw_company" not in inspector.get_table_names()
        assert "screening_entry" not in inspector.get_table_names()
        raw_columns = {column["name"] for column in inspector.get_columns("raw_job")}
        assert {"list_url", "boss_name", "company_desc"} <= raw_columns
        assert {"district", "exp_min_years", "exp_max_years", "degree_code"}.isdisjoint(
            raw_columns
        )

        command.downgrade(config, "base")
        inspector = sa.inspect(engine)
        assert set(inspector.get_table_names()) <= {"alembic_version"}
        with engine.connect() as connection:
            assert connection.scalar(sa.text("SELECT count(*) FROM alembic_version")) == 0
            enum_names = set(
                connection.execute(sa.text("SELECT typname FROM pg_type WHERE typtype = 'e'"))
                .scalars()
                .all()
            )
        assert {
            "capture_kind", "batch_status", "salary_unit",
            "shortlist_status", "screening_entry_status",
        }.isdisjoint(enum_names)

        command.upgrade(config, "head")
        inspector = sa.inspect(engine)
        assert "screening_entry" in inspector.get_table_names()
        assert "account_user" in inspector.get_table_names()
        with engine.begin() as connection:
            connection.execute(sa.text("""
                INSERT INTO account_user (id, email, password_hash, role, display_name)
                VALUES
                ('00000000-0000-4000-8000-000000000001', 'a@example.test', 'test', 'seeker', 'A'),
                ('00000000-0000-4000-8000-000000000002', 'b@example.test', 'test', 'seeker', 'B')
            """))
        with pytest.raises(RuntimeError, match="multi-user downgrade"):
            command.downgrade(config, "20260917_0004")
        with engine.begin() as connection:
            assert connection.scalar(sa.text("SELECT version_num FROM alembic_version")) == "20260918_0005"
            connection.execute(sa.text("DELETE FROM account_user"))
        command.downgrade(config, "20260917_0004")
        with engine.begin() as connection:
            connection.execute(sa.text(
                "ALTER TABLE raw_job RENAME CONSTRAINT uq_raw_job_source_ext_id "
                "TO raw_job_source_id_ext_id_key"
            ))
        command.upgrade(config, "head")
        assert "owner_user_id" in {
            column["name"] for column in sa.inspect(engine).get_columns("raw_job")
        }
        command.downgrade(config, "20260917_0004")
        legacy_keys = sa.inspect(engine).get_unique_constraints("raw_job")
        assert any(item["column_names"] == ["source_id", "ext_id"] for item in legacy_keys)
    finally:
        engine.dispose()
