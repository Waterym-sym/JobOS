"""Create the Capture domain foundation.

Revision ID: 20260916_0001
Revises:
Create Date: 2026-09-16
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260916_0001"
down_revision = None
branch_labels = None
depends_on = None

capture_kind = postgresql.ENUM(
    "list", "detail", "chat", name="capture_kind", create_type=False
)
batch_status = postgresql.ENUM(
    "queued",
    "running",
    "completed",
    "aborted",
    "risk_halted",
    "failed",
    name="batch_status",
    create_type=False,
)
salary_unit = postgresql.ENUM(
    "month_K",
    "month_yuan",
    "day",
    "hour",
    "year",
    "unknown",
    name="salary_unit",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    capture_kind.create(bind, checkfirst=True)
    batch_status.create(bind, checkfirst=True)
    salary_unit.create(bind, checkfirst=True)

    op.create_table(
        "capture_source",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.Text(), nullable=False, unique=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "config_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("protocol_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "batch_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("capture_source.id"),
            nullable=False,
        ),
        sa.Column("kind", capture_kind, nullable=False),
        sa.Column("status", batch_status, nullable=False, server_default="queued"),
        sa.Column(
            "stats_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("risk_halted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("trigger", sa.Text(), nullable=False, server_default="manual"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "raw_job",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("capture_source.id"),
            nullable=False,
        ),
        sa.Column("ext_id", sa.Text(), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("batch_run.id")),
        sa.Column("fingerprint", sa.Text(), nullable=False),
        sa.Column("list_json", postgresql.JSONB()),
        sa.Column("detail_json", postgresql.JSONB()),
        sa.Column("list_url", sa.Text()),
        sa.Column("jd_text", sa.Text()),
        sa.Column("title", sa.Text()),
        sa.Column("company", sa.Text()),
        sa.Column("city", sa.Text()),
        sa.Column("salary_text", sa.Text()),
        sa.Column("low_salary", sa.Numeric()),
        sa.Column("high_salary", sa.Numeric()),
        sa.Column("salary_unit", salary_unit, nullable=False, server_default="unknown"),
        sa.Column("exp_text", sa.Text()),
        sa.Column("degree", sa.Text()),
        sa.Column("boss_name", sa.Text()),
        sa.Column("industry", sa.Text()),
        sa.Column("stage", sa.Text()),
        sa.Column("scale", sa.Text()),
        sa.Column("address", sa.Text()),
        sa.Column("company_desc", sa.Text()),
        sa.Column("list_tags", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("skill_tags", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("ats_direct_post", sa.Boolean()),
        sa.Column(
            "boss_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("active_time", sa.Text()),
        sa.Column("active_at", sa.DateTime(timezone=True)),
        sa.Column("list_at", sa.DateTime(timezone=True)),
        sa.Column("detail_at", sa.DateTime(timezone=True)),
        sa.Column("migrated_from", sa.Text()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("source_id", "ext_id", name="uq_raw_job_source_ext_id"),
    )
    op.create_index("idx_rawjob_active_at", "raw_job", ["active_at"])
    op.execute(
        "CREATE INDEX idx_rawjob_fingerprint ON raw_job "
        "USING gin (to_tsvector('simple', fingerprint))"
    )
    op.create_table(
        "ws_event_inbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("capture_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.execute(
        "INSERT INTO capture_source (id, code, display_name) "
        "VALUES ('01993f9c-4c00-7000-8000-000000000001', 'boss', 'BOSS 直聘')"
    )


def downgrade() -> None:
    raise RuntimeError("JobOS migrations are forward-only")
