"""Add durable automatic investigation jobs without backfilling history.

Revision ID: d150b8e2a731
Revises: c14a0e7d921b
"""

from alembic import op
import sqlalchemy as sa

revision = "d150b8e2a731"
down_revision = "c14a0e7d921b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "investigation_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("incident_id", sa.Integer(), sa.ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trigger", sa.String(32), nullable=False, server_default="automatic_initial"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("claim_token", sa.String(36)),
        sa.Column("error_category", sa.String(32)),
        sa.Column("error_message", sa.String(200)),
        sa.Column("investigation_id", sa.Integer(), sa.ForeignKey("investigations.id")),
        sa.UniqueConstraint("incident_id", "trigger", name="uq_investigation_jobs_incident_trigger"),
        sa.UniqueConstraint("investigation_id", name="uq_investigation_jobs_result"),
        sa.CheckConstraint("trigger = 'automatic_initial'", name="ck_investigation_jobs_trigger"),
        sa.CheckConstraint("status IN ('pending','running','completed','failed')", name="ck_investigation_jobs_status"),
        sa.CheckConstraint("attempts >= 0 AND max_attempts BETWEEN 1 AND 10 AND attempts <= max_attempts", name="ck_investigation_jobs_attempts"),
        sa.CheckConstraint("(status = 'completed') = (investigation_id IS NOT NULL)", name="ck_investigation_jobs_result"),
        sa.CheckConstraint("(status = 'running' AND claim_token IS NOT NULL AND lease_expires_at IS NOT NULL) OR (status <> 'running' AND claim_token IS NULL AND lease_expires_at IS NULL)", name="ck_investigation_jobs_claim"),
    )
    op.create_index("ix_investigation_jobs_ready", "investigation_jobs", ["status", "next_attempt_at", "lease_expires_at"])


def downgrade():
    raise RuntimeError("Durable investigation history is forward-only; downgrade is disabled")
