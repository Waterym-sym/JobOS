"""Identity tables and ownership boundary for ADR-013.

Revision ID: 20260918_0005
Revises: 20260917_0004
Create Date: 2026-09-18
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection

revision = "20260918_0005"
down_revision = "20260917_0004"
branch_labels = None
depends_on = None

PRIVATE_TABLES = (
    "batch_run",
    "raw_job",
    "raw_company",
    "shortlist",
    "screening_entry",
    "ws_event_inbox",
)


def _legacy_job_unique_name(bind: Connection) -> str:
    """Accept the original live-schema name and the later explicit 0001 name.

    Older installed databases used SQLAlchemy's generated name. Verify the
    constrained columns before dropping anything; unknown schema drift fails.
    """
    known = {"uq_raw_job_source_ext_id", "raw_job_source_id_ext_id_key"}
    matches = [
        item["name"]
        for item in sa.inspect(bind).get_unique_constraints("raw_job")
        if item["name"] in known and item["column_names"] == ["source_id", "ext_id"]
    ]
    if len(matches) != 1:
        raise RuntimeError("raw_job legacy unique constraint is missing or ambiguous")
    return matches[0]


def upgrade() -> None:
    op.create_table(
        "account_user",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("role IN ('seeker', 'recruiter')", name="ck_account_user_role"),
    )
    op.create_table(
        "account_session",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("account_user.id"), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("csrf_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "account_invite",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("account_user.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("role IN ('seeker', 'recruiter')", name="ck_account_invite_role"),
    )
    op.create_table(
        "account_reset",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("account_user.id"), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("account_user.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "account_profile",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("account_user.id"), primary_key=True),
        sa.Column("basic_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("education_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("preference_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("onboarding_step", sa.Text(), nullable=False, server_default="entry"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "resume_file",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("account_user.id"), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False, unique=True),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="stored"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('stored', 'parsing', 'parsed', 'failed')", name="ck_resume_file_status"),
    )

    # NULL means legacy data awaits the server-side first-admin bootstrap.
    # Public mode must refuse startup while any private row is unassigned.
    for table in PRIVATE_TABLES:
        op.add_column(table, sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("account_user.id")))
        op.create_index(f"ix_{table}_owner", table, ["owner_user_id"])
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_owner_isolation ON {table} "
            "USING (owner_user_id = NULLIF(current_setting('app.user_id', true), '')::uuid) "
            "WITH CHECK (owner_user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)"
        )

    op.drop_constraint(_legacy_job_unique_name(op.get_bind()), "raw_job", type_="unique")
    op.create_unique_constraint(
        "uq_raw_job_owner_source_ext", "raw_job", ["owner_user_id", "source_id", "ext_id"]
    )
    op.drop_constraint("uq_raw_company_source_ext", "raw_company", type_="unique")
    op.create_unique_constraint(
        "uq_raw_company_owner_source_ext", "raw_company", ["owner_user_id", "source_id", "ext_company_id"]
    )


def downgrade() -> None:
    bind = op.get_bind()
    users = bind.scalar(sa.text("SELECT count(*) FROM account_user"))
    if users is not None and users > 1:
        raise RuntimeError("multi-user downgrade requires explicit export and data reconciliation")

    op.drop_constraint("uq_raw_company_owner_source_ext", "raw_company", type_="unique")
    op.create_unique_constraint(
        "uq_raw_company_source_ext", "raw_company", ["source_id", "ext_company_id"]
    )
    op.drop_constraint("uq_raw_job_owner_source_ext", "raw_job", type_="unique")
    op.create_unique_constraint("uq_raw_job_source_ext_id", "raw_job", ["source_id", "ext_id"])
    for table in reversed(PRIVATE_TABLES):
        op.execute(f"DROP POLICY {table}_owner_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.drop_index(f"ix_{table}_owner", table_name=table)
        op.drop_column(table, "owner_user_id")
    op.drop_table("resume_file")
    op.drop_table("account_profile")
    op.drop_table("account_reset")
    op.drop_table("account_invite")
    op.drop_table("account_session")
    op.drop_table("account_user")
