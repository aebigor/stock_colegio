"""Registrar unidades nuevas detectadas como sobrantes en devolución."""
from alembic import op
import sqlalchemy as sa

revision = "c41e8b9d72a6"
down_revision = "8ab4c9d2e701"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "levantamientos_inventario_detalle",
        sa.Column("cantidad_sobrante", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("levantamientos_inventario_detalle", "cantidad_sobrante")
