"""account is_paused

Revision ID: c5d18e7a2f40
Revises: 8aea495b270a
Create Date: 2026-11-08 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5d18e7a2f40"
down_revision: Union[str, None] = "8aea495b270a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("uplynk_accounts", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("is_paused", sa.Boolean(), server_default=sa.false(), nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("uplynk_accounts", schema=None) as batch_op:
        batch_op.drop_column("is_paused")
