"""Aislamiento multiempresa aplicado directamente en SQLAlchemy."""
from sqlalchemy import Column, ForeignKey, Integer


class TenantScoped:
    """Mixin para filas que pertenecen a una empresa concreta."""
    empresa_id = Column(
        Integer,
        ForeignKey("empresas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
