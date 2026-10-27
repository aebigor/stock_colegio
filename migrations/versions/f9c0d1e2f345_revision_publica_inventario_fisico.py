"""Add public teacher links and logistics verification to physical inventory."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "f9c0d1e2f345"
down_revision: Union[str, Sequence[str], None] = "f8b9c0d1e234"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("levantamientos_inventario", sa.Column("public_token", sa.String(96), nullable=True))
    op.create_index("ix_levantamientos_inventario_public_token", "levantamientos_inventario", ["public_token"], unique=True)
    # Existing records receive unique tokens through PostgreSQL.
    op.execute("UPDATE levantamientos_inventario SET public_token = md5(random()::text || clock_timestamp()::text || id::text) WHERE public_token IS NULL")
    op.alter_column("levantamientos_inventario", "public_token", nullable=False)
    op.add_column("levantamientos_inventario_detalle", sa.Column("verificado_logistica", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("levantamientos_inventario_detalle", sa.Column("revisado_por", sa.String(120), nullable=True))
    op.add_column("levantamientos_inventario_detalle", sa.Column("revisado_at", sa.DateTime(timezone=True), nullable=True))

def downgrade() -> None:
    op.drop_column("levantamientos_inventario_detalle", "revisado_at")
    op.drop_column("levantamientos_inventario_detalle", "revisado_por")
    op.drop_column("levantamientos_inventario_detalle", "verificado_logistica")
    op.drop_index("ix_levantamientos_inventario_public_token", table_name="levantamientos_inventario")
    op.drop_column("levantamientos_inventario", "public_token")
