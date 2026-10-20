"""Separate inventory data by area and record audit ownership.

Revision ID: a91f4e2d7c60
Revises: 96eb93c3e519
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a91f4e2d7c60"
down_revision: Union[str, Sequence[str], None] = "96eb93c3e519"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    users_columns = {column["name"] for column in inspector.get_columns("usuarios")}
    if "area" not in users_columns:
        op.add_column("usuarios", sa.Column("area", sa.String(length=50), nullable=False, server_default="Medios"))
        op.execute(sa.text("""
            UPDATE usuarios AS u
            SET area = CASE
                WHEN r.nombre IN ('Super Admin', 'Superadministrador', 'Administrador') THEN 'Todas'
                WHEN r.nombre IN ('Administrador de Logística', 'Admin de Logística') THEN 'Logística'
                ELSE 'Medios'
            END
            FROM roles AS r WHERE r.id = u.rol_id
        """))

    asset_columns = {column["name"] for column in sa.inspect(bind).get_columns("activos")}
    if "area" not in asset_columns:
        op.add_column("activos", sa.Column("area", sa.String(length=50), nullable=False, server_default="Medios"))
        op.create_index("ix_activos_area", "activos", ["area"], unique=False)

    movement_columns = {column["name"] for column in sa.inspect(bind).get_columns("movimientos")}
    if "area" not in movement_columns:
        op.add_column("movimientos", sa.Column("area", sa.String(length=50), nullable=False, server_default="Medios"))
        op.create_index("ix_movimientos_area", "movimientos", ["area"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_movimientos_area", table_name="movimientos")
    op.drop_column("movimientos", "area")
    op.drop_index("ix_activos_area", table_name="activos")
    op.drop_column("activos", "area")
    op.drop_column("usuarios", "area")
