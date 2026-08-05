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
from sqlalchemy.orm import relationship


class Categoria(Base):

    __tablename__ = "categorias"

    id = Column(Integer, primary_key=True, index=True)

    nombre = Column(String(120), unique=True, nullable=False)

    prefijo = Column(String(10), unique=True, nullable=False)

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