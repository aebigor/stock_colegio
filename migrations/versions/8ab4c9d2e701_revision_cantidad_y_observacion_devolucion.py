"""Add return quantity, observation and reviewer audit to physical inventory details.

Revision ID: 8ab4c9d2e701
Revises: f9c0d1e2f345, faa1b2c3d456, a7c4e91f2b30
"""
from alembic import op
import sqlalchemy as sa

revision = "8ab4c9d2e701"
down_revision = "e8340e4d274d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {column["name"] for column in inspector.get_columns("levantamientos_inventario_detalle")}
    if "cantidad_devuelta" not in existing:
        op.add_column("levantamientos_inventario_detalle", sa.Column("cantidad_devuelta", sa.Integer(), nullable=True))
    if "observacion_devolucion" not in existing:
        op.add_column("levantamientos_inventario_detalle", sa.Column("observacion_devolucion", sa.Text(), nullable=True))
    if "devolucion_revisada_por" not in existing:
        op.add_column("levantamientos_inventario_detalle", sa.Column("devolucion_revisada_por", sa.String(length=120), nullable=True))
    if "devolucion_revisada_at" not in existing:
        op.add_column("levantamientos_inventario_detalle", sa.Column("devolucion_revisada_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    existing = {column["name"] for column in sa.inspect(bind).get_columns("levantamientos_inventario_detalle")}
    for name in ("devolucion_revisada_at", "devolucion_revisada_por", "observacion_devolucion", "cantidad_devuelta"):
        if name in existing:
            op.drop_column("levantamientos_inventario_detalle", name)
