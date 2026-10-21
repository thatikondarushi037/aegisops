"""Baseline existing incidents schema

Revision ID: 38d847db2cfe
Revises: 
Create Date: 2026-10-20 15:42:32.378158

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '38d847db2cfe'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None




def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("service", sa.String(100), nullable=False),
        sa.Column("error_rate", sa.Float(), nullable=False),
        sa.Column("latency", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("incidents")

