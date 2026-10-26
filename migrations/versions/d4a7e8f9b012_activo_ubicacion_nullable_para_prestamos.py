"""Allow an asset to have no physical location while it is loaned.

Revision ID: d4a7e8f9b012
Revises: c3f8b260f092
Create Date: 2026-10-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d4a7e8f9b012"
down_revision: Union[str, Sequence[str], None] = "c3f8b260f092"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "activos",
        "ubicacion_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    # Only safe if no active loan currently has a NULL location.
    bind = op.get_bind()
    pendientes = bind.execute(sa.text("SELECT COUNT(*) FROM activos WHERE ubicacion_id IS NULL")).scalar()
    if pendientes:
        raise RuntimeError("No se puede revertir: existen activos prestados sin ubicación física.")
    op.alter_column(
        "activos",
        "ubicacion_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
