"""Añadir aislamiento multiempresa y administrador de plataforma.

Revision ID: a7c4e91f2b30
Revises: d7e3a2f4c901
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a7c4e91f2b30"
down_revision: Union[str, Sequence[str], None] = "d7e3a2f4c901"
branch_labels = None
depends_on = None

TENANT_TABLES = (
    "usuarios",
    "categorias",
    "ubicaciones",
    "activos",
    "personas",
    "movimientos",
    "mantenimientos",
    "configuracion",
)


def _table_exists(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _drop_unique_rules(table_name: str, scoped_columns: set[str]) -> None:
    """Quita la unicidad global para reemplazarla por unicidad por empresa."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for constraint in inspector.get_unique_constraints(table_name):
        cols = set(constraint.get("column_names") or [])
        name = constraint.get("name")
        if name and cols and cols.issubset(scoped_columns):
            op.drop_constraint(name, table_name, type_="unique")

    inspector = sa.inspect(bind)
    for index in inspector.get_indexes(table_name):
        cols = set(index.get("column_names") or [])
        name = index.get("name")
        if (index.get("unique") and name and cols and cols.issubset(scoped_columns)
                and not index.get("duplicates_constraint")):
            op.drop_index(name, table_name=table_name)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _table_exists(inspector, "empresas"):
        op.create_table(
            "empresas",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("nombre", sa.String(length=180), nullable=False),
            sa.Column("contacto_nombre", sa.String(length=180), nullable=False),
            sa.Column("correo_contacto", sa.String(length=180), nullable=False),
            sa.Column("estado", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("nombre", name="uq_empresas_nombre"),
        )
        op.create_index("ix_empresas_id", "empresas", ["id"], unique=False)
        op.create_index("ix_empresas_nombre", "empresas", ["nombre"], unique=False)
        op.create_index("ix_empresas_correo_contacto", "empresas", ["correo_contacto"], unique=False)

    # La empresa histórica conserva todos los datos existentes.
    default_id = bind.execute(sa.text("SELECT id FROM empresas WHERE nombre = 'GIMSAU' ORDER BY id LIMIT 1")).scalar()
    if default_id is None:
        default_id = bind.execute(sa.text("""
            INSERT INTO empresas (nombre, contacto_nombre, correo_contacto, estado)
            VALUES ('GIMSAU', 'Administración GIMSAU', 'tecnologia@gimsau.edu.co', TRUE)
            RETURNING id
        """)).scalar_one()

    for table_name in TENANT_TABLES:
        inspector = sa.inspect(bind)
        if not _table_exists(inspector, table_name):
            continue
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if "empresa_id" not in columns:
            op.add_column(table_name, sa.Column("empresa_id", sa.Integer(), nullable=True))
            op.create_foreign_key(
                f"fk_{table_name}_empresa_id_empresas",
                table_name,
                "empresas",
                ["empresa_id"],
                ["id"],
                ondelete="SET NULL" if table_name == "usuarios" else "CASCADE",
            )
            op.create_index(f"ix_{table_name}_empresa_id", table_name, ["empresa_id"], unique=False)
        bind.execute(
            sa.text(f"UPDATE {table_name} SET empresa_id = :default_id WHERE empresa_id IS NULL"),
            {"default_id": default_id},
        )
        if table_name != "usuarios":
            op.alter_column(table_name, "empresa_id", existing_type=sa.Integer(), nullable=False)

    # El correo de tecnología es un administrador de plataforma; no pertenece a
    # ningún tenant y no debe entrar en las vistas del inventario de GIMSAU.
    role_id = bind.execute(sa.text("""
        INSERT INTO roles (nombre, descripcion, estado)
        VALUES ('Administrador de Plataforma',
                'Gestiona empresas y crea sus Super Admin; no administra directamente sus inventarios.',
                TRUE)
        ON CONFLICT (nombre) DO UPDATE SET descripcion = EXCLUDED.descripcion, estado = TRUE
        RETURNING id
    """)).scalar_one()
    bind.execute(sa.text("""
        UPDATE usuarios
        SET empresa_id = NULL,
            rol_id = :role_id,
            area = 'Plataforma'
        WHERE LOWER(correo) = LOWER('tecnologia@gimsau.edu.co')
    """), {"role_id": role_id})

    # Los códigos se independizan por empresa para que dos inventarios puedan
    # reutilizar nomenclaturas y prefijos sin afectar a la otra empresa.
    inspector = sa.inspect(bind)
    if _table_exists(inspector, "activos"):
        _drop_unique_rules("activos", {"codigo", "codigo_barras", "serial"})
        op.create_unique_constraint("uq_activos_empresa_codigo", "activos", ["empresa_id", "codigo"])
        op.create_unique_constraint("uq_activos_empresa_codigo_barras", "activos", ["empresa_id", "codigo_barras"])
        op.create_unique_constraint("uq_activos_empresa_serial", "activos", ["empresa_id", "serial"])
    inspector = sa.inspect(bind)
    if _table_exists(inspector, "categorias"):
        _drop_unique_rules("categorias", {"nombre", "prefijo"})
        op.create_unique_constraint("uq_categorias_empresa_nombre", "categorias", ["empresa_id", "nombre"])
        op.create_unique_constraint("uq_categorias_empresa_prefijo", "categorias", ["empresa_id", "prefijo"])
    inspector = sa.inspect(bind)
    if _table_exists(inspector, "ubicaciones"):
        _drop_unique_rules("ubicaciones", {"area", "codigo"})
        op.create_unique_constraint(
            "uq_ubicaciones_empresa_area_codigo",
            "ubicaciones",
            ["empresa_id", "area", "codigo"],
        )


def downgrade() -> None:
    raise RuntimeError(
        "El downgrade multiempresa está bloqueado para no mezclar datos de empresas distintas. "
        "Restaura una copia previa de la base de datos si necesitas volver atrás."
    )
