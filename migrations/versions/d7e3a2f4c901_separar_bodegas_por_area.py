"""Separar bodegas/ubicaciones por inventario.

Revision ID: d7e3a2f4c901
Revises: a91f4e2d7c60
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d7e3a2f4c901"
down_revision: Union[str, Sequence[str], None] = "a91f4e2d7c60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "area" not in {col["name"] for col in inspector.get_columns("ubicaciones")}:
        op.add_column(
            "ubicaciones",
            sa.Column("area", sa.String(length=50), nullable=False, server_default="Medios"),
        )

    # Si una misma bodega era utilizada por ambas áreas, duplica su registro
    # para Logística y mueve a esa copia solo los activos de Logística. Así no
    # mezcla inventarios ni cambia las ubicaciones que usa Medios.
    location_rows = bind.execute(sa.text(
        "SELECT id, nombre, codigo, curso, sede, tipo, piso, descripcion, activo, area "
        "FROM ubicaciones ORDER BY id"
    )).mappings().all()

    for location in location_rows:
        areas = {
            row[0]
            for row in bind.execute(
                sa.text("SELECT DISTINCT area FROM activos WHERE ubicacion_id = :id"),
                {"id": location["id"]},
            ).all()
        }
        if areas == {"Logística"}:
            bind.execute(
                sa.text("UPDATE ubicaciones SET area = 'Logística' WHERE id = :id"),
                {"id": location["id"]},
            )
        elif "Logística" in areas and "Medios" in areas:
            base_code = (location["codigo"] or "BOD")[:15]
            new_code = f"{base_code}-LOG"
            suffix = 1
            while bind.execute(
                sa.text("SELECT 1 FROM ubicaciones WHERE codigo = :codigo"),
                {"codigo": new_code},
            ).first():
                suffix += 1
                new_code = f"{base_code[:max(1, 19-len(str(suffix)))]}-L{suffix}"
            new_id = bind.execute(
                sa.text("""
                    INSERT INTO ubicaciones
                        (nombre, codigo, curso, sede, tipo, piso, descripcion, activo, area)
                    VALUES
                        (:nombre, :codigo, :curso, :sede, :tipo, :piso, :descripcion, :activo, 'Logística')
                    RETURNING id
                """),
                {
                    "nombre": location["nombre"],
                    "codigo": new_code,
                    "curso": location["curso"],
                    "sede": location["sede"],
                    "tipo": location["tipo"],
                    "piso": location["piso"],
                    "descripcion": location["descripcion"],
                    "activo": location["activo"],
                },
            ).scalar_one()
            bind.execute(
                sa.text("UPDATE activos SET ubicacion_id = :new_id WHERE ubicacion_id = :old_id AND area = 'Logística'"),
                {"new_id": new_id, "old_id": location["id"]},
            )
            # Conserva las ubicaciones históricas de los movimientos de Logística.
            if "movimientos" in sa.inspect(bind).get_table_names():
                movement_columns = {c["name"] for c in sa.inspect(bind).get_columns("movimientos")}
                if "area" in movement_columns and "ubicacion_id" in movement_columns:
                    bind.execute(
                        sa.text("UPDATE movimientos SET ubicacion_id = :new_id WHERE ubicacion_id = :old_id AND area = 'Logística'"),
                        {"new_id": new_id, "old_id": location["id"]},
                    )

    # Ya no exigir códigos únicos entre áreas: la unicidad corresponde al
    # inventario (área) y al código de bodega.
    inspector = sa.inspect(bind)
    for constraint in inspector.get_unique_constraints("ubicaciones"):
        if constraint.get("column_names") == ["codigo"] and constraint.get("name"):
            op.drop_constraint(constraint["name"], "ubicaciones", type_="unique")
    for index in inspector.get_indexes("ubicaciones"):
        if index.get("unique") and index.get("column_names") == ["codigo"]:
            op.drop_index(index["name"], table_name="ubicaciones")

    inspector = sa.inspect(bind)
    names = {c.get("name") for c in inspector.get_unique_constraints("ubicaciones")}
    if "uq_ubicaciones_area_codigo" not in names:
        op.create_unique_constraint("uq_ubicaciones_area_codigo", "ubicaciones", ["area", "codigo"])
    indexes = {idx.get("name") for idx in inspector.get_indexes("ubicaciones")}
    if "ix_ubicaciones_area" not in indexes:
        op.create_index("ix_ubicaciones_area", "ubicaciones", ["area"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "uq_ubicaciones_area_codigo" in {c.get("name") for c in inspector.get_unique_constraints("ubicaciones")}:
        op.drop_constraint("uq_ubicaciones_area_codigo", "ubicaciones", type_="unique")
    indexes = {idx.get("name") for idx in inspector.get_indexes("ubicaciones")}
    if "ix_ubicaciones_area" in indexes:
        op.drop_index("ix_ubicaciones_area", table_name="ubicaciones")
    op.create_unique_constraint("ubicaciones_codigo_key", "ubicaciones", ["codigo"])
    if "area" in {col["name"] for col in sa.inspect(bind).get_columns("ubicaciones")}:
        op.drop_column("ubicaciones", "area")
