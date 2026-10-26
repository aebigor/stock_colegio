"""Add configurable technology protocol to categories and record acceptance on movements.

Revision ID: e5b6c7d8e901
Revises: d4a7e8f9b012
Create Date: 2026-10-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e5b6c7d8e901"
down_revision: Union[str, Sequence[str], None] = "d4a7e8f9b012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    categoria_columns = {column["name"] for column in inspector.get_columns("categorias")}
    if "requiere_protocolo" not in categoria_columns:
        op.add_column(
            "categorias",
            sa.Column("requiere_protocolo", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    movimiento_columns = {column["name"] for column in inspector.get_columns("movimientos")}
    if "protocolo_aceptado" not in movimiento_columns:
        op.add_column(
            "movimientos",
            sa.Column("protocolo_aceptado", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    movimiento_columns = {column["name"] for column in inspector.get_columns("movimientos")}
    if "protocolo_aceptado" in movimiento_columns:
        op.drop_column("movimientos", "protocolo_aceptado")
    categoria_columns = {column["name"] for column in inspector.get_columns("categorias")}
    if "requiere_protocolo" in categoria_columns:
        op.drop_column("categorias", "requiere_protocolo")
