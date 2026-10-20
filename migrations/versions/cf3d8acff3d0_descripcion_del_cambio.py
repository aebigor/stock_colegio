"""descripcion del cambio

Revision ID: cf3d8acff3d0
Revises: 1dcd8f554044
Create Date: 2026-07-28 11:55:13.329006

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cf3d8acff3d0'
down_revision: Union[str, Sequence[str], None] = '1dcd8f554044'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op: the user/role schema and indexes are already created by e870/1dcd.

    This historical revision accidentally tried to create ``usuarios`` a second
    time. Keeping the revision in the chain preserves databases already stamped
    with it while allowing a clean install to proceed.
    """
    pass


def downgrade() -> None:
    """No-op; schema belongs to previous revisions."""
    pass
