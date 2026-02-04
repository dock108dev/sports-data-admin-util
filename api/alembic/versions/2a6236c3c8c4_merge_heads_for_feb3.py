"""merge_heads_for_feb3

Revision ID: 2a6236c3c8c4
Revises: 20260131_000002, 20260203_000003
Create Date: 2026-02-03 19:20:05.118656

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2a6236c3c8c4'
down_revision: Union[str, Sequence[str], None] = ('20260131_000002', '20260203_000003')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
