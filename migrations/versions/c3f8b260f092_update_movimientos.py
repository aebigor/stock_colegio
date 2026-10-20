"""update movimientos

Revision ID: c3f8b260f092
Revises: b87a93a2a37f
Create Date: 2026-08-05 08:19:23.918508

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3f8b260f092'
down_revision: Union[str, Sequence[str], None] = 'b87a93a2a37f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Extend the original movements table to the current audit schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column['name'] for column in inspector.get_columns('movimientos')}

    if 'ubicacion_id' not in columns:
        op.add_column('movimientos', sa.Column('ubicacion_id', sa.Integer(), nullable=True))
        if not any(fk.get('constrained_columns') == ['ubicacion_id'] for fk in sa.inspect(bind).get_foreign_keys('movimientos')):
            op.create_foreign_key('fk_movimientos_ubicacion_id_ubicaciones', 'movimientos', 'ubicaciones', ['ubicacion_id'], ['id'])
    if 'estado' not in columns:
        op.add_column('movimientos', sa.Column('estado', sa.String(length=40), nullable=True))
        if 'estado_nuevo' in columns:
            op.execute(sa.text("UPDATE movimientos SET estado = COALESCE(estado_nuevo, 'Disponible')"))
        else:
            op.execute(sa.text("UPDATE movimientos SET estado = 'Disponible' WHERE estado IS NULL"))
        op.alter_column('movimientos', 'estado', existing_type=sa.String(length=40), nullable=False)
    if 'estado_entrega' not in columns:
        op.add_column('movimientos', sa.Column('estado_entrega', sa.String(length=80), nullable=True))
    if 'firma' not in columns:
        op.add_column('movimientos', sa.Column('firma', sa.Text(), nullable=True))
    if 'imagen' not in columns:
        op.add_column('movimientos', sa.Column('imagen', sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Non-destructive downgrade; existing movement history is retained."""
    pass
