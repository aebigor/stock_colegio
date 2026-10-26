"""Track responsible holder and origin location for loans.

Revision ID: f7a9b0c1d234
Revises: e5b6c7d8e901
Create Date: 2026-10-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f7a9b0c1d234"
down_revision: Union[str, Sequence[str], None] = "e5b6c7d8e901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    activos = {c["name"] for c in inspector.get_columns("activos")}
    if "responsable_id" not in activos:
        op.add_column("activos", sa.Column("responsable_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_activos_responsable_persona",
            "activos",
            "personas",
            ["responsable_id"],
            ["id"],
        )
        op.create_index("ix_activos_responsable_id", "activos", ["responsable_id"])

    activos = {c["name"] for c in sa.inspect(bind).get_columns("activos")}
    if "tenedor_id" not in activos:
        op.add_column("activos", sa.Column("tenedor_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_activos_tenedor_persona",
            "activos",
            "personas",
            ["tenedor_id"],
            ["id"],
        )
        op.create_index("ix_activos_tenedor_id", "activos", ["tenedor_id"])

    movimientos = {c["name"] for c in sa.inspect(bind).get_columns("movimientos")}
    if "ubicacion_origen_id" not in movimientos:
        op.add_column("movimientos", sa.Column("ubicacion_origen_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_movimientos_ubicacion_origen",
            "movimientos",
            "ubicaciones",
            ["ubicacion_origen_id"],
            ["id"],
        )
        op.create_index("ix_movimientos_ubicacion_origen_id", "movimientos", ["ubicacion_origen_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    movimientos = {c["name"] for c in inspector.get_columns("movimientos")}
    if "ubicacion_origen_id" in movimientos:
        op.drop_index("ix_movimientos_ubicacion_origen_id", table_name="movimientos")
        op.drop_constraint("fk_movimientos_ubicacion_origen", "movimientos", type_="foreignkey")
        op.drop_column("movimientos", "ubicacion_origen_id")

    activos = {c["name"] for c in sa.inspect(bind).get_columns("activos")}
    if "tenedor_id" in activos:
        op.drop_index("ix_activos_tenedor_id", table_name="activos")
        op.drop_constraint("fk_activos_tenedor_persona", "activos", type_="foreignkey")
        op.drop_column("activos", "tenedor_id")

    activos = {c["name"] for c in sa.inspect(bind).get_columns("activos")}
    if "responsable_id" in activos:
        op.drop_index("ix_activos_responsable_id", table_name="activos")
        op.drop_constraint("fk_activos_responsable_persona", "activos", type_="foreignkey")
        op.drop_column("activos", "responsable_id")
