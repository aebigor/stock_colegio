"""Permite registrar altas nuevas de Logística durante la revisión física."""
from alembic import op
import sqlalchemy as sa

revision = "a6c4d8e12f90"
down_revision = "c41e8b9d72a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = {column["name"] for column in sa.inspect(bind).get_columns("levantamientos_inventario_detalle")}
    if "alta_logistica" not in existing:
        op.add_column(
            "levantamientos_inventario_detalle",
            sa.Column("alta_logistica", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )
    if "descripcion" not in existing:
        op.add_column(
            "levantamientos_inventario_detalle",
            sa.Column("descripcion", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    existing = {column["name"] for column in sa.inspect(bind).get_columns("levantamientos_inventario_detalle")}
    if "descripcion" in existing:
        op.drop_column("levantamientos_inventario_detalle", "descripcion")
    if "alta_logistica" in existing:
        op.drop_column("levantamientos_inventario_detalle", "alta_logistica")
