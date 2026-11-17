"""Permite registrar altas nuevas de Logística durante la revisión física."""
from alembic import op
import sqlalchemy as sa

revision = "a6c4d8e12f90"
down_revision = "c41e8b9d72a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "levantamientos_inventario_detalle",
        sa.Column("alta_logistica", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "levantamientos_inventario_detalle",
        sa.Column("descripcion", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("levantamientos_inventario_detalle", "descripcion")
    op.drop_column("levantamientos_inventario_detalle", "alta_logistica")
