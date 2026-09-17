"""Shortlist (岗位池) table.

Mirrors contracts/db/0001_baseline.skeleton.sql §二（shortlist）。
入池即人工确认进入候选区，同时是 enrich（详情/公司按需补全）的排队依据。

Revision ID: 20260916_0003
Revises: 20260916_0002
Create Date: 2026-09-16
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260916_0003"
down_revision = "20260916_0002"
branch_labels = None
depends_on = None

shortlist_status = postgresql.ENUM(
    "confirmed", "removed", name="shortlist_status", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    shortlist_status.create(bind, checkfirst=True)

    op.create_table(
        "shortlist",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "raw_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("raw_job.id"),
            nullable=False,
        ),
        # job_id / match_result_id 的 FK 待 v1.0 既有表迁入后补（骨架契约注释）。
        sa.Column("job_id", postgresql.UUID(as_uuid=True)),
        sa.Column("match_result_id", postgresql.UUID(as_uuid=True)),
        sa.Column("status", shortlist_status, nullable=False, server_default="confirmed"),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("note", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # 一个岗位同一时刻仅一条有效 confirmed（removed 后可重新入池）。
    op.create_index(
        "uq_shortlist_confirmed_raw_job",
        "shortlist",
        ["raw_job_id"],
        unique=True,
        postgresql_where=sa.text("status = 'confirmed'"),
    )


def downgrade() -> None:
    op.drop_index("uq_shortlist_confirmed_raw_job", table_name="shortlist")
    op.drop_table("shortlist")
    shortlist_status.drop(op.get_bind(), checkfirst=True)
