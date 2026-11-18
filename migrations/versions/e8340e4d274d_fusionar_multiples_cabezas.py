"""Fusionar multiples cabezas existentes de inventario físico.

Revision ID: e8340e4d274d
Revises: a7c4e91f2b30, f9c0d1e2f345, faa1b2c3d456
Create Date: 2026-10-27 14:56:16.862807
"""
from typing import Sequence, Union

revision: str = "e8340e4d274d"
down_revision: Union[str, Sequence[str], None] = (
    "a7c4e91f2b30",
    "f9c0d1e2f345",
    "faa1b2c3d456",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Merge revision: no schema changes.
    pass


def downgrade() -> None:
    # Merge revision: no schema changes.
    pass
