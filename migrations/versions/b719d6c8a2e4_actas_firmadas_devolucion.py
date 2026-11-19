"""Conserva firmas y detalle de cada acta de devolución.

Revision ID: b719d6c8a2e4
Revises: a6c4d8e12f90
"""
from alembic import op
import sqlalchemy as sa

revision = "b719d6c8a2e4"
down_revision = "a6c4d8e12f90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "levantamientos_inventario_devoluciones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("levantamiento_id", sa.Integer(), nullable=False),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("area", sa.String(length=50), nullable=False),
        sa.Column("firma_docente", sa.Text(), nullable=False),
        sa.Column("docente_nombre", sa.String(length=180), nullable=True),
        sa.Column("registrado_por", sa.String(length=120), nullable=False),
        sa.Column("total_entregadas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_recibidas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_nuevas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_faltantes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("detalles_resumen", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["levantamiento_id"], ["levantamientos_inventario.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_levantamientos_inventario_devoluciones_levantamiento_id",
        "levantamientos_inventario_devoluciones",
        ["levantamiento_id"],
    )
    op.create_index(
        "ix_levantamientos_inventario_devoluciones_empresa_id",
        "levantamientos_inventario_devoluciones",
        ["empresa_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_levantamientos_inventario_devoluciones_empresa_id", table_name="levantamientos_inventario_devoluciones")
    op.drop_index("ix_levantamientos_inventario_devoluciones_levantamiento_id", table_name="levantamientos_inventario_devoluciones")
    op.drop_table("levantamientos_inventario_devoluciones")
