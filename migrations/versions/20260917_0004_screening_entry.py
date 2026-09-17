"""Screening entry (筛选池 → 候选区流转).

补全完成的岗位池岗位自动流入筛选池（screened），进入候选区必须人工确认
（candidate），忽略为终态（dismissed）。一个 raw_job 只流转一次，避免自动
重流转环路。本对象为本期新增，不属于 v1.0 baseline 骨架，故只存在于迁移中。

Revision ID: 20260917_0004
Revises: 20260916_0003
Create Date: 2026-09-17
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260917_0004"
down_revision = "20260916_0003"
branch_labels = None
depends_on = None

screening_entry_status = postgresql.ENUM(
    "screened", "candidate", "dismissed", name="screening_entry_status", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    screening_entry_status.create(bind, checkfirst=True)

    op.create_table(
        "screening_entry",
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
        sa.Column(
            "status",
            screening_entry_status,
            nullable=False,
            server_default="screened",
        ),
        # 评分引擎（Prompt/权重经人审后）的快照槽；本期始终为空。
        sa.Column("assessment_json", postgresql.JSONB()),
        sa.Column(
            "entered_at",
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
        # 一个岗位只流转一次：dismissed 也不回岗位池，杜绝自动重流转环路。
        sa.UniqueConstraint("raw_job_id", name="uq_screening_entry_raw_job"),
    )
    op.create_index(
        "ix_screening_entry_status_entered",
        "screening_entry",
        ["status", sa.text("entered_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_screening_entry_status_entered", table_name="screening_entry")
    op.drop_table("screening_entry")
    screening_entry_status.drop(op.get_bind(), checkfirst=True)
