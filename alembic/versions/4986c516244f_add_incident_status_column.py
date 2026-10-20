"""Add incident status column

Revision ID: 4986c516244f
Revises: 38d847db2cfe
Create Date: 2026-10-20 16:03:54.565547

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4986c516244f'
down_revision: Union[str, Sequence[str], None] = '38d847db2cfe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade() -> None:
        op.add_column(
            "incidents",
            sa.Column(
                "status",
                sa.String(length=20),
                server_default="open",
                nullable=False
            )
        )
    # ### end Alembic commands ###


def downgrade() -> None:
    op.drop_column("incidents", "status")
