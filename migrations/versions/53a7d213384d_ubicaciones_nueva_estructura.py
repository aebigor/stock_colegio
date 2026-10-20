"""ubicaciones nueva estructura

Revision ID: 53a7d213384d
Revises: caca4bc28930
Create Date: 2026-07-31 11:14:01.977779

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '53a7d213384d'
down_revision: Union[str, Sequence[str], None] = 'caca4bc28930'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Convert the legacy location type FK into the current text field.

    The previous migration accidentally recreated ``ubicaciones``. This
    migration now preserves location records and moves their type name into
    ``tipo``.
    """
    bind = op.get_bind()
    op.add_column('ubicaciones', sa.Column('tipo', sa.String(length=80), nullable=True))
    op.execute(sa.text("""
        UPDATE ubicaciones AS u
        SET tipo = COALESCE(
            (SELECT t.nombre FROM tipos_ubicacion AS t WHERE t.id = u.tipo_id),
            'General'
        )
    """))
    # Ensure all existing rows have a type before applying NOT NULL.
    op.execute(sa.text("UPDATE ubicaciones SET tipo = 'General' WHERE tipo IS NULL OR tipo = ''"))
    op.alter_column('ubicaciones', 'tipo', existing_type=sa.String(length=80), nullable=False)
    constraints = sa.inspect(bind).get_foreign_keys('ubicaciones')
    for constraint in constraints:
        if 'tipo_id' in (constraint.get('constrained_columns') or []):
            op.drop_constraint(constraint['name'], 'ubicaciones', type_='foreignkey')
    op.drop_column('ubicaciones', 'tipo_id')
    # Legacy lookup table is no longer used by the current model.
    if 'tipos_ubicacion' in sa.inspect(bind).get_table_names():
        op.drop_table('tipos_ubicacion')


def downgrade() -> None:
    """Downgrade is intentionally non-destructive for location data."""
    op.add_column('ubicaciones', sa.Column('tipo_id', sa.Integer(), nullable=True))
    op.drop_column('ubicaciones', 'tipo')
