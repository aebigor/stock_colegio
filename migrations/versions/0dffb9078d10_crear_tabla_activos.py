"""crear tabla activos

Revision ID: 0dffb9078d10
Revises: 53a7d213384d
Create Date: 2026-08-01 09:19:11.794580

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0dffb9078d10'
down_revision: Union[str, Sequence[str], None] = '53a7d213384d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade the legacy asset table without recreating it or losing rows."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column['name'] for column in inspector.get_columns('activos')}
    if 'ubicacion_id' not in columns:
        op.add_column('activos', sa.Column('ubicacion_id', sa.Integer(), nullable=True))

    # Migrate the old free-text location into a real location record.
    inspector = sa.inspect(bind)
    columns = {column['name'] for column in inspector.get_columns('activos')}
    if 'ubicacion' in columns:
        rows = bind.execute(sa.text("SELECT DISTINCT ubicacion FROM activos WHERE ubicacion IS NOT NULL AND TRIM(ubicacion) <> ''")).fetchall()
        next_code = 1
        for row in rows:
            name = str(row[0]).strip()[:120]
            location_id = bind.execute(sa.text("SELECT id FROM ubicaciones WHERE nombre = :name ORDER BY id LIMIT 1"), {"name": name}).scalar()
            if location_id is None:
                code = f"MIG{next_code:05d}"
                next_code += 1
                result = bind.execute(sa.text("""
                    INSERT INTO ubicaciones (nombre, codigo, curso, sede, tipo, piso, descripcion, activo)
                    VALUES (:nombre, :codigo, NULL, 'Principal', 'General', NULL, 'Creada al migrar ubicación histórica', TRUE)
                    RETURNING id
                """), {"nombre": name, "codigo": code})
                location_id = result.scalar()
            bind.execute(sa.text("UPDATE activos SET ubicacion_id = :location_id WHERE ubicacion = :old_name AND ubicacion_id IS NULL"), {"location_id": location_id, "old_name": row[0]})

    # Old installations may have assets without a location; create a safe default.
    null_count = bind.execute(sa.text("SELECT COUNT(*) FROM activos WHERE ubicacion_id IS NULL")).scalar() or 0
    if null_count:
        location_id = bind.execute(sa.text("SELECT id FROM ubicaciones ORDER BY id LIMIT 1")).scalar()
        if location_id is None:
            location_id = bind.execute(sa.text("""
                INSERT INTO ubicaciones (nombre, codigo, curso, sede, tipo, piso, descripcion, activo)
                VALUES ('Sin ubicación asignada', 'MIG00000', NULL, 'Principal', 'General', NULL, 'Ubicación de respaldo de migración', TRUE)
                RETURNING id
            """)).scalar()
        bind.execute(sa.text("UPDATE activos SET ubicacion_id = :location_id WHERE ubicacion_id IS NULL"), {"location_id": location_id})

    op.alter_column('activos', 'ubicacion_id', existing_type=sa.Integer(), nullable=False)
    if not any(fk.get('constrained_columns') == ['ubicacion_id'] for fk in sa.inspect(bind).get_foreign_keys('activos')):
        op.create_foreign_key('fk_activos_ubicacion_id_ubicaciones', 'activos', 'ubicaciones', ['ubicacion_id'], ['id'])

    # Serial is optional; several old assets do not have one.
    op.alter_column('activos', 'serial', existing_type=sa.String(length=150), nullable=True)
    # Fill missing barcode values before enforcing the current unique index.
    if 'codigo_barras' in {column['name'] for column in sa.inspect(bind).get_columns('activos')}:
        bind.execute(sa.text("UPDATE activos SET codigo_barras = 'TEC-GLS-' || LPAD(id::text, 6, '0') WHERE codigo_barras IS NULL OR TRIM(codigo_barras) = ''"))
        op.alter_column('activos', 'codigo_barras', existing_type=sa.String(length=255), nullable=False)
        indexes = {index['name'] for index in sa.inspect(bind).get_indexes('activos')}
        if 'ix_activos_codigo_barras' not in indexes:
            op.create_index('ix_activos_codigo_barras', 'activos', ['codigo_barras'], unique=True)


def downgrade() -> None:
    """Non-destructive downgrade; asset/location migration is intentionally retained."""
    pass
