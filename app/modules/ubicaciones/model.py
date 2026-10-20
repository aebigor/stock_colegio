from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
    func,
)

from app.core.database import Base
from app.core.tenancy import TenantScoped


class Ubicacion(TenantScoped, Base):

    __tablename__ = "ubicaciones"
    __table_args__ = (UniqueConstraint("empresa_id", "area", "codigo", name="uq_ubicaciones_empresa_area_codigo"),)

    id = Column(
        Integer,
        primary_key=True
    )

    nombre = Column(
        String(120),
        nullable=False
    )

    codigo = Column(
        String(20),
        nullable=False
    )

    # Cada bodega/ubicación pertenece a un inventario independiente.
    area = Column(
        String(50),
        nullable=False,
        default="Medios",
        server_default="Medios",
        index=True,
    )

    curso = Column(
        String(20),
        nullable=True
    )

    sede = Column(
        String(50),
        nullable=False
    )

    tipo = Column(
        String(80),
        nullable=False
    )

    piso = Column(
        String(10),
        nullable=True
    )

    descripcion = Column(
        String(255),
        nullable=True
    )

    activo = Column(
        Boolean,
        default=True,
        nullable=False
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )