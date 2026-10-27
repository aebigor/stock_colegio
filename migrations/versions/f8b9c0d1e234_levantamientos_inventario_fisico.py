"""Create physical inventory surveys and findings."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "f8b9c0d1e234"
down_revision: Union[str, Sequence[str], None] = "f7a9b0c1d234"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "levantamientos_inventario",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("ubicacion_id", sa.Integer(), sa.ForeignKey("ubicaciones.id"), nullable=False),
        sa.Column("responsable_id", sa.Integer(), sa.ForeignKey("personas.id"), nullable=True),
        sa.Column("estado", sa.String(30), nullable=False, server_default="Borrador"),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("creado_por", sa.String(120), nullable=False),
        sa.Column("aprobado_por", sa.String(120), nullable=True),
        sa.Column("enviado_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("aprobado_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("area", sa.String(50), nullable=False, server_default="Medios"),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_levantamientos_inventario_id", "levantamientos_inventario", ["id"])
    op.create_index("ix_levantamientos_inventario_empresa_id", "levantamientos_inventario", ["empresa_id"])
    op.create_index("ix_levantamientos_inventario_area", "levantamientos_inventario", ["area"])

    op.create_table(
        "levantamientos_inventario_detalle",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("levantamiento_id", sa.Integer(), sa.ForeignKey("levantamientos_inventario.id", ondelete="CASCADE"), nullable=False),
        sa.Column("activo_id", sa.Integer(), sa.ForeignKey("activos.id"), nullable=True),
        sa.Column("categoria_id", sa.Integer(), sa.ForeignKey("categorias.id"), nullable=True),
        sa.Column("nombre", sa.String(180), nullable=False),
        sa.Column("referencia", sa.String(180), nullable=True),
        sa.Column("serial", sa.String(150), nullable=True),
        sa.Column("marca", sa.String(100), nullable=True),
        sa.Column("modelo", sa.String(100), nullable=True),
        sa.Column("cantidad_sistema", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cantidad_encontrada", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("estado_fisico", sa.String(40), nullable=False, server_default="Bueno"),
        sa.Column("observacion", sa.Text(), nullable=True),
        sa.Column("es_nuevo", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_levantamientos_inventario_detalle_id", "levantamientos_inventario_detalle", ["id"])
    op.create_index("ix_levantamientos_inventario_detalle_levantamiento_id", "levantamientos_inventario_detalle", ["levantamiento_id"])


def downgrade() -> None:
    op.drop_index("ix_levantamientos_inventario_detalle_levantamiento_id", table_name="levantamientos_inventario_detalle")
    op.drop_index("ix_levantamientos_inventario_detalle_id", table_name="levantamientos_inventario_detalle")
    op.drop_table("levantamientos_inventario_detalle")
    op.drop_index("ix_levantamientos_inventario_area", table_name="levantamientos_inventario")
    op.drop_index("ix_levantamientos_inventario_empresa_id", table_name="levantamientos_inventario")
    op.drop_index("ix_levantamientos_inventario_id", table_name="levantamientos_inventario")
    op.drop_table("levantamientos_inventario")
