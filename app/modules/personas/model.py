from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    func,
)

from app.core.database import Base
from app.core.tenancy import TenantScoped


class Persona(TenantScoped, Base):

    __tablename__ = "personas"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    nombre = Column(
        String(150),
        nullable=False
    )

    cargo = Column(
        String(100),
        nullable=False
    )

    area = Column(
        String(100),
        nullable=False
    )

    correo = Column(
        String(150),
        nullable=True
    )

    telefono = Column(
        String(30),
        nullable=True
    )

    sede = Column(
        String(50),
        nullable=False
    )

    activo = Column(
        Boolean,
        default=True
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