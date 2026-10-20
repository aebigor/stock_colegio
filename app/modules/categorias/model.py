from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    func,
)

from app.core.database import Base
from app.core.tenancy import TenantScoped
from sqlalchemy.orm import relationship
from sqlalchemy import UniqueConstraint


class Categoria(TenantScoped, Base):

    __tablename__ = "categorias"

    __table_args__ = (
        UniqueConstraint("empresa_id", "nombre", name="uq_categorias_empresa_nombre"),
        UniqueConstraint("empresa_id", "prefijo", name="uq_categorias_empresa_prefijo"),
    )

    id = Column(Integer, primary_key=True, index=True)

    nombre = Column(String(120), nullable=False)

    prefijo = Column(String(10), nullable=False)

    descripcion = Column(Text)

    icono = Column(String(50), default="bi-pc-display")

    color = Column(String(20), default="#00E5FF")

    permite_prestamo = Column(Boolean, default=True)

    requiere_firma = Column(Boolean, default=False)

    requiere_mantenimiento = Column(Boolean, default=False)

    genera_qr = Column(Boolean, default=True)

    genera_codigo_barras = Column(Boolean, default=True)

    activo = Column(Boolean, default=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    activos = relationship(
        "Activo",
        back_populates="categoria",
        cascade="all, delete-orphan"
    )