from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func
)

from sqlalchemy.orm import relationship

from app.core.database import Base
from app.core.tenancy import TenantScoped


class Mantenimiento(TenantScoped, Base):

    __tablename__ = "mantenimientos"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    activo_id = Column(
        Integer,
        ForeignKey("activos.id"),
        nullable=False
    )

    tecnico = Column(
        String(150)
    )

    empresa = Column(
        String(150)
    )

    diagnostico = Column(Text)

    solucion = Column(Text)

    costo = Column(Integer)

    fecha_ingreso = Column(
        Date,
        server_default=func.current_date()
    )

    fecha_salida = Column(Date)

    estado = Column(
        String(30),
        default="En mantenimiento"
    )

    observaciones = Column(Text)

    activo = Column(
        Boolean,
        default=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    activo_rel = relationship("Activo")