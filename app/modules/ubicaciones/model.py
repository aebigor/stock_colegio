from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    func,
)

from app.core.database import Base


class Ubicacion(Base):

    __tablename__ = "ubicaciones"

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
        unique=True,
        nullable=False
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