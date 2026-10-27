"""add signature to physical inventory reviews

Revision ID: faa1b2c3d456
Revises: f7a9b0c1d234
Create Date: 2026-10-27
"""
from alembic import op
import sqlalchemy as sa

revision = "faa1b2c3d456"
down_revision = "f7a9b0c1d234"
branch_labels = None
depends_on = None

def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("levantamientos_inventario")}
    if "firma" not in cols:
        op.add_column("levantamientos_inventario", sa.Column("firma", sa.Text(), nullable=True))

def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("levantamientos_inventario")}
    if "firma" in cols:
        op.drop_column("levantamientos_inventario", "firma")
