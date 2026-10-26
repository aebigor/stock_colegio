from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)

from sqlalchemy.orm import relationship

from app.core.database import Base
from app.core.tenancy import TenantScoped


class Movimiento(TenantScoped, Base):

    __tablename__ = "movimientos"

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

    persona_id = Column(
        Integer,
        ForeignKey("personas.id"),
        nullable=True
    )

    # Ubicación actual/destino después del movimiento.
    ubicacion_id = Column(
        Integer,
        ForeignKey("ubicaciones.id"),
        nullable=True
    )

    # Ubicación física desde la que salió el activo. Permite reconstruir
    # el origen aunque después se traslade a otra ubicación.
    ubicacion_origen_id = Column(
        Integer,
        ForeignKey("ubicaciones.id"),
        nullable=True
    )

    tipo = Column(
        String(50),
        nullable=False
    )

    estado = Column(
        String(40),
        nullable=False
    )

    observaciones = Column(
        Text
    )

    usuario = Column(
        String(120)
    )

    # NUEVO
    estado_entrega = Column(
        String(80)
    )

    firma = Column(
        Text
    )

    protocolo_aceptado = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    imagen = Column(
        String(255)
    )

    area = Column(
        String(50),
        nullable=False,
        default="Medios",
        server_default="Medios",
        index=True,
    )

    activo = Column(
        Boolean,
        default=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    activo_rel = relationship("Activo", back_populates="movimientos")

    persona = relationship("Persona")

    ubicacion = relationship("Ubicacion", foreign_keys=[ubicacion_id])

    ubicacion_origen = relationship("Ubicacion", foreign_keys=[ubicacion_origen_id])