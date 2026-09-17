"""List-tier clean columns + raw_company (gongsi snapshots).

Revision ID: 20260916_0002
Revises: 20260916_0001
Create Date: 2026-09-16
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260916_0002"
down_revision = "20260916_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Columns from the retired SQL-runner era that the Alembic baseline does
    # not carry; environments built purely from Alembic need them because the
    # capture repo upsert writes them.
    op.execute("ALTER TABLE raw_job ADD COLUMN IF NOT EXISTS list_url text")
    op.execute("ALTER TABLE raw_job ADD COLUMN IF NOT EXISTS boss_name text")
    op.execute("ALTER TABLE raw_job ADD COLUMN IF NOT EXISTS company_desc text")

    # Clean columns derived server-side from raw text (protocol #21 §5).
    op.execute("ALTER TABLE raw_job ADD COLUMN IF NOT EXISTS district text")
    op.execute("ALTER TABLE raw_job ADD COLUMN IF NOT EXISTS exp_min_years integer")
    op.execute("ALTER TABLE raw_job ADD COLUMN IF NOT EXISTS exp_max_years integer")
    op.execute("ALTER TABLE raw_job ADD COLUMN IF NOT EXISTS degree_code text")

    # Company profile snapshots captured from /gongsi/ pages.
    op.create_table(
        "raw_company",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("capture_source.id"),
            nullable=False,
        ),
        sa.Column("ext_company_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text()),
        sa.Column(
            "sections", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("raw_json", postgresql.JSONB()),
        sa.Column(
            "first_seen_at",
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
        sa.UniqueConstraint("source_id", "ext_company_id", name="uq_raw_company_source_ext"),
    )


def downgrade() -> None:
    op.drop_table("raw_company")
    op.drop_column("raw_job", "degree_code")
    op.drop_column("raw_job", "exp_max_years")
    op.drop_column("raw_job", "exp_min_years")
    op.drop_column("raw_job", "district")
    # list_url, boss_name and company_desc belong to 0001; preserve them.
