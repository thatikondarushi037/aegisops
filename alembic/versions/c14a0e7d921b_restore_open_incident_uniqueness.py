"""Restore open incident uniqueness without changing incident history.

Revision ID: c14a0e7d921b
Revises: f52e0932e446
"""

from alembic import context, op
import sqlalchemy as sa

revision = "c14a0e7d921b"
down_revision = "f52e0932e446"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("This repair requires an online duplicate preflight")

    connection = op.get_bind()
    # Hold until commit: prevent inserts/updates between preflight and index
    # creation while allowing ordinary readers. PostgreSQL DDL is transactional.
    connection.execute(sa.text("LOCK TABLE incidents IN SHARE ROW EXCLUSIVE MODE"))
    duplicates = connection.execute(sa.text(
        "SELECT array_agg(id ORDER BY id) AS ids FROM incidents "
        "WHERE status = 'open' GROUP BY service HAVING count(*) > 1"
    )).scalars().all()
    if duplicates:
        raise RuntimeError(
            "Cannot restore uq_incidents_open_service; duplicate open incident "
            f"ID groups: {duplicates}. No historical records were changed."
        )

    op.create_index(
        "uq_incidents_open_service",
        "incidents",
        ["service"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )


def downgrade() -> None:
    raise RuntimeError("This integrity repair is forward-only; downgrade is disabled")
