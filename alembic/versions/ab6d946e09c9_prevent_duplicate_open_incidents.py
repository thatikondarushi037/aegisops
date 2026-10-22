"""Prevent duplicate open incidents

Revision ID: ab6d946e09c9
Revises: 4986c516244f
Create Date: 2026-10-23 01:12:01.482874

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ab6d946e09c9'
down_revision: Union[str, Sequence[str], None] = '4986c516244f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None




def upgrade() -> None:
    op.create_index(
        "uq_incidents_open_service",
        "incidents",
        ["service"],
        unique=True,
        postgresql_where=sa.text("status = 'open'")
    )


def downgrade() -> None:
    op.drop_index(
        "uq_incidents_open_service",
        table_name="incidents"
    )

